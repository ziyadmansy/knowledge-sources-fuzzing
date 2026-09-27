# Where does an LLM fuzzer's domain knowledge come from?

Research artifact for the paper *Where Does an LLM Fuzzer's Domain Knowledge Come From? Human, Code-Read, and
Self-Acquired Knowledge for Differential Testing of Typed Deserializers*.

Preprint: [doi:10.5281/zenodo.23002933](https://doi.org/10.5281/zenodo.23002933)

An earlier study ([Beyond Sanitizers](https://doi.org/10.5281/zenodo.22555794)) found that an LLM-guided
refinement loop for differential testing of Dart JSON deserializers found divergence in 2.9% of generated
documents on its own, but in 28.8% with four observations written by a human. This repository asks whether the
fuzzer can acquire that knowledge itself. The loop is held fixed, and only a 1,500-character knowledge slot in its
prompt changes:

| Arm | Knowledge slot | Targets |
|---|---|---|
| `none` | empty | Dart, Kotlin |
| `human` | the four human observations, verbatim | Dart |
| `code` | a summary by an agent that reads the four paths' deserialization code | Dart |
| `probe` | a summary by an agent that runs 20 black-box probe documents | Dart, Kotlin |

## Results

Divergence rate, % of all generated documents (mean over seeds):

| | none | human | code | probe |
|---|---|---|---|---|
| Dart (n=5 each) | 1.45 | 30.89 | 11.55 | 10.51 |
| Kotlin (n=10 each) | 49.95 | – | – | 67.13 |

- Dart: human > code > none, each pair p ≈ 0.008 (Holm 0.048). Probe vs none is not detected (p ≈ 0.69). Probing
  is all-or-nothing: 49% on the one seed whose probes hit a divergence, at most 1.3% on the others.
- Kotlin: probe vs none p ≈ 0.007 over ten seeds, pooling the pre-registered seeds with a replication that was
  declared before it ran.
- The divergence patterns each arm finds match the facts its knowledge states.

Full analysis: [`artifacts/analysis.json`](artifacts/analysis.json) and
[`artifacts/analysis-kotlin-pooled.json`](artifacts/analysis-kotlin-pooled.json). Kotlin triage:
[`docs/kotlin-triage.md`](docs/kotlin-triage.md).

## Pre-registration

[`docs/design.md`](docs/design.md) fixed the research questions, arms, seeds, tests and decision rules before any
code or API spend. Every later change is in its §10 deviations log, with the date, the reason, and whether data
existed at the time. The git history shows the order.

## Layout

| Path | Contents |
|---|---|
| `docs/design.md` | design, pre-registration, deviations log |
| `kotlin-harness/` | Kotlin 4-path harness (Gson, Moshi codegen, kotlinx.serialization, Jackson), NDJSON protocol |
| `src/ksfuzz/` | refinement loop (ported from the earlier study), target configs, knowledge slot, probing and code-reading agents |
| `scripts/` | `acquire_knowledge.py`, `run_arm.py`, `run_all_arms.sh`, `analyze.py` |
| `knowledge/` | every agent prompt, response, probe result and final knowledge summary, per seed |
| `artifacts/` | every refinement run: prompts, generators, per-document results, summaries, manifests; pilots in `artifacts/pilot/` |
| `docs/kotlin-triage.md` | minimal repros of each Kotlin divergence class, checked against docs and issue trackers |
| `docs/upstream/` | a drafted upstream report with a standalone reproducer |
| `paper/` | LaTeX source |
| `tests/` | includes a byte-for-byte replay of the earlier study's committed prompts |

## Reproducing

Requirements: Python 3.14, a JDK 21 (no system Java is needed; any JDK 21 works through `JAVA_HOME`), and for
Dart the compiled harness from
[agentic-fuzzing-dart-json](https://github.com/ziyadmansy/agentic-fuzzing-dart-json) checked out next to this
repository.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
export JAVA_HOME=/path/to/jdk-21
(cd kotlin-harness && ./gradlew --no-daemon -q installDist)
.venv/bin/pytest -q                      # offline: prompt parity, harness smoke tests, agents with a fake LLM
.venv/bin/python scripts/analyze.py      # recomputes every reported number from the committed artifacts
```

Re-running the arms needs an OpenAI API key in `OPENAI_API_KEY` and costs about $1 in total at `gpt-4.1-mini`
prices. LLM responses are not deterministic, so a re-run reproduces the procedure, not the exact documents;
the committed artifacts are the data the paper reports.

## License

MIT, see [LICENSE](LICENSE).
