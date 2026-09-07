package pk.trustguard.app.data

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import androidx.compose.ui.platform.LocalContext
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.emptyPreferences
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

/** Default gateway base URL: laptop's LAN IP for physical phones. */
const val DEFAULT_BASE_URL = "http://192.168.1.10:8080"

data class AppSettings(
    val deviceId: String?,
    val displayName: String,
    val baseUrl: String,
    /** Bearer token from /accounts/login or /accounts/register; null in device demo mode. */
    val token: String? = null,
    val userId: String? = null,
    val username: String? = null,
    /** The signed-in user's registered phone number (caller ID). */
    val phoneNumber: String = ""
) {
    val isLoggedIn: Boolean get() = !token.isNullOrBlank()
}

private val Context.settingsDataStore by preferencesDataStore(
    name = "trustguard_settings"
)

/**
 * DataStore-backed persistence for account identity, device identity and
 * gateway configuration.
 */
object SettingsStore {

    private val KEY_DEVICE_ID = stringPreferencesKey("device_id")
    private val KEY_DISPLAY_NAME = stringPreferencesKey("display_name")
    private val KEY_BASE_URL = stringPreferencesKey("base_url")
    private val KEY_TOKEN = stringPreferencesKey("auth_token")
    private val KEY_USER_ID = stringPreferencesKey("user_id")
    private val KEY_USERNAME = stringPreferencesKey("username")
    private val KEY_PHONE_NUMBER = stringPreferencesKey("phone_number")

    fun flow(context: Context): Flow<AppSettings> =
        context.settingsDataStore.data
            .catch { emit(emptyPreferences()) }
            .map { prefs ->
                AppSettings(
                    deviceId = prefs[KEY_DEVICE_ID],
                    displayName = prefs[KEY_DISPLAY_NAME].orEmpty(),
                    baseUrl = prefs[KEY_BASE_URL] ?: DEFAULT_BASE_URL,
                    token = prefs[KEY_TOKEN],
                    userId = prefs[KEY_USER_ID],
                    username = prefs[KEY_USERNAME],
                    phoneNumber = prefs[KEY_PHONE_NUMBER].orEmpty()
                )
            }

    suspend fun current(context: Context): AppSettings = flow(context).first()

    suspend fun saveRegistration(context: Context, deviceId: String, displayName: String, baseUrl: String) {
        context.settingsDataStore.edit { prefs ->
            prefs[KEY_DEVICE_ID] = deviceId
            prefs[KEY_DISPLAY_NAME] = displayName
            prefs[KEY_BASE_URL] = baseUrl
        }
    }

    /** Persists an authenticated account session (login / signup). */
    suspend fun saveAuth(
        context: Context,
        userId: String,
        username: String,
        token: String,
        displayName: String,
        baseUrl: String,
        phoneNumber: String = ""
    ) {
        context.settingsDataStore.edit { prefs ->
            prefs[KEY_USER_ID] = userId
            prefs[KEY_USERNAME] = username
            prefs[KEY_TOKEN] = token
            prefs[KEY_DISPLAY_NAME] = displayName.ifBlank { username }
            prefs[KEY_BASE_URL] = baseUrl
            prefs[KEY_PHONE_NUMBER] = phoneNumber.trim()
        }
    }

    /** Clears the account session (logout); keeps device + gateway config. */
    suspend fun clearAuth(context: Context) {
        context.settingsDataStore.edit { prefs ->
            prefs.remove(KEY_TOKEN)
            prefs.remove(KEY_USER_ID)
            prefs.remove(KEY_USERNAME)
            prefs.remove(KEY_PHONE_NUMBER)
        }
    }

    suspend fun saveBaseUrl(context: Context, baseUrl: String) {
        context.settingsDataStore.edit { prefs ->
            prefs[KEY_BASE_URL] = baseUrl.trim()
        }
    }

    suspend fun saveDisplayName(context: Context, displayName: String) {
        context.settingsDataStore.edit { prefs ->
            prefs[KEY_DISPLAY_NAME] = displayName.trim()
        }
    }
}

/**
 * Compose-friendly snapshot of [AppSettings]; recomposes whenever DataStore
 * contents change.
 */
@Composable
fun rememberAppSettings(): AppSettings {
    val context = LocalContext.current
    return produceState(
        initialValue = AppSettings(deviceId = null, displayName = "", baseUrl = DEFAULT_BASE_URL),
        key1 = context
    ) {
        SettingsStore.flow(context).collect { value = it }
    }.value
}
