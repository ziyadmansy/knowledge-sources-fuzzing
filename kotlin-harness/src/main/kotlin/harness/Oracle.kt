package harness

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import com.google.gson.Gson
import com.squareup.moshi.Moshi
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// Each library at its documented defaults, parsing the raw text itself (unlike Dart, there is no
// shared parse step; docs/design.md §10).
private val gson = Gson()
private val moshiAdapter = Moshi.Builder().build().adapter(Record::class.java)
private val kotlinxJson = Json
private val jackson = jacksonObjectMapper()

private val decoders: List<Pair<String, (String) -> Record?>> = listOf(
    "A_gson" to { text -> gson.fromJson(text, Record::class.java) },
    "B_moshi" to { text -> moshiAdapter.fromJson(text) },
    "C_kotlinx" to { text -> kotlinxJson.decodeFromString<Record>(text) },
    "D_jackson" to { text -> jackson.readValue<Record>(text) },
)

/**
 * Canonical value of a decoded Record, built only from JSON primitives so comparison can't
 * reintroduce the errors the oracle looks for. Every property is read into a *nullable* local
 * first: Gson constructs objects without running Kotlin's constructor null checks, so a
 * "non-null" property can really be null (or, for `id: Long`, the JVM default 0), and that
 * must show up in the canonical value instead of crashing the canonicalizer.
 */
@Suppress("USELESS_CAST", "UNNECESSARY_SAFE_CALL")
fun canonical(record: Record?): JsonElement {
    if (record == null) return JsonNull
    val tags = record.tags as List<String?>?
    val status = record.status as Status?
    return buildJsonObject {
        put("id", record.id)
        put("amount", record.amount as String?)
        put("name", record.name)
        put("status", status?.name)
        put("tags", if (tags == null) JsonNull else buildJsonArray { tags.forEach { add(JsonPrimitive(it)) } })
        put("child", canonical(record.child as Record?))
    }
}

fun runOracle(text: String): JsonObject {
    val results = decoders.map { (name, decode) ->
        try {
            val record = decode(text)
            // Moshi returns null for the literal `null` document; treat a null top-level result as
            // accepted-with-null, same as any other accepted value.
            name to Result.success(canonical(record))
        } catch (e: Throwable) {
            name to Result.failure(e)
        }
    }
    val accepted = results.map { it.second.isSuccess }.toSet()
    val divergence = when {
        accepted.size > 1 -> "accept_reject"
        accepted.single() && results.map { it.second.getOrNull() }.toSet().size > 1 -> "value"
        else -> "none"
    }
    return buildJsonObject {
        put("paths", JsonArray(results.map { (name, result) ->
            result.fold(
                onSuccess = { value ->
                    buildJsonObject {
                        put("path", name)
                        put("status", "accepted")
                        put("canonical", value)
                    }
                },
                onFailure = { e ->
                    buildJsonObject {
                        put("path", name)
                        put("status", "rejected")
                        put("exception_type", e.javaClass.name)
                        // Dart's private-type (leading underscore) notion has no JVM equivalent.
                        put("is_private", false)
                        put("message", (e.message ?: "").take(300))
                    }
                },
            )
        }))
        put("tier_b_paths", JsonArray(emptyList()))
        put("tier_c_divergence", divergence)
    }
}
