package pk.trustguard.app.ui.screens

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
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

/**
 * R CHAT sign-up: username + password + display name + phone number ->
 * POST /accounts/register. On success the issued token is persisted and the
 * user lands in the app.
 */
@Composable
fun SignupScreen(
    onSignedUp: () -> Unit,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()

    var username by rememberSaveable { mutableStateOf("") }
    var displayName by rememberSaveable { mutableStateOf("") }
    var phoneNumber by rememberSaveable { mutableStateOf("") }
    var password by rememberSaveable { mutableStateOf("") }
    var passwordVisible by rememberSaveable { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    fun signUp() {
        val uname = username.trim()
        val name = displayName.trim().ifEmpty { uname }
        val phone = phoneNumber.trim()
        if (uname.isEmpty() || password.isEmpty() || phone.isEmpty() || busy) return
        busy = true
        error = null
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                GatewayApi(settings.baseUrl).registerAccount(uname, password, name, phone)
            }
            result.onSuccess { session ->
                SettingsStore.saveAuth(
                    context = context,
                    userId = session.userId,
                    username = session.username,
                    token = session.token,
                    displayName = name,
                    baseUrl = settings.baseUrl,
                    phoneNumber = session.phoneNumber.ifBlank { phone }
                )
                onSignedUp()
            }.onFailure { failure ->
                error = failure.message ?: "Sign up failed"
            }
            busy = false
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = 28.dp, vertical = 32.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
            }
            Text(
                text = "Create your account",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(start = 4.dp)
            )
        }
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Join R CHAT — private messaging and calls with real-time scam detection.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(28.dp))

        AuthField(
            value = displayName,
            onValueChange = { displayName = it },
            label = "Display name",
            enabled = !busy
        )
        Spacer(Modifier.height(14.dp))
        AuthField(
            value = username,
            onValueChange = { username = it },
            label = "Username",
            enabled = !busy,
            keyboardType = KeyboardType.Ascii
        )
        Spacer(Modifier.height(14.dp))
        AuthField(
            value = phoneNumber,
            onValueChange = { phoneNumber = it },
            label = "Phone number",
            enabled = !busy,
            keyboardType = KeyboardType.Phone
        )
        Spacer(Modifier.height(14.dp))
        AuthField(
            value = password,
            onValueChange = { password = it },
            label = "Password (min 6 characters)",
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

        Spacer(Modifier.height(26.dp))
        GradientButton(
            text = "Create Account",
            onClick = ::signUp,
            enabled = !busy && username.isNotBlank() && password.isNotEmpty() && phoneNumber.isNotBlank(),
            loading = busy,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))
        Text(
            text = "Usernames: 3-30 characters, letters, numbers and underscores. Phone: 7-15 digits — used as your caller ID for calls.",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(16.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                "Already have an account?",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            TextButton(onClick = onBack, enabled = !busy) {
                Text("Sign in", fontWeight = FontWeight.Bold)
            }
        }
    }
}
