#!/usr/bin/env python3
"""Run one arm (docs/design.md §4) of the refinement loop on one target, for one or
more seeds. Adapted from the previous study's `run_dart_rq2_refinement.py`.

  set -a; . ../previous-study-artifact/.env; set +a
  .venv/bin/python scripts/run_arm.py --target dart --arm none --seed 700 --runs 5

For the `code` and `probe` arms the knowledge body is per seed: pass
`--knowledge-file` with a `{seed}` placeholder, e.g. `knowledge/probe/dart-{seed}.txt`.
"""

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ksfuzz.campaign import run_refinement_loop  # noqa: E402
from ksfuzz.experiment import run_directory, write_summary  # noqa: E402
from ksfuzz.knowledge import ARMS, HUMAN_DART_BODY, knowledge_section  # noqa: E402
from ksfuzz.llm import OpenAIProposer  # noqa: E402
from ksfuzz.seeding import build_manifest, resolved_arguments, seed_everything, write_manifest  # noqa: E402
from ksfuzz.targets import TARGETS  # noqa: E402


def knowledge_body(arm: str, target: str, knowledge_file: str | None, seed: int) -> str | None:
    if arm == "none":
        return None
    if arm == "human":
        if target != "dart":
            raise SystemExit("the human arm exists only for Dart (docs/design.md §4)")
        return HUMAN_DART_BODY
    if arm == "code" and target != "dart":
        raise SystemExit("the code arm is Dart-only (docs/design.md §4.2)")
    if not knowledge_file:
        raise SystemExit(f"--knowledge-file is required for the {arm} arm")
    return Path(knowledge_file.format(seed=seed)).read_text(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--arm", choices=ARMS, required=True)
    parser.add_argument("--knowledge-file")
    parser.add_argument("--executable")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--examples", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--seed", type=int, required=True, help="seed of the first run; run N uses seed+N-1")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    target = TARGETS[args.target]
    executable = args.executable or str(target.default_executable)
    artifact_dir = args.artifact_dir or Path("artifacts") / args.target / args.arm
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if not Path(executable).is_file():
        raise SystemExit(f"harness not found: {executable}")
    # Resolve every seed's knowledge before any API spend.
    bodies = {
        args.seed + i: knowledge_body(args.arm, args.target, args.knowledge_file, args.seed + i)
        for i in range(args.runs)
    }
    sections = {seed: knowledge_section(args.arm, body) for seed, body in bodies.items()}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY environment variable is not set")
    from openai import OpenAI

    proposer = OpenAIProposer(OpenAI(api_key=api_key), model=args.model)
    arguments = resolved_arguments(args)

    for run_index in range(args.runs):
        seed = args.seed + run_index
        try:
            run_dir = run_directory(artifact_dir, run_index, seed, args.overwrite)
        except FileExistsError as error:
            raise SystemExit(str(error)) from error
        manifest = build_manifest(seed, arguments, model=args.model)
        manifest.update(
            target=target.name,
            arm=args.arm,
            path_order=list(target.path_order),
            harness_sha256=target.harness_sha256(executable),
            knowledge_section=sections[seed],
        )
        write_manifest(run_dir / "manifest.json", manifest)

        seed_everything(seed)
        calls_before = len(proposer.usage)
        print(f"== {run_dir} (seed={seed})")
        summaries = run_refinement_loop(
            target,
            executable,
            proposer,
            run_dir,
            knowledge=sections[seed],
            iterations=args.iterations,
            examples_per_iteration=args.examples,
            timeout_seconds=args.timeout,
        )
        for index, summary in enumerate(summaries, start=1):
            print(f"iteration-{index}: score={summary.score}/{summary.total} {dict(summary.divergence_signatures)}")
            write_summary(run_dir / f"iteration-{index}", summary.as_dict())
        run_usage = proposer.usage[calls_before:]
        manifest["llm_usage"] = {
            "calls": len(run_usage),
            "input_tokens": sum(u["input_tokens"] for u in run_usage),
            "output_tokens": sum(u["output_tokens"] for u in run_usage),
            "truncated": sum(u.get("truncated", 0) for u in run_usage),
        }
        write_manifest(run_dir / "manifest.json", manifest)


if __name__ == "__main__":
    main()
