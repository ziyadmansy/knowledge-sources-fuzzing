"""End-to-end run of a fixed (non-LLM) generator through each real harness.

These pin down the pipeline wiring, not results: known single-document
behaviours from the design's answer keys and the Kotlin smoke test (§5, §10).
Skipped if a harness is not built.
"""

import json
from pathlib import Path

import pytest

from ksfuzz.campaign import run_campaign, summarize_records
from ksfuzz.proposal import proposal_inputs
from ksfuzz.targets import DART, KOTLIN

VALID = '{"id":1,"amount":"1","name":null,"status":"active","tags":[],"child":null}'
MISSING_TAGS = '{"id":1,"amount":"1","name":null,"status":"active","child":null}'
SINGLE_QUOTES = VALID.replace('"', "'")

# Cycles through three fixed documents, so 30 examples contain 10 of each.
_FIXED = f"""
DOCS = [{VALID!r}, {MISSING_TAGS!r}, {SINGLE_QUOTES!r}]

@st.composite
def generated_json(draw):
    return DOCS[draw(st.integers(0, 2))].encode()
"""


def _run(target, tmp_path: Path):
    executable = str(target.default_executable)
    if not Path(executable).is_file():
        pytest.skip(f"{target.name} harness not built")
    out = tmp_path / "results.jsonl"
    run_campaign(target, executable, proposal_inputs(_FIXED, 30), out, max_examples=30)
    records = [json.loads(line) for line in out.read_text().splitlines()]
    by_doc = {bytes.fromhex(r["input_hex"]).decode(): r["harness_response"] for r in records}
    return records, by_doc


def test_dart_pipeline(tmp_path: Path) -> None:
    records, by_doc = _run(DART, tmp_path)
    summary = summarize_records(DART, records)
    assert by_doc[VALID]["tier_c_divergence"] == "none"
    # Dart answer key: built_value alone accepts a missing `tags`.
    assert "RRRA" in summary.divergence_signatures
    # Invalid JSON never reaches the four paths, so it never counts.
    assert by_doc[SINGLE_QUOTES]["status"] == "structural_reject"
    assert summary.tier_c_by_gate.keys() <= {"schema_evaluated"}


def test_kotlin_pipeline(tmp_path: Path) -> None:
    records, by_doc = _run(KOTLIN, tmp_path)
    summary = summarize_records(KOTLIN, records)
    assert by_doc[VALID]["tier_c_divergence"] == "none"
    # Gson nulls the missing non-null `tags` (issue #1657); the others reject.
    assert "ARRR" in summary.divergence_signatures
    # Single quotes fail the strict gate but Gson (lenient) accepts, and it still counts (§10).
    assert by_doc[SINGLE_QUOTES]["status"] == "structural_reject"
    assert summary.tier_c_by_gate["structural_reject"] > 0
    assert summary.score == sum(summary.tier_c_by_gate.values())
