package pk.trustguard.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
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

/**
 * Device demo mode (legacy fallback): display name -> POST /api/v1/devices/register,
 * identity persisted in DataStore. Lets the app work end-to-end without an
 * account when the gateway account API is unavailable. Auto-skips when a
 * device is already registered.
 */
@Composable
fun RegisterScreen(onDone: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()

    var name by rememberSaveable { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }

    // Already registered on a previous run (or just now) -> straight to main.
    LaunchedEffect(settings.deviceId) {
        if (settings.deviceId != null) onDone()
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        BrandMark()
        Spacer(Modifier.height(8.dp))
        Text(
            text = "Device demo mode",
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.primary
        )
        Text(
            text = "Continue without an account — this device gets a demo ID that can still chat, call and run the scam shield.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 4.dp)
        )
        Spacer(Modifier.height(28.dp))

        OutlinedTextField(
            value = name,
            onValueChange = { name = it },
            label = { Text("Your display name") },
            singleLine = true,
            enabled = !busy,
            keyboardOptions = KeyboardOptions.Default,
            shape = MaterialTheme.shapes.large,
            modifier = Modifier.fillMaxWidth()
        )
        error?.let {
            Spacer(Modifier.height(8.dp))
            Text(
                text = it,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                textAlign = TextAlign.Start,
                modifier = Modifier.fillMaxWidth()
            )
        }
        Spacer(Modifier.height(16.dp))

        GradientButton(
            text = "Register device",
            onClick = {
                val displayName = name.trim()
                if (displayName.isEmpty() || busy) return@GradientButton
                busy = true
                error = null
                scope.launch {
                    val result = withContext(Dispatchers.IO) {
                        GatewayApi(settings.baseUrl).register(displayName)
                    }
                    result.onSuccess { info ->
                        SettingsStore.saveRegistration(context, info.deviceId, displayName, settings.baseUrl)
                        showToast(context, "Device registered")
                        // LaunchedEffect above reacts to the new deviceId and navigates.
                    }.onFailure { failure ->
                        error = failure.message ?: "Registration failed"
                    }
                    busy = false
                }
            },
            enabled = !busy && name.isNotBlank(),
            loading = busy,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(24.dp))
        Text(
            text = "Gateway: ${settings.baseUrl}",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
