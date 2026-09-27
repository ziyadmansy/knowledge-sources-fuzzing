#!/bin/sh
# Step 4 (docs/design.md §6): every arm on every seed, one arm at a time, stopping at the first failure.
set -eu
cd "$(dirname "$0")/.."
run() { .venv/bin/python scripts/run_arm.py --runs 5 "$@"; }
run --target dart --arm none --seed 700
run --target dart --arm human --seed 700
run --target dart --arm code --seed 700 --knowledge-file 'knowledge/dart/code/seed-{seed:04d}/knowledge.txt'
run --target dart --arm probe --seed 700 --knowledge-file 'knowledge/dart/probe/seed-{seed:04d}/knowledge.txt'
run --target kotlin --arm none --seed 800
run --target kotlin --arm probe --seed 800 --knowledge-file 'knowledge/kotlin/probe/seed-{seed:04d}/knowledge.txt'
