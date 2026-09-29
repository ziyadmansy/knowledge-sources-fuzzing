# Where Does an LLM Fuzzer's Domain Knowledge Come From?

**Working title:** *Self-Acquired Knowledge for Differential Testing of Typed Deserializers.*
**Status:** design and pre-registration, written 2026-09-27, before any code or API spend.
Everything in §4–§7 is fixed now. Changes after data exists are recorded in §10 with the reason, never edited in place.

---

## 1. Motivation (from the previous study)

The previous study (anonymized for review; design doc §17–18)
ended with a controlled result. An LLM-guided refinement loop found cross-implementation divergence in
2.9% of documents, against 22.2% for a hand-built static generator. Given **four observations from a
13-case manual characterization** (the knowledge the static generator was designed from), the same loop
reached 28.8% (pooled n=10, p≈0.013 vs no knowledge; indistinguishable from or above the static
generator). A larger model (`gpt-4.1`) without that knowledge did not improve (1.91%, p≈0.31). The
loop exploited the knowledge it was given but never found a divergence it had not been told about.

**So the bottleneck is domain knowledge, and in the previous study it came from a human.** This study asks whether the
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
them against the targets, and writes its own knowledge summary, the way the human did in the previous study. It is
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

All arms use the previous study's unchanged refinement loop: 5 iterations × 500 examples, score-only prompt,
constrained sandbox, `gpt-4.1-mini`, temperature 0.2, lenient fence parsing ON for every arm (a fixed
setting in this repo, so there's no asymmetry). The **only** difference between arms is the text in the
knowledge slot of the prompt, which is capped at **1,500 characters** for every arm (the previous study's human
section was about 1,400).

| Arm | Knowledge slot content | Targets |
|---|---|---|
| **none** | empty | Dart, Kotlin |
| **human** | the previous study's four observations, verbatim | Dart only (no human characterization exists for Kotlin) |
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

The previous study's harness and Record schema, reused byte-for-byte (json_serializable 6.14.1, freezed 4.0.1,
built_value 8.13.0, Dart 3.13.2). Known divergence patterns: `RAAR` (id saturation) and `RRRA`
(built_value missing `tags`).

### 5.2 Kotlin (discovery)

The same logical Record schema, as a Kotlin data class with a non-null `id: Long`, `amount: String`,
nullable `name: String?`, `status` enum, `tags: List<String>`, and nullable recursive `child`. Four
paths, each at its **documented defaults** (as the previous study used "out of the box" configurations):

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
- **Primary metric:** per-run divergence rate over all generated documents, as in the previous study.
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
    seeds may be added **only** if declared in §10 *before* it runs, as in the previous study §17.2.
- **Bug reports:** any Kotlin divergence becomes a candidate. Each is minimized, reproduced by hand
  outside the harness, checked against docs and existing issues, and only then reported. The paper
  counts reported / acknowledged / fixed separately.

## 7. Budget

`gpt-4.1-mini` at about $0.003 per refinement call (measured in the previous study), so about $0.08 per 25-call arm.
Probing adds about 3 calls per seed. Estimate: 6 arm-sets × 5 seeds ≈ $0.6–1.0 total, well inside the
$3/month org limit (resets 1 October). Actual spend is taken from the OpenAI dashboard, not estimates.

## 8. Steps (progress-based, not dated; hard deadline: 1 December)

1. **Harnesses**: Kotlin 4-path harness (same NDJSON protocol as Dart); port the Dart pipeline into this repo; hand-characterization smoke test on Kotlin.
2. **Agents**: probing agent and code-reading agent; knowledge-slot plumbing in the refinement loop.
3. **Gate**: Kotlin shows ≥1 divergence pattern, and the probing agent runs end-to-end on Dart. If Kotlin fails, fall back to Dart-only RQ1–RQ2.
4. **Experiments**: all arms (§6); analyses; Kotlin bug triage and upstream reports.
5. **Paper**: draft, then revision.
6. **Release**: artifact release, DOI, preprint.

## 9. Threats known up front

- **Knowledge-slot fairness:** summaries are capped at the same length, but quality isn't controlled;
  that is the variable under study.
- **Probe budget choice (P=20):** it is arbitrary. A sensitivity check with P=10 is optional and only if
  declared in §10 first.
- **Model family:** a single model family again (cost). Stated as a limitation.
- **Kotlin defaults:** some divergences are documented, configurable behaviour. Reports must say what is
  a default, and bug reports must not claim "bug" for documented choices.

## 10. Deviations log

- **2026-09-27, before any data: Kotlin has no shared parsing gate (clarifies §5.2).** In Dart, all
  four paths receive the output of one shared `jsonDecode`, so invalid JSON can never cause divergence.
  In Kotlin, each library parses the raw text itself (Gson, Moshi, kotlinx.serialization, and Jackson
  each have their own parser; Gson is lenient by default). So the Kotlin harness runs **all four paths
  on every input**, and still reports the Dart-style gate `status` computed by a strict reference parser
  (`kotlinx.serialization.json.Json.parseToJsonElement`). Syntax-level divergences are therefore
  possible and counted in Kotlin's primary metric (divergence over all documents); they are also
  reported separately by gate status, so the Dart and Kotlin rates can be compared like for like.
- **2026-09-27, before any data: Kotlin schema is idiomatic, with no default values.** The Record is a
  plain data class with no default parameter values and no annotations beyond what each library needs
  to run (`@Serializable`, `@JsonClass(generateAdapter = true)`). Enum constants are lowercase so that
  every library maps them by name with zero configuration. Documented library behaviour that follows
  from this (e.g. kotlinx.serialization requiring a default for an *optional* nullable field) counts as
  divergence, but is labelled "documented default", never "bug".
- **2026-09-27, before any data: knowledge-slot framing.** Each arm's slot is a one-sentence header
  naming the source ("from a hand-run characterization", "from reading their deserialization code",
  "from running probe documents"), then the body. The 1,500-character cap applies to the body. The human
  section is the previous study's, verbatim with its header (body: 1,291 characters), so the Dart `human` arm is
  the previous study's knowledge-parity prompt exactly. A test (`tests/test_prompt_parity.py`) rebuilds every
  committed the previous study prompt for the score-only and knowledge-parity arms (20 runs, 100 prompts) byte for byte.
- **2026-09-27, before any data: Kotlin prompt text.** It uses the same prompt skeleton, schema and
  strategy hint as Dart. Two Dart-specific sentences are replaced with harness facts only: the path list
  (Gson, Moshi generated adapter, kotlinx.serialization, Jackson with its Kotlin module, each at defaults
  and decoding into the same data class), and "each library parses the raw text itself" in place of
  Dart's "invalid JSON is rejected identically before any path runs" (false for Kotlin, see the first
  entry). The Dart goal sentence's clause about private exception types is dropped for Kotlin, because
  the JVM has no equivalent (Tier B is always empty there). No behavioural claim about any library
  appears in the Kotlin `none` prompt.
- **2026-09-27, before any data: the previous study's ablation flags are not ported.** `allow_json`,
  `category_feedback` and `mutate_source` belong to no arm in §4. Divergence signatures counted per
  run (for pattern recall) and LLM token usage per run (for cost) are recorded in each run's artifacts.
- **2026-09-27, before any data: probing-agent protocol details (fixes §4.1's "e.g.").** Round 1 allows
  at most 12 probes, and round 2 gets the rest of the 20. Probes are written as raw text in ```probe
  blocks, so non-JSON probes are possible (they matter for Kotlin). Probes over a round's budget are
  dropped in order. If a response has no probe block, the agent gets one retry with a format reminder.
  The agent is shown, per path, accepted/rejected, the exception type, and the decoded canonical value,
  but not the exception message (§4.1's list). A Dart input that fails the shared gate is shown as
  "rejected before any implementation ran" with its gate status. The agent prompt uses the same target
  description as the refinement prompt, so it holds no more a priori knowledge than the `none` arm.
- **2026-09-27, before any data: summary cap enforcement (both agents).** If the summary is over 1,500
  characters, there is one shortening call. If it is still over, it is cut at the last line break under
  the cap. Both events are recorded in `agent.json`, never silently.
- **2026-09-27, before any data: code-arm reading list.** For each Dart path, the model source and its
  generated `*.g.dart` (manual.dart; json_serializable, freezed and built_value models and `.g.dart`;
  built_value's serializers). That is about 17K characters, under a fixed 24K-character budget, so
  nothing is truncated. Freezed's `.freezed.dart` (copyWith/equality boilerplate, no JSON decoding) is
  not included, per §4.2's list. The harness entry point with the shared `jsonDecode` is not included:
  it is not a path's deserialization code.
- **2026-09-27, before any data: pilot seed.** The step-3 gate run uses seed 699, which is outside every
  experiment seed range. It checks the pipeline end to end, and its output is never pooled with results.
  Any prompt change it prompts is logged here before seeds 700+ run.
- **2026-09-27, pilot (seed 699), before any experiment data: both knowledge agents get the refinement
  prompt's strategy hint.** Pilot v1 (`artifacts/pilot/knowledge/dart/probe-v1/`) spent 13 of 20 probes on
  well-formed documents and 7 on duplicate keys. It found no divergence, and its summary claimed "no
  unnameable exceptions" although `_TypeError` is private. The refinement prompt's generic strategy hint
  (one thing off at a time: wrong type, missing field, type boundary), which every arm including `none`
  already sees, was missing from the agent prompts. It is now included verbatim in both the probe and
  code agent prompts, so each agent starts from exactly the `none` arm's a priori information and
  nothing more. This was the only change, and the agent prompts are now frozen. Pilot v2 tested one wrong
  thing at a time, but still never removed a field or used a non-integer `id`, and found 0 divergences
  in 20 probes. That is kept as data about the method, not tuned away.
- **2026-09-27, pilot: Kotlin probe agent (seed 799, outside 800–804), frozen prompts.** 11 of 20 probes
  diverged (patterns AARA, ARRR, AARR). The summary was cut from 2,235 to 1,482 characters by the cap rule.
  **Step-3 gate: passed.** Kotlin shows divergence, and the probe agent plus loop ran end to end on Dart.
- **2026-09-27, pilot, before any experiment data: refinement output limit raised from 2,500 to 8,000
  tokens for every arm.** On the Dart pilot loop, 4 of 5 proposals were cut off mid-generator at paper
  2's 2,500-token limit (the previous study's knowledge-parity arm: 1 of 50), because a long knowledge section
  invites one branch per observation. Truncation measures code length, not knowledge quality. Every arm
  is re-run fresh on seeds 700+, so the within-paper comparison stays fair; the prompts are unchanged
  (the parity test still passes). Re-pilot (`artifacts/pilot/dart/probe-8k/`): 0 of 5 truncated. The two
  remaining failures were ordinary generator bugs, and one iteration found `RRRA`. Whether each response
  was truncated is now recorded per call and reported per arm. Decided by the author on 2026-09-27.
- **2026-09-27, step 4 run log (not a deviation).** All 30 runs finished as pre-registered (Dart 700–704 ×
  4 arms, Kotlin 800–804 × 2 arms); no truncated responses. Summaries hit the hard cap cut in 14 of 15
  knowledge acquisitions, and the cut was recorded in each `agent.json`. Some iterations stalled for hours
  because the host went to sleep, which delayed them but did not change any result. Results are in
  `artifacts/analysis.json`. Kotlin probe vs none came out suggestive but not significant (p=0.095). Any
  replication on fresh seeds would have to be declared here before it runs (§6).
- **2026-09-27, declared before it runs: Kotlin replication (§6 rule).** The RQ3 primary (Kotlin probe vs none,
  n=5) came out p=0.095, δ=+0.68, which is suggestive but not significant. Both Kotlin arms are re-run on fresh
  seeds 805–809 with everything else identical: probe knowledge is acquired anew for each new seed, and the
  prompts and code are unchanged. Reporting will cover both the replication alone (n=5 vs 5) and the pooled data
  (n=10 vs 10), with the original n=5 result always reported alongside. No Dart replication is declared: Dart
  probe vs none was p=0.69, which is not the "suggestive" case.
- **2026-09-27, AFTER data (secondary metric only): the Kotlin gate label is not RFC-strict.** During triage,
  the harness's "strict reference" (`kotlinx…Json.parseToJsonElement`) turned out to accept raw U+0000–U+001F
  inside strings, unquoted string values and `NaN`, all of which RFC 8259 forbids. So the Kotlin
  `schema_evaluated` label over-counts valid JSON. The primary metric (divergence over all documents) does not
  use the label and is unaffected. The gate split is re-derived post hoc in `scripts/analyze.py`
  (`rfc_object`: strict UTF-8, Python `json` with strict=True, NaN/Infinity rejected, top-level object) and
  reported as `rate_rfc_valid`. The harness is left unchanged so the committed runs stay reproducible. Original
  seeds: none 39.51%, probe 49.36% over RFC-valid objects (vs 47.02% / 64.40% under the harness label).

### 10.1 Extension study (declared 2026-09-27, pushed to GitHub before any run)

The main study (§4–§7) is complete and its analysis is unchanged by this extension. The extension tests two
explanations for why unguided probing failed on Dart (paper §V), with new arms only; **no seed is added to any
existing arm**, so no existing comparison is re-tested with more data.

- **E1: `sysprobe` (systematic probing).** The same probing agent, model (`gpt-4.1-mini`), budget (20 probes,
  12 + rest) and summary cap. Its prompt adds the category checklist in `src/ksfuzz/agents.py` (`CHECKLIST`,
  verbatim at this commit), and its summary must end with a "Not tested:" line. The knowledge header is the same as
  `probe`'s, so only the body differs. Seeds: Dart 700–704 and Kotlin 800–804, the same labels as the `probe`
  arm's pre-registered seeds, so the arms pair up by seed.
  *Bias disclosure:* the checklist was written by an author who knows the answer key. To limit this, every item is a
  standard, schema-independent category (category-partition testing, boundary-value analysis for 32/53/64-bit
  integers, JSON-syntax variants), and none names a field, path, or library.
- **E2: `probe` knowledge from a larger model.** The unchanged `probe` agent and prompts, run with `gpt-4.1` for
  knowledge acquisition only. The refinement loop stays `gpt-4.1-mini`. Dart seeds 700–704. Knowledge goes to
  `knowledge/dart/probe-gpt41/` and runs to `artifacts/dart/probe-gpt41/`.

**Tests** (exact two-sided Mann-Whitney U, mean difference, Cliff's δ; n=5 per arm):
- E1 primary: Dart `sysprobe` vs `none`. Secondary: Dart `sysprobe` vs `probe`, vs `human`, vs `code`; Kotlin
  `sysprobe` vs `none` (seeds 800–804) and vs `probe` (800–804). Holm correction across these six, reported next to
  the raw p-values.
- E2: Dart `probe-gpt41` vs `probe` and vs `none` (Holm across the two).
- Also reported: Dart pattern recall per arm (`RAAR`, `RRRA`), probe coverage by category (the paper's Table VII),
  whether each summary's "Not tested:" line is accurate, and cost.

**Decision rules** are as in §6. If E1 shows `sysprobe` > `none` at p < 0.05 on Dart, the paper reports that the
failure of unguided probing is a coverage problem that a generic checklist fixes. If not, it reports that coverage
alone is not enough. If E2 shows no improvement, it reports that a larger model does not fix unguided probing
either. No further arms or seeds are added after these results without a new, earlier entry here.

**Budget:** about $0.55 (E1 about $0.26, E2 about $0.28), taken from the dashboard afterwards.

**2026-09-27, extension run log (not a deviation).** Everything ran as declared in §10.1. Results are in
`artifacts/analysis-extension.json`.
- E1: Dart `sysprobe` vs `none` has p=0.032 and δ=+0.84, which meets the pre-registered rule (p < 0.05). The
  Holm-adjusted p across the declared family of six is 0.159; both are reported. Kotlin `sysprobe` vs `none` has
  p=0.016 (Holm 0.095).
- E2: `probe-gpt41` vs `none` has p=0.032 (Holm 0.063); vs `probe`, p=0.151.
- One `sysprobe` refinement response was truncated at the 8,000-token limit.
- The "Not tested:" line was lost to the cap cut in 3 of 5 Dart and 5 of 5 Kotlin summaries, because it comes last
  and the pre-registered cut removes trailing lines. This is a flaw in the extension's design; it is reported, not
  fixed after the fact.
