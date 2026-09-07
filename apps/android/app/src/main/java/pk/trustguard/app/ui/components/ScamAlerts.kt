package pk.trustguard.app.ui.components

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.GppMaybe
import androidx.compose.material.icons.filled.HealthAndSafety
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import pk.trustguard.app.net.RiskState
import pk.trustguard.app.ui.theme.AlertCritical
import pk.trustguard.app.ui.theme.AlertHigh
import pk.trustguard.app.ui.theme.AlertMedium
import kotlin.math.abs
import kotlin.math.roundToInt

/** Ordered severity for a risk band; low = 0, medium = 1, high = 2, critical = 3. */
fun bandSeverity(band: String): Int = when (band.lowercase()) {
    "low" -> 0
    "medium" -> 1
    "high" -> 2
    "critical" -> 3
    else -> 0
}

/** Scam-alert banner colours by band (spec: medium amber, high orange, critical red). */
fun bandAlertColor(band: String): Color = when (band.lowercase()) {
    "medium" -> AlertMedium
    "high" -> AlertHigh
    "critical" -> AlertCritical
    "low" -> Color(0xFF22C55E)
    else -> Color(0xFF6B7280)
}

/**
 * Human-readable names for gateway signal types so alerts read like reasons,
 * not raw rule ids.
 */
fun humanSignalName(type: String): String {
    val t = type.trim().lowercase()
    return when {
        t.contains("otp") -> "Asking for an OTP / verification code"
        t.contains("credential") -> "Requesting your password or PIN"
        t.contains("bank") && t.contains("imperson") -> "Impersonating your bank"
        t.contains("bank") -> "Suspicious bank claims"
        t.contains("wallet") -> "Wallet / payment app impersonation"
        t.contains("urgency") || t.contains("pressure") -> "Creating false urgency"
        t.contains("authority") -> "Claiming false authority"
        t.contains("gift") -> "Gift card payment demand"
        t.contains("remote") || t.contains("screen") || t.contains("app_install") -> "Remote access / app install request"
        t.contains("caller_id") -> "Caller ID not matching the official number"
        t.contains("crypto") -> "Crypto payment demand"
        t.contains("groom") || t.contains("romance") || t.contains("investment") -> "Romance / investment grooming"
        t.contains("person") || t.contains("private_question") -> "Unsafe personal questions"
        t.contains("injection") || t.contains("prompt") -> "Manipulating the safety system"
        t.contains("threat") || t.contains("intimidat") -> "Threats and intimidation"
        t.contains("prize") || t.contains("lottery") -> "Fake prize / lottery claim"
        t.contains("job") || t.contains("task") -> "Fake job / task scam"
        t.contains("link") || t.contains("phish") -> "Suspicious link (phishing)"
        else -> type.replace('_', ' ').replaceFirstChar { it.uppercase() }
    }
}

/**
 * Vibrates for a newly surfaced scam alert: waveform pulses for high/critical,
 * a single short pulse for medium. minSdk 26 so VibrationEffect is always
 * available.
 */
fun vibrateForBand(context: Context, band: String) {
    val vibrator = context.getSystemService(Vibrator::class.java) ?: return
    if (!vibrator.hasVibrator()) return
    when (bandSeverity(band)) {
        3 -> vibrator.vibrate(
            VibrationEffect.createWaveform(longArrayOf(0, 350, 150, 350, 150, 600), -1)
        )
        2 -> vibrator.vibrate(
            VibrationEffect.createWaveform(longArrayOf(0, 250, 120, 250), -1)
        )
        1 -> vibrator.vibrate(
            VibrationEffect.createOneShot(200, VibrationEffect.DEFAULT_AMPLITUDE)
        )
    }
}

/**
 * Tracks scam-alert UI state across recompositions:
 * - the band severity the user dismissed at (alerts stay hidden until escalation),
 * - the severity currently shown (drives "new alert" vibration).
 */
class ScamAlertState {
    var dismissedSeverity by mutableIntStateOf(0)
        private set
    var shownSeverity by mutableIntStateOf(0)
        private set

    fun dismissAt(severity: Int) {
        dismissedSeverity = severity
        shownSeverity = 0
    }

    fun markShown(severity: Int) {
        shownSeverity = severity
    }

    fun reset() {
        dismissedSeverity = 0
        shownSeverity = 0
    }
}

@Composable
fun rememberScamAlertState(): ScamAlertState = remember { ScamAlertState() }

/**
 * Watches the live risk stream and vibrates whenever a NEW alert becomes
 * visible (band >= medium and above what the user already dismissed/saw).
 * Only vibrates if [enabled] is true (i.e., the user is likely the victim).
 */
@Composable
fun ScamAlertWatcher(
    risk: RiskState,
    alertState: ScamAlertState,
    enabled: Boolean = true
) {
    val context = LocalContext.current
    val severity = bandSeverity(risk.band)
    val visible = enabled && severity >= 1 && severity > alertState.dismissedSeverity
    LaunchedEffect(visible, severity) {
        if (visible && severity > alertState.shownSeverity) {
            vibrateForBand(context, risk.band)
        }
        alertState.markShown(if (visible) severity else 0)
    }
}

/** Small shield indicator for top bars: "Protected" when calm, band-coloured when alerted. */
@Composable
fun ShieldIndicator(band: String, darkSurface: Boolean = false, modifier: Modifier = Modifier) {
    val severity = bandSeverity(band)
    val (tint, label) = when {
        severity >= 1 -> bandAlertColor(band) to band.replaceFirstChar { it.uppercase() } + " risk"
        else -> (if (darkSurface) Color(0xFF4DBDAC) else MaterialTheme.colorScheme.primary) to "Protected"
    }
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            imageVector = if (severity >= 1) Icons.Filled.GppMaybe else Icons.Filled.HealthAndSafety,
            contentDescription = label,
            tint = tint,
            modifier = Modifier.size(18.dp)
        )
        Spacer(Modifier.width(6.dp))
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold,
            color = tint,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

/**
 * THE scam alert banner. Shown while band >= medium and above the dismissed
 * severity. Colours by band (amber / orange / red), lists up to three
 * human-readable reasons plus the top safe action, and offers an
 * "I've verified this contact" dismiss button that keeps the banner hidden
 * until the band escalates.
 */
@Composable
fun ScamAlertBanner(
    risk: RiskState,
    alertState: ScamAlertState,
    onDismiss: () -> Unit,
    onEndCall: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    val severity = bandSeverity(risk.band)
    val visible = severity >= 1 && severity > alertState.dismissedSeverity
    AnimatedVisibility(
        visible = visible,
        enter = fadeIn() + expandVertically(),
        exit = fadeOut() + shrinkVertically(),
        modifier = modifier
    ) {
        val color = bandAlertColor(risk.band)
        val headline = when (severity) {
            3 -> "Critical Scam Alert"
            2 -> "High Scam Risk Detected"
            else -> "Scam Warning"
        }
        Surface(
            shape = RoundedCornerShape(18.dp),
            color = color.copy(alpha = 0.16f),
            border = androidx.compose.foundation.BorderStroke(1.dp, color.copy(alpha = 0.55f)),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(Modifier.padding(horizontal = 14.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .size(30.dp)
                            .background(color.copy(alpha = 0.25f), CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            Icons.Filled.Warning,
                            contentDescription = null,
                            tint = color,
                            modifier = Modifier.size(18.dp)
                        )
                    }
                    Spacer(Modifier.width(10.dp))
                    Column {
                        Text(
                            text = headline,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = color
                        )
                        Text(
                            text = "Risk score ${risk.score}/100",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }

                if (risk.deltaSignals.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        text = "Why you're seeing this:",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.SemiBold,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(2.dp))
                    for (signal in risk.deltaSignals.sortedByDescending { abs(it.contribution) }.take(3)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier
                                    .size(6.dp)
                                    .background(color, CircleShape)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                text = buildString {
                                    append(humanSignalName(signal.type))
                                    if (signal.contribution > 0.0) {
                                        append("  +${signal.contribution.roundToInt()}")
                                    }
                                },
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurface,
                                maxLines = 2,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                }

                risk.safeActions.firstOrNull()?.let { action ->
                    Spacer(Modifier.height(8.dp))
                    Surface(
                        shape = RoundedCornerShape(12.dp),
                        color = color.copy(alpha = 0.22f)
                    ) {
                        Text(
                            text = action,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.onSurface,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                        )
                    }
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    if (onEndCall != null && severity >= 2) {
                        TextButton(onClick = onEndCall) {
                            Text("End call now", color = color, fontWeight = FontWeight.Bold)
                        }
                    }
                    TextButton(onClick = onDismiss) {
                        Text(
                            "I've verified this contact",
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }
        }
    }
}
