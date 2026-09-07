package pk.trustguard.director

import android.content.Context
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

/**
 * One scripted line from a director scenario file.
 *
 * Scenario files are JSON objects whose array lives under the key "lines"
 * (scenario B) or "messages" (scenario C); both shapes are handled.
 * Older files may omit "n" — the loader then assigns sequential numbers.
 */
data class ScriptLine(
    val n: Int,
    val speaker: String,
    val text: String,
    val pauseMs: Long,
    val crossChannelOtpText: String? = null
)

object DirectorScripts {

    const val ASSET_DIR: String = "director/scripts"
    const val CLIP_DIR: String = "director/clips"

    val SCRIPT_FILES: List<String> = listOf(
        "scenario_b_bank_otp.json",
        "scenario_c_grooming.json"
    )

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
    }

    /** Loads and normalises a scenario file from app assets. Returns an empty list on any failure. */
    fun loadLines(context: Context, fileName: String): List<ScriptLine> {
        val raw = runCatching {
            context.assets.open("$ASSET_DIR/$fileName").bufferedReader().use { it.readText() }
        }.getOrElse { return emptyList() }
        return parse(raw)
    }

    /** Parses scenario JSON text; accepts arrays under either "lines" or "messages". */
    fun parse(raw: String): List<ScriptLine> {
        val root = runCatching { json.parseToJsonElement(raw) }.getOrNull() as? JsonObject
            ?: return emptyList()
        val arr = (root["lines"] as? JsonArray)
            ?: (root["messages"] as? JsonArray)
            ?: return emptyList()

        var fallbackN = 0
        val lines = ArrayList<ScriptLine>(arr.size)
        for (element in arr) {
            val o = element as? JsonObject ?: continue
            val text = o.optString("text") ?: continue
            fallbackN += 1
            lines += ScriptLine(
                n = o.optInt("n") ?: fallbackN,
                speaker = o.optString("speaker") ?: "them",
                text = text,
                pauseMs = o.optLong("pause_ms") ?: 0L,
                crossChannelOtpText = o.optString("cross_channel_otp_text")
            )
        }
        return lines.sortedBy { it.n }
    }

    /** Conventional clip filename for a line index, e.g. line 3 -> "line_03.wav". */
    fun clipNameFor(n: Int): String = "line_%02d.wav".format(n)

    private fun JsonObject.optString(key: String): String? =
        (this[key] as? JsonPrimitive)?.contentOrNull

    private fun JsonObject.optInt(key: String): Int? =
        (this[key] as? JsonPrimitive)?.intOrNull

    private fun JsonObject.optLong(key: String): Long? =
        (this[key] as? JsonPrimitive)?.longOrNull
}
