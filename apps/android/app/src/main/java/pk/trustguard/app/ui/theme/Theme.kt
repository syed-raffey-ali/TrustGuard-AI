package pk.trustguard.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

// ------------------------------------------------------------------ brand palette
// Deep teal / emerald primary with gradient accents (#00695C -> #26A69A).
val TealPrimary = Color(0xFF00897B)
val TealDeep = Color(0xFF00695C)
val TealLight = Color(0xFF26A69A)
val TealContainer = Color(0xFFB2DFDB)
val OnTealContainer = Color(0xFF00201C)

val AmberAccent = Color(0xFFF59E0B)
val AlertMedium = Color(0xFFF59E0B)
val AlertHigh = Color(0xFFF97316)
val AlertCritical = Color(0xFFDC2626)

val DangerRed = Color(0xFFDC2626)
val DangerRedDark = Color(0xFFB91C1C)

/** Signature brand gradient used for buttons, headers and outgoing bubbles. */
val BrandGradient = Brush.linearGradient(listOf(TealDeep, TealLight))

/** Dark full-screen gradient used by the call screen. */
val CallScreenGradient = Brush.verticalGradient(
    listOf(Color(0xFF041F1B), Color(0xFF06352E), Color(0xFF00564B))
)

/** Light chat canvas gradient (subtle, premium). */
val ChatCanvasLight = Brush.verticalGradient(
    listOf(Color(0xFFF1F8F6), Color(0xFFE6F2EF))
)

// ------------------------------------------------------------------ color schemes
private val LightColors = lightColorScheme(
    primary = TealPrimary,
    onPrimary = Color.White,
    primaryContainer = TealContainer,
    onPrimaryContainer = OnTealContainer,
    inversePrimary = TealLight,
    secondary = Color(0xFF4A635F),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFCCE8E2),
    onSecondaryContainer = Color(0xFF051F1B),
    tertiary = Color(0xFF22A06B),
    onTertiary = Color.White,
    tertiaryContainer = Color(0xFFC8F5DC),
    onTertiaryContainer = Color(0xFF00210F),
    background = Color(0xFFF7FBFA),
    onBackground = Color(0xFF171D1B),
    surface = Color(0xFFF7FBFA),
    onSurface = Color(0xFF171D1B),
    surfaceVariant = Color(0xFFDBE5E1),
    onSurfaceVariant = Color(0xFF3F4946),
    surfaceTint = TealPrimary,
    inverseSurface = Color(0xFF2B3230),
    inverseOnSurface = Color(0xFFECF2F0),
    error = DangerRedDark,
    onError = Color.White,
    errorContainer = Color(0xFFFCE8E6),
    onErrorContainer = Color(0xFF410002),
    outline = Color(0xFF6F7976),
    outlineVariant = Color(0xFFBEC9C5),
    scrim = Color(0xFF000000)
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF4DBDAC),
    onPrimary = Color(0xFF003731),
    primaryContainer = Color(0xFF005048),
    onPrimaryContainer = Color(0xFF9CF1E4),
    inversePrimary = TealPrimary,
    secondary = Color(0xFFB1CCC6),
    onSecondary = Color(0xFF1C3530),
    secondaryContainer = Color(0xFF334B47),
    onSecondaryContainer = Color(0xFFCDE8E1),
    tertiary = Color(0xFF7FD9AC),
    onTertiary = Color(0xFF00391D),
    tertiaryContainer = Color(0xFF00522C),
    onTertiaryContainer = Color(0xFF9CF6C6),
    background = Color(0xFF0F1513),
    onBackground = Color(0xFFDEE4E1),
    surface = Color(0xFF0F1513),
    onSurface = Color(0xFFDEE4E1),
    surfaceVariant = Color(0xFF3F4946),
    onSurfaceVariant = Color(0xFFBEC9C5),
    surfaceTint = Color(0xFF4DBDAC),
    inverseSurface = Color(0xFFDEE4E1),
    inverseOnSurface = Color(0xFF2B3230),
    error = Color(0xFFF2B8B5),
    onError = Color(0xFF601410),
    errorContainer = Color(0xFF8C1D18),
    onErrorContainer = Color(0xFFF9DEDC),
    outline = Color(0xFF889390),
    outlineVariant = Color(0xFF3F4946),
    scrim = Color(0xFF000000)
)

// ------------------------------------------------------------------ typography
private val AppTypography = Typography().let { base ->
    base.copy(
        displaySmall = base.displaySmall.copy(fontWeight = FontWeight.Bold),
        headlineLarge = base.headlineLarge.copy(fontWeight = FontWeight.Bold),
        headlineMedium = base.headlineMedium.copy(fontWeight = FontWeight.SemiBold),
        headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.SemiBold),
        titleLarge = base.titleLarge.copy(fontWeight = FontWeight.SemiBold),
        titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        titleSmall = base.titleSmall.copy(fontWeight = FontWeight.Medium),
        labelLarge = base.labelLarge.copy(fontWeight = FontWeight.SemiBold)
    )
}

// ------------------------------------------------------------------ shapes
private val AppShapes = Shapes(
    extraSmall = RoundedCornerShape(6.dp),
    small = RoundedCornerShape(10.dp),
    medium = RoundedCornerShape(16.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(32.dp)
)

/** Premium R CHAT theme: teal/emerald Material3 with light + dark schemes. */
@Composable
fun RChatTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        typography = AppTypography,
        shapes = AppShapes,
        content = content
    )
}

/** Backwards-compatible alias used by existing call sites. */
@Composable
fun TrustGuardTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit
) = RChatTheme(darkTheme = darkTheme, content = content)
