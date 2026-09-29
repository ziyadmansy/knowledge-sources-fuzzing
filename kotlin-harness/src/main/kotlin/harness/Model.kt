package harness

import com.squareup.moshi.JsonClass
import kotlinx.serialization.Serializable

// The shared Record schema from the previous study (docs/design.md §5.2), as one idiomatic Kotlin data class
// used by all four paths. No default values and no configuration: the only annotations are the ones
// kotlinx.serialization and Moshi codegen need to run at all (Gson and Jackson ignore them).
// Enum constants are lowercase so every library maps them by name with zero configuration.

@Serializable
enum class Status { active, inactive, unknown }

@Serializable
@JsonClass(generateAdapter = true)
data class Record(
    val id: Long,
    val amount: String,
    val name: String?,
    val status: Status,
    val tags: List<String>,
    val child: Record?,
)
