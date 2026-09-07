package pk.trustguard.app.net

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/**
 * Base class for the app's WebSocket managers.
 *
 * Features:
 * - automatic reconnect with exponential backoff (1 s doubling up to 15 s),
 *   reset on every successful open; disabled after [close] or when
 *   [autoReconnect] is false;
 * - a single internal coroutine scope used for reconnect scheduling and
 *   subclass keepalive loops, cancelled in [close];
 * - thread-safe [sendText]/[sendBinary] helpers usable from any thread.
 *
 * Instances are single-use: once [close] has been called, create a new one.
 */
abstract class ReconnectingSocket(
    private val url: String,
    private val autoReconnect: Boolean = true
) {

    companion object {
        private const val BASE_BACKOFF_MS = 1_000L
        private const val MAX_BACKOFF_MS = 15_000L
        private const val MAX_BACKOFF_SHIFT = 4 // 1000 << 4 = 16000 -> clamped to 15000
    }

    protected val scope: CoroutineScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    @Volatile
    var isConnected: Boolean = false
        private set

    private val manualClose = AtomicBoolean(false)
    private val attempts = AtomicInteger(0)
    private var webSocket: WebSocket? = null

    /**
     * Outbound text frames queued while the socket is down (or before the
     * subclass handshake completes). Flushed by [flushPending] so messages
     * typed during a brief network blip are never silently lost.
     */
    private val pendingText = ConcurrentLinkedQueue<String>()

    /** True once the subclass handshake finished and queued frames may flow. */
    @Volatile
    protected var readyForSend: Boolean = false

    /** Opens the socket. Safe to call again after an unexpected drop. */
    fun connect() {
        manualClose.set(false)
        openSocket()
    }

    private fun openSocket() {
        val request = Request.Builder().url(url).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isConnected = true
                attempts.set(0)
                readyForSend = false
                this@ReconnectingSocket.onSocketOpen(ws)
            }

            override fun onMessage(ws: WebSocket, text: String) {
                runCatching { this@ReconnectingSocket.onSocketText(text) }
            }

            override fun onMessage(ws: WebSocket, bytes: ByteString) {
                runCatching { this@ReconnectingSocket.onSocketBinary(bytes.toByteArray()) }
            }

            override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                ws.close(code, reason)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                isConnected = false
                transportDown(code, reason)
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                transportDown(-1, t.message ?: "connection failure")
            }
        })
    }

    private fun transportDown(code: Int, reason: String) {
        runCatching { onSocketClosed(code, reason) }
        if (!manualClose.get() && autoReconnect) {
            scheduleReconnect()
        }
    }

    private fun scheduleReconnect() {
        if (manualClose.get()) return
        val backoffMs = minOf(
            BASE_BACKOFF_MS shl attempts.getAndIncrement().coerceAtMost(MAX_BACKOFF_SHIFT),
            MAX_BACKOFF_MS
        )
        scope.launch {
            delay(backoffMs)
            if (!manualClose.get() && !isConnected) {
                openSocket()
            }
        }
    }

    fun sendText(text: String): Boolean {
        val ws = webSocket
        if (ws == null || !isConnected || !readyForSend) {
            pendingText.offer(text)
            return true // queued; will be flushed after (re)connect + handshake
        }
        return try {
            ws.send(text)
        } catch (_: Exception) {
            pendingText.offer(text)
            true
        }
    }

    /**
     * Subclasses call this after their handshake frame (e.g. register) has
     * been sent, so frames queued while offline are delivered in order.
     */
    protected fun flushPending() {
        readyForSend = true
        val ws = webSocket ?: return
        while (true) {
            val queued = pendingText.poll() ?: break
            try {
                ws.send(queued)
            } catch (_: Exception) {
                pendingText.offer(queued)
                break
            }
        }
    }

    fun sendBinary(bytes: ByteArray): Boolean {
        val ws = webSocket ?: return false
        return try {
            ws.send(bytes.toByteString())
        } catch (_: Exception) {
            false
        }
    }

    /**
     * Permanently closes the socket and cancels all scheduled reconnects /
     * keepalive loops. Idempotent; the instance must not be reused afterwards.
     */
    fun close() {
        if (!manualClose.compareAndSet(false, true)) return
        runCatching { onBeforeClose() }
        isConnected = false
        runCatching { webSocket?.close(1000, "client closing") }
        runCatching { webSocket?.cancel() }
        webSocket = null
        scope.cancel()
    }

    /** OkHttp client shared by all sockets; overridable for tests. */
    protected open val client: OkHttpClient = OkHttpClient()

    /** Invoked right before teardown on [close]; subclasses may flush state here. */
    protected open fun onBeforeClose() {}

    /** Socket is open; subclasses must perform their handshake (e.g. register frame). */
    protected abstract fun onSocketOpen(ws: WebSocket)

    /** A text frame arrived (control JSON / chat JSON / risk JSON). */
    protected open fun onSocketText(text: String) {}

    /** A binary frame arrived (call audio PCM16 chunks). */
    protected open fun onSocketBinary(bytes: ByteArray) {}

    /** The socket went down (failure or closed), before any reconnect decision. */
    protected open fun onSocketClosed(code: Int, reason: String) {}
}
