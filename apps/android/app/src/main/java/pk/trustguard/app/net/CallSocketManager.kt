package pk.trustguard.app.net

import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.WebSocket

/** Events delivered from [CallSocketManager]; invoked on OkHttp reader threads. */
interface CallSocketListener {
    /** Server confirmed registration and reported the far-end peer id. */
    fun onRegistered(peerId: String?)

    /** Account token auth result (server sends auth_ok / auth_failed). */
    fun onAuthResult(ok: Boolean, peerName: String?) {}

    /** A binary frame of PCM16 16 kHz mono audio arrived from the peer. */
    fun onAudio(bytes: ByteArray)

    /** The peer sent an end/hang-up control event. */
    fun onPeerEnded()

    /** Both call peers are now connected — start the call timer. */
    fun onCallConnected() {}

    /** The transport went down. */
    fun onDisconnected()
}

/**
 * Call channel socket: ws://{host}/ws/call/{session_id}
 *
 * TEXT frames carry control JSON, BINARY frames carry PCM16/16 kHz/mono audio.
 * On connect it sends {"type":"control","event":"start","device_id":...}
 * (plus an optional account "token") and expects
 * {"type":"control","event":"registered","peer_id":...} back.
 * Reconnects are disabled: a dropped call stays dropped.
 */
class CallSocketManager(
    url: String,
    private val deviceId: String,
    private val listener: CallSocketListener,
    private val token: String? = null
) : ReconnectingSocket(url, autoReconnect = false) {

    override fun onSocketOpen(ws: WebSocket) {
        ws.send(
            buildJsonObject {
                put("type", "control")
                put("event", "start")
                put("device_id", deviceId)
                if (!token.isNullOrBlank()) put("token", token)
            }.toString()
        )
        flushPending()
    }

    override fun onSocketText(text: String) {
        val obj = parseJsonObject(text) ?: return
        if (obj.optString("type") != "control") return
        when (obj.optString("event")) {
            "registered" -> listener.onRegistered(obj.optString("peer_id"))
            "auth_ok" -> listener.onAuthResult(ok = true, peerName = obj.optString("peer_name"))
            "auth_failed" -> listener.onAuthResult(ok = false, peerName = null)
            "call_connected" -> listener.onCallConnected()
            "end", "ended", "hang_up", "hangup" -> listener.onPeerEnded()
        }
    }

    override fun onSocketBinary(bytes: ByteArray) {
        listener.onAudio(bytes)
    }

    override fun onSocketClosed(code: Int, reason: String) {
        listener.onDisconnected()
    }

    /** Streams one captured PCM chunk to the peer as a binary WS frame. */
    fun sendAudio(chunk: ByteArray) {
        if (chunk.isNotEmpty()) {
            sendBinary(chunk)
        }
    }

    /**
     * Graceful hang-up: sends {"type":"control","event":"end"} then closes
     * the socket for good.
     */
    fun endCall() {
        sendText(
            buildJsonObject {
                put("type", "control")
                put("event", "end")
            }.toString()
        )
        close()
    }
}
