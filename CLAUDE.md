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

## Sibling repos

- `../agentic-fuzzing-dart-json`: paper 2. The Dart harness binary is `build/dart_json_harness`. The Python pipeline to port is in `src/agentic_fuzzing/`. The OpenAI key is in its `.env`: load it into the environment only, and never print it or copy it here.
- `../agentic-fuzzing`: paper 1.
