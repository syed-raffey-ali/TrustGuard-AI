package pk.trustguard.app.notify

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import pk.trustguard.app.MainActivity
import pk.trustguard.app.net.GatewayApi

/**
 * Handles the Accept / Decline actions on the incoming-call notification so
 * the user can answer without opening the app first.
 */
class CallActionReceiver : BroadcastReceiver() {

    companion object {
        const val ACTION_ACCEPT = "pk.trustguard.app.receiver.ACCEPT_CALL"
        const val ACTION_DECLINE = "pk.trustguard.app.receiver.DECLINE_CALL"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val inviteId = intent.getStringExtra(NotifyExtras.KEY_INVITE_ID) ?: return
        val baseUrl = intent.getStringExtra(NotifyExtras.KEY_BASE_URL) ?: return
        val caller = intent.getStringExtra(NotifyExtras.KEY_CALLER).orEmpty()
        val sessionId = intent.getStringExtra(NotifyExtras.KEY_SESSION_ID).orEmpty()

        cancelIncomingCallNotification(context, inviteId)

        val pendingResult = goAsync()
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val api = GatewayApi(baseUrl)
                if (intent.action == ACTION_ACCEPT) {
                    val accepted = api.acceptCall(inviteId).getOrNull()
                    val resolvedSession = accepted?.sessionId?.takeIf { it.isNotBlank() } ?: sessionId
                    // Hand over to the activity which navigates into the call.
                    val openCall = Intent(context, MainActivity::class.java).apply {
                        action = NotifyExtras.ACTION_ACCEPT_CALL
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                        putExtra(NotifyExtras.KEY_INVITE_ID, inviteId)
                        putExtra(NotifyExtras.KEY_CALLER, caller)
                        putExtra(NotifyExtras.KEY_SESSION_ID, resolvedSession)
                        putExtra(NotifyExtras.KEY_BASE_URL, baseUrl)
                    }
                    context.startActivity(openCall)
                } else {
                    api.rejectCall(inviteId)
                }
            } finally {
                pendingResult.finish()
            }
        }
    }
}
