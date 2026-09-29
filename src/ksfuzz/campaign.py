"""Divergence campaign, summary and refinement loop (docs/design.md §4).

Ported from the previous study's `dart_divergence_campaign.py`. The loop and the score-only
prompt are unchanged; what is new:

- a `Target` (targets.py) supplies the path names and the prompt's description of
  the four paths, so the same loop drives Dart and Kotlin;
- a generic knowledge slot replaces the previous study's `knowledge_parity` flag. Each arm
  differs only in the text placed there (knowledge.py);
- for Kotlin, divergence is counted on all inputs, not only `schema_evaluated`
  ones (§10), and the summary also splits divergence by gate status;
- the summary keeps a count per divergent signature, for pattern recall (§6).

The previous study's `allow_json`, `category_feedback` and `mutate_source` ablations are
not ported: no arm in this design uses them.
"""

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable, Iterable

from .proposal import GenerationError, proposal_inputs
from .runner import HarnessBatchResult, run_batch
from .targets import Target


def run_campaign(
    target: Target,
    executable: str,
    inputs: Iterable[bytes | GenerationError],
    output_path: Path,
    max_examples: int = 500,
    timeout_seconds: float = 5.0,
) -> Counter[str]:
    """One harness invocation per campaign; persists the full oracle result per line."""
    counts: Counter[str] = Counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    items: list[bytes | GenerationError] = []
    for index, item in enumerate(inputs):
        if index >= max_examples:
            break
        items.append(item)

    data_items = [item for item in items if not isinstance(item, GenerationError)]
    if data_items:
        batch_timeout = max(30.0, timeout_seconds * len(data_items))
        batch = run_batch(executable, data_items, batch_timeout, env=target.env())
    else:
        batch = HarnessBatchResult(lines=[], timed_out=False, returncode=0)

    with output_path.open("w", encoding="utf-8") as output:
        response_iter = iter(batch.lines)
        for index, item in enumerate(items):
            if isinstance(item, GenerationError):
                counts["encoding_error"] += 1
                output.write(json.dumps(_generation_error_observation(index, item)) + "\n")
                continue

            response = next(response_iter, None)
            if response is None:
                status = "harness_timeout" if batch.timed_out else "harness_crash"
                counts[status] += 1
                output.write(
                    json.dumps(_harness_failure_observation(index, item, status, batch.returncode)) + "\n"
                )
                continue

            counts[response.get("status", "unknown")] += 1
            output.write(json.dumps(_observation(index, item, response)) + "\n")
    return counts


def _observation(index: int, data: bytes, response: dict) -> dict[str, object]:
    return {
        "index": index,
        "input_hex": data.hex(),
        "input_length": len(data),
        "harness_response": response,
    }


def _harness_failure_observation(
    index: int, data: bytes, status: str, returncode: int | None
) -> dict[str, object]:
    return {
        "index": index,
        "input_hex": data.hex(),
        "input_length": len(data),
        "harness_response": {"status": status, "returncode": returncode},
    }


def _generation_error_observation(index: int, error: GenerationError) -> dict[str, object]:
    return {
        "index": index,
        "input_hex": "",
        "input_length": 0,
        "harness_response": {"status": "encoding_error", "generation_error": error.error},
    }


# Summary keys that are new in this repo. They are left out of the prompt's
# "other metrics" blob so the Dart prompts stay byte-identical to the previous study's.
_NEW_SUMMARY_KEYS = ("divergence_signatures", "tier_c_by_gate")


@dataclass(frozen=True)
class DivergenceCampaignSummary:
    total: int
    top_level_counts: Counter[str]
    tier_b_counts: Counter[str]
    tier_c_accept_reject: int
    tier_c_value: int
    unique_divergence_signatures: int
    divergence_perturbation_categories: Counter[str]
    divergence_signatures: Counter[str] = field(default_factory=Counter)
    tier_c_by_gate: Counter[str] = field(default_factory=Counter)

    @property
    def score(self) -> int:
        return self.tier_c_accept_reject + self.tier_c_value

    def as_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "top_level_counts": dict(self.top_level_counts),
            "tier_b_counts": dict(self.tier_b_counts),
            "tier_c_accept_reject": self.tier_c_accept_reject,
            "tier_c_value": self.tier_c_value,
            "unique_divergence_signatures": self.unique_divergence_signatures,
            "divergence_perturbation_categories": dict(self.divergence_perturbation_categories),
            "divergence_signatures": dict(self.divergence_signatures),
            "tier_c_by_gate": dict(self.tier_c_by_gate),
        }


def empty_summary() -> DivergenceCampaignSummary:
    return DivergenceCampaignSummary(0, Counter(), Counter(), 0, 0, 0, Counter())


_SCHEMA_FIELDS = ("id", "amount", "name", "status", "tags", "child")
_NON_NULLABLE_FIELDS = ("id", "amount", "status", "tags")
_STATUS_VALUES = ("active", "inactive", "unknown")


def _classify_perturbations(document: object) -> set[str]:
    """Categorize what is unusual about a document, by its shape against the schema.
    Unchanged from the previous study; reporting only (no arm feeds it back to the proposer)."""
    categories: set[str] = set()
    if not isinstance(document, dict):
        return categories
    for name in _SCHEMA_FIELDS:
        if name not in document:
            categories.add("missing_field")
    for name in _NON_NULLABLE_FIELDS:
        if name in document and document[name] is None:
            categories.add("null_override")
    if "id" in document and document["id"] is not None and not isinstance(document["id"], int):
        categories.add("wrong_type")
    if "amount" in document and document["amount"] is not None and not isinstance(document["amount"], str):
        categories.add("wrong_type")
    if "name" in document and document["name"] is not None and not isinstance(document["name"], str):
        categories.add("wrong_type")
    if "tags" in document and document["tags"] is not None and not isinstance(document["tags"], list):
        categories.add("wrong_type")
    if "status" in document:
        status = document["status"]
        if isinstance(status, str) and status not in _STATUS_VALUES:
            categories.add("bad_enum")
        elif status is not None and not isinstance(status, str):
            categories.add("wrong_type")
    if "id" in document and isinstance(document["id"], int):
        if abs(document["id"]) >= 2**53 - 1024:
            categories.add("boundary_id")
    if set(document.keys()) - set(_SCHEMA_FIELDS):
        categories.add("extra_key")
    depth = 0
    node = document.get("child")
    while isinstance(node, dict):
        depth += 1
        node = node.get("child")
    if depth > 3:
        categories.add("deep_nesting")
    return categories


def _counts_for_divergence(target: Target, response: dict) -> bool:
    if "paths" not in response:
        return False
    return target.divergence_on_all_inputs or response.get("status") == "schema_evaluated"


def signature(target: Target, response: dict) -> str | None:
    """Accept/reject pattern over the four paths in `target.path_order` (e.g. 'AARR'),
    with ':value' when all accepted but disagreed on the decoded value. `None` for
    inputs where divergence is not counted for this target."""
    if not _counts_for_divergence(target, response):
        return None
    by_path = {p["path"]: p for p in response["paths"]}
    pattern = "".join("A" if by_path[name]["status"] == "accepted" else "R" for name in target.path_order)
    if response.get("tier_c_divergence") == "value":
        pattern += ":value"
    return pattern


def summarize_records(target: Target, records: Iterable[dict[str, object]]) -> DivergenceCampaignSummary:
    total = 0
    top_level_counts: Counter[str] = Counter()
    tier_b_counts: Counter[str] = Counter()
    tier_c_accept_reject = 0
    tier_c_value = 0
    signatures: set[str] = set()
    divergence_signatures: Counter[str] = Counter()
    tier_c_by_gate: Counter[str] = Counter()
    perturbation_categories: Counter[str] = Counter()
    for record in records:
        total += 1
        response = record["harness_response"]
        gate = str(response.get("status", "unknown"))
        top_level_counts[gate] += 1
        if not _counts_for_divergence(target, response):
            continue
        for path_name in response.get("tier_b_paths", []):
            tier_b_counts[path_name] += 1
        divergence = response.get("tier_c_divergence")
        if divergence == "accept_reject":
            tier_c_accept_reject += 1
        elif divergence == "value":
            tier_c_value += 1
        pattern = signature(target, response)
        if pattern is not None:
            signatures.add(pattern)
        if divergence in ("accept_reject", "value"):
            tier_c_by_gate[gate] += 1
            if pattern is not None:
                divergence_signatures[pattern] += 1
            input_hex = record.get("input_hex")
            if input_hex:
                try:
                    document = json.loads(bytes.fromhex(input_hex).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    document = None
                for category in _classify_perturbations(document):
                    perturbation_categories[category] += 1
    return DivergenceCampaignSummary(
        total=total,
        top_level_counts=top_level_counts,
        tier_b_counts=tier_b_counts,
        tier_c_accept_reject=tier_c_accept_reject,
        tier_c_value=tier_c_value,
        unique_divergence_signatures=len(signatures),
        divergence_perturbation_categories=perturbation_categories,
        divergence_signatures=divergence_signatures,
        tier_c_by_gate=tier_c_by_gate,
    )


_IMPORT_INSTRUCTION = (
    "The only import allowed is `from hypothesis import strategies as st` -- "
    "do not import `json` or anything else; build the JSON text yourself "
    "with string concatenation and Hypothesis `.map()`/`.flatmap()` transforms."
)

STRATEGY_HINT = """Strategy hint: implementations are more likely to disagree on documents that
are *almost* well-formed with one specific thing off (a field of the wrong
type, a field missing rather than present-but-wrong, a value at a type
boundary) than on documents that are broadly malformed in many ways at once
-- broad malformation tends to make every implementation reject identically,
which scores zero. Vary one or two things about an otherwise valid document
at a time, across many documents, rather than maximizing how unusual any
single document looks."""


def build_refinement_prompt(
    target: Target,
    summary: DivergenceCampaignSummary,
    previous_error: str | None = None,
    knowledge: str | None = None,
) -> str:
    """The previous study's score-only prompt. `knowledge` is the arm's whole knowledge section
    (knowledge.py), or None for the `none` arm."""
    other_metrics = {
        key: value
        for key, value in summary.as_dict().items()
        if key
        not in ("tier_c_accept_reject", "tier_c_value", "divergence_perturbation_categories", *_NEW_SUMMARY_KEYS)
    }
    error_section = (
        f"\nThe previous iteration's proposal failed before producing usable data:\n{previous_error}\n"
        if previous_error
        else ""
    )
    knowledge_section = f"\n{knowledge}\n" if knowledge else ""
    # The two empty lines where the previous study had its (unused here) regression and
    # previous-source sections are kept, so the prompt bytes match.
    return f"""You are refining a Hypothesis strategy to find behavioral divergence between four {target.title}.

{target.description}
{knowledge_section}
YOUR SCORE (from the last iteration that produced usable data): {summary.score} documents
out of {summary.total} where the four implementations disagreed with each other
({summary.tier_c_accept_reject} where one accepted and another rejected,
{summary.tier_c_value} where two accepted but decoded to different values).
Maximizing this score is the objective. A high rejection count on its own
(see tier_b_counts below) is not the goal by itself -- a document every
implementation rejects the same way scores zero, no matter how "malformed"
it looks.

Other metrics from that iteration, for context only:
{json.dumps(other_metrics, sort_keys=True)}
{error_section}

{STRATEGY_HINT}

Return only Python source defining `@st.composite def generated_json(draw) -> bytes`.
{target.syntax_note}
Use bounded recursion and output sizes. The campaign runs at most 500
examples per iteration. {_IMPORT_INSTRUCTION}
Do not use subprocesses, filesystem, network access, eval, exec, or
coverage instrumentation.
"""


def run_refinement_loop(
    target: Target,
    executable: str,
    proposer: Callable[[str], str],
    artifact_dir: Path,
    knowledge: str | None = None,
    iterations: int = 5,
    examples_per_iteration: int = 500,
    timeout_seconds: float = 5.0,
) -> list[DivergenceCampaignSummary]:
    """The previous study's bounded loop: each iteration writes a fresh generator from the
    score of the last iteration that produced data; failures fall back to it."""
    summaries: list[DivergenceCampaignSummary] = []
    last_good = empty_summary()
    last_error: str | None = None
    examples = min(examples_per_iteration, 500)
    for iteration in range(min(iterations, 5)):
        prompt = build_refinement_prompt(target, last_good, last_error, knowledge=knowledge)
        proposal = proposer(prompt)
        iteration_dir = artifact_dir / f"iteration-{iteration + 1}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        (iteration_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
        (iteration_dir / "proposal.py").write_text(proposal, encoding="utf-8")
        result_path = iteration_dir / "results.jsonl"
        try:
            run_campaign(
                target,
                executable,
                proposal_inputs(proposal, examples),
                result_path,
                max_examples=examples,
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            error_text = f"{type(error).__name__}: {error}"
            (iteration_dir / "proposal_error.txt").write_text(error_text, encoding="utf-8")
            last_error = error_text
            if result_path.exists() and result_path.stat().st_size > 0:
                with result_path.open(encoding="utf-8") as result_file:
                    partial = summarize_records(target, (json.loads(line) for line in result_file))
                last_good = partial
                summaries.append(partial)
            else:
                summaries.append(
                    DivergenceCampaignSummary(1, Counter({"proposal_rejected": 1}), Counter(), 0, 0, 0, Counter())
                )
            continue
        with result_path.open(encoding="utf-8") as result_file:
            summary = summarize_records(target, (json.loads(line) for line in result_file))
        last_good = summary
        last_error = None
        summaries.append(summary)
    return summaries
