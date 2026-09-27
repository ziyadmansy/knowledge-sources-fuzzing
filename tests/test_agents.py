"""Knowledge agents with a scripted fake LLM: budgets, parsing, the cap, and what
the agent is shown. Probe runs use the real harnesses (skipped if not built)."""

from pathlib import Path

import pytest

from ksfuzz.agents import (
    CHECKLIST,
    PROBE_BUDGET,
    ROUND1_MAX,
    parse_probes,
    probe_summary_prompt,
    round1_prompt,
    run_code_agent,
    run_probe_agent,
)
from ksfuzz.knowledge import KNOWLEDGE_CAP, knowledge_section
from ksfuzz.targets import DART, KOTLIN, REPO_ROOT

VALID = '{"id":1,"amount":"1","name":null,"status":"active","tags":[],"child":null}'
MISSING_TAGS = '{"id":1,"amount":"1","name":null,"status":"active","child":null}'


class FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.usage: list[dict[str, int]] = []

    def complete(self, prompt: str, max_output_tokens: int = 2500) -> str:
        self.prompts.append(prompt)
        self.usage.append({"input_tokens": 1, "output_tokens": 1})
        return self.responses.pop(0)


def _blocks(*docs: str) -> str:
    return "\n".join(f"tests something\n```probe\n{d}\n```" for d in docs)


def test_parse_probes_keeps_raw_text() -> None:
    text = "intro\n```probe\n{'a': 1}\n```\nnote\n```probe\n{\n  \"id\": 1\n}\n```\n```python\nx\n```"
    assert parse_probes(text) == ["{'a': 1}", '{\n  "id": 1\n}']


@pytest.mark.parametrize("target", [DART, KOTLIN], ids=lambda t: t.name)
def test_probe_agent_end_to_end(target, tmp_path: Path) -> None:
    if not target.default_executable.is_file():
        pytest.skip("harness not built")
    too_many = [VALID] * (ROUND1_MAX + 3)
    llm = FakeLLM(
        [
            _blocks(*too_many[:-1], MISSING_TAGS),  # over budget: the extras are dropped
            "no blocks at all",  # round 2: triggers one format retry
            _blocks(MISSING_TAGS, "{'id': 1}"),
            "```\n1. An observation.\n```",
        ]
    )
    body = run_probe_agent(target, str(target.default_executable), llm, tmp_path)
    assert body == "1. An observation."
    assert (tmp_path / "knowledge.txt").read_text() == "1. An observation.\n"
    round2, retry, summary = llm.prompts[1], llm.prompts[2], llm.prompts[3]
    assert f"at most {PROBE_BUDGET - ROUND1_MAX} more probes" in round2
    assert "Probe 12:" in round2 and "Probe 13:" not in round2
    assert "no ```probe blocks" in retry
    assert "Probe 14:" in summary and "Probe 15:" not in summary
    # Per-path outcomes are shown; missing `tags` diverges on both targets.
    assert "accepted, decoded as" in summary and "rejected (" in summary
    assert len(knowledge_section("probe", body)) > len(body)


def test_summary_over_cap_is_shortened_then_cut(tmp_path: Path) -> None:
    long_line = "x" * 100
    too_long = "\n".join(f"{i}. {long_line}" for i in range(30))  # ~3,100 chars
    llm = FakeLLM([too_long, too_long])
    body = run_code_agent(DART, llm, [("manual.dart", "// code")], tmp_path)
    assert len(body) <= KNOWLEDGE_CAP and body.endswith(long_line)
    assert "manual.dart" in llm.prompts[0] and "Shorten" in llm.prompts[1]
    log = (tmp_path / "agent.json").read_text()
    assert '"truncated_from_chars"' in log and '"calls": 2' in log


@pytest.mark.parametrize("target", [DART, KOTLIN], ids=lambda t: t.name)
def test_probe_arm_prompt_unchanged_by_extension(target) -> None:
    """The `probe` arm's committed round-1 prompts must still be what the code builds."""
    first = sorted((REPO_ROOT / "knowledge" / target.name / "probe").glob("seed-*/round1_prompt.txt"))
    if not first:
        pytest.skip("no committed probe knowledge")
    assert round1_prompt(target) == first[0].read_text(encoding="utf-8")


def test_sysprobe_adds_checklist_and_not_tested_line() -> None:
    assert CHECKLIST in round1_prompt(DART, systematic=True)
    assert CHECKLIST not in round1_prompt(DART)
    assert '"Not tested:"' in probe_summary_prompt(DART, [], systematic=True)
    assert "Not tested" not in probe_summary_prompt(DART, [])
