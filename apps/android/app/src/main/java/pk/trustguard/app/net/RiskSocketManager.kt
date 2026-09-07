package pk.trustguard.app.net

import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.WebSocket

data class DeltaSignal(
    val type: String,
    val severity: Int,
    val confidence: Double,
    val contribution: Double = 0.0
)

data class RiskState(
    val score: Int = 0,
    val band: String = "low",
    val deltaSignals: List<DeltaSignal> = emptyList(),
    val stage: String? = null,
    val safeActions: List<String> = emptyList(),
    val timestamp: Long? = null,
    /**
     * Server-authoritative scam-alert routing: usernames that should see the
     * warning (the potential victims). Empty = unknown topology; clients fall
     * back to their local heuristic.
     */
    val alertTargets: List<String> = emptyList()
) {
    companion object {
        val EMPTY = RiskState()
    }
}

/**
 * Per-session risk channel: ws://{host}/ws/session/{session_id}/risk
 *
 * Receives {"score","band","delta_signals","stage","safe_actions","timestamp"}
 * risk-update frames plus transcript_segment live-caption frames from the
 * gateway's STT pipeline. Non-risk notices (analysis_notice,
 * cross_channel_evidence, …) are ignored so they can never reset the
 * displayed score. Sends a literal "ping" text frame every 25 seconds as
 * keepalive.
 */
class RiskSocketManager(
    url: String,
    private val onRisk: (RiskState) -> Unit,
    private val onTranscript: ((speaker: String, text: String, username: String) -> Unit)? = null
) : ReconnectingSocket(url) {

    private var pingJob: Job? = null

    override fun onSocketOpen(ws: WebSocket) {
        flushPending()
        startPingLoop()
    }

    private fun startPingLoop() {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (isActive) {
                delay(PING_INTERVAL_MS)
                if (isConnected && !sendText("ping")) break
            }
        }
    }

    override fun onSocketText(text: String) {
        val obj = parseJsonObject(text) ?: return // ignore "pong" / non-JSON keepalives

        // Live voice captions from the gateway's faster-whisper pipeline.
        // "username" is the server-resolved account of WHO is speaking.
        if (obj.optString("type") == "transcript_segment") {
            val speech = obj.optString("text").orEmpty()
            if (speech.isNotBlank()) {
                onTranscript?.invoke(
                    obj.optString("speaker") ?: "them",
                    speech,
                    obj.optString("username").orEmpty()
                )
            }
            return
        }

        // Only genuine risk updates drive the alert UI; every other server
        // notice is informational and must not touch the displayed state.
        if (obj["band"] == null && obj["score"] == null) return

        val signals = obj.array("delta_signals")
            ?.mapNotNull { element ->
                val s = element as? JsonObject ?: return@mapNotNull null
                DeltaSignal(
                    type = s.optString("type") ?: "signal",
                    severity = s.optInt("severity") ?: 0,
                    confidence = s.optDouble("confidence") ?: 0.0,
                    contribution = s.optDouble("contribution") ?: 0.0
                )
            }
            ?: emptyList()

        onRisk(
            RiskState(
                score = obj.optInt("score") ?: 0,
                band = (obj.optString("band") ?: "low").lowercase(),
                deltaSignals = signals,
                stage = obj.optString("stage"),
                safeActions = safeActions(obj),
                timestamp = obj.optLong("timestamp"),
                alertTargets = obj.array("alert_targets")?.mapNotNull {
                    (it as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull
                } ?: emptyList()
            )
        )
    }

    /**
     * Reports a user-dismissed scam alert ("I've verified this contact") to the
     * gateway so the dashboard can see the acknowledgement. Harmless if the
     * gateway ignores unknown frames.
     */
    fun sendAlertDismissed(reason: String = "user_verified"): Boolean =
        sendText(
            buildJsonObject {
                put("type", "alert_dismissed")
                put("reason", reason)
            }.toString()
        )

    private fun safeActions(obj: kotlinx.serialization.json.JsonObject): List<String> =
        obj.array("safe_actions")
            ?.mapNotNull { element ->
                (element as? kotlinx.serialization.json.JsonPrimitive)?.contentOrNull
            }
            ?.filter { it.isNotBlank() }
            ?: emptyList()

    override fun onSocketClosed(code: Int, reason: String) {
        stopPingLoop()
    }

    override fun onBeforeClose() {
        stopPingLoop()
    }

    private fun stopPingLoop() {
        pingJob?.cancel()
        pingJob = null
    }

    companion object {
        private const val PING_INTERVAL_MS = 25_000L
    }
}
