package pk.trustguard.app.ui.screens

import android.os.VibrationEffect
import android.os.Vibrator
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.CallEnd
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import pk.trustguard.app.ui.components.InitialsAvatar
import pk.trustguard.app.ui.theme.CallScreenGradient
import pk.trustguard.app.ui.theme.DangerRed

/**
 * WhatsApp-style incoming call screen with ringing, accept and reject buttons.
 */
@Composable
fun IncomingCallScreen(
    callerName: String,
    callerUsername: String,
    onAccept: () -> Unit,
    onReject: () -> Unit
) {
    val context = LocalContext.current

    // Ring vibration pattern while this screen is shown.
    DisposableEffect(Unit) {
        val vibrator = context.getSystemService(Vibrator::class.java)
        val pattern = longArrayOf(0, 800, 400, 800, 400, 800)
        val effect = VibrationEffect.createWaveform(pattern, 0)
        vibrator?.vibrate(effect)

        onDispose {
            vibrator?.cancel()
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(CallScreenGradient),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Text(
                text = "Incoming call",
                style = MaterialTheme.typography.titleLarge,
                color = Color.White.copy(alpha = 0.85f),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(48.dp))

            InitialsAvatar(name = callerName, size = 120.dp)

            Spacer(Modifier.height(24.dp))

            Text(
                text = callerName,
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = Color.White,
                textAlign = TextAlign.Center
            )

            Text(
                text = "@$callerUsername",
                style = MaterialTheme.typography.bodyLarge,
                color = Color.White.copy(alpha = 0.7f),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(8.dp))

            Text(
                text = "R CHAT voice call",
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.6f),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.weight(1f))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Reject button
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    IconButton(
                        onClick = onReject,
                        modifier = Modifier
                            .size(72.dp)
                            .background(DangerRed, CircleShape)
                    ) {
                        Icon(
                            Icons.Filled.CallEnd,
                            contentDescription = "Decline",
                            tint = Color.White,
                            modifier = Modifier.size(32.dp)
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Decline", color = Color.White)
                }

                // Accept button
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    IconButton(
                        onClick = onAccept,
                        modifier = Modifier
                            .size(72.dp)
                            .background(Color(0xFF4CAF50), CircleShape)
                    ) {
                        Icon(
                            Icons.Filled.Call,
                            contentDescription = "Accept",
                            tint = Color.White,
                            modifier = Modifier.size(32.dp)
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    Text("Accept", color = Color.White)
                }
            }

            Spacer(Modifier.height(48.dp))
        }
    }
}
