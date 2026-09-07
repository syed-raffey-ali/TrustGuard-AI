package pk.trustguard.app.ui.components

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import pk.trustguard.app.net.RiskState
import pk.trustguard.tier1.Tier1Hit
import kotlin.math.roundToInt

/** Band -> colour strip mapping mandated by the design spec. */
fun bandColor(band: String): Color = when (band.lowercase()) {
    "low" -> Color(0xFF22C55E)
    "medium" -> Color(0xFFF59E0B)
    "high" -> Color(0xFFF97316)
    "critical" -> Color(0xFFDC2626)
    else -> Color(0xFF6B7280)
}

fun severityColor(severity: Int): Color = when {
    severity >= 5 -> Color(0xFFEF4444)
    severity == 4 -> Color(0xFFF97316)
    severity == 3 -> Color(0xFFEAB308)
    else -> Color(0xFF64748B)
}

private fun Color.readable(): Color =
    if (luminance() > 0.5f) {
        Color(red = red * 0.55f, green = green * 0.55f, blue = blue * 0.55f)
    } else {
        this
    }

/** Shows a toast on the main looper regardless of calling thread. */
fun showToast(context: Context, message: String) {
    Handler(Looper.getMainLooper()).post {
        Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
    }
}

/**
 * Pinned risk strip: colour-coded band bar + score + latest delta signals.
 * Used by both ChatScreen and CallScreen above their bottom content.
 */
@Composable
fun RiskBanner(state: RiskState, modifier: Modifier = Modifier) {
    val color = bandColor(state.band)
    Surface(
        modifier = modifier.fillMaxWidth(),
        color = color.copy(alpha = 0.14f)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .width(6.dp)
                    .fillMaxHeight()
                    .background(color)
            )
            Column(Modifier.padding(horizontal = 10.dp, vertical = 6.dp)) {
                Text(
                    text = "Risk ${state.score}/100 · ${state.band.uppercase()}" +
                        (state.stage?.let { stage -> " · stage: $stage" } ?: ""),
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = color.readable()
                )
                if (state.deltaSignals.isNotEmpty()) {
                    Text(
                        text = state.deltaSignals.joinToString(" · ") { signal ->
                            "${signal.type} (sev ${signal.severity}, ${(signal.confidence * 100).roundToInt()}%)"
                        },
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
                    )
                }
                if (state.safeActions.isNotEmpty()) {
                    Text(
                        text = "Safe actions: ${state.safeActions.joinToString(", ")}",
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f)
                    )
                }
            }
        }
    }
}

/**
 * Inline chips for Tier-1 hits under a sent bubble, plus the locally measured
 * scan latency backing the "<150 ms" claim.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun Tier1HitChips(
    hits: List<Tier1Hit>,
    elapsedMs: Long?,
    modifier: Modifier = Modifier
) {
    if (hits.isEmpty() && elapsedMs == null) return
    FlowRow(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalArrangement = Arrangement.spacedBy(2.dp)
    ) {
        for (hit in hits) {
            val color = severityColor(hit.severity)
            Surface(
                shape = RoundedCornerShape(50),
                color = color.copy(alpha = 0.16f)
            ) {
                Text(
                    text = "${hit.label} · sev ${hit.severity} · ${(hit.confidence * 100).roundToInt()}%",
                    style = MaterialTheme.typography.labelSmall,
                    color = color.readable(),
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                )
            }
        }
        if (elapsedMs != null) {
            Surface(
                shape = RoundedCornerShape(50),
                color = MaterialTheme.colorScheme.surfaceVariant
            ) {
                Text(
                    text = "tier1 $elapsedMs ms (<150 ms)",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                )
            }
        }
    }
}

/** Small labelled section header used across screens. */
@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(
        text = text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.primary,
        modifier = modifier.padding(top = 12.dp, bottom = 4.dp)
    )
}
