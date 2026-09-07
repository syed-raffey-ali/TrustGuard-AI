package pk.trustguard.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubble
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.data.SettingsStore
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.ui.components.GradientButton
import pk.trustguard.app.ui.components.showToast
import pk.trustguard.app.ui.theme.BrandGradient

/**
 * R CHAT sign-in: username + password against the gateway account API.
 * Saves the bearer token and navigates to the main hub. Includes a
 * "demo mode" escape hatch that keeps the legacy device_id flow working.
 */
@Composable
fun LoginScreen(
    onLoggedIn: () -> Unit,
    onOpenSignup: () -> Unit,
    onOpenDemoMode: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()

    var username by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var passwordVisible by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun signIn() {
        val uname = username.trim()
        if (uname.isEmpty() || password.isEmpty() || busy) return
        busy = true
        error = null
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                GatewayApi(settings.baseUrl).login(uname, password)
            }
            result.onSuccess { session ->
                SettingsStore.saveAuth(
                    context = context,
                    userId = session.userId,
                    username = session.username,
                    token = session.token,
                    displayName = session.username,
                    baseUrl = settings.baseUrl
                )
                onLoggedIn()
            }.onFailure { failure ->
                error = failure.message ?: "Sign in failed"
            }
            busy = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = 28.dp, vertical = 48.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        BrandMark()
        Spacer(Modifier.height(40.dp))

        AuthField(
            value = username,
            onValueChange = { username = it },
            label = "Username",
            enabled = !busy,
            keyboardType = KeyboardType.Ascii
        )
        Spacer(Modifier.height(14.dp))
        AuthField(
            value = password,
            onValueChange = { password = it },
            label = "Password",
            enabled = !busy,
            keyboardType = KeyboardType.Password,
            visualTransformation = if (passwordVisible) VisualTransformation.None
            else PasswordVisualTransformation(),
            trailing = {
                IconButton(onClick = { passwordVisible = !passwordVisible }) {
                    Icon(
                        imageVector = if (passwordVisible) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                        contentDescription = if (passwordVisible) "Hide password" else "Show password",
                        tint = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        )

        error?.let {
            Spacer(Modifier.height(10.dp))
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Start,
                modifier = Modifier.fillMaxWidth()
            )
        }

        Spacer(Modifier.height(24.dp))
        GradientButton(
            text = "Sign In",
            onClick = ::signIn,
            enabled = !busy && username.isNotBlank() && password.isNotEmpty(),
            loading = busy,
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(Modifier.height(18.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                "New to R CHAT?",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            TextButton(onClick = onOpenSignup, enabled = !busy) {
                Text("Create account", fontWeight = FontWeight.Bold)
            }
        }

        Spacer(Modifier.height(28.dp))
        TextButton(onClick = onOpenDemoMode, enabled = !busy) {
            Text(
                "Continue in device demo mode",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Gateway: ${settings.baseUrl}",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
    }
}

/** R CHAT logo: gradient chat bubble badge + wordmark. */
@Composable
fun BrandMark(modifier: Modifier = Modifier) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            modifier = Modifier
                .size(84.dp)
                .background(BrandGradient, CircleShape),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.Filled.ChatBubble,
                contentDescription = "R CHAT",
                tint = Color.White,
                modifier = Modifier.size(40.dp)
            )
        }
        Spacer(Modifier.height(18.dp))
        Text(
            text = "R CHAT",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary
        )
        Spacer(Modifier.height(4.dp))
        Text(
            text = "Premium messaging & calls with live scam protection",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center
        )
    }
}

/** Rounded premium outlined field used by the auth screens. */
@Composable
fun AuthField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    keyboardType: KeyboardType = KeyboardType.Text,
    visualTransformation: VisualTransformation = VisualTransformation.None,
    trailing: (@Composable () -> Unit)? = null
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        shape = MaterialTheme.shapes.large,
        keyboardOptions = KeyboardOptions(keyboardType = keyboardType),
        visualTransformation = visualTransformation,
        trailingIcon = trailing,
        modifier = modifier.fillMaxWidth()
    )
}
