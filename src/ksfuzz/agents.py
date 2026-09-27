"""Knowledge-acquisition agents (docs/design.md §4.1, §4.2).

Both end in a knowledge body of at most KNOWLEDGE_CAP characters stating
observations, not generator code, which goes into the refinement loop's
knowledge slot. Everything each agent sees and says is written to `out_dir`.

- Probing agent: up to PROBE_BUDGET probe documents over two rounds (at most
  ROUND1_MAX in round 1, the rest in round 2), each run through the real
  harness; it sees per path accepted/rejected, the exception type, and the
  decoded canonical value. Then it writes the summary.
- Code-reading agent (Dart only): reads a fixed, per-seed-identical set of
  source files, then writes the summary.

`llm` is anything with `complete(prompt, max_output_tokens) -> str` and a
`usage` list (llm.OpenAIProposer, or a fake in tests).
"""

import json
from pathlib import Path
import re
from typing import Any

from .campaign import STRATEGY_HINT
from .knowledge import KNOWLEDGE_CAP
from .runner import run_batch
from .targets import Target

PROBE_BUDGET = 20
ROUND1_MAX = 12
_PROBE_DISPLAY_CHARS = 1000
_PROBE_BLOCK = re.compile(r"```probe[ \t]*\n(.*?)\n```", re.DOTALL)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*?)\n```\s*$", re.DOTALL)


def parse_probes(text: str) -> list[str]:
    return [block for block in _PROBE_BLOCK.findall(text) if block.strip()]


def format_result(number: int, document: str, response: dict[str, Any]) -> str:
    shown = document if len(document) <= _PROBE_DISPLAY_CHARS else document[:_PROBE_DISPLAY_CHARS] + " [truncated]"
    lines = [f"Probe {number}:", shown]
    if "paths" in response:
        for path in response["paths"]:
            if path["status"] == "accepted":
                value = json.dumps(path.get("canonical"), ensure_ascii=False, separators=(",", ":"))
                lines.append(f"  {path['path']}: accepted, decoded as {value}")
            else:
                lines.append(f"  {path['path']}: rejected ({path.get('exception_type', 'unknown')})")
    else:
        detail = response.get("reason") or response.get("decoded_type") or ""
        lines.append(
            f"  rejected before any implementation ran: {response.get('status')}"
            + (f" ({detail})" if detail else "")
        )
    return "\n".join(lines)


# Extension arm `sysprobe` (docs/design.md §10, declared before it ran): the same agent,
# told to cover schema-independent test categories first (category-partition testing and
# boundary-value analysis) and to say what it did not test. The default prompts, used by
# the `probe` arm, are unchanged (tests/test_agents.py checks them against committed runs).
CHECKLIST = """Probe systematically. Spend your probes on these categories first; they
apply to any JSON schema (category-partition testing and boundary-value
analysis), and each probe should change one thing in an otherwise valid
document:
1. a required field missing (one probe per field, as far as the budget allows);
2. a non-nullable field set to null;
3. a field with a value of the wrong JSON type (string, number, boolean,
   array, object);
4. a numeric field at a representation boundary: a fraction, an exponent
   form, and integers just beyond the 32-, 53- and 64-bit ranges, positive
   and negative;
5. an enum-like field with an unknown value, and with a case variant;
6. an extra unknown key, and a duplicate key;
7. the same kinds of change inside a nested object;
8. text that is not strict JSON: single quotes, an unquoted value, a
   trailing comma, NaN, and a raw control character inside a string.
You cannot cover every field in every category with the budget: prefer
breadth across categories over repetition, and use round 2 for what
round 1 left out or found surprising."""

_NOT_TESTED = """- End with one line that starts with "Not tested:" and lists the
  categories above that no probe covered."""


def _probe_intro(target: Target, systematic: bool = False) -> str:
    checklist = f"\n\n{CHECKLIST}" if systematic else ""
    return f"""You are characterizing four {target.title} by experiment, before a fuzzing campaign.

{target.description}

You will not write the fuzzer. Your job is to find out, by running probe
documents, how these four implementations behave, and then write down what
you learned for the model that will write the fuzzer.

You have a budget of {PROBE_BUDGET} probe documents in total, over two rounds.
Each probe is run through all four implementations. For each probe you see,
per implementation, whether it accepted or rejected the document, the
exception type if it rejected, and the decoded value if it accepted.

{STRATEGY_HINT}{checklist}"""


_PROBE_FORMAT = """Write each probe as the exact document text inside its own fenced block
labelled `probe`, like this:
```probe
{"id": 1, "amount": "1", "name": null, "status": "active", "tags": [], "child": null}
```
Outside the blocks, write at most one short line per probe saying what it tests."""


def round1_prompt(target: Target, systematic: bool = False) -> str:
    return f"""{_probe_intro(target, systematic)}

This is round 1: write at most {ROUND1_MAX} probes. After you see their results
you get a second round with the rest of the budget, so you can follow up on
anything surprising.

{_PROBE_FORMAT}
"""


def round2_prompt(target: Target, results: list[str], remaining: int, systematic: bool = False) -> str:
    joined = "\n\n".join(results)
    return f"""{_probe_intro(target, systematic)}

Round 1 probes and their results:

{joined}

This is round 2: write at most {remaining} more probes. Use them to follow up on
what round 1 showed: confirm surprises, find where a behaviour starts and
stops, and try what round 1 did not cover.

{_PROBE_FORMAT}
"""


_SUMMARY_INSTRUCTION = f"""Write down what you learned, for the model that will write a generator to
make these four implementations disagree. Rules:
- At most {KNOWLEDGE_CAP} characters in total.
- A numbered list of observations about behaviour: which implementations
  accept or reject what, and how they decode it.
- State only what the evidence above shows. No generator code.
Return only the list."""


def probe_summary_prompt(target: Target, results: list[str], systematic: bool = False) -> str:
    joined = "\n\n".join(results)
    instruction = _SUMMARY_INSTRUCTION
    if systematic:
        instruction = instruction.replace("\nReturn only the list.", f"\n{_NOT_TESTED}\nReturn only the list.")
    return f"""{_probe_intro(target, systematic)}

All probes and their results:

{joined}

{instruction}
"""


def code_summary_prompt(target: Target, sources: list[tuple[str, str]]) -> str:
    listing = "\n\n".join(f"=== {name} ===\n{text}" for name, text in sources)
    return f"""You are characterizing four {target.title} by reading their deserialization
code, before a fuzzing campaign.

{target.description}

You will not write the fuzzer. Your job is to read the code below, work out
how these four implementations behave, and then write down what you learned
for the model that will write the fuzzer.

{STRATEGY_HINT}

{listing}

{_SUMMARY_INSTRUCTION}
"""


def _clean_summary(text: str) -> str:
    text = text.strip()
    match = _FENCE.match(text)
    return match.group(1).strip() if match else text


def _finish_summary(llm: Any, prompt: str, out_dir: Path, log: dict[str, Any]) -> str:
    """One summary call, one shortening call if over the cap, then a hard cut at the
    last line break under the cap (recorded, never silent)."""
    (out_dir / "summary_prompt.txt").write_text(prompt, encoding="utf-8")
    response = llm.complete(prompt, max_output_tokens=1000)
    (out_dir / "summary_response.txt").write_text(response, encoding="utf-8")
    body = _clean_summary(response)
    if len(body) > KNOWLEDGE_CAP:
        log["summary_over_cap_chars"] = len(body)
        shorten = (
            f"Shorten this list to at most {KNOWLEDGE_CAP} characters, keeping the most useful "
            f"observations and their exact facts. Return only the list.\n\n{body}\n"
        )
        (out_dir / "shorten_prompt.txt").write_text(shorten, encoding="utf-8")
        response = llm.complete(shorten, max_output_tokens=1000)
        (out_dir / "shorten_response.txt").write_text(response, encoding="utf-8")
        body = _clean_summary(response)
    if len(body) > KNOWLEDGE_CAP:
        log["truncated_from_chars"] = len(body)
        cut = body.rfind("\n", 0, KNOWLEDGE_CAP + 1)
        body = body[: cut if cut > 0 else KNOWLEDGE_CAP].rstrip()
    (out_dir / "knowledge.txt").write_text(body + "\n", encoding="utf-8")
    return body


def _ask_for_probes(llm: Any, prompt: str, limit: int, out_dir: Path, name: str, log: dict[str, Any]) -> list[str]:
    """One call; one retry (with a format reminder) only if no probe block parsed."""
    (out_dir / f"{name}_prompt.txt").write_text(prompt, encoding="utf-8")
    response = llm.complete(prompt, max_output_tokens=2500)
    (out_dir / f"{name}_response.txt").write_text(response, encoding="utf-8")
    probes = parse_probes(response)
    if not probes:
        log[f"{name}_format_retry"] = True
        retry = prompt + "\nYour previous answer had no ```probe blocks. Use exactly that format.\n"
        response = llm.complete(retry, max_output_tokens=2500)
        (out_dir / f"{name}_retry_response.txt").write_text(response, encoding="utf-8")
        probes = parse_probes(response)
    if len(probes) > limit:
        log[f"{name}_dropped_over_budget"] = len(probes) - limit
        probes = probes[:limit]
    return probes


def _run_probes(
    target: Target, executable: str, probes: list[str], first_number: int, out_dir: Path, name: str
) -> list[str]:
    if not probes:
        return []
    batch = run_batch(executable, [p.encode("utf-8") for p in probes], 60.0, env=target.env())
    formatted = []
    with (out_dir / f"{name}_results.jsonl").open("w", encoding="utf-8") as f:
        for offset, probe in enumerate(probes):
            response = batch.lines[offset] if offset < len(batch.lines) else {"status": "harness_crash"}
            f.write(json.dumps({"probe": probe, "harness_response": response}, ensure_ascii=False) + "\n")
            formatted.append(format_result(first_number + offset, probe, response))
    return formatted


def run_probe_agent(target: Target, executable: str, llm: Any, out_dir: Path, systematic: bool = False) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    log: dict[str, Any] = {"agent": "sysprobe" if systematic else "probe", "target": target.name}
    calls_before = len(llm.usage)

    probes1 = _ask_for_probes(llm, round1_prompt(target, systematic), ROUND1_MAX, out_dir, "round1", log)
    results = _run_probes(target, executable, probes1, 1, out_dir, "round1")
    remaining = PROBE_BUDGET - len(probes1)
    probes2 = _ask_for_probes(
        llm, round2_prompt(target, results, remaining, systematic), remaining, out_dir, "round2", log
    )
    results += _run_probes(target, executable, probes2, len(probes1) + 1, out_dir, "round2")
    log["probes"] = [len(probes1), len(probes2)]

    body = _finish_summary(llm, probe_summary_prompt(target, results, systematic), out_dir, log)
    _write_log(llm, calls_before, body, out_dir, log)
    return body


def run_code_agent(target: Target, llm: Any, sources: list[tuple[str, str]], out_dir: Path) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    log: dict[str, Any] = {"agent": "code", "target": target.name, "sources": [name for name, _ in sources]}
    calls_before = len(llm.usage)
    body = _finish_summary(llm, code_summary_prompt(target, sources), out_dir, log)
    _write_log(llm, calls_before, body, out_dir, log)
    return body


def _write_log(llm: Any, calls_before: int, body: str, out_dir: Path, log: dict[str, Any]) -> None:
    usage = llm.usage[calls_before:]
    log["knowledge_chars"] = len(body)
    log["llm_usage"] = {
        "calls": len(usage),
        "input_tokens": sum(u["input_tokens"] for u in usage),
        "output_tokens": sum(u["output_tokens"] for u in usage),
        "truncated": sum(u.get("truncated", 0) for u in usage),
    }
    (out_dir / "agent.json").write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
