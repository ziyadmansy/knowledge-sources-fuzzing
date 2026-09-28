#!/usr/bin/env python3
"""Classify every probe document by what it changes relative to a valid record.

Reproduces the probe-coverage table in the paper (Discussion). A probe can fall
in several rows. "Wrong type" includes a list element of the wrong type (for
example tags [1, 2]); "nested child changed" means any change inside child, at
any depth. Reads only committed knowledge/ artifacts; no API calls.

    .venv/bin/python scripts/probe_coverage.py
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("id", "amount", "name", "status", "tags", "child")
NON_NULLABLE = ("id", "amount", "status", "tags")
STATUS = {"active", "inactive", "unknown"}
ROWS = (
    "nothing at top level",
    "field missing",
    "non-nullable field null",
    "wrong type",
    "unknown enum constant",
    "extra key",
    "nested child changed",
    "fractional or exponent id",
    "id near 53/64-bit bound",
    "not JSON",
)
# (target, arm, seeds) columns in the order the paper's table prints them.
COLUMNS = (
    ("dart", "probe", range(700, 705)),
    ("dart", "sysprobe", range(700, 705)),
    ("dart", "probe-gpt41", range(700, 705)),
    ("kotlin", "probe", range(800, 810)),
    ("kotlin", "sysprobe", range(800, 805)),
)


def _reject_constant(name: str) -> None:
    raise ValueError(f"non-standard constant {name}")


def parse_strict(text: str):
    """RFC 8259 JSON only: Python's json also accepts NaN/Infinity, which we reject."""
    return json.loads(text, parse_constant=_reject_constant)


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def top_level_changes(record: dict) -> set[str]:
    """Categories that a record changes at its own level (not inside child)."""
    changes: set[str] = set()
    if any(field not in record for field in FIELDS):
        changes.add("field missing")
    if any(field in record and record[field] is None for field in NON_NULLABLE):
        changes.add("non-nullable field null")
    if set(record) - set(FIELDS):
        changes.add("extra key")

    wrong_type = False
    if "id" in record and record["id"] is not None:
        value = record["id"]
        # json.loads returns float for any literal with a fraction or an
        # exponent (1.5, 1e3), which is the checklist's "fraction, exponent form".
        if isinstance(value, float):
            changes.add("fractional or exponent id")
        elif not _is_int(value):
            wrong_type = True
        if (_is_int(value) or isinstance(value, float)) and abs(value) >= 2**53:
            changes.add("id near 53/64-bit bound")
    for field in ("amount", "status"):
        if field in record and record[field] is not None and not isinstance(record[field], str):
            wrong_type = True
    if "name" in record and record["name"] is not None and not isinstance(record["name"], str):
        wrong_type = True
    if "tags" in record and record["tags"] is not None:
        tags = record["tags"]
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            wrong_type = True
    if "child" in record and record["child"] is not None and not isinstance(record["child"], dict):
        wrong_type = True
    if wrong_type:
        changes.add("wrong type")
    if isinstance(record.get("status"), str) and record["status"] not in STATUS:
        changes.add("unknown enum constant")
    return changes


def subtree_changed(record: dict) -> bool:
    if top_level_changes(record):
        return True
    child = record.get("child")
    return isinstance(child, dict) and subtree_changed(child)


def classify(text: str) -> set[str]:
    try:
        document = parse_strict(text)
    except ValueError:
        return {"not JSON"}
    if not isinstance(document, dict):
        return {"not JSON"}
    rows = top_level_changes(document)
    if not rows:
        rows.add("nothing at top level")
    child = document.get("child")
    if isinstance(child, dict) and subtree_changed(child):
        rows.add("nested child changed")
    return rows


def main() -> None:
    table: dict[tuple[str, str], dict[str, int]] = {}
    divergent: dict[tuple[str, str], list[int]] = {}
    for target, arm, seeds in COLUMNS:
        counts = dict.fromkeys(ROWS, 0)
        per_seed = []
        for seed in seeds:
            seed_dir = REPO_ROOT / "knowledge" / target / arm / f"seed-{seed:04d}"
            hits = 0
            for results in sorted(seed_dir.glob("round*_results.jsonl")):
                for line in results.read_text().splitlines():
                    record = json.loads(line)
                    for row in classify(record["probe"]):
                        counts[row] += 1
                    hits += record["harness_response"].get("tier_c_divergence") in ("accept_reject", "value")
            per_seed.append(hits)
        table[(target, arm)] = counts
        divergent[(target, arm)] = per_seed

    header = "".join(f"{t[:6]}/{a:<11}" for t, a, _ in COLUMNS)
    print(f"{'change':<26}{header}")
    for row in ROWS:
        print(f"{row:<26}" + "".join(f"{table[(t, a)][row]:<18}" for t, a, _ in COLUMNS))
    print(
        f"{'divergent probes / seed':<26}"
        + "".join(f"{f'{min(divergent[(t, a)])}-{max(divergent[(t, a)])}':<18}" for t, a, _ in COLUMNS)
    )


if __name__ == "__main__":
    main()
