package pk.trustguard.app.service

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * Restarts the notification bridge after a device reboot so incoming calls
 * and messages can arrive before the user opens the app again. Android
 * exempts BOOT_COMPLETED from the background foreground-service start
 * restriction for the dataSync type; start() is failure-safe regardless.
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            NotifyForegroundService.start(context)
        }
    }
}
