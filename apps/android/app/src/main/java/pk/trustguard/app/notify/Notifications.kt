package pk.trustguard.app.notify

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.media.AudioAttributes
import android.media.RingtoneManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import pk.trustguard.app.MainActivity

/** Intent extra keys shared between notifications, receivers and MainActivity. */
object NotifyExtras {
    const val ACTION_INCOMING_CALL = "pk.trustguard.app.action.INCOMING_CALL"
    const val ACTION_ACCEPT_CALL = "pk.trustguard.app.action.ACCEPT_CALL"
    const val ACTION_OPEN_CHAT = "pk.trustguard.app.action.OPEN_CHAT"

    const val KEY_INVITE_ID = "tg_invite_id"
    const val KEY_CALLER = "tg_caller"
    const val KEY_SESSION_ID = "tg_session_id"
    const val KEY_BASE_URL = "tg_base_url"
}

/** Notification channel ids. */
object NotifyChannels {
    const val CALLS = "rchat_calls"
    const val MESSAGES = "rchat_messages"

    fun createAll(context: Context) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val ringtone = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
            val calls = NotificationChannel(
                CALLS, "Incoming calls", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "R CHAT voice call invitations with accept / decline actions"
                enableVibration(true)
                vibrationPattern = longArrayOf(0, 800, 400, 800, 400, 800)
                lockscreenVisibility = android.app.Notification.VISIBILITY_PUBLIC
                if (ringtone != null) {
                    setSound(
                        ringtone,
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_NOTIFICATION_RINGTONE)
                            .build()
                    )
                }
            }
            val messages = NotificationChannel(
                MESSAGES, "Messages", NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "New R CHAT message notifications"
                enableVibration(true)
            }
            manager.createNotificationChannel(calls)
            manager.createNotificationChannel(messages)
        }
    }
}

private const val CALL_NOTIFY_BASE = 9000
private const val MESSAGE_NOTIFY_BASE = 9500

private fun activityIntent(context: Context, action: String, extras: Map<String, String>): PendingIntent {
    val intent = Intent(context, MainActivity::class.java).apply {
        setAction(action)
        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        extras.forEach { (k, v) -> putExtra(k, v) }
    }
    return PendingIntent.getActivity(
        context, action.hashCode(), intent,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )
}

/**
 * WhatsApp-style incoming call notification: ringtone + vibration, heads-up,
 * full-screen intent (shows over other apps / lock screen) and inline
 * Accept / Decline actions.
 */
fun showIncomingCallNotification(
    context: Context,
    inviteId: String,
    caller: String,
    sessionId: String,
    baseUrl: String
) {
    val id = CALL_NOTIFY_BASE + (inviteId.hashCode() and 0xFFF)

    // Tap / full-screen: opens the in-app incoming call UI.
    val fullScreen = activityIntent(
        context, NotifyExtras.ACTION_INCOMING_CALL, mapOf(
            NotifyExtras.KEY_INVITE_ID to inviteId,
            NotifyExtras.KEY_CALLER to caller,
            NotifyExtras.KEY_SESSION_ID to sessionId,
            NotifyExtras.KEY_BASE_URL to baseUrl
        )
    )

    val acceptAction = Intent(context, CallActionReceiver::class.java).apply {
        action = CallActionReceiver.ACTION_ACCEPT
        putExtra(NotifyExtras.KEY_INVITE_ID, inviteId)
        putExtra(NotifyExtras.KEY_CALLER, caller)
        putExtra(NotifyExtras.KEY_SESSION_ID, sessionId)
        putExtra(NotifyExtras.KEY_BASE_URL, baseUrl)
    }
    val acceptPending = PendingIntent.getBroadcast(
        context, id, acceptAction,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    val declineAction = Intent(context, CallActionReceiver::class.java).apply {
        action = CallActionReceiver.ACTION_DECLINE
        putExtra(NotifyExtras.KEY_INVITE_ID, inviteId)
        putExtra(NotifyExtras.KEY_BASE_URL, baseUrl)
    }
    val declinePending = PendingIntent.getBroadcast(
        context, id + 1, declineAction,
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
    )

    val notification = NotificationCompat.Builder(context, NotifyChannels.CALLS)
        .setSmallIcon(android.R.drawable.sym_action_call)
        .setContentTitle("Incoming R CHAT call")
        .setContentText("@$caller is calling you")
        .setStyle(NotificationCompat.BigTextStyle().bigText("@$caller is calling you — accept or decline"))
        .setPriority(NotificationCompat.PRIORITY_MAX)
        .setCategory(NotificationCompat.CATEGORY_CALL)
        .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
        .setOngoing(true)
        .setAutoCancel(false)
        .setFullScreenIntent(fullScreen, true)
        .setContentIntent(fullScreen)
        .addAction(android.R.drawable.sym_action_call, "Accept", acceptPending)
        .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Decline", declinePending)
        .build()

    runCatching { NotificationManagerCompat.from(context).notify(id, notification) }
}

/** Cancel the incoming-call notification (accept/decline/take in-app). */
fun cancelIncomingCallNotification(context: Context, inviteId: String) {
    val id = CALL_NOTIFY_BASE + (inviteId.hashCode() and 0xFFF)
    runCatching { NotificationManagerCompat.from(context).cancel(id) }
}

/** New-chat-message notification; tapping opens that conversation. */
fun showMessageNotification(
    context: Context,
    fromUser: String,
    sessionId: String,
    preview: String,
    baseUrl: String
) {
    val id = MESSAGE_NOTIFY_BASE + (sessionId.hashCode() and 0xFFF)
    val openChat = activityIntent(
        context, NotifyExtras.ACTION_OPEN_CHAT, mapOf(
            NotifyExtras.KEY_CALLER to fromUser,
            NotifyExtras.KEY_SESSION_ID to sessionId,
            NotifyExtras.KEY_BASE_URL to baseUrl
        )
    )
    val notification = NotificationCompat.Builder(context, NotifyChannels.MESSAGES)
        .setSmallIcon(android.R.drawable.sym_action_chat)
        .setContentTitle(fromUser)
        .setContentText(preview.ifBlank { "New message" })
        .setStyle(NotificationCompat.BigTextStyle().bigText(preview.ifBlank { "New message" }))
        .setPriority(NotificationCompat.PRIORITY_HIGH)
        .setCategory(NotificationCompat.CATEGORY_MESSAGE)
        .setAutoCancel(true)
        .setContentIntent(openChat)
        .build()
    runCatching { NotificationManagerCompat.from(context).notify(id, notification) }
}
