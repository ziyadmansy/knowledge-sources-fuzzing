"""The Dart arms must run the previous study's loop unchanged (docs/design.md §4).

Replays the previous study's committed runs: every prompt.txt must be rebuilt byte for byte
from the previous iterations' summary.json / proposal_error.txt, and every
results.jsonl must summarize to the committed summary.json. Skipped if the
sibling repo is not checked out.
"""

from collections import Counter
import json
from pathlib import Path

import pytest

from ksfuzz.campaign import DivergenceCampaignSummary, build_refinement_prompt, empty_summary, summarize_records
from ksfuzz.knowledge import knowledge_section
from ksfuzz.targets import DART, REPO_ROOT

PAPER2 = REPO_ROOT.parent / "previous-study-artifact" / "artifacts" / "repeated"

# The previous study arms with the score-only prompt (no json/category/mutate ablation), and
# which knowledge arm each corresponds to here.
_ARMS = {"rq2-loop-knowledge-parity": "human", "rq2-loop-gpt41": "none", "rq2-loop-gpt41-lenient": "none"}


def _runs():
    if not PAPER2.is_dir():
        return []
    return [
        pytest.param(run_dir, arm, id=f"{name}/{run_dir.name}")
        for name, arm in _ARMS.items()
        for run_dir in sorted((PAPER2 / name).glob("run-*"))
    ]


def _from_dict(d: dict) -> DivergenceCampaignSummary:
    return DivergenceCampaignSummary(
        total=d["total"],
        top_level_counts=Counter(d["top_level_counts"]),
        tier_b_counts=Counter(d["tier_b_counts"]),
        tier_c_accept_reject=d["tier_c_accept_reject"],
        tier_c_value=d["tier_c_value"],
        unique_divergence_signatures=d["unique_divergence_signatures"],
        divergence_perturbation_categories=Counter(d["divergence_perturbation_categories"]),
    )


@pytest.mark.parametrize("run_dir,arm", _runs())
def test_replayed_prompts_match_paper2(run_dir: Path, arm: str) -> None:
    knowledge = knowledge_section(arm, None if arm == "none" else _human_body())
    last_good = empty_summary()
    last_error = None
    iterations = sorted(run_dir.glob("iteration-*"), key=lambda p: int(p.name.split("-")[1]))
    assert iterations
    for iteration in iterations:
        expected = (iteration / "prompt.txt").read_text(encoding="utf-8")
        assert build_refinement_prompt(DART, last_good, last_error, knowledge=knowledge) == expected, iteration
        summary = json.loads((iteration / "summary.json").read_text())
        error_path = iteration / "proposal_error.txt"
        if "proposal_rejected" not in summary["top_level_counts"]:
            last_good = _from_dict(summary)
        last_error = error_path.read_text(encoding="utf-8") if error_path.exists() else None


@pytest.mark.parametrize("run_dir,arm", _runs())
def test_summaries_match_paper2(run_dir: Path, arm: str) -> None:
    for results in run_dir.glob("iteration-*/results.jsonl"):
        expected = json.loads((results.parent / "summary.json").read_text())
        with results.open(encoding="utf-8") as f:
            got = summarize_records(DART, (json.loads(line) for line in f)).as_dict()
        assert {k: got[k] for k in expected} == expected, results


def _human_body() -> str:
    from ksfuzz.knowledge import HUMAN_DART_BODY

    return HUMAN_DART_BODY
