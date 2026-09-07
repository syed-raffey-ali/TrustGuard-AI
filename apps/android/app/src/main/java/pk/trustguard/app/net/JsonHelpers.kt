package pk.trustguard.app.net

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

/** Lenient JSON mapper shared by the gateway client and socket managers. */
internal val tolerantJson: Json = Json {
    ignoreUnknownKeys = true
    isLenient = true
}

/** Parses [text] as a JSON object; returns null for non-JSON payloads (e.g. "pong"). */
internal fun parseJsonObject(text: String): JsonObject? =
    runCatching { tolerantJson.parseToJsonElement(text) }.getOrNull() as? JsonObject

internal fun JsonObject.optString(key: String): String? =
    (this[key] as? JsonPrimitive)?.contentOrNull

internal fun JsonObject.optInt(key: String): Int? =
    (this[key] as? JsonPrimitive)?.intOrNull

internal fun JsonObject.optLong(key: String): Long? =
    (this[key] as? JsonPrimitive)?.longOrNull

internal fun JsonObject.optDouble(key: String): Double? =
    (this[key] as? JsonPrimitive)?.doubleOrNull

internal fun JsonObject.optBoolean(key: String): Boolean? =
    (this[key] as? JsonPrimitive)?.booleanOrNull

internal fun JsonObject.array(key: String): JsonArray? =
    this[key] as? JsonArray
