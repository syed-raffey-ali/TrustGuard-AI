package pk.trustguard.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.notify.CallEventBus
import pk.trustguard.app.ui.components.InitialsAvatar
import pk.trustguard.app.ui.components.showToast
import pk.trustguard.app.ui.theme.CallScreenGradient
import pk.trustguard.app.ui.theme.DangerRed

/** No-answer timeout for the ringing state (WhatsApp-style ~45 s). */
private const val RING_TIMEOUT_MS = 45_000L

/**
 * Caller-side "Calling…" screen shown while the invite is ringing on the
 * other phone. The audio connection and call timer only start once the peer
 * accepts ([CallEventBus.accepted]); rejection or timeout cancels the invite.
 */
@Composable
fun OutgoingCallScreen(
    inviteId: String,
    sessionId: String,
    peerName: String,
    onAccepted: (sessionId: String) -> Unit,
    onCancelled: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()
    var finished by remember { mutableStateOf(false) }

    fun cancelInvite(reason: String) {
        if (finished) return
        finished = true
        scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    GatewayApi(settings.baseUrl).rejectCall(inviteId)
                }
            }
            showToast(context, reason)
            onCancelled()
        }
    }

    // Peer accepted -> hand over to the live call screen.
    LaunchedEffect(inviteId) {
        CallEventBus.accepted.collect { event ->
            if (event.inviteId == inviteId && !finished) {
                finished = true
                onAccepted(event.sessionId.ifBlank { sessionId })
            }
        }
    }

    // Peer rejected -> abort ringing.
    LaunchedEffect(inviteId) {
        CallEventBus.rejected.collect { event ->
            if (event.inviteId == inviteId && !finished) {
                cancelInvite("Call declined")
            }
        }
    }

    // Ring timeout.
    LaunchedEffect(inviteId) {
        delay(RING_TIMEOUT_MS)
        if (!finished) cancelInvite("No answer")
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(CallScreenGradient),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp),
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "R CHAT voice call",
                style = MaterialTheme.typography.titleMedium,
                color = Color.White.copy(alpha = 0.7f),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(48.dp))

            InitialsAvatar(name = peerName, size = 120.dp)

            Spacer(Modifier.height(24.dp))

            Text(
                text = peerName,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(8.dp))

            // Ringing label — the timer only starts after the call is picked up.
            Text(
                text = "Ringing…",
                style = MaterialTheme.typography.titleMedium,
                color = Color(0xFF9CE5DA),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(12.dp))
            CircularProgressIndicator(
                modifier = Modifier.size(24.dp),
                strokeWidth = 2.dp,
                color = Color(0xFF9CE5DA)
            )

            Spacer(Modifier.height(72.dp))

            // Cancel the outgoing call.
            Surface(
                onClick = { cancelInvite("Call cancelled") },
                shape = CircleShape,
                color = DangerRed,
                modifier = Modifier.size(74.dp)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Filled.CallEnd,
                        contentDescription = "Cancel call",
                        tint = Color.White,
                        modifier = Modifier.size(32.dp)
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Text("Cancel", color = Color.White)
        }
    }
}
