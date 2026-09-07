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
import pk.trustguard.app.MainActivity

/**
 * Foreground service started while a call is in progress. It performs no audio
 * itself (the activity owns the AudioEngine) — its sole purpose is keeping the
 * process alive so call audio streaming and live scam analysis survive the app
 * being backgrounded.
 *
 * Notification channel "calls" is LOW importance (silent) so an active call
 * never disturbs the user.
 */
class CallForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        return START_STICKY
    }

    private fun startInForeground() {
        val notification = buildNotification()
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                startForeground(
                    NOTIFICATION_ID,
                    notification,
                    ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
                )
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
        } catch (e: Exception) {
            // Typed start can be denied (e.g. mic permission revoked mid-call);
            // fall back to a plain foreground start so the 5s deadline is met.
            try {
                startForeground(NOTIFICATION_ID, notification)
            } catch (ignored: Exception) {
                stopSelf()
            }
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
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("R CHAT")
            .setContentText("Call in progress · Scam protection active")
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(contentIntent)
            .setCategory(NotificationCompat.CATEGORY_CALL)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun createChannel() {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Calls",
            NotificationManager.IMPORTANCE_LOW
        ).apply {
            description = "Ongoing call status and scam protection indicator"
            setShowBadge(false)
        }
        manager.createNotificationChannel(channel)
    }

    companion object {
        const val CHANNEL_ID = "calls"
        const val NOTIFICATION_ID = 42
        const val ACTION_STOP = "pk.trustguard.app.action.STOP_CALL_SERVICE"

        /** Starts the call foreground service (safe to call repeatedly). */
        fun start(context: Context) {
            val intent = Intent(context, CallForegroundService::class.java)
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }

        /** Stops the call foreground service and removes its notification. */
        fun stop(context: Context) {
            val intent = Intent(context, CallForegroundService::class.java).apply {
                action = ACTION_STOP
            }
            runCatching { ContextCompat.startForegroundService(context, intent) }
        }
    }
}
