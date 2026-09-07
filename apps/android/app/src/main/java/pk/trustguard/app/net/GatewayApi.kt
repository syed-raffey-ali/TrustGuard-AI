package pk.trustguard.app.net

import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/** REST DTOs mirroring the TrustGuard gateway contract. */
data class DeviceInfo(
    val deviceId: String,
    val displayName: String?,
    val registeredAt: String?,
    val status: String?
)

data class RosterEntry(val deviceId: String, val sessionId: String?)

data class StartedSession(val sessionId: String, val type: String?, val mode: String?)

data class CallInvite(
    val inviteId: String,
    val sessionId: String,
    val fromUser: String,
    val toUser: String,
    val status: String
)

data class PersistedMessage(
    val messageId: String,
    val speaker: String,
    val text: String,
    val timestamp: String?,
    val deliveredTo: List<String>,
    val readBy: List<String>
)

/** Authenticated account session returned by /accounts/register and /accounts/login. */
data class AuthSession(
    val userId: String,
    val username: String,
    val token: String,
    val phoneNumber: String = ""
)

/** One account in the global contact directory (GET /accounts/users). */
data class UserEntry(
    val userId: String,
    val username: String,
    val displayName: String,
    val createdAt: String? = null,
    val phoneNumber: String = ""
)

/**
 * Converts an http(s) base URL plus a path into a ws(s) WebSocket URL.
 * Example: "http://10.0.2.2:8080", "/ws/chat/s1" -> "ws://10.0.2.2:8080/ws/chat/s1"
 */
fun toWsUrl(baseUrl: String, path: String): String {
    val trimmed = baseUrl.trim().trimEnd('/')
    return when {
        trimmed.startsWith("https://") -> "wss://" + trimmed.removePrefix("https://") + path
        trimmed.startsWith("http://") -> "ws://" + trimmed.removePrefix("http://") + path
        else -> "ws://$trimmed$path"
    }
}

/**
 * Thin synchronous OkHttp client for the TrustGuard gateway REST API.
 * Callers are expected to invoke methods from a background dispatcher
 * (e.g. `withContext(Dispatchers.IO) { ... }`).
 */
class GatewayApi(private val baseUrl: String) {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .build()

    private val jsonBody = "application/json; charset=utf-8".toMediaType()

    private fun url(path: String): String = baseUrl.trim().trimEnd('/') + path

    private fun execute(request: Request): Result<JsonObject> = runCatching {
        client.newCall(request).execute().use { response ->
            val bodyText = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw IllegalStateException("HTTP ${response.code}: ${bodyText.take(200)}")
            }
            if (bodyText.isBlank()) buildJsonObject { } else parseJsonObject(bodyText)
                ?: throw IllegalStateException("Malformed JSON in response")
        }
    }

    private fun postJson(path: String, body: JsonObject, bearer: String? = null): Result<JsonObject> =
        execute(
            Request.Builder()
                .url(url(path))
                .post(body.toString().toRequestBody(jsonBody))
                .apply { bearer?.let { header("Authorization", "Bearer $it") } }
                .build()
        )

    private fun getJson(path: String, bearer: String? = null): Result<JsonObject> =
        execute(
            Request.Builder()
                .url(url(path))
                .get()
                .apply { bearer?.let { header("Authorization", "Bearer $it") } }
                .build()
        )

    /** POST /api/v1/devices/register {"display_name": ...} -> device identity. */
    fun register(displayName: String): Result<DeviceInfo> =
        postJson(
            "/api/v1/devices/register",
            buildJsonObject { put("display_name", displayName) }
        ).map { obj ->
            DeviceInfo(
                deviceId = obj.optString("device_id")
                    ?: throw IllegalStateException("Gateway response missing device_id"),
                displayName = obj.optString("display_name"),
                registeredAt = obj.optString("registered_at"),
                status = obj.optString("status")
            )
        }

    // -------------------------------------------------------------- accounts

    /** POST /accounts/register {username,password,display_name,phone_number} -> {user_id,username,token}. */
    fun registerAccount(
        username: String,
        password: String,
        displayName: String,
        phoneNumber: String = ""
    ): Result<AuthSession> =
        postJson(
            "/accounts/register",
            buildJsonObject {
                put("username", username)
                put("password", password)
                put("display_name", displayName)
                if (phoneNumber.isNotBlank()) put("phone_number", phoneNumber)
            }
        ).map { obj ->
            AuthSession(
                userId = obj.optString("user_id")
                    ?: throw IllegalStateException("Gateway response missing user_id"),
                username = obj.optString("username") ?: username,
                token = obj.optString("token")
                    ?: throw IllegalStateException("Gateway response missing token"),
                phoneNumber = obj.optString("phone_number").orEmpty()
            )
        }

    /** POST /accounts/login {username,password} -> {user_id,username,token}. */
    fun login(username: String, password: String): Result<AuthSession> =
        postJson(
            "/accounts/login",
            buildJsonObject {
                put("username", username)
                put("password", password)
            }
        ).map { obj ->
            AuthSession(
                userId = obj.optString("user_id")
                    ?: throw IllegalStateException("Gateway response missing user_id"),
                username = obj.optString("username") ?: username,
                token = obj.optString("token")
                    ?: throw IllegalStateException("Gateway response missing token")
            )
        }

    /** GET /accounts/users -> global contact directory (public endpoint). */
    fun listUsers(): Result<List<UserEntry>> =
        getJson("/accounts/users").map { obj ->
            val users = obj.array("users") ?: return@map emptyList()
            users.mapNotNull { element ->
                val u = element as? JsonObject ?: return@mapNotNull null
                val id = u.optString("user_id") ?: return@mapNotNull null
                val uname = u.optString("username") ?: return@mapNotNull null
                UserEntry(
                    userId = id,
                    username = uname,
                    displayName = u.optString("display_name").takeUnless { it.isNullOrBlank() } ?: uname,
                    createdAt = u.optString("created_at"),
                    phoneNumber = u.optString("phone_number").orEmpty()
                )
            }
        }

    /** GET /accounts/me (Bearer) -> the signed-in user's profile. */
    fun me(token: String): Result<UserEntry> =
        getJson("/accounts/me", bearer = token).map { obj ->
            UserEntry(
                userId = obj.optString("user_id")
                    ?: throw IllegalStateException("Gateway response missing user_id"),
                username = obj.optString("username") ?: "",
                displayName = obj.optString("display_name").takeUnless { it.isNullOrBlank() }
                    ?: obj.optString("username").orEmpty(),
                createdAt = obj.optString("created_at")
            )
        }

    /** POST /accounts/logout (Bearer) -> invalidates the current token. */
    fun logout(token: String): Result<Unit> =
        postJson("/accounts/logout", buildJsonObject { }, bearer = token).map { }

    /** GET /api/v1/devices -> roster of known devices. */
    fun listDevices(): Result<List<RosterEntry>> =
        getJson("/api/v1/devices").map { obj ->
            val devices = obj.array("devices") ?: return@map emptyList()
            devices.mapNotNull { element ->
                val entry = element as? JsonObject ?: return@mapNotNull null
                val id = entry.optString("device_id") ?: return@mapNotNull null
                RosterEntry(deviceId = id, sessionId = entry.optString("session_id"))
            }
        }

    /** POST /api/v1/sessions/start {"type":"chat"|"call","device_a":"alice","device_b":"bob"} -> session handle. */
    fun startSession(type: String, deviceA: String, deviceB: String): Result<StartedSession> =
        postJson(
            "/api/v1/sessions/start",
            buildJsonObject {
                put("type", type)
                put("device_a", deviceA)
                put("device_b", deviceB)
            }
        ).map { obj ->
            StartedSession(
                sessionId = obj.optString("session_id")
                    ?: throw IllegalStateException("Gateway response missing session_id"),
                type = obj.optString("type"),
                mode = obj.optString("mode")
            )
        }

    /** POST /api/v1/sessions/{id}/end */
    fun endSession(sessionId: String): Result<Unit> =
        postJson("/api/v1/sessions/$sessionId/end", buildJsonObject { }).map { }

    /** GET /api/v1/sessions/{id}/messages -> persisted chat history. */
    fun getMessages(sessionId: String): Result<List<PersistedMessage>> =
        getJson("/api/v1/sessions/$sessionId/messages").map { obj ->
            val msgs = obj.array("messages") ?: return@map emptyList()
            msgs.mapNotNull { element ->
                val m = element as? JsonObject ?: return@mapNotNull null
                PersistedMessage(
                    messageId = m.optString("message_id") ?: return@mapNotNull null,
                    speaker = m.optString("speaker").orEmpty(),
                    text = m.optString("text").orEmpty(),
                    timestamp = m.optString("timestamp"),
                    deliveredTo = m.array("delivered_to")?.mapNotNull {
                        (it as? kotlinx.serialization.json.JsonPrimitive)?.content
                    } ?: emptyList(),
                    readBy = m.array("read_by")?.mapNotNull {
                        (it as? kotlinx.serialization.json.JsonPrimitive)?.content
                    } ?: emptyList()
                )
            }
        }

    /** POST /api/v1/messages/delivered */
    fun markDelivered(messageId: String, user: String): Result<Unit> =
        postJson(
            "/api/v1/messages/delivered",
            buildJsonObject {
                put("message_id", messageId)
                put("user", user)
            }
        ).map { }

    /** POST /api/v1/messages/read */
    fun markRead(messageId: String, user: String): Result<Unit> =
        postJson(
            "/api/v1/messages/read",
            buildJsonObject {
                put("message_id", messageId)
                put("user", user)
            }
        ).map { }

    /** POST /api/v1/calls/invite {"to_user":"bob","from_user":"alice"} -> {invite_id,session_id,status}. */
    fun inviteCall(toUser: String, fromUser: String): Result<CallInvite> =
        postJson(
            "/api/v1/calls/invite",
            buildJsonObject {
                put("to_user", toUser)
                put("from_user", fromUser)
            }
        ).map { obj ->
            CallInvite(
                inviteId = obj.optString("invite_id")
                    ?: throw IllegalStateException("Gateway response missing invite_id"),
                sessionId = obj.optString("session_id")
                    ?: throw IllegalStateException("Gateway response missing session_id"),
                fromUser = obj.optString("from_user").orEmpty(),
                toUser = obj.optString("to_user").orEmpty(),
                status = obj.optString("status").orEmpty()
            )
        }

    /** POST /api/v1/calls/{invite_id}/accept */
    fun acceptCall(inviteId: String): Result<CallInvite> =
        postJson("/api/v1/calls/$inviteId/accept", buildJsonObject { }).map { obj ->
            CallInvite(
                inviteId = obj.optString("invite_id") ?: inviteId,
                sessionId = obj.optString("session_id").orEmpty(),
                fromUser = "",
                toUser = "",
                status = obj.optString("status").orEmpty()
            )
        }

    /** POST /api/v1/calls/{invite_id}/reject */
    fun rejectCall(inviteId: String): Result<String> =
        postJson("/api/v1/calls/$inviteId/reject", buildJsonObject { }).map { obj ->
            obj.optString("status") ?: "rejected"
        }

    /** GET /api/v1/calls/pending?user=bob -> list of incoming invites. */
    fun pendingCalls(user: String): Result<List<CallInvite>> =
        execute(
            Request.Builder()
                .url(url("/api/v1/calls/pending?user=$user"))
                .get()
                .build()
        ).map { obj ->
            val invites = obj.array("invites") ?: return@map emptyList()
            invites.mapNotNull { element ->
                val inv = element as? JsonObject ?: return@mapNotNull null
                CallInvite(
                    inviteId = inv.optString("invite_id") ?: return@mapNotNull null,
                    sessionId = inv.optString("session_id") ?: return@mapNotNull null,
                    fromUser = inv.optString("from_user").orEmpty(),
                    toUser = inv.optString("to_user").orEmpty(),
                    status = inv.optString("status").orEmpty()
                )
            }
        }

    /** POST /api/v1/bank/freeze {"session_id": ...} -> human-readable demo result. */
    fun freezeAccounts(sessionId: String): Result<String> =
        postJson(
            "/api/v1/bank/freeze",
            buildJsonObject { put("session_id", sessionId) }
        ).map { obj ->
            val ok = obj.optBoolean("ok")
            val explicit = obj.optString("result") ?: obj.optString("message") ?: obj.optString("status")
            when {
                ok == true -> "Accounts frozen (demo)"
                !explicit.isNullOrBlank() -> explicit
                else -> "Freeze request acknowledged (demo)"
            }
        }
}
