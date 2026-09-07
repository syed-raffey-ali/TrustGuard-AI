package pk.trustguard.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import pk.trustguard.app.ui.theme.BrandGradient

/** Deterministic avatar palette; index picked from a stable hash of the name. */
private val AvatarPalette = listOf(
    Color(0xFF00897B), Color(0xFF039BE5), Color(0xFF7CB342), Color(0xFFF9A825),
    Color(0xFFEF6C00), Color(0xFF8E24AA), Color(0xFFD81B60), Color(0xFF5E35B1),
    Color(0xFF00838F), Color(0xFF43A047)
)

fun avatarColorFor(name: String): Color =
    AvatarPalette[Math.floorMod(name.hashCode(), AvatarPalette.size)]

/** Circle avatar with up to two initials, background colour hashed from [name]. */
@Composable
fun InitialsAvatar(
    name: String,
    size: Dp = 48.dp,
    modifier: Modifier = Modifier,
    textColor: Color = Color.White
) {
    val label = name.trim()
        .split(Regex("\\s+"))
        .filter { it.isNotEmpty() }
        .take(2)
        .joinToString("") { it.first().uppercase() }
        .ifEmpty { "?" }
    Box(
        modifier = modifier
            .size(size)
            .background(
                Brush.linearGradient(
                    listOf(avatarColorFor(name).copy(alpha = 0.85f), avatarColorFor(name))
                ),
                CircleShape
            ),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            color = textColor,
            style = if (size >= 56.dp) MaterialTheme.typography.titleLarge else MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )
    }
}

/**
 * Premium gradient button (teal brand gradient), optionally showing a
 * progress spinner while [loading].
 */
@Composable
fun GradientButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    icon: ImageVector? = null
) {
    val brush = if (enabled) BrandGradient else Brush.linearGradient(
        listOf(
            MaterialTheme.colorScheme.surfaceVariant,
            MaterialTheme.colorScheme.surfaceVariant
        )
    )
    Box(
        modifier = modifier
            .heightIn(min = 54.dp)
            .background(brush, MaterialTheme.shapes.large)
            .clickable(enabled = enabled && !loading, onClick = onClick)
            .padding(horizontal = 20.dp, vertical = 14.dp),
        contentAlignment = Alignment.Center
    ) {
        if (loading) {
            CircularProgressIndicator(
                modifier = Modifier.size(22.dp),
                strokeWidth = 2.dp,
                color = Color.White
            )
        } else {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (icon != null) {
                    Icon(
                        icon,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    text = text,
                    color = Color.White,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    textAlign = TextAlign.Center
                )
            }
        }
    }
}
