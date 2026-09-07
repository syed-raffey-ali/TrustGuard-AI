package pk.trustguard.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.AckInfo
import pk.trustguard.app.net.ChatSocketListener
import pk.trustguard.app.net.ChatSocketManager
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.net.RiskSocketManager
import pk.trustguard.app.net.RiskState
import pk.trustguard.app.net.toWsUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.ui.components.InitialsAvatar
import pk.trustguard.app.ui.components.ScamAlertBanner
import pk.trustguard.app.ui.components.ScamAlertState
import pk.trustguard.app.ui.components.ScamAlertWatcher
import pk.trustguard.app.ui.components.ShieldIndicator
import pk.trustguard.app.ui.components.Tier1HitChips
import pk.trustguard.app.ui.components.bandSeverity
import pk.trustguard.app.ui.theme.BrandGradient
import pk.trustguard.app.ui.theme.ChatCanvasLight
import pk.trustguard.tier1.Tier1Hit
import pk.trustguard.tier1.Tier1Rules
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** One rendered chat bubble. */
data class ChatUiMessage(
    val messageId: String,
    val text: String,
    val mine: Boolean,
    val sentAtMs: Long = System.currentTimeMillis(),
    val hits: List<Tier1Hit> = emptyList(),
    val elapsedMs: Long? = null,
    val ackHits: List<Tier1Hit> = emptyList(),
    val ackLatencyMs: Double? = null,
    val otpArmed: Boolean? = null,
    val isDelivered: Boolean = false,
    val isRead: Boolean = false
)

private val TimeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())

/**
 * R CHAT conversation: premium WhatsApp-style bubbles (rounded with grouped
 * tails + timestamps), a rounded composer with a gradient send FAB, a top bar
 * with the peer's avatar, and the same LIVE SCAM DETECTION banner as the call
 * screen (band >= medium with vibration + verified-contact dismissal), since
 * chat messages are analysed too.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    sessionId: String,
    peerId: String,
    peerName: String? = null,
    onBack: () -> Unit
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()
    val api = remember(settings.baseUrl) { GatewayApi(settings.baseUrl) }
    val peerLabel = peerName?.takeIf { it.isNotBlank() } ?: peerId

    val messages = remember { mutableStateListOf<ChatUiMessage>() }
    val seenMessageIds = remember { HashSet<String>() }
    var input by rememberSaveable { mutableStateOf("") }
    var risk by remember { mutableStateOf(RiskState.EMPTY) }
    val alertState = remember { ScamAlertState() }
    var connected by remember { mutableStateOf(false) }
    var chatManager by remember { mutableStateOf<ChatSocketManager?>(null) }
    var riskSocketRef by remember { mutableStateOf<RiskSocketManager?>(null) }
    val listState = rememberLazyListState()

    val wsIdentity = settings.username ?: settings.deviceId

    // Load persisted chat history when opening the screen.
    //
    // IMPORTANT: settings (username) load asynchronously from DataStore, so
    // wsIdentity starts out null. If we loaded history with a null identity,
    // `mine` would be false for EVERY message — my own bubbles would all
    // render on the left ("my messages vanished"). Wait for the identity,
    // compare case-insensitively (the server stores the canonical lowercase
    // username), and REPLACE any previously loaded copies on re-run.
    LaunchedEffect(sessionId, settings.baseUrl, wsIdentity) {
        if (sessionId.isBlank() || wsIdentity.isNullOrBlank()) return@LaunchedEffect
        val me = wsIdentity
        val history = withContext(Dispatchers.IO) { api.getMessages(sessionId) }
        history.getOrNull()?.let { persisted ->
            val loaded = persisted.map { m ->
                val isMine = m.speaker.equals(me, ignoreCase = true)
                ChatUiMessage(
                    messageId = m.messageId,
                    text = m.text,
                    mine = isMine,
                    isDelivered = m.deliveredTo.any { !it.equals(me, ignoreCase = true) },
                    isRead = m.readBy.any { !it.equals(me, ignoreCase = true) }
                )
            }
            val loadedIds = loaded.mapTo(HashSet()) { it.messageId }
            messages.removeAll { it.messageId in loadedIds }
            seenMessageIds += loadedIds
            messages.addAll(0, loaded)
            // Mark all incoming messages as read since the chat is now open.
            loaded.filter { !it.mine }.forEach { m ->
                if (!m.isRead) {
                    scope.launch(Dispatchers.IO) { api.markRead(m.messageId, me) }
                    chatManager?.sendReadReceipt(m.messageId)
                }
            }
        }
    }

    // Victim-only alerting: the server names the alert recipients explicitly
    // (risk.alertTargets = everyone except the sender of the flagged content).
    // Fallback heuristic when the session topology is unknown: if the last 3
    // messages are all from "me", I'm the scammer — suppress the alert.
    val iAmLikelyVictim = remember(messages, risk.alertTargets) {
        if (risk.alertTargets.isNotEmpty()) {
            val me = wsIdentity?.lowercase()
            me != null && me in risk.alertTargets
        } else {
            val recent = messages.takeLast(3)
            recent.isEmpty() || recent.any { !it.mine }
        }
    }

    // Live-scam alert vibration trigger — only vibrate if I'm the victim.
    ScamAlertWatcher(risk = risk, alertState = alertState, enabled = iAmLikelyVictim)

    DisposableEffect(sessionId, settings.baseUrl, wsIdentity) {
        val identity = wsIdentity
        var manager: ChatSocketManager? = null
        var riskSocket: RiskSocketManager? = null
        if (identity != null && sessionId.isNotBlank()) {
            manager = ChatSocketManager(
                url = toWsUrl(settings.baseUrl, "/ws/chat/$sessionId"),
                deviceId = identity,
                token = settings.token,
                speakerId = identity,
                listener = object : ChatSocketListener {
                    override fun onChatConnected() {
                        connected = true
                    }

                    override fun onChatDisconnected() {
                        connected = false
                    }

                    override fun onIncoming(
                        speaker: String,
                        text: String,
                        messageId: String,
                        timestamp: Long?
                    ) {
                        if (messageId.isNotEmpty() && !seenMessageIds.add(messageId)) return
                        val displayId = messageId.ifEmpty { "in_${System.nanoTime()}" }
                        messages.add(ChatUiMessage(messageId = displayId, text = text, mine = false))
                        // Chat is open, so mark the incoming message as read immediately.
                        scope.launch(Dispatchers.IO) {
                            api.markRead(displayId, wsIdentity ?: return@launch)
                        }
                        chatManager?.sendReadReceipt(displayId)
                    }

                    override fun onAck(info: AckInfo) {
                        val index = messages.indexOfFirst { it.messageId == info.messageId }
                        if (index >= 0) {
                            messages[index] = messages[index].copy(
                                ackHits = info.hits,
                                ackLatencyMs = info.latencyMs,
                                otpArmed = info.crossChannelOtpArmed
                            )
                        }
                    }

                    override fun onReceipt(messageId: String, kind: String, user: String) {
                        val index = messages.indexOfFirst { it.messageId == messageId }
                        if (index >= 0) {
                            val current = messages[index]
                            messages[index] = current.copy(
                                isDelivered = current.isDelivered || kind == "delivered_receipt" || kind == "read_receipt",
                                isRead = current.isRead || kind == "read_receipt"
                            )
                        }
                    }
                }
            )
            riskSocket = RiskSocketManager(
                url = toWsUrl(settings.baseUrl, "/ws/session/$sessionId/risk"),
                onRisk = { state ->
                    risk = state
                }
            )
            manager.connect()
            riskSocket.connect()
            chatManager = manager
            riskSocketRef = riskSocket
        }
        onDispose {
            manager?.close()
            riskSocket?.close()
            if (chatManager === manager) chatManager = null
            if (riskSocketRef === riskSocket) riskSocketRef = null
        }
    }

    fun sendMessageNow(textRaw: String): Boolean {
        val text = textRaw.trim()
        if (text.isEmpty()) return false
        // Local Tier-1 sweep runs synchronously; measure the wall-clock cost.
        var elapsedMs: Long? = null
        val hits = Tier1Rules.scan(text) { measured -> elapsedMs = measured }
        val id = chatManager?.sendMessage(text)
            ?: "m_offline_${System.currentTimeMillis()}"
        seenMessageIds.add(id)
        messages.add(
            ChatUiMessage(messageId = id, text = text, mine = true, hits = hits, elapsedMs = elapsedMs)
        )
        return true
    }

    fun dismissAlert() {
        riskSocketRef?.sendAlertDismissed("user_verified")
        alertState.dismissAt(bandSeverity(risk.band))
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.lastIndex)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        InitialsAvatar(name = peerLabel, size = 38.dp)
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text(peerLabel, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(
                                text = if (connected) "online · protected by scam shield"
                                else "connecting…",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (connected) MaterialTheme.colorScheme.primary
                                else MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    ShieldIndicator(band = risk.band, modifier = Modifier.padding(end = 16.dp))
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        },
        bottomBar = {
            Column(Modifier.imePadding().navigationBarsPadding()) {
                // Only show the scam alert banner if I'm likely the victim (receiving scam messages).
                if (iAmLikelyVictim) {
                    ScamAlertBanner(
                        risk = risk,
                        alertState = alertState,
                        onDismiss = ::dismissAlert,
                        onEndCall = null,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 10.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.Bottom
                ) {
                    OutlinedTextField(
                        value = input,
                        onValueChange = { input = it },
                        placeholder = { Text("Message") },
                        shape = RoundedCornerShape(26.dp),
                        colors = OutlinedTextFieldDefaults.colors(
                            unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
                            focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.30f),
                            unfocusedBorderColor = Color.Transparent,
                            focusedBorderColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.5f)
                        ),
                        modifier = Modifier.weight(1f),
                        maxLines = 4
                    )
                    Spacer(Modifier.width(8.dp))
                    // Gradient send FAB.
                    Surface(
                        onClick = {
                            if (sendMessageNow(input)) input = ""
                        },
                        enabled = connected && input.isNotBlank(),
                        shape = CircleShape,
                        color = Color.Transparent,
                        modifier = Modifier.size(52.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .fillMaxSize()
                                .background(BrandGradient, CircleShape),
                            contentAlignment = Alignment.Center
                        ) {
                            Icon(
                                Icons.AutoMirrored.Filled.Send,
                                contentDescription = "Send",
                                tint = Color.White,
                                modifier = Modifier.size(22.dp)
                            )
                        }
                    }
                }
            }
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(ChatCanvasLight)
        ) {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    start = 10.dp, end = 10.dp, top = 10.dp, bottom = 6.dp
                ),
                verticalArrangement = Arrangement.spacedBy(2.dp)
            ) {
                item {
                    Text(
                        text = "Messages in this chat are analysed for scam signals",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 6.dp),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center
                    )
                }
                items(messages) { message ->
                    MessageBubble(message)
                }
                item { Spacer(Modifier.padding(top = 8.dp)) }
            }
        }
    }
}

/** Premium WhatsApp-style bubble: 20dp rounded, grouped tail corner, timestamp. */
@Composable
private fun MessageBubble(message: ChatUiMessage) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 8.dp, vertical = 3.dp),
        horizontalAlignment = if (message.mine) Alignment.End else Alignment.Start
    ) {
        val bubbleShape = if (message.mine) {
            RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp, bottomStart = 20.dp, bottomEnd = 6.dp)
        } else {
            RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp, bottomStart = 6.dp, bottomEnd = 20.dp)
        }
        if (message.mine) {
            Box(
                modifier = Modifier
                    .widthIn(max = 300.dp)
                    .background(BrandGradient, bubbleShape)
            ) {
                Text(
                    text = message.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = Color.White,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp)
                )
            }
        } else {
            Surface(
                shape = bubbleShape,
                color = MaterialTheme.colorScheme.surface,
                tonalElevation = 1.dp,
                border = androidx.compose.foundation.BorderStroke(
                    1.dp,
                    MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.6f)
                ),
                modifier = Modifier.widthIn(max = 300.dp)
            ) {
                Text(
                    text = message.text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 9.dp)
                )
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                text = TimeFormat.format(Date(message.sentAtMs)),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
            // WhatsApp-style ticks for my messages.
            if (message.mine) {
                Spacer(Modifier.width(4.dp))
                val tickColor = when {
                    message.isRead -> Color(0xFF53BDEB)   // blue read ticks
                    message.isDelivered -> MaterialTheme.colorScheme.onSurfaceVariant
                    else -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.5f)
                }
                Text(
                    text = if (message.isDelivered || message.isRead) "✓✓" else "✓",
                    style = MaterialTheme.typography.labelSmall,
                    color = tickColor,
                    fontWeight = FontWeight.Bold
                )
            }
            if (message.mine && !message.ackHits.isNullOrEmpty()) {
                Spacer(Modifier.width(6.dp))
                Text(
                    text = "· ${message.ackHits.size} flag(s)",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
        if (message.mine) {
            Tier1HitChips(hits = message.hits, elapsedMs = message.elapsedMs)
        }
    }
}
