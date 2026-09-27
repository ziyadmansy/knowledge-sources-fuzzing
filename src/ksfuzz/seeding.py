"""Deterministic experiment seeding and run provenance.

All randomness control lives in this one file so the coupling to Hypothesis
internals is auditable in a single place.

Why two seeds are needed (measured on hypothesis 6.165.5 / CPython 3.14.7, not
assumed): a `SearchStrategy.example()` call runs an internal `@given` whose RNG
comes from `hypothesis.core.threadlocal._hypothesis_global_random` -- a private
`Random()` instance seeded from OS entropy that `random.seed()` does not touch.
The winning draw is then picked by the module-level `random.shuffle`. Seeding
only one of the two leaves the example stream non-reproducible across
processes; seeding both makes it byte-identical. In a small check (8 draws of
`baseline_json`, repeated across processes) seeding did not reduce the number of
distinct values drawn -- 8/8 unique seeded versus 7/8 unseeded -- which is a
sanity check against the generator collapsing, not a measurement of the draw
distribution.

The two documented alternatives were rejected on measurement, not preference:
`settings(derandomize=True)` and `hypothesis.core.global_force_seed` both give
`.example()`'s internal test a fixed seed on every call, collapsing 500 draws
into repeats of the same batch of 10. That would change the fuzzing algorithm;
this module does not.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import random
import sys
from typing import Any

import hypothesis
import hypothesis.core


class SeedingError(RuntimeError):
    """Raised when Hypothesis no longer exposes the entropy hook we seed."""


def seed_everything(seed: int) -> None:
    """Make the Hypothesis draw stream a pure function of ``seed``.

    Call once per experiment run, before any strategy is drawn.
    """
    random.seed(seed)

    # Private Hypothesis API: there is no public way to derandomize `.example()`
    # without also collapsing its draw diversity (see module docstring). Fail
    # loudly rather than silently producing runs that are labelled reproducible
    # but are not.
    threadlocal = getattr(hypothesis.core, "threadlocal", None)
    if threadlocal is None or not hasattr(threadlocal, "_hypothesis_global_random"):
        raise SeedingError(
            "hypothesis.core.threadlocal._hypothesis_global_random is missing; this "
            "seeding shim is coupled to Hypothesis internals and was verified against "
            f"6.165.5 (installed: {hypothesis.__version__}). Re-verify before running "
            "experiments that claim reproducibility."
        )
    # thread-local: strategies drawn on another thread are not covered by this seed
    threadlocal._hypothesis_global_random = random.Random(seed)


def build_manifest(
    seed: int,
    arguments: dict[str, Any],
    model: str | None = None,
    feedback_mode: str | None = None,
) -> dict[str, Any]:
    """Describe one run well enough to judge whether it can be repeated."""
    return {
        "seed": seed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "hypothesis_version": hypothesis.__version__,
        "model": model,
        "feedback_mode": feedback_mode,
        "arguments": arguments,
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def resolved_arguments(args: Any) -> dict[str, str]:
    """Flatten parsed CLI arguments to strings so Paths survive JSON round-trips."""
    return {key: str(value) for key, value in sorted(vars(args).items())}
