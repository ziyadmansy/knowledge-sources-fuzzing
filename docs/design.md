# Where Does an LLM Fuzzer's Domain Knowledge Come From?

**Working title:** *Self-Acquired Knowledge for Differential Testing of Typed Deserializers.*
**Status:** design and pre-registration, written 2026-09-27, before any code or API spend.
Everything in §4–§7 is fixed now. Changes after data exists are recorded in §10 with the reason, never edited in place.

---

## 1. Motivation (from paper 2)

Paper 2 (*Beyond Sanitizers*, AST 2027 submission, repo `agentic-fuzzing-dart-json`, design doc §17–18)
ended with a controlled result. An LLM-guided refinement loop found cross-implementation divergence in
2.9% of documents, against 22.2% for a hand-built static generator. Given **four observations from a
13-case manual characterization** (the knowledge the static generator was designed from), the same loop
reached 28.8% (pooled n=10, p≈0.013 vs no knowledge; indistinguishable from or above the static
generator). A larger model (`gpt-4.1`) without that knowledge did not improve (1.91%, p≈0.31). The
loop exploited the knowledge it was given but never found a divergence it had not been told about.

**So the bottleneck is domain knowledge, and in paper 2 it came from a human.** Paper 3 asks whether the
fuzzer can acquire that knowledge itself.

## 2. Positioning against related work (checked 2026-09-27)

| Work | What it does | Gap this paper fills |
|---|---|---|
| AIJon (arXiv 2609.18457, Sep 2026) | LLM-generated IJON annotations ≈ human-expert ones, coverage-guided fuzzing, Magma | Knowledge from **reading code** for **coverage** feedback. We study **behavioural** knowledge for a **coverage-free differential** oracle, including knowledge acquired by **running experiments** |
| DiffSpec (arXiv 2410.04249) | LLM reads specs + code to generate differential tests (eBPF, Wasm) | No ablation of knowledge sources; no black-box acquisition |
| WhiteFox (OOPSLA 2024), KernelGPT (ASPLOS 2025) | LLM reads source to derive test requirements / syscall specs | White-box only; no comparison with human or probe-acquired knowledge |
| Möller et al. (AsiaCCS 2024) | Differential testing of 22 raw JSON parsers | Parser level (text → tree); we test **typed binding** (tree → class) |
| JsonATG (APSEC 2025) | LLM test generation for Java JSON libraries (fastjson) | Single-library, Java; not cross-framework differential, not Kotlin codegen |
| Gson issue #1657 | Gson bypasses Kotlin null-safety (known) | Used as a **second answer key**: a known behaviour the agent should rediscover |

The novel element is **black-box self-characterization**: an agent that designs probe documents, runs
them against the targets, and writes its own knowledge summary, the way the human did in paper 2. It is
compared under control with no knowledge, human knowledge, and code-derived knowledge.

## 3. Research questions

- **RQ1 (acquisition).** Can an LLM agent that probes the targets black-box acquire knowledge that closes
  the refinement gap as well as human knowledge does? (Dart, where the answer key is known.)
- **RQ2 (sources).** How do knowledge sources compare: none, human, code-reading, and probing? We compare
  divergence rate, recall of known divergence patterns, and cost.
- **RQ3 (transfer and discovery).** On a new ecosystem with no human knowledge (Kotlin: Gson, Moshi,
  kotlinx.serialization, Jackson-Kotlin), does probing-acquired knowledge find divergences? Does it
  rediscover the known Gson null-safety bypass, and does it find anything previously unreported?

## 4. Arms

All arms use paper 2's unchanged refinement loop: 5 iterations × 500 examples, score-only prompt,
constrained sandbox, `gpt-4.1-mini`, temperature 0.2, lenient fence parsing ON for every arm (a fixed
setting in this repo, so there's no asymmetry). The **only** difference between arms is the text in the
knowledge slot of the prompt, which is capped at **1,500 characters** for every arm (paper 2's human
section was about 1,400).

| Arm | Knowledge slot content | Targets |
|---|---|---|
| **none** | empty | Dart, Kotlin |
| **human** | paper 2's four observations, verbatim | Dart only (no human characterization exists for Kotlin) |
| **code** | an LLM summary written after reading the four paths' deserialization code | Dart only (see §4.2) |
| **probe** | an LLM summary written after running its own probe documents (§4.1) | Dart, Kotlin |

### 4.1 Probing agent (the new method)

1. The agent gets the schema, the four path names, and a budget of **P = 20 probe documents**
   (comparable to the human's 13 cases plus follow-ups). It writes the probes as literal JSON documents,
   in up to **2 rounds** (e.g. 12 + 8), so it can follow up on surprises.
2. Each probe runs through the same harness. The agent sees, per path, accepted/rejected, the exception
   type, and the decoded canonical value. This is exactly what the human saw.
3. The agent writes a knowledge summary (≤ 1,500 chars) stating observations, **not** generator code.
4. The summary goes into the knowledge slot of the unchanged refinement loop.

The probing phase uses the same model (`gpt-4.1-mini`). It is run **once per seed**, so knowledge
quality varies across seeds and that variance is part of the result.

### 4.2 Code-reading arm, and why it is Dart-only

For Dart, all four paths have readable source: `manual.dart` and the generated `*.g.dart` for
json_serializable, freezed and built_value. The agent reads these (truncated to a fixed token budget,
identical per seed) and writes a summary under the same cap. For Kotlin, kotlinx.serialization generates
bytecode via a compiler plugin and Gson/Jackson use reflection, so no comparable source exists. This
asymmetry is itself a practical argument for black-box probing and is reported as such, not hidden.

## 5. Targets

### 5.1 Dart (answer key known)

Paper 2's harness and Record schema, reused byte-for-byte (json_serializable 6.14.1, freezed 4.0.1,
built_value 8.13.0, Dart 3.13.2). Known divergence patterns: `RAAR` (id saturation) and `RRRA`
(built_value missing `tags`).

### 5.2 Kotlin (discovery)

The same logical Record schema, as a Kotlin data class with a non-null `id: Long`, `amount: String`,
nullable `name: String?`, `status` enum, `tags: List<String>`, and nullable recursive `child`. Four
paths, each at its **documented defaults** (as paper 2 used "out of the box" configurations):

| Path | Library | Mechanism |
|---|---|---|
| A | Gson | reflection (known null-safety bypass) |
| B | Moshi + codegen (`@JsonClass(generateAdapter = true)`) | generated adapter |
| C | kotlinx.serialization | compiler plugin |
| D | Jackson + jackson-module-kotlin | reflection plus Kotlin module |

The harness uses the same NDJSON stdin/stdout protocol and the same canonical-value output as the Dart
harness, so the Python pipeline is reused unchanged. Build: a Gradle wrapper using Android Studio's
bundled JDK 21 and a cached Gradle distribution, with no global installs. Versions are pinned in a
committed lockfile/version catalog.

**Kotlin answer key (partial, from public sources):** Gson accepts a missing or explicit `null` for a
non-null field (issue #1657). Anything else found is a candidate new finding, to be verified by hand
before any report.

## 6. Design and analysis (pre-registered)

- **Seeds:** Dart arms 700–704 (none, human, code, probe; each n=5, fresh seeds, all re-run in this repo
  for self-containment). Kotlin arms 800–804 (none, probe).
- **Primary metric:** per-run divergence rate over all generated documents, as in paper 2.
- **Secondary:** rate over schema-evaluated documents; **pattern recall** (fraction of answer-key
  patterns found at least once per run); new patterns; LLM calls and tokens per arm.
- **Tests:** exact two-sided Mann-Whitney U, reported with the mean difference and Cliff's δ.
  - Primary RQ1 test: **probe vs none** (Dart). Co-primary: **probe vs human** (Dart).
  - RQ2: all pairwise comparisons among the four Dart arms, reported in full (no selective reporting),
    with a Holm correction noted alongside the raw p-values.
  - RQ3 primary: **probe vs none** (Kotlin).
- **Decision rules** (every direction covered; non-significance is *not* treated as "no effect"):
  - probe vs none: p < 0.05 higher → acquisition works; p < 0.05 lower → probing hurts (inspect before
    interpreting); p ≥ 0.05 → "not detected at n=5", with effect size and CI reported.
  - probe vs human: p ≥ 0.05 with |Cliff's δ| < 0.33 → "comparable to human knowledge" (an
    equivalence-style claim is only made if the effect size is small, not from p alone); p < 0.05 either
    direction → report the direction.
  - If the first n=5 of any primary comparison is suggestive but not significant, a replication on fresh
    seeds may be added **only** if declared in §10 *before* it runs, as in paper 2 §17.2.
- **Bug reports:** any Kotlin divergence becomes a candidate. Each is minimized, reproduced by hand
  outside the harness, checked against docs and existing issues, and only then reported. The paper
  counts reported / acknowledged / fixed separately.

## 7. Budget

`gpt-4.1-mini` at about $0.003 per refinement call (measured in paper 2), so about $0.08 per 25-call arm.
Probing adds about 3 calls per seed. Estimate: 6 arm-sets × 5 seeds ≈ $0.6–1.0 total, well inside the
$3/month org limit (resets 1 October). Actual spend is taken from the OpenAI dashboard, not estimates.

## 8. Steps (progress-based, not dated; hard deadline: preprint before PhD applications on 1 December)

1. **Harnesses**: Kotlin 4-path harness (same NDJSON protocol as Dart); port the Dart pipeline into this repo; hand-characterization smoke test on Kotlin.
2. **Agents**: probing agent and code-reading agent; knowledge-slot plumbing in the refinement loop.
3. **Gate**: Kotlin shows ≥1 divergence pattern, and the probing agent runs end-to-end on Dart. If Kotlin fails, fall back to Dart-only RQ1–RQ2.
4. **Experiments**: all arms (§6); analyses; Kotlin bug triage and upstream reports.
5. **Paper**: draft, then revision.
6. **Release**: artifact release, Zenodo DOI, preprint; CV/SOP entry.

## 9. Threats known up front

- **Knowledge-slot fairness:** summaries are capped at the same length, but quality isn't controlled;
  that is the variable under study.
- **Probe budget choice (P=20):** it is arbitrary. A sensitivity check with P=10 is optional and only if
  declared in §10 first.
- **Model family:** a single model family again (cost). Stated as a limitation.
- **Kotlin defaults:** some divergences are documented, configurable behaviour. Reports must say what is
  a default, and bug reports must not claim "bug" for documented choices.

## 10. Deviations log

*(empty; every change to §4–§7 after data exists goes here, with date and reason)*
