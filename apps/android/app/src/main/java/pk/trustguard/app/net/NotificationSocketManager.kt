package pk.trustguard.app.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

/**
 * Persistent notification socket for incoming calls and messages.
 * Connects to /ws/notifications/{username} and forwards events to the app.
 */
class NotificationSocketManager(
    private val url: String,
    private val username: String,
    private val onIncomingCall: (inviteId: String, fromUser: String, sessionId: String) -> Unit,
    private val onCallAccepted: (inviteId: String, sessionId: String) -> Unit = { _, _ -> },
    private val onCallRejected: (inviteId: String) -> Unit = { _ -> },
    private val onNewMessage: (fromUser: String, sessionId: String, preview: String, messageId: String) -> Unit = { _, _, _, _ -> }
) {
    private val client = OkHttpClient.Builder()
        .pingInterval(20, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var socket: WebSocket? = null
    private var connected = false

    fun connect() {
        if (connected) return
        val request = Request.Builder().url(url).build()
        socket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                connected = true
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val obj = parseJsonObject(text) ?: return
                when (obj.optString("type")) {
                    "incoming_call" -> {
                        val inviteId = obj.optString("invite_id") ?: return
                        val fromUser = obj.optString("from_user") ?: return
                        val sessionId = obj.optString("session_id") ?: return
                        onIncomingCall(inviteId, fromUser, sessionId)
                    }
                    "call_accepted" -> {
                        val inviteId = obj.optString("invite_id") ?: return
                        val sessionId = obj.optString("session_id") ?: return
                        onCallAccepted(inviteId, sessionId)
                    }
                    "call_rejected" -> {
                        val inviteId = obj.optString("invite_id") ?: return
                        onCallRejected(inviteId)
                    }
                    "new_message" -> {
                        val fromUser = obj.optString("from_user") ?: return
                        val sessionId = obj.optString("session_id") ?: return
                        val preview = obj.optString("text").orEmpty()
                        val messageId = obj.optString("message_id").orEmpty()
                        onNewMessage(fromUser, sessionId, preview, messageId)
                    }
                }
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                connected = false
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                connected = false
                reconnect()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                connected = false
                reconnect()
            }
        })

        // Keepalive pings
        scope.launch {
            while (isActive) {
                delay(30_000)
                socket?.send("ping")
            }
        }
    }

    private fun reconnect() {
        scope.launch {
            delay(3_000)
            connect()
        }
    }

    fun close() {
        socket?.close(1000, "closing")
        socket = null
        scope.cancel()
    }
}
