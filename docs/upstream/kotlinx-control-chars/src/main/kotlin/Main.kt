import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class Payload(val text: String)

fun attempt(label: String, block: () -> Any?) =
    println("$label -> " + runCatching(block).fold({ "accepted: " + it.toString().replace("\u0001", "\\u0001").replace("\n", "\\n") }, { "rejected: ${it::class.simpleName}" }))

fun main() {
    println("kotlinx-serialization-json " + (Json::class.java.`package`.implementationVersion ?: "?"))
    // U+0001 and U+000A written raw (unescaped) inside the JSON string.
    val rawCtrl = "{\"text\":\"a\u0001b\"}"
    val rawLf = "{\"text\":\"a\nb\"}"
    val escaped = "{\"text\":\"a\\u0001b\"}"
    attempt("decodeFromString, raw U+0001") { Json.decodeFromString<Payload>(rawCtrl) }
    attempt("decodeFromString, raw U+000A") { Json.decodeFromString<Payload>(rawLf) }
    attempt("parseToJsonElement, raw U+0001") { Json.parseToJsonElement(rawCtrl) }
    attempt("decodeFromString<String>, raw U+0001") { Json.decodeFromString<String>("\"a\u0001b\"") }
    attempt("decodeFromString, escaped \\u0001 (valid)") { Json.decodeFromString<Payload>(escaped) }
}
