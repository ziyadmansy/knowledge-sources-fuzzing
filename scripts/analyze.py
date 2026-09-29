#!/usr/bin/env python3
"""Pre-registered analysis (docs/design.md §6) over artifacts/<target>/<arm>/run-*.

Per run, following the previous study's aggregate_rq2_runs.py: iterations whose proposal was
rejected before producing data are excluded; divergence is summed over the rest.
Primary metric: divergence rate over all generated documents. Secondary: rate over
schema-evaluated documents, pattern recall, LLM calls/tokens/truncation.

Tests: exact two-sided Mann-Whitney U, mean difference, Cliff's delta, and for
RQ2 a Holm correction reported next to the raw p-values.

  .venv/bin/python scripts/analyze.py [--json out.json]
"""

import argparse
from itertools import combinations
import json
from pathlib import Path
import statistics
import sys

from scipy.stats import mannwhitneyu

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ksfuzz.targets import TARGETS  # noqa: E402

ARMS = {"dart": ("none", "human", "code", "probe"), "kotlin": ("none", "probe")}
# Extension study (design §10.1): new arms only, analysed as their own families.
EXTENSION_ARMS = {"dart": ("sysprobe", "probe-gpt41"), "kotlin": ("sysprobe",)}
# Dart answer key (§5.1): id saturation and built_value's missing-tags default.
DART_KEY = ("RAAR", "RRRA")
_NON_NULL = ("amount", "status", "tags")


def gson_null_bypass(response: dict) -> bool:
    """Kotlin answer key (§5.2, Gson #1657): Gson accepts, others don't all agree, and
    Gson's decoded value has null in a non-null field."""
    if response.get("tier_c_divergence") not in ("accept_reject", "value"):
        return False
    gson = next((p for p in response.get("paths", []) if p["path"] == "A_gson"), None)
    if not gson or gson["status"] != "accepted" or not isinstance(gson.get("canonical"), dict):
        return False
    return any(gson["canonical"].get(k) is None for k in _NON_NULL)


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def rfc_object(data: bytes) -> bool:
    """RFC 8259-valid JSON object: strict UTF-8, no raw control characters in strings
    (json's strict=True), no NaN/Infinity. Replaces the Kotlin harness's gate label,
    which uses kotlinx's parseToJsonElement and turned out to accept raw control
    characters, unquoted strings and NaN (docs/design.md §10, post-data)."""
    try:
        return isinstance(json.loads(data.decode("utf-8"), parse_constant=_reject_constant), dict)
    except (ValueError, UnicodeDecodeError):
        return False


def collect_run(target_name: str, run_dir: Path) -> dict:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    total = schema = tier_c = tier_c_schema = 0
    rejected = 0
    signatures: dict[str, int] = {}
    bypass = 0
    rfc = rfc_divergent = 0
    for iteration in sorted(run_dir.glob("iteration-*")):
        summary = json.loads((iteration / "summary.json").read_text())
        counts = summary["top_level_counts"]
        if "proposal_rejected" in counts:
            rejected += 1
            continue
        total += summary["total"]
        schema += counts.get("schema_evaluated", 0)
        tier_c += summary["tier_c_accept_reject"] + summary["tier_c_value"]
        tier_c_schema += summary.get("tier_c_by_gate", {}).get("schema_evaluated", 0)
        for sig, n in summary.get("divergence_signatures", {}).items():
            signatures[sig] = signatures.get(sig, 0) + n
        if target_name == "kotlin" and (iteration / "results.jsonl").exists():
            with (iteration / "results.jsonl").open() as f:
                for line in f:
                    record = json.loads(line)
                    response = record["harness_response"]
                    bypass += gson_null_bypass(response)
                    if record.get("input_hex") and rfc_object(bytes.fromhex(record["input_hex"])):
                        rfc += 1
                        rfc_divergent += response.get("tier_c_divergence") in ("accept_reject", "value")
    if target_name == "dart":
        recall = sum(k in signatures for k in DART_KEY) / len(DART_KEY)
    else:
        recall = float(bypass > 0)
    usage = manifest.get("llm_usage", {})
    return {
        "run": run_dir.name,
        "seed": manifest["seed"],
        "iterations_rejected": rejected,
        "total": total,
        "schema_evaluated": schema,
        "tier_c": tier_c,
        "rate_total": 100.0 * tier_c / total if total else 0.0,
        "rate_schema": 100.0 * tier_c_schema / schema if schema else None,
        # Kotlin only: the same rate over RFC 8259-valid objects (see rfc_object).
        "rfc_valid": rfc if target_name == "kotlin" else None,
        "rate_rfc_valid": 100.0 * rfc_divergent / rfc if rfc else None,
        "pattern_recall": recall,
        "gson_null_bypass_docs": bypass if target_name == "kotlin" else None,
        "signatures": signatures,
        "llm_usage": usage,
    }


def cliffs_delta(a: list[float], b: list[float]) -> float:
    gt = sum(x > y for x in a for y in b)
    lt = sum(x < y for x in a for y in b)
    return (gt - lt) / (len(a) * len(b))


def compare(a: list[float], b: list[float]) -> dict:
    p = mannwhitneyu(a, b, alternative="two-sided", method="exact").pvalue
    return {
        "mean_a": statistics.mean(a),
        "mean_b": statistics.mean(b),
        "mean_diff": statistics.mean(a) - statistics.mean(b),
        "p": float(p),
        "cliffs_delta": cliffs_delta(a, b),
    }


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    m, running, adjusted = len(ordered), 0.0, {}
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * p))
        adjusted[name] = running
    return adjusted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--artifacts", type=Path, default=REPO_ROOT / "artifacts")
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--kotlin-seeds",
        choices=("original", "replication", "pooled"),
        default="original",
        help="800-804 (pre-registered), 805-809 (declared replication, §10), or both",
    )
    args = parser.parse_args()

    report: dict = {"runs": {}, "tests": {}}
    rates: dict[tuple[str, str], list[float]] = {}
    for target_name, arms in {t: ARMS[t] + EXTENSION_ARMS[t] for t in ARMS}.items():
        assert target_name in TARGETS
        for arm in arms:
            # run_arm.py adds llm_usage to the manifest only once a run has finished.
            finished = [
                d
                for d in sorted((args.artifacts / target_name / arm).glob("run-*"))
                if "llm_usage" in json.loads((d / "manifest.json").read_text())
            ]
            rows = [collect_run(target_name, d) for d in finished]
            if target_name == "kotlin" and args.kotlin_seeds != "pooled":
                wanted = range(800, 805) if args.kotlin_seeds == "original" else range(805, 810)
                rows = [r for r in rows if r["seed"] in wanted]
            if not rows:
                continue
            report["runs"][f"{target_name}/{arm}"] = rows
            rates[(target_name, arm)] = [r["rate_total"] for r in rows]
            schema_rates = [r["rate_schema"] for r in rows if r["rate_schema"] is not None]
            calls = sum(r["llm_usage"].get("calls", 0) for r in rows)
            truncated = sum(r["llm_usage"].get("truncated", 0) for r in rows)
            print(
                f"{target_name:6} {arm:5} n={len(rows)} "
                f"rate={statistics.mean(rates[(target_name, arm)]):6.2f}% "
                f"values={[round(v, 2) for v in rates[(target_name, arm)]]} "
                f"schema_rate={statistics.mean(schema_rates) if schema_rates else float('nan'):6.2f}% "
                + (
                    f"rfc_rate={statistics.mean(r['rate_rfc_valid'] for r in rows if r['rate_rfc_valid'] is not None):6.2f}% "
                    if target_name == "kotlin"
                    else ""
                )
                + f"recall={statistics.mean(r['pattern_recall'] for r in rows):.2f} "
                f"rejected_iters={sum(r['iterations_rejected'] for r in rows)} "
                f"calls={calls} truncated={truncated}"
            )

    def test(name: str, a: tuple[str, str], b: tuple[str, str]) -> None:
        if a in rates and b in rates:
            result = compare(rates[a], rates[b])
            report["tests"][name] = result
            print(
                f"{name:28} diff={result['mean_diff']:+7.2f}pp p={result['p']:.4f} "
                f"delta={result['cliffs_delta']:+.2f}"
            )

    print()
    test("RQ1 primary: dart probe-none", ("dart", "probe"), ("dart", "none"))
    test("RQ1 co-primary: probe-human", ("dart", "probe"), ("dart", "human"))
    test("RQ3 primary: kotlin probe-none", ("kotlin", "probe"), ("kotlin", "none"))
    rq2 = {}
    for a, b in combinations(ARMS["dart"], 2):
        name = f"RQ2 dart {b}-{a}"
        test(name, ("dart", b), ("dart", a))
        if name in report["tests"]:
            rq2[name] = report["tests"][name]["p"]
    if rq2:
        for name, p_holm in holm(rq2).items():
            report["tests"][name]["p_holm"] = p_holm
        print("Holm-adjusted RQ2:", {k: round(v, 4) for k, v in holm(rq2).items()})

    def family(label: str, pairs: list[tuple[str, tuple[str, str], tuple[str, str]]]) -> None:
        names = []
        for name, a, b in pairs:
            test(name, a, b)
            if name in report["tests"]:
                names.append(name)
        if names:
            adjusted = holm({n: report["tests"][n]["p"] for n in names})
            for n, p_holm in adjusted.items():
                report["tests"][n]["p_holm"] = p_holm
            print(f"Holm-adjusted {label}:", {k: round(v, 4) for k, v in adjusted.items()})

    print()
    family(
        "E1",
        [
            ("E1 primary: dart sysprobe-none", ("dart", "sysprobe"), ("dart", "none")),
            ("E1 dart sysprobe-probe", ("dart", "sysprobe"), ("dart", "probe")),
            ("E1 dart sysprobe-human", ("dart", "sysprobe"), ("dart", "human")),
            ("E1 dart sysprobe-code", ("dart", "sysprobe"), ("dart", "code")),
            ("E1 kotlin sysprobe-none", ("kotlin", "sysprobe"), ("kotlin", "none")),
            ("E1 kotlin sysprobe-probe", ("kotlin", "sysprobe"), ("kotlin", "probe")),
        ],
    )
    family(
        "E2",
        [
            ("E2 dart probe-gpt41 - probe", ("dart", "probe-gpt41"), ("dart", "probe")),
            ("E2 dart probe-gpt41 - none", ("dart", "probe-gpt41"), ("dart", "none")),
        ],
    )
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
