package pk.trustguard.app.ui.screens

import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.automirrored.filled.Message
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.data.SettingsStore
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.net.UserEntry
import pk.trustguard.app.ui.components.InitialsAvatar
import pk.trustguard.app.ui.components.showToast
import pk.trustguard.app.ui.theme.BrandGradient

/**
 * R CHAT main hub — WhatsApp-style. Gradient top bar with the R CHAT brand,
 * settings + logout actions, a contact list backed by GET /accounts/users
 * (avatars with hashed colours, display name, @username, last-active
 * placeholder), a tap-to-act bottom sheet (Message / Call), a new-chat FAB
 * and a premium empty state.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    onOpenChat: (sessionId: String, peerId: String, peerName: String) -> Unit,
    onStartOutgoingCall: (inviteId: String, sessionId: String, peerId: String, peerName: String) -> Unit,
    onOpenSettings: () -> Unit,
    onLogout: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()
    val api = remember(settings.baseUrl) { GatewayApi(settings.baseUrl) }

    var users by remember { mutableStateOf<List<UserEntry>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var refreshTick by remember { mutableIntStateOf(0) }
    var starting by remember { mutableStateOf(false) }
    var selectedUser by remember { mutableStateOf<UserEntry?>(null) }
    var showNewChatSheet by remember { mutableStateOf(false) }
    var manualPeer by remember { mutableStateOf("") }

    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    val selfUserId = settings.userId
    val contacts = remember(users, selfUserId) {
        users.filter { selfUserId == null || it.userId != selfUserId }
    }

    fun performLogout() {
        scope.launch {
            val token = settings.token
            if (!token.isNullOrBlank()) {
                runCatching {
                    withContext(Dispatchers.IO) { api.logout(token) }
                }
            }
            SettingsStore.clearAuth(context)
            showToast(context, "Logged out")
            onLogout()
        }
    }

    LaunchedEffect(settings.baseUrl, refreshTick) {
        loading = true
        error = null
        val result = withContext(Dispatchers.IO) { api.listUsers() }
        result
            .onSuccess { users = it }
            .onFailure { error = it.message ?: "Failed to load contacts" }
        loading = false
    }

    fun startSession(type: String, peerId: String, peerName: String) {
        if (peerId.isBlank() || starting) return
        val self = settings.username ?: return showToast(context, "Not signed in")
        starting = true
        scope.launch {
            if (type == "call") {
                // WhatsApp-style: send a call invitation and show the ringing
                // screen; audio + timer only start after the peer accepts.
                val inviteResult = withContext(Dispatchers.IO) {
                    api.inviteCall(peerId, self)
                }
                inviteResult
                    .getOrNull()
                    ?.let { invite ->
                        onStartOutgoingCall(
                            Uri.encode(invite.inviteId),
                            Uri.encode(invite.sessionId),
                            Uri.encode(peerId),
                            Uri.encode(peerName)
                        )
                    }
                    ?: showToast(context, "Could not place call")
            } else {
                val result = withContext(Dispatchers.IO) { api.startSession(type, self, peerId) }
                result.onSuccess { session ->
                    onOpenChat(Uri.encode(session.sessionId), Uri.encode(peerId), Uri.encode(peerName))
                }.onFailure {
                    showToast(context, "Could not start chat: ${it.message}")
                }
            }
            starting = false
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        // -------------------------------------------------- gradient top bar
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(BrandGradient)
        ) {
            Column(Modifier.statusBarsPadding()) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        Icons.Filled.Shield,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(26.dp)
                    )
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(
                            text = "R CHAT",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                        Text(
                            text = settings.username?.let { "signed in as @$it" }
                                ?: "demo device mode",
                            style = MaterialTheme.typography.labelSmall,
                            color = Color.White.copy(alpha = 0.85f),
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                    IconButton(onClick = { refreshTick++ }) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh", tint = Color.White)
                    }
                    if (settings.isLoggedIn) {
                        IconButton(onClick = ::performLogout) {
                            Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = "Log out", tint = Color.White)
                        }
                    }
                    IconButton(onClick = onOpenSettings) {
                        Icon(Icons.Filled.Settings, contentDescription = "Settings", tint = Color.White)
                    }
                }
            }
        }

        // -------------------------------------------------- contact list
        Box(modifier = Modifier.fillMaxSize()) {
            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(Modifier.size(34.dp))
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            text = error ?: "",
                            color = MaterialTheme.colorScheme.error,
                            style = MaterialTheme.typography.bodyMedium
                        )
                        Spacer(Modifier.height(8.dp))
                        Button(onClick = { refreshTick++ }) { Text("Retry") }
                    }
                }
                contacts.isEmpty() -> EmptyContacts(
                    onInvite = { refreshTick++ },
                    onManual = { showNewChatSheet = true }
                )
                else -> LazyColumn(modifier = Modifier.fillMaxSize()) {
                    item {
                        Text(
                            text = "Contacts on R CHAT",
                            style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(start = 18.dp, top = 14.dp, bottom = 4.dp)
                        )
                    }
                    items(contacts, key = { it.userId }) { user ->
                        ContactRow(user = user) { selectedUser = user }
                    }
                    item {
                        Text(
                            text = if (settings.isLoggedIn)
                                "Conversations are analysed by the R CHAT scam shield"
                            else
                                "Device demo mode · conversations still run through the scam shield",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp)
                        )
                    }
                }
            }

            // -------------------------------------------------- new chat FAB
            FloatingActionButton(
                onClick = { showNewChatSheet = true },
                containerColor = Color.Transparent,
                modifier = Modifier
                    .align(Alignment.BottomEnd)
                    .padding(20.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(56.dp)
                        .background(BrandGradient, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.AutoMirrored.Filled.Chat, contentDescription = "New chat", tint = Color.White, modifier = Modifier.size(24.dp))
                }
            }
        }
    }

    // -------------------------------------------------- contact action sheet
    selectedUser?.let { user ->
        ModalBottomSheet(
            onDismissRequest = { selectedUser = null },
            sheetState = sheetState
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 28.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                InitialsAvatar(name = user.displayName, size = 72.dp)
                Spacer(Modifier.height(10.dp))
                Text(
                    text = user.displayName,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "@${user.username}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(20.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    SheetAction(
                        icon = Icons.AutoMirrored.Filled.Message,
                        label = "Message",
                        modifier = Modifier.weight(1f),
                        enabled = !starting
                    ) {
                        selectedUser = null
                        startSession("chat", user.username, user.displayName)
                    }
                    SheetAction(
                        icon = Icons.Filled.Call,
                        label = "Call",
                        modifier = Modifier.weight(1f),
                        enabled = !starting
                    ) {
                        selectedUser = null
                        startSession("call", user.username, user.displayName)
                    }
                }
            }
        }
    }

    // -------------------------------------------------- new chat sheet
    if (showNewChatSheet) {
        ModalBottomSheet(
            onDismissRequest = { showNewChatSheet = false },
            sheetState = sheetState
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp)
                    .padding(bottom = 28.dp)
            ) {
                Text(
                    text = "New chat",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(12.dp))
                if (contacts.isEmpty()) {
                    Text(
                        text = "No contacts yet — create a second account on another device, or start a manual session below.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                } else {
                    for (user in contacts.take(6)) {
                        ContactRow(user = user, compact = true) {
                            showNewChatSheet = false
                            startSession("chat", user.username, user.displayName)
                        }
                    }
                }
                Spacer(Modifier.height(16.dp))
                OutlinedTextField(
                    value = manualPeer,
                    onValueChange = { manualPeer = it },
                    label = { Text("Manual peer id (demo)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                Spacer(Modifier.height(10.dp))
                SheetAction(
                    icon = Icons.AutoMirrored.Filled.Message,
                    label = "Start chat with peer id",
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !starting && manualPeer.isNotBlank()
                ) {
                    showNewChatSheet = false
                    val peer = manualPeer.trim()
                    startSession("chat", peer, peer)
                }
            }
        }
    }
}

@Composable
private fun ContactRow(user: UserEntry, compact: Boolean = false, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .padding(horizontal = 16.dp, vertical = if (compact) 8.dp else 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        InitialsAvatar(name = user.displayName, size = if (compact) 44.dp else 52.dp)
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = user.displayName,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = "@${user.username}" +
                    if (user.phoneNumber.isNotBlank()) " · ${user.phoneNumber}" else " · Active recently",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
        if (!compact) {
            Icon(
                Icons.AutoMirrored.Filled.Chat,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f),
                modifier = Modifier.size(20.dp)
            )
        }
    }
}

@Composable
private fun SheetAction(
    icon: ImageVector,
    label: String,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    onClick: () -> Unit
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        shape = MaterialTheme.shapes.large,
        colors = ButtonDefaults.buttonColors(
            containerColor = MaterialTheme.colorScheme.primary,
            contentColor = Color.White
        ),
        modifier = modifier
    ) {
        Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp))
        Spacer(Modifier.width(8.dp))
        Text(label)
    }
}

@Composable
private fun EmptyContacts(onInvite: () -> Unit, onManual: () -> Unit) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Box(
            modifier = Modifier
                .size(72.dp)
                .background(
                    Brush.linearGradient(
                        listOf(
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.14f),
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.04f)
                        )
                    ),
                    CircleShape
                ),
            contentAlignment = Alignment.Center
        ) {
            Icon(
                Icons.AutoMirrored.Filled.Chat,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(32.dp)
            )
        }
        Spacer(Modifier.height(16.dp))
        Text(
            text = "No contacts yet",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(6.dp))
        Text(
            text = "Create a second account on another device, or search for a username below to start chatting.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = androidx.compose.ui.text.style.TextAlign.Center
        )
        Spacer(Modifier.height(16.dp))
        Button(onClick = onInvite) { Text("Refresh contacts") }
        Spacer(Modifier.height(6.dp))
        Surface(
            onClick = onManual,
            shape = MaterialTheme.shapes.large,
            color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        ) {
            Text(
                text = "Search for a username",
                style = MaterialTheme.typography.labelLarge,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp)
            )
        }
    }
}
