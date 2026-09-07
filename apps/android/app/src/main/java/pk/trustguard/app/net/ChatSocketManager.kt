package pk.trustguard.app.net

import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.JsonObject
import okhttp3.WebSocket
import pk.trustguard.tier1.Tier1Hit
import java.util.UUID

/** Server ack for one sent chat message (Tier-2 echo of Tier-1 results). */
data class AckInfo(
    val messageId: String,
    val hits: List<Tier1Hit>,
    val latencyMs: Double?,
    val crossChannelOtpArmed: Boolean?
)

/** Events delivered from [ChatSocketManager]; invoked on OkHttp reader threads. */
interface ChatSocketListener {
    fun onChatConnected()

    fun onChatDisconnected()

    /** Server confirmed the registration frame (identity + auth status). */
    fun onRegistered(peerName: String?, auth: String?) {}

    fun onIncoming(speaker: String, text: String, messageId: String, timestamp: Long?)

    fun onAck(info: AckInfo)

    /** Receipt from server: message was delivered to or read by the peer. */
    fun onReceipt(messageId: String, kind: String, user: String) {}
}

/**
 * Chat channel socket: ws://{host}/ws/chat/{session_id}
 *
 * On every (re)connect it first sends the register frame (device_id plus an
 * optional account token), then outbound messages as
 * {"type":"message","text","speaker","message_id"}.
 * Incoming relayed messages and tier-1 acks are forwarded to [listener].
 */
open class ChatSocketManager(
    url: String,
    private val deviceId: String,
    private val listener: ChatSocketListener,
    private val token: String? = null,
    /** Identity used as the outgoing speaker label (username when logged in). */
    private val speakerId: String = deviceId
) : ReconnectingSocket(url) {

    private val devicePrefix = UUID.randomUUID().toString().take(8)

    override fun onSocketOpen(ws: WebSocket) {
        val register = buildJsonObject {
            put("type", "register")
            put("device_id", deviceId)
            if (!token.isNullOrBlank()) put("token", token)
        }.toString()
        ws.send(register)
        flushPending()
        listener.onChatConnected()
    }

    /**
     * Sends a chat message. Returns the generated message id.
     * IDs are globally unique (device prefix + UUID) so history persistence
     * and delivery/read receipts never collide between users or reconnects.
     * The default speaker is this client's identity; the director panel passes "them".
     */
    fun sendMessage(text: String, speaker: String = speakerId): String {
        val messageId = "m_${devicePrefix}_${UUID.randomUUID().toString().take(12)}"
        val frame = buildJsonObject {
            put("type", "message")
            put("text", text)
            put("speaker", speaker)
            put("message_id", messageId)
        }.toString()
        sendText(frame)
        return messageId
    }

    /** Send a delivery receipt for a received message. */
    fun sendDeliveryReceipt(messageId: String) {
        sendText(buildJsonObject {
            put("type", "delivery_receipt")
            put("message_id", messageId)
        }.toString())
    }

    /** Send a read receipt for messages seen by the user. */
    fun sendReadReceipt(messageId: String) {
        sendText(buildJsonObject {
            put("type", "read_receipt")
            put("message_id", messageId)
        }.toString())
    }

    override fun onSocketText(text: String) {
        val obj = parseJsonObject(text) ?: return
        when (obj.optString("type")) {
            "registered" -> listener.onRegistered(obj.optString("peer_name"), obj.optString("auth"))
            "message" -> {
                val speaker = obj.optString("speaker") ?: return
                if (speaker.equals(speakerId, ignoreCase = true)) return // our own echo
                val body = obj.optString("text") ?: return
                val id = obj.optString("message_id").orEmpty()
                // Auto-acknowledge delivery for the sender.
                sendDeliveryReceipt(id)
                listener.onIncoming(speaker, body, id, obj.optLong("timestamp"))
            }
            "ack" -> {
                val messageId = obj.optString("message_id") ?: return
                val hits: List<Tier1Hit> = obj.array("tier1_hits")
                    ?.mapNotNull { element ->
                        val h = element as? JsonObject ?: return@mapNotNull null
                        val label = h.optString("type") ?: return@mapNotNull null
                        Tier1Hit(label, h.optInt("severity") ?: 0, h.optDouble("confidence") ?: 0.0)
                    }
                    ?: emptyList()
                listener.onAck(
                    AckInfo(
                        messageId = messageId,
                        hits = hits,
                        latencyMs = obj.optDouble("tier1_latency_ms"),
                        crossChannelOtpArmed = obj.optBoolean("cross_channel_otp_armed")
                    )
                )
            }
            "delivered_receipt", "read_receipt" -> {
                val messageId = obj.optString("message_id") ?: return
                val user = obj.optString("user") ?: return
                listener.onReceipt(messageId, obj.optString("type") ?: "receipt", user)
            }
        }
    }

    override fun onSocketClosed(code: Int, reason: String) {
        listener.onChatDisconnected()
    }
}
