package pk.trustguard.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.VolumeOff
import androidx.compose.material.icons.automirrored.filled.VolumeUp
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.audio.AudioEngine
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.CallSocketListener
import pk.trustguard.app.net.CallSocketManager
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.net.RiskSocketManager
import pk.trustguard.app.net.RiskState
import pk.trustguard.app.net.toWsUrl
import pk.trustguard.app.service.CallForegroundService
import pk.trustguard.app.ui.components.ScamAlertBanner
import pk.trustguard.app.ui.components.ScamAlertState
import pk.trustguard.app.ui.components.ScamAlertWatcher
import pk.trustguard.app.ui.components.InitialsAvatar
import pk.trustguard.app.ui.components.ShieldIndicator
import pk.trustguard.app.ui.components.showToast
import pk.trustguard.app.ui.theme.CallScreenGradient
import pk.trustguard.app.ui.theme.DangerRed

/**
 * R CHAT voice call screen: full-screen premium dark gradient, live PCM audio
 * over the call WebSocket, and the LIVE SCAM DETECTION system:
 *
 *  - risk WebSocket drives a dismissible alert banner for band >= medium
 *    (amber / orange / red) with human-readable reasons and the top safe action;
 *  - new alerts vibrate (waveform for high/critical, single pulse for medium);
 *  - "I've verified this contact" dismisses the banner until the band escalates
 *    and reports the dismissal to the gateway;
 *  - a shield indicator in the header shows the current protection state;
 *  - a microphone foreground service keeps the process alive during calls.
 */
@Composable
fun CallScreen(
    sessionId: String,
    peerId: String,
    peerName: String? = null,
    onEnded: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()

    // ------------------------------------------------------------- permissions
    fun hasPermission(permission: String): Boolean =
        ActivityCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED

    var micPermissionGranted by remember {
        mutableStateOf(hasPermission(Manifest.permission.RECORD_AUDIO))
    }
    var permissionRequested by rememberSaveable { mutableStateOf(false) }
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        micPermissionGranted = grants[Manifest.permission.RECORD_AUDIO] == true
    }

    LaunchedEffect(Unit) {
        if (!permissionRequested) {
            permissionRequested = true
            val wanted = mutableListOf(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                !hasPermission(Manifest.permission.POST_NOTIFICATIONS)
            ) {
                wanted += Manifest.permission.POST_NOTIFICATIONS
            }
            if (!micPermissionGranted || wanted.size > 1) {
                permissionLauncher.launch(wanted.toTypedArray())
            }
        }
    }

    // ------------------------------------------------------------- call state
    var connected by remember { mutableStateOf(false) }
    /** True once BOTH peers are on the call socket — the timer starts here. */
    var callConnected by remember { mutableStateOf(false) }
    var peerLabel by rememberSaveable { mutableStateOf(peerName?.takeIf { it.isNotBlank() } ?: peerId) }
    var risk by remember { mutableStateOf(RiskState.EMPTY) }
    // Live captions of the remote speaker, streamed from the gateway's STT.
    var captions by remember { mutableStateOf(listOf<String>()) }
    val alertState = remember { ScamAlertState() }
    var ended by remember { mutableStateOf(false) }
    var muted by remember { mutableStateOf(false) }
    var speakerOn by remember { mutableStateOf(false) }
    var callSeconds by remember { mutableIntStateOf(0) }
    var callManager by remember { mutableStateOf<CallSocketManager?>(null) }
    var engineRef by remember { mutableStateOf<AudioEngine?>(null) }
    var riskSocketRef by remember { mutableStateOf<RiskSocketManager?>(null) }

    // The device identity used for WS registration: account-backed when logged
    // in, otherwise the legacy device_id (demo mode fallback).
    val wsIdentity = settings.username ?: settings.deviceId

    // Call timer ticks only once both sides are actually connected.
    LaunchedEffect(callConnected) {
        if (callConnected) {
            callSeconds = 0
            while (isActive) {
                delay(1_000)
                callSeconds += 1
            }
        }
    }

    // Keep the process alive with a microphone foreground service during calls.
    LaunchedEffect(connected, micPermissionGranted, ended) {
        if (connected && micPermissionGranted && !ended) {
            CallForegroundService.start(context)
        }
    }
    DisposableEffect(Unit) {
        onDispose { CallForegroundService.stop(context) }
    }

    // Live scam alert vibration trigger — VICTIM-ONLY.
    // Authoritative routing comes from the server (risk.alertTargets = the
    // participants who did NOT send the flagged content). Fallback heuristic:
    // if there are recent captions from the other person, I'm receiving their
    // words (potential victim); if I'm the only one speaking, suppress.
    val myUsername = settings.username?.lowercase()
    val iAmLikelyVictim = if (risk.alertTargets.isNotEmpty()) {
        myUsername != null && myUsername in risk.alertTargets
    } else {
        captions.isNotEmpty()
    }
    ScamAlertWatcher(risk = risk, alertState = alertState, enabled = iAmLikelyVictim)

    // Speaker routing follows the toggle.
    LaunchedEffect(speakerOn) {
        engineRef?.setLoudspeaker(speakerOn)
    }

    fun finishCall() {
        if (ended) return
        ended = true
        scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    GatewayApi(settings.baseUrl).endSession(sessionId)
                }
            }
            callManager?.endCall()
            onEnded()
        }
    }

    fun dismissAlert() {
        riskSocketRef?.sendAlertDismissed("user_verified")
        alertState.dismissAt(pk.trustguard.app.ui.components.bandSeverity(risk.band))
    }

    // ------------------------------------------------------------- audio + sockets
    DisposableEffect(micPermissionGranted, wsIdentity, settings.baseUrl, sessionId) {
        val identity = wsIdentity
        var engine: AudioEngine? = null
        var manager: CallSocketManager? = null
        var riskSocket: RiskSocketManager? = null
        if (micPermissionGranted && identity != null && sessionId.isNotBlank()) {
            engine = AudioEngine(context.applicationContext) { chunk ->
                if (!muted) manager?.sendAudio(chunk)
            }
            manager = CallSocketManager(
                url = toWsUrl(settings.baseUrl, "/ws/call/$sessionId"),
                deviceId = identity,
                token = settings.token,
                listener = object : CallSocketListener {
                    override fun onRegistered(peerId: String?) {
                        connected = true
                        // Only fall back to the server-assigned peer id when no
                        // friendly peer name was passed in via navigation.
                        peerId?.let { id ->
                            if (peerName.isNullOrBlank()) peerLabel = id
                        }
                    }

                    override fun onCallConnected() {
                        callConnected = true
                    }

                    override fun onAuthResult(ok: Boolean, peerName: String?) {
                        // auth_ok carries OUR OWN username (server echo), so it
                        // never replaces the remote peer label.
                    }

                    override fun onAudio(bytes: ByteArray) {
                        // Remote audio flowing means the call is live even if
                        // the call_connected control frame was missed.
                        if (!callConnected) callConnected = true
                        engine?.playChunk(bytes)
                    }

                    override fun onPeerEnded() {
                        showToast(context, "Call ended by the other side")
                        finishCall()
                    }

                    override fun onDisconnected() {
                        connected = false
                        callConnected = false
                    }
                }
            )
            riskSocket = RiskSocketManager(
                url = toWsUrl(settings.baseUrl, "/ws/session/$sessionId/risk"),
                onRisk = { state -> risk = state },
                onTranscript = { speaker, text, username ->
                    // Show what the OTHER side is saying — the audio the
                    // detection pipeline is scoring live. Prefer the
                    // server-resolved username; fall back to the speaker
                    // label for anonymous peers.
                    val mine = settings.username
                    val fromOther = when {
                        username.isNotBlank() && !mine.isNullOrBlank() ->
                            !username.equals(mine, ignoreCase = true)
                        else -> speaker != "me"
                    }
                    if (fromOther) {
                        captions = (captions + text).takeLast(3)
                    }
                }
            )

            manager.connect()
            riskSocket.connect()
            engine.start()
            engine.setLoudspeaker(speakerOn)
            callManager = manager
            engineRef = engine
            riskSocketRef = riskSocket
        }
        onDispose {
            engine?.stop()
            manager?.close()
            riskSocket?.close()
            if (callManager === manager) callManager = null
            if (engineRef === engine) engineRef = null
            if (riskSocketRef === riskSocket) riskSocketRef = null
        }
    }

    // ------------------------------------------------------------- UI
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(CallScreenGradient)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = 24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Header: shield / protection indicator + privacy notice.
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                ShieldIndicator(band = risk.band, darkSurface = true)
                Spacer(Modifier.weight(1f))
                Surface(
                    shape = CircleShape,
                    color = Color.White.copy(alpha = 0.10f)
                ) {
                    Text(
                        text = "This call is being analysed",
                        style = MaterialTheme.typography.labelSmall,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFFB9E8DF),
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                    )
                }
            }

            Spacer(Modifier.weight(0.7f))

            // Peer identity.
            InitialsAvatar(name = peerLabel, size = 104.dp)
            Spacer(Modifier.height(20.dp))
            Text(
                text = peerLabel,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = when {
                    ended -> "Call ended"
                    callConnected -> formatCallDuration(callSeconds)
                    connected -> "Waiting for other side…"
                    else -> "Connecting…"
                },
                style = MaterialTheme.typography.titleMedium,
                color = if (callConnected) Color(0xFF9CE5DA) else Color(0xFFB9E8DF)
            )
            if (!callConnected && !ended) {
                Spacer(Modifier.height(10.dp))
                CircularProgressIndicator(
                    modifier = Modifier.size(22.dp),
                    strokeWidth = 2.dp,
                    color = Color(0xFF9CE5DA)
                )
            }

            Spacer(Modifier.height(18.dp))

            // THE live scam alert banner — only show if I'm likely the victim.
            if (iAmLikelyVictim) {
                ScamAlertBanner(
                    risk = risk,
                    alertState = alertState,
                    onDismiss = ::dismissAlert,
                    onEndCall = ::finishCall,
                    modifier = Modifier.fillMaxWidth()
                )
            }

            // Live transcript: the remote speaker's words as fast-whisper
            // transcribes them on the gateway (visible proof of detection).
            if (captions.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = Color.White.copy(alpha = 0.08f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(Modifier.padding(horizontal = 14.dp, vertical = 10.dp)) {
                        Text(
                            text = "Live transcript",
                            style = MaterialTheme.typography.labelSmall,
                            fontWeight = FontWeight.Medium,
                            color = Color(0xFF9CE5DA)
                        )
                        Spacer(Modifier.height(4.dp))
                        for (line in captions) {
                            Text(
                                text = line,
                                style = MaterialTheme.typography.bodySmall,
                                color = Color.White.copy(alpha = 0.92f),
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }
            }

            Spacer(Modifier.weight(1f))

            // Call controls.
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 36.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                CallControlButton(
                    icon = if (muted) Icons.Filled.MicOff else Icons.Filled.Mic,
                    label = if (muted) "Unmute" else "Mute",
                    active = muted,
                    enabled = connected && !ended
                ) { muted = !muted }

                // End call: prominent red circle.
                Surface(
                    onClick = ::finishCall,
                    enabled = !ended,
                    shape = CircleShape,
                    color = DangerRed,
                    modifier = Modifier.size(74.dp)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(
                            Icons.Filled.CallEnd,
                            contentDescription = "End call",
                            tint = Color.White,
                            modifier = Modifier.size(32.dp)
                        )
                    }
                }

                CallControlButton(
                    icon = if (speakerOn) Icons.AutoMirrored.Filled.VolumeUp else Icons.AutoMirrored.Filled.VolumeOff,
                    label = "Speaker",
                    active = speakerOn,
                    enabled = connected && !ended
                ) { speakerOn = !speakerOn }
            }
        }

        if (!micPermissionGranted) {
            Surface(
                color = Color.Black.copy(alpha = 0.55f),
                modifier = Modifier.fillMaxSize()
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        text = "Microphone permission denied — you can listen but not transmit.\nGrant the permission in system settings and re-open the call.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Color.White,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(32.dp)
                    )
                }
            }
        }
    }
}

/** Circular glassy control button used by the call controls row. */
@Composable
private fun CallControlButton(
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    label: String,
    active: Boolean,
    enabled: Boolean,
    onClick: () -> Unit
) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Surface(
            onClick = onClick,
            enabled = enabled,
            shape = CircleShape,
            color = if (active) Color.White else Color.White.copy(alpha = 0.14f),
            contentColor = if (active) Color(0xFF00695C) else Color.White,
            modifier = Modifier.size(58.dp)
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = label, modifier = Modifier.size(26.dp))
            }
        }
        Spacer(Modifier.height(6.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelSmall,
            color = Color(0xFFB9E8DF)
        )
    }
}

private fun formatCallDuration(totalSeconds: Int): String {
    val h = totalSeconds / 3600
    val m = (totalSeconds % 3600) / 60
    val s = totalSeconds % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
}
