package pk.trustguard.app.ui.screens

import android.media.MediaPlayer
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import pk.trustguard.app.data.rememberAppSettings
import pk.trustguard.app.net.AckInfo
import pk.trustguard.app.net.ChatSocketListener
import pk.trustguard.app.net.ChatSocketManager
import pk.trustguard.app.net.GatewayApi
import pk.trustguard.app.net.StartedSession
import pk.trustguard.app.net.toWsUrl
import pk.trustguard.app.ui.components.SectionLabel
import pk.trustguard.app.ui.components.showToast
import pk.trustguard.director.DirectorScripts
import pk.trustguard.director.ScriptLine

/**
 * Director panel: pick a scripted scam scenario, open a chat session as the
 * scammer side and push its lines one by one over the chat WebSocket.
 * Also lists the pre-recorded clip files expected under assets/director/clips.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DirectorPanelScreen(onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val settings = rememberAppSettings()

    var selectedFile by rememberSaveable { mutableStateOf(DirectorScripts.SCRIPT_FILES.first()) }
    var scriptsByName by remember { mutableStateOf<Map<String, List<ScriptLine>>>(emptyMap()) }
    var clipNames by remember { mutableStateOf<Set<String>>(emptySet()) }

    LaunchedEffect(Unit) {
        scriptsByName = DirectorScripts.SCRIPT_FILES.associateWith { file ->
            runCatching { DirectorScripts.loadLines(context, file) }.getOrElse { emptyList() }
        }
        clipNames = runCatching {
            context.assets.list(DirectorScripts.CLIP_DIR)?.toSet() ?: emptySet()
        }.getOrElse { emptySet() }
    }

    val lines = scriptsByName[selectedFile].orEmpty()
    val sendableLines = lines.filter { it.speaker.equals("them", ignoreCase = true) }

    // Account username when logged in, otherwise the legacy device id.
    val wsIdentity = settings.username ?: settings.deviceId

    // Scripted session state.
    var session by remember { mutableStateOf<StartedSession?>(null) }
    var chatManager by remember { mutableStateOf<ChatSocketManager?>(null) }
    var connected by remember { mutableStateOf(false) }
    var sentCount by remember { mutableStateOf(0) }
    var startingSession by remember { mutableStateOf(false) }

    DisposableEffect(chatManager) {
        onDispose { chatManager?.close() }
    }

    fun beginScriptedSession() {
        if (session != null || startingSession || wsIdentity == null) return
        startingSession = true
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                GatewayApi(settings.baseUrl).startSession("chat", wsIdentity ?: "director", "peer")
            }
            result.onSuccess { started ->
                val manager = ChatSocketManager(
                    url = toWsUrl(settings.baseUrl, "/ws/chat/${started.sessionId}"),
                    deviceId = wsIdentity ?: return@onSuccess,
                    token = settings.token,
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
                            // The director only pushes lines; incoming traffic is ignored here.
                        }

                        override fun onAck(info: AckInfo) {
                            // Acks are surfaced on the receiving device's chat screen.
                        }
                    }
                )
                manager.connect()
                chatManager = manager
                session = started
                sentCount = 0
            }.onFailure {
                showToast(context, "Could not start session: ${it.message}")
            }
            startingSession = false
        }
    }

    fun sendNextLine() {
        val manager = chatManager ?: return
        if (sentCount >= sendableLines.size) return
        val line = sendableLines[sentCount]
        manager.sendMessage(line.text, speaker = "them")
        line.crossChannelOtpText?.let { otpText ->
            manager.sendMessage(otpText, speaker = "them")
        }
        sentCount += 1
    }

    fun endScriptedSession() {
        val current = session ?: return
        scope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    GatewayApi(settings.baseUrl).endSession(current.sessionId)
                }
            }
            chatManager?.close()
            chatManager = null
            session = null
            connected = false
            sentCount = 0
        }
    }

    fun playClip(name: String) {
        if (name !in clipNames) {
            showToast(context, "clip not recorded yet")
            return
        }
        runCatching {
            val player = MediaPlayer()
            context.assets.openFd("${DirectorScripts.CLIP_DIR}/$name").use { afd ->
                player.setDataSource(afd.fileDescriptor, afd.startOffset, afd.length)
            }
            player.setOnCompletionListener { it.release() }
            player.prepare()
            player.start()
        }.onFailure {
            showToast(context, "Playback failed: ${it.message}")
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Director Panel") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(horizontal = 16.dp)
                .verticalScroll(rememberScrollState())
        ) {
            SectionLabel("Scenario script")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (file in DirectorScripts.SCRIPT_FILES) {
                    FilterChip(
                        selected = selectedFile == file,
                        onClick = { selectedFile = file },
                        label = {
                            Text(
                                text = file.removePrefix("scenario_").removeSuffix(".json"),
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis
                            )
                        }
                    )
                }
            }

            Card(Modifier.fillMaxWidth().padding(top = 8.dp)) {
                LazyColumn(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 220.dp)
                ) {
                    items(lines) { line ->
                        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 6.dp)) {
                            Text(
                                text = "#${line.n} · ${line.speaker} · pause ${line.pauseMs} ms",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Text(
                                text = line.text +
                                    (line.crossChannelOtpText?.let { "\n↳ OTP cross-channel: $it" } ?: ""),
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)
                    }
                    if (lines.isEmpty()) {
                        item {
                            Text(
                                text = "Script not found in assets.",
                                color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall,
                                modifier = Modifier.padding(12.dp)
                            )
                        }
                    }
                }
            }

            SectionLabel("Scripted session")
            val current = session
            if (current == null) {
                Button(
                    onClick = ::beginScriptedSession,
                    enabled = !startingSession && wsIdentity != null
                ) {
                    Text(if (wsIdentity == null) "Register first" else "Start scripted session")
                }
                Text(
                    text = "Opens a chat session from this device; push scammer lines to the victim phone.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(top = 4.dp)
                )
            } else {
                Text(
                    text = "session ${current.sessionId} · " +
                        "${minOf(sentCount + 1, sendableLines.size)}/${sendableLines.size} · " +
                        (if (connected) "chat connected" else "chat connecting…"),
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium
                )
                LinearProgressIndicator(
                    progress = {
                        if (sendableLines.isEmpty()) 0f else sentCount.toFloat() / sendableLines.size
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 8.dp)
                )
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Button(
                        onClick = ::sendNextLine,
                        enabled = connected && sentCount < sendableLines.size
                    ) { Text("Send next line") }
                    OutlinedButton(onClick = ::endScriptedSession) { Text("End session") }
                }
            }

            SectionLabel("Pre-recorded clips (${DirectorScripts.CLIP_DIR}/)")
            if (lines.isEmpty()) {
                Text(
                    text = "Select a scenario to see its clip files.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            } else {
                for (line in lines) {
                    ClipHintRow(
                        fileName = DirectorScripts.clipNameFor(line.n),
                        exists = DirectorScripts.clipNameFor(line.n) in clipNames,
                        onPlay = ::playClip
                    )
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun ClipHintRow(fileName: String, exists: Boolean, onPlay: (String) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(
            Icons.Filled.PlayArrow,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Column(Modifier.weight(1f).padding(start = 4.dp)) {
            Text(fileName, style = MaterialTheme.typography.bodyMedium)
            Text(
                text = if (exists) "recorded" else "not recorded yet",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
        IconButton(onClick = { onPlay(fileName) }) {
            Icon(Icons.Filled.PlayArrow, contentDescription = "Play $fileName")
        }
    }
}
