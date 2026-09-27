<!-- DRAFT, not filed. Target: https://github.com/Kotlin/kotlinx.serialization/issues/new
     Label suggestion: bug. Reproducer: ./src/main/kotlin/Main.kt (./gradlew run -Pkx=1.12.0-RC) -->

**Title:** Default (non-lenient) `Json` accepts unescaped control characters (U+0000–U+001F) inside strings

**Describe the bug**

The default `Json` instance accepts JSON strings that contain raw, unescaped control
characters, for example a literal U+0001 or a literal newline between the quotes. RFC 8259
§7 (and RFC 4627 §2.5, which the docs cite) requires these to be escaped:

> All Unicode characters may be placed within the quotation marks, except for the characters
> that MUST be escaped: quotation mark, reverse solidus, and the control characters
> (U+0000 through U+001F).

The [Lenient parsing](https://github.com/Kotlin/kotlinx.serialization/blob/master/docs/json.md#lenient-parsing)
section says the default parser "enforces various JSON restrictions to be as
specification-compliant as possible (see RFC-4627)", and `isLenient` is `false` here, so I
expected these inputs to be rejected.

**To Reproduce**

```kotlin
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class Payload(val text: String)

fun main() {
    // U+0001 and U+000A written raw (unescaped) inside the JSON string
    println(Json.decodeFromString<Payload>("{\"text\":\"a\u0001b\"}"))  // accepted
    println(Json.decodeFromString<Payload>("{\"text\":\"a\nb\"}"))      // accepted
    println(Json.parseToJsonElement("{\"text\":\"a\u0001b\"}"))         // accepted
    println(Json.decodeFromString<String>("\"a\u0001b\""))              // accepted
}
```

All four calls succeed and return the raw control character in the decoded value, on both
1.11.0 and 1.12.0-RC (JVM, Kotlin 2.4.20).

**Expected behavior**

A `JsonDecodingException`, as for other syntax errors in non-lenient mode. For comparison,
with the same inputs:

| Parser | Raw U+0001 in a string |
|---|---|
| kotlinx.serialization 1.11.0 / 1.12.0-RC, default `Json` | accepted |
| Jackson 2.22.3 (default `ObjectMapper`) | rejected: "Illegal unquoted character ((CTRL-CHAR, code 1)): has to be escaped using backslash" |
| Dart `jsonDecode` (Dart 3.13) | rejected: "Control character in string" |
| Gson 2.14.0 (default, legacy-lenient strictness) | accepted |

**Where it happens**

`AbstractJsonLexer.consumeString(source, startPosition, current)` loops until the closing
`"` and only special-cases `\`; there is no check for characters below U+0020 in the
non-lenient path.

**Context**

I found this while differential-testing four JSON libraries on the same Kotlin data class
(kotlinx.serialization, Jackson, Moshi, Gson): documents with a raw control character inside a
string were accepted by kotlinx.serialization and rejected by Jackson. The case may already be
among the misses listed in the benchmark report #3273, which was closed without discussion of
individual cases, so I'm filing it separately with a minimal reproducer.

If accepting these characters is intended, a note in the lenient-parsing docs would help, since
the current wording suggests the default mode is strict.

**Environment**
- Kotlin version: 2.4.20
- Library version: 1.11.0 and 1.12.0-RC
- Kotlin platforms: JVM (JDK 21)
- Gradle version: 9.3.1
