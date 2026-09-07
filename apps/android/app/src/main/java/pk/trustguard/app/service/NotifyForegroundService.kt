package pk.trustguard.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import pk.trustguard.app.MainActivity
import pk.trustguard.app.data.SettingsStore
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.net.NotificationSocketManager
import pk.trustguard.app.net.toWsUrl
import pk.trustguard.app.notify.CallEventBus
import pk.trustguard.app.notify.NotifyChannels
import pk.trustguard.app.notify.cancelIncomingCallNotification
import pk.trustguard.app.notify.showIncomingCallNotification
import pk.trustguard.app.notify.showMessageNotification

/**
 * Always-on notification bridge. Holds the /ws/notifications/{user} socket
 * inside a lightweight foreground service so incoming calls and message
 * alerts still arrive when the activity is backgrounded, minimized, swiped
 * away, or the screen is locked (the same role FCM plays for WhatsApp, but
 * over our existing WebSocket — no new backend component required).
 *
 * The service posts the actual system notifications (full-screen incoming
 * call, message heads-up) and forwards events to a running UI via
 * [CallEventBus]. It posts no message content anywhere except the local
 * notification shade.
 */
class NotifyForegroundService : Service() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var socket: NotificationSocketManager? = null
    private var runningFor: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        NotifyChannels.createAll(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            teardown()
            return START_NOT_STICKY
        }
        scope.launch {
            val settings = SettingsStore.current(applicationContext)
            val username = settings.username
            if (username.isNullOrBlank()) {
                // Logged out (or never logged in) — nothing to listen for.
                teardown()
                return@launch
            }
            if (runningFor == username && socket != null) return@launch
            startInForeground()
            connectSocket(username, settings.baseUrl)
        }
        return START_STICKY
    }

    private fun connectSocket(username: String, baseUrl: String) {
        socket?.close()
        runningFor = username
        val appContext = applicationContext
        socket = NotificationSocketManager(
            url = toWsUrl(baseUrl, "/ws/notifications/$username"),
            username = username,
            onIncomingCall = { inviteId, fromUser, sessionId ->
                showIncomingCallNotification(appContext, inviteId, fromUser, sessionId, baseUrl)
                CallEventBus.emitIncoming(inviteId, fromUser, sessionId)
            },
            onCallAccepted = { inviteId, sessionId ->
                CallEventBus.emitAccepted(inviteId, sessionId)
            },
            onCallRejected = { inviteId ->
                cancelIncomingCallNotification(appContext, inviteId)
                CallEventBus.emitRejected(inviteId)
            },
            onNewMessage = { fromUser, sessionId, preview, messageId ->
                showMessageNotification(appContext, fromUser, sessionId, preview, baseUrl)
                // WhatsApp-style ✓✓: the message reached this device, so tell
                // the gateway it is DELIVERED even though the chat is closed
                // (read receipts only fire when the user actually opens it).
                if (messageId.isNotBlank()) {
                    scope.launch {
                        runCatching {
                            GatewayApi(baseUrl).markDelivered(messageId, username)
                        }
                    }
                }
            }
        ).also { it.connect() }
    }

    private fun startInForeground() {
        val notification = buildNotification()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
                )
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (e: Exception) {
            runCatching { startForeground(NOTIFICATION_ID, notification) }
                .onFailure { stopSelf() }
        }
    }

    private fun buildNotification(): Notification {
        val launchIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val contentIntent = PendingIntent.getActivity(
            this, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_notify_chat)
            .setContentTitle("R CHAT")
            .setContentText("Connected — you'll get calls and messages")
            .setOngoing(true)
            .setSilent(true)
            .setShowWhen(false)
            .setContentIntent(contentIntent)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Background connection",
            NotificationManager.IMPORTANCE_MIN
        ).apply {
            description = "Keeps R CHAT reachable for incoming calls and messages"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    private fun teardown() {
        socket?.close()
        socket = null
        runningFor = null
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    override fun onDestroy() {
        socket?.close()
        socket = null
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        const val CHANNEL_ID = "rchat_background"
        const val NOTIFICATION_ID = 43
        const val ACTION_STOP = "pk.trustguard.app.action.STOP_NOTIFY_SERVICE"

        /** Starts (or refreshes) the notification service. Safe to repeat. */
        fun start(context: Context) {
            val intent = Intent(context, NotifyForegroundService::class.java)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }

        /** Stops the service and drops the notification socket. */
        fun stop(context: Context) {
            val intent = Intent(context, NotifyForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            runCatching { context.startService(intent) }
        }
    }
}
