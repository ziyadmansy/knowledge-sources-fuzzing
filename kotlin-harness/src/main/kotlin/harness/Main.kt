package harness

import java.nio.ByteBuffer
import java.nio.charset.CharacterCodingException
import java.nio.charset.CodingErrorAction
import java.util.Base64
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

// NDJSON batch harness, same protocol as paper 2's Dart harness:
//   stdin:  {"input_b64": "<base64 of the candidate's raw bytes>"}   (one per line)
//   stdout: one JSON result per line, flushed immediately.
// Difference from Dart (docs/design.md §10): the four paths are run on EVERY input, because each
// Kotlin library parses the text itself. `status` is still the Dart-style gate, computed by a strict
// reference parser, so results can be split by gate status when comparing with Dart.

private val strictReference = Json

fun main() {
    val out = System.out.bufferedWriter()
    System.`in`.bufferedReader(Charsets.UTF_8).useLines { lines ->
        for (line in lines) {
            if (line.isBlank()) continue
            out.write(processLine(line).toString())
            out.newLine()
            out.flush()
        }
    }
}

fun processLine(line: String): JsonObject {
    val bytes = try {
        val request = Json.parseToJsonElement(line).jsonObject
        Base64.getDecoder().decode(request["input_b64"]!!.jsonPrimitive.content)
    } catch (e: Exception) {
        return buildJsonObject {
            put("status", "harness_error")
            put("reason", "invalid_request_line")
            put("message", e.toString())
        }
    }

    // Real apps (e.g. OkHttp/Retrofit) decode response bytes as UTF-8 with replacement, so the
    // libraries always receive a String; invalid UTF-8 only affects the reported gate status.
    val strictUtf8 = try {
        Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes)).toString()
    } catch (e: CharacterCodingException) {
        null
    }
    val text = strictUtf8 ?: String(bytes, Charsets.UTF_8)

    val (status, reason) = when {
        strictUtf8 == null -> "structural_reject" to "invalid_utf8"
        else -> try {
            val element = strictReference.parseToJsonElement(text)
            if (element is JsonObject) "schema_evaluated" to null else "structural_valid_non_object" to null
        } catch (e: Exception) {
            "structural_reject" to "invalid_json_syntax"
        }
    }

    val oracle = runOracle(text)
    return buildJsonObject {
        put("status", status)
        if (reason != null) put("reason", reason)
        oracle.forEach { (key, value) -> put(key, value) }
    }
}
