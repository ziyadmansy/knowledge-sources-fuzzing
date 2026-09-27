#!/usr/bin/env python3
"""Run a knowledge agent (probe or code) once per seed (docs/design.md §4.1, §4.2).

  .venv/bin/python scripts/acquire_knowledge.py --target dart --arm probe --seed 700 --runs 5

writes knowledge/<target>/<arm>/seed-NNNN/ (every prompt, response, probe result,
and knowledge.txt), which run_arm.py then reads with
  --knowledge-file 'knowledge/dart/probe/seed-{seed:04d}/knowledge.txt'
"""

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ksfuzz.agents import run_code_agent, run_probe_agent  # noqa: E402
from ksfuzz.llm import OpenAIProposer  # noqa: E402
from ksfuzz.seeding import build_manifest, resolved_arguments, write_manifest  # noqa: E402
from ksfuzz.targets import DART, TARGETS  # noqa: E402

# The code arm's reading list (§4.2): each path's model source and its generated
# `*.g.dart`, identical for every seed. ~17K characters, under the budget, so
# nothing is truncated; the check below fails loudly if that ever changes.
DART_SCHEMA_DIR = REPO_ROOT.parent / "agentic-fuzzing-dart-json" / "harness" / "lib" / "schema"
DART_CODE_SOURCES = (
    "manual.dart",
    "json_serializable_model.dart",
    "json_serializable_model.g.dart",
    "freezed_model.dart",
    "freezed_model.g.dart",
    "built_value_model.dart",
    "built_value_model.g.dart",
    "serializers.dart",
    "serializers.g.dart",
)
CODE_CHAR_BUDGET = 24_000


def dart_code_sources() -> list[tuple[str, str]]:
    sources = [(name, (DART_SCHEMA_DIR / name).read_text(encoding="utf-8")) for name in DART_CODE_SOURCES]
    total = sum(len(text) for _, text in sources)
    if total > CODE_CHAR_BUDGET:
        raise SystemExit(f"code sources are {total} chars, over the {CODE_CHAR_BUDGET} budget")
    return sources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--arm", choices=("probe", "sysprobe", "code"), required=True)
    parser.add_argument("--executable")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--model", default="gpt-4.1-mini")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    target = TARGETS[args.target]
    executable = args.executable or str(target.default_executable)
    out_root = args.out_dir or REPO_ROOT / "knowledge" / args.target / args.arm
    if args.arm == "code" and target is not DART:
        raise SystemExit("the code arm is Dart-only (docs/design.md §4.2)")
    sources = dart_code_sources() if args.arm == "code" else None
    if args.arm != "code" and not Path(executable).is_file():
        raise SystemExit(f"harness not found: {executable}")
    seed_dirs = [out_root / f"seed-{args.seed + i:04d}" for i in range(args.runs)]
    for d in seed_dirs:
        if d.exists() and any(d.iterdir()) and not args.overwrite:
            raise SystemExit(f"{d} already has results; pass --overwrite to replace them")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY environment variable is not set")
    from openai import OpenAI

    llm = OpenAIProposer(OpenAI(api_key=api_key), model=args.model)
    for i, out_dir in enumerate(seed_dirs):
        seed = args.seed + i
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest = build_manifest(seed, resolved_arguments(args), model=args.model)
        manifest.update(target=target.name, arm=args.arm)
        if args.arm != "code":
            manifest["harness_sha256"] = target.harness_sha256(executable)
        write_manifest(out_dir / "manifest.json", manifest)
        # The API call is not seedable; the seed only labels the run (§4.1: knowledge
        # quality varies across seeds, and that variance is part of the result).
        if args.arm != "code":
            body = run_probe_agent(target, executable, llm, out_dir, systematic=args.arm == "sysprobe")
        else:
            body = run_code_agent(target, llm, sources, out_dir)
        print(f"== {out_dir} ({len(body)} chars)\n{body}\n")


if __name__ == "__main__":
    main()
