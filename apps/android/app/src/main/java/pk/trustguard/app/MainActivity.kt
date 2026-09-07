package pk.trustguard.app

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import pk.trustguard.app.data.SettingsStore
import pk.trustguard.app.notify.CallEventBus
import pk.trustguard.app.notify.NotifyChannels
import pk.trustguard.app.notify.NotifyExtras
import pk.trustguard.app.notify.cancelIncomingCallNotification
import pk.trustguard.app.service.NotifyForegroundService
import pk.trustguard.app.ui.screens.CallScreen
import pk.trustguard.app.ui.screens.ChatScreen
import pk.trustguard.app.ui.screens.DirectorPanelScreen
import pk.trustguard.app.ui.screens.IncomingCallScreen
import pk.trustguard.app.ui.screens.LoginScreen
import pk.trustguard.app.ui.screens.MainScreen
import pk.trustguard.app.ui.screens.OutgoingCallScreen
import pk.trustguard.app.ui.screens.RegisterScreen
import pk.trustguard.app.ui.screens.SettingsScreen
import pk.trustguard.app.ui.screens.SignupScreen
import pk.trustguard.app.ui.theme.BrandGradient
import pk.trustguard.app.ui.theme.RChatTheme

/** A navigation request delivered via an Intent (notification tap / full-screen intent). */
data class NotifyNavRequest(
    val action: String,
    val inviteId: String = "",
    val caller: String = "",
    val sessionId: String = "",
    val baseUrl: String = ""
)

/**
 * Single-activity Compose app. Routes:
 * login / signup / register (demo device mode) / main / chat/{sessionId}/{peerId}
 * / call/{sessionId}/{peerId} / outgoing_call / incoming_call / director / settings
 *
 * The start destination depends on the persisted session: a saved account
 * token boots straight into the main hub, otherwise the login screen shows.
 */
class MainActivity : ComponentActivity() {

    /** Latest notification-driven navigation request, consumed by AppNavigation. */
    val notifyRequest = mutableStateOf<NotifyNavRequest?>(null)

    private val notificationPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotifyChannels.createAll(this)
        requestNotificationPermission()
        captureNotifyIntent(intent)
        setContent {
            RChatTheme {
                val navController = rememberNavController()
                AppNavigation(navController = navController)
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        captureNotifyIntent(intent)
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) {
            notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
    }

    /** Translates notification intents into navigation requests for the Compose layer. */
    private fun captureNotifyIntent(intent: Intent?) {
        val action = intent?.action ?: return
        when (action) {
            NotifyExtras.ACTION_INCOMING_CALL -> {
                // Full-screen intent landed us here, possibly from the lock screen.
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
                    setShowWhenLocked(true)
                    setTurnScreenOn(true)
                }
                notifyRequest.value = NotifyNavRequest(
                    action = NotifyExtras.ACTION_INCOMING_CALL,
                    inviteId = intent.getStringExtra(NotifyExtras.KEY_INVITE_ID).orEmpty(),
                    caller = intent.getStringExtra(NotifyExtras.KEY_CALLER).orEmpty(),
                    sessionId = intent.getStringExtra(NotifyExtras.KEY_SESSION_ID).orEmpty(),
                    baseUrl = intent.getStringExtra(NotifyExtras.KEY_BASE_URL).orEmpty()
                )
            }
            NotifyExtras.ACTION_ACCEPT_CALL -> {
                notifyRequest.value = NotifyNavRequest(
                    action = NotifyExtras.ACTION_ACCEPT_CALL,
                    inviteId = intent.getStringExtra(NotifyExtras.KEY_INVITE_ID).orEmpty(),
                    caller = intent.getStringExtra(NotifyExtras.KEY_CALLER).orEmpty(),
                    sessionId = intent.getStringExtra(NotifyExtras.KEY_SESSION_ID).orEmpty(),
                    baseUrl = intent.getStringExtra(NotifyExtras.KEY_BASE_URL).orEmpty()
                )
            }
            NotifyExtras.ACTION_OPEN_CHAT -> {
                notifyRequest.value = NotifyNavRequest(
                    action = NotifyExtras.ACTION_OPEN_CHAT,
                    caller = intent.getStringExtra(NotifyExtras.KEY_CALLER).orEmpty(),
                    sessionId = intent.getStringExtra(NotifyExtras.KEY_SESSION_ID).orEmpty(),
                    baseUrl = intent.getStringExtra(NotifyExtras.KEY_BASE_URL).orEmpty()
                )
            }
        }
    }
}

@Composable
private fun AppNavigation(navController: androidx.navigation.NavHostController) {
    val context = LocalContext.current
    val activity = context as? MainActivity
    val settings by remember(context) { SettingsStore.flow(context) }
        .collectAsState(initial = null)
    val loaded = settings

    var incomingCall by remember { mutableStateOf<Triple<String, String, String>?>(null) }

    // The foreground service owns the persistent notification socket, so calls
    // and messages keep arriving when the activity is backgrounded, swiped
    // away, or the screen is locked. The UI only starts/stops the service and
    // consumes its events through CallEventBus (one socket = no duplicates).
    LaunchedEffect(loaded?.username, loaded?.baseUrl) {
        if (!loaded?.username.isNullOrBlank() && !loaded?.baseUrl.isNullOrBlank()) {
            NotifyForegroundService.start(context)
        } else if (loaded != null) {
            // Logged out (or logged into a blank identity) — stop listening.
            NotifyForegroundService.stop(context)
        }
    }

    // In-app ringing UI when a call arrives while the app is running (the
    // service posts the system notification either way).
    LaunchedEffect(Unit) {
        CallEventBus.incoming.collect { event ->
            incomingCall = Triple(event.inviteId, event.fromUser, event.sessionId)
            navController.navigate(
                "incoming_call/${event.inviteId}/${event.fromUser}/${event.sessionId}"
            ) { launchSingleTop = true }
        }
    }

    // The peer declined our call, or the caller cancelled an invite we're
    // currently ringing about.
    LaunchedEffect(Unit) {
        CallEventBus.rejected.collect { event ->
            val current = incomingCall
            if (current != null && current.first == event.inviteId) {
                incomingCall = null
                cancelIncomingCallNotification(context, event.inviteId)
                navController.popBackStack()
            }
        }
    }

    if (loaded == null) {
        BrandSplash()
        return
    }

    // Notification-driven navigation (full-screen incoming call, accept from
    // the notification shade, tap on a message notification).
    LaunchedEffect(activity?.notifyRequest?.value) {
        val request = activity?.notifyRequest?.value ?: return@LaunchedEffect
        activity.notifyRequest.value = null
        when (request.action) {
            NotifyExtras.ACTION_INCOMING_CALL -> {
                if (request.inviteId.isNotBlank()) {
                    incomingCall = Triple(request.inviteId, request.caller, request.sessionId)
                    navController.navigate(
                        "incoming_call/${request.inviteId}/${request.caller}/${request.sessionId}"
                    ) { launchSingleTop = true }
                }
            }
            NotifyExtras.ACTION_ACCEPT_CALL -> {
                if (request.sessionId.isNotBlank()) {
                    incomingCall = null
                    // Clear any incoming-call UI, then go straight into the live call.
                    navController.popBackStack(Routes.MAIN, false)
                    navController.navigate(
                        "call/${request.sessionId}/${request.caller}?name=${request.caller}"
                    ) { launchSingleTop = true }
                }
            }
            NotifyExtras.ACTION_OPEN_CHAT -> {
                if (request.sessionId.isNotBlank()) {
                    navController.popBackStack(Routes.MAIN, false)
                    navController.navigate(
                        "chat/${request.sessionId}/${request.caller}?name=${request.caller}"
                    ) { launchSingleTop = true }
                }
            }
        }
    }

    NavHost(
        navController = navController,
        startDestination = if (loaded.isLoggedIn) Routes.MAIN else Routes.LOGIN
    ) {
        composable(Routes.LOGIN) {
            LoginScreen(
                onLoggedIn = {
                    navController.navigate(Routes.MAIN) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onOpenSignup = { navController.navigate(Routes.SIGNUP) },
                onOpenDemoMode = {
                    navController.navigate(Routes.REGISTER) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.SIGNUP) {
            SignupScreen(
                onSignedUp = {
                    navController.navigate(Routes.MAIN) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onBack = { navController.popBackStack() }
            )
        }

        composable(Routes.REGISTER) {
            RegisterScreen(
                onDone = {
                    navController.navigate(Routes.MAIN) {
                        popUpTo(Routes.REGISTER) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.MAIN) {
            MainScreen(
                onOpenChat = { sessionId, peerId, peerName ->
                    navController.navigate("chat/$sessionId/$peerId?name=$peerName")
                },
                onStartOutgoingCall = { inviteId, sessionId, peerId, peerName ->
                    navController.navigate(
                        "outgoing_call/$inviteId/$sessionId/$peerId?name=$peerName"
                    )
                },
                onOpenSettings = { navController.navigate(Routes.SETTINGS) },
                onLogout = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = "outgoing_call/{inviteId}/{sessionId}/{peerId}?name={name}",
            arguments = listOf(
                navArgument("inviteId") { type = NavType.StringType },
                navArgument("sessionId") { type = NavType.StringType },
                navArgument("peerId") { type = NavType.StringType },
                navArgument("name") { type = NavType.StringType; defaultValue = "" }
            )
        ) { entry ->
            val inviteId = entry.arguments?.getString("inviteId").orEmpty()
            val sessionId = entry.arguments?.getString("sessionId").orEmpty()
            val peerId = entry.arguments?.getString("peerId").orEmpty()
            val peerName = entry.arguments?.getString("name")?.takeIf { it.isNotBlank() } ?: peerId
            OutgoingCallScreen(
                inviteId = inviteId,
                sessionId = sessionId,
                peerName = peerName,
                onAccepted = { liveSession ->
                    // Picked up -> drop the ringing screen, start audio + timer.
                    navController.popBackStack()
                    navController.navigate("call/$liveSession/$peerId?name=$peerName")
                },
                onCancelled = { navController.popBackStack() }
            )
        }

        composable(
            route = "chat/{sessionId}/{peerId}?name={name}",
            arguments = listOf(
                navArgument("sessionId") { type = NavType.StringType },
                navArgument("peerId") { type = NavType.StringType },
                navArgument("name") { type = NavType.StringType; defaultValue = "" }
            )
        ) { entry ->
            ChatScreen(
                sessionId = entry.arguments?.getString("sessionId").orEmpty(),
                peerId = entry.arguments?.getString("peerId").orEmpty(),
                peerName = entry.arguments?.getString("name").orEmpty(),
                onBack = { navController.popBackStack() }
            )
        }

        composable(
            route = "call/{sessionId}/{peerId}?name={name}",
            arguments = listOf(
                navArgument("sessionId") { type = NavType.StringType },
                navArgument("peerId") { type = NavType.StringType },
                navArgument("name") { type = NavType.StringType; defaultValue = "" }
            )
        ) { entry ->
            CallScreen(
                sessionId = entry.arguments?.getString("sessionId").orEmpty(),
                peerId = entry.arguments?.getString("peerId").orEmpty(),
                peerName = entry.arguments?.getString("name").orEmpty(),
                onEnded = { navController.popBackStack() }
            )
        }

        composable(Routes.DIRECTOR) {
            DirectorPanelScreen(onBack = { navController.popBackStack() })
        }

        composable(Routes.SETTINGS) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
                onOpenDirector = { navController.navigate(Routes.DIRECTOR) },
                onLoggedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = "incoming_call/{inviteId}/{caller}/{sessionId}",
            arguments = listOf(
                navArgument("inviteId") { type = NavType.StringType },
                navArgument("caller") { type = NavType.StringType },
                navArgument("sessionId") { type = NavType.StringType }
            )
        ) { entry ->
            val inviteId = entry.arguments?.getString("inviteId").orEmpty()
            val caller = entry.arguments?.getString("caller").orEmpty()
            val sessionId = entry.arguments?.getString("sessionId").orEmpty()
            val api = remember(loaded.baseUrl) { pk.trustguard.app.net.GatewayApi(loaded.baseUrl) }

            IncomingCallScreen(
                callerName = caller,
                callerUsername = caller,
                onAccept = {
                    cancelIncomingCallNotification(context, inviteId)
                    CoroutineScope(Dispatchers.IO).launch { api.acceptCall(inviteId) }
                    incomingCall = null
                    navController.popBackStack()
                    navController.navigate("call/$sessionId/$caller?name=$caller")
                },
                onReject = {
                    cancelIncomingCallNotification(context, inviteId)
                    CoroutineScope(Dispatchers.IO).launch { api.rejectCall(inviteId) }
                    incomingCall = null
                    navController.popBackStack()
                }
            )
        }
    }
}

@Composable
private fun BrandSplash() {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(BrandGradient),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    Icons.Filled.Shield,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(56.dp)
                )
                Text(
                    text = "R CHAT",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
            }
        }
    }
}

private object Routes {
    const val LOGIN = "login"
    const val SIGNUP = "signup"
    const val REGISTER = "register"
    const val MAIN = "main"
    const val DIRECTOR = "director"
    const val SETTINGS = "settings"
}
