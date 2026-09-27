"""Shared on-disk layout for repeated experiment runs.

The baseline and refined entry points must agree exactly on run-directory
naming and summary format, otherwise the aggregation and figure tooling reads
only one of the two arms. Keeping both in one place makes that agreement
structural rather than a convention two scripts have to remember.
"""

import json
from pathlib import Path
import shutil
from typing import Any


def run_directory(artifact_dir: Path, run_index: int, seed: int, overwrite: bool = False) -> Path:
    """Create `run-NN-seed-SSSS/` for one run, refusing to clobber existing results."""
    run_dir = artifact_dir / f"run-{run_index + 1:02d}-seed-{seed:04d}"
    if run_dir.exists() and any(run_dir.iterdir()):
        if not overwrite:
            raise FileExistsError(f"{run_dir} already contains results; pass --overwrite to replace them")
        # a shorter re-run would otherwise leave the previous run's extra
        # iteration-N directories behind, and aggregation would sum both
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_summary(iteration_dir: Path, summary: dict[str, Any]) -> Path:
    """Persist one iteration's CampaignSummary in the established artifact format."""
    iteration_dir.mkdir(parents=True, exist_ok=True)
    path = iteration_dir / "summary.json"
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path
