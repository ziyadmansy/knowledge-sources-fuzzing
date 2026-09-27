# knowledge-sources-fuzzing (paper 3)

Design and pre-registration: `docs/design.md`. Sections 4–7 are fixed; any change after data exists goes in the §10 deviations log, never edited in place.

## Build and run the Kotlin harness

There is no system Java. Use Android Studio's bundled JDK 21 through the Gradle wrapper, and don't install anything globally.

```sh
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
cd kotlin-harness && ./gradlew --no-daemon -q installDist
printf '{"input_b64":"%s"}\n' "$(printf '{"id":1,"amount":"1","name":null,"status":"active","tags":[],"child":null}' | base64)" \
  | build/install/kotlin-json-harness/bin/kotlin-json-harness
```

## Python pipeline

Package `src/ksfuzz` is paper 2's loop, ported with a per-target config (`targets.py`) and a knowledge slot (`knowledge.py`). Python 3.14 venv with pinned deps (hypothesis must stay 6.165.5, because `seeding.py` depends on its internals):

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q          # includes byte-for-byte replay of paper 2's prompts
set -a; . ../agentic-fuzzing-dart-json/.env; set +a
.venv/bin/python scripts/run_arm.py --target dart --arm none --seed 700 --runs 5
```

## Sibling repos

- `../agentic-fuzzing-dart-json`: paper 2. The Dart harness binary is `build/dart_json_harness`. The Python pipeline to port is in `src/agentic_fuzzing/`. The OpenAI key is in its `.env`: load it into the environment only, and never print it or copy it here.
- `../agentic-fuzzing`: paper 1.
