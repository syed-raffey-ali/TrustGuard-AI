package pk.trustguard.app.audio

import android.annotation.SuppressLint
import android.content.Context
import android.media.AudioAttributes
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.AudioTrack
import android.media.MediaRecorder
import android.os.Process

/**
 * Full-duplex PCM voice engine for TrustGuard demo calls.
 *
 * Capture: AudioRecord, VOICE_COMMUNICATION source, 16 kHz mono PCM16,
 * read in ~100 ms chunks (3200 bytes) and handed to [onCaptureChunk]
 * (typically forwarded to the call WebSocket as binary frames).
 *
 * Playback: AudioTrack in MODE_STREAM; incoming binary WebSocket frames are
 * fed via [playChunk] from the OkHttp reader thread (write() blocks as needed).
 * Optional [context] enables loudspeaker routing via [setLoudspeaker].
 *
 * RECORD_AUDIO must already be granted before calling [start].
 */
class AudioEngine(
    private val context: Context? = null,
    private val onCaptureChunk: (ByteArray) -> Unit
) {

    companion object {
        const val SAMPLE_RATE = 16_000
        const val CHUNK_BYTES = 3_200 // ~100 ms of PCM16 mono at 16 kHz
        private const val CHANNEL_IN = AudioFormat.CHANNEL_IN_MONO
        private const val CHANNEL_OUT = AudioFormat.CHANNEL_OUT_MONO
        private const val ENCODING = AudioFormat.ENCODING_PCM_16BIT
    }

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var captureThread: Thread? = null
    private var focusRequest: AudioFocusRequest? = null

    @Volatile
    private var running = false

    @SuppressLint("MissingPermission") // permission is requested by CallScreen before start()
    fun start() {
        if (running) return

        // Voice-call audio mode + focus: without this, playback can be ducked
        // or stuck on the wrong route (a classic "can't hear each other" cause).
        context?.let { appContext ->
            runCatching {
                val manager = appContext.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
                manager?.mode = AudioManager.MODE_IN_COMMUNICATION
                val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                    .setAudioAttributes(
                        AudioAttributes.Builder()
                            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build()
                    )
                    .setOnAudioFocusChangeListener { }
                    .build()
                manager?.requestAudioFocus(request)
                focusRequest = request
            }
        }

        val minRecordBuffer = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_IN, ENCODING)
        val recordBuffer = maxOf(minRecordBuffer, CHUNK_BYTES * 4)
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            CHANNEL_IN,
            ENCODING,
            recordBuffer
        )

        val minTrackBuffer = AudioTrack.getMinBufferSize(SAMPLE_RATE, CHANNEL_OUT, ENCODING)
        audioTrack = AudioTrack(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build(),
            AudioFormat.Builder()
                .setSampleRate(SAMPLE_RATE)
                .setEncoding(ENCODING)
                .setChannelMask(CHANNEL_OUT)
                .build(),
            maxOf(minTrackBuffer, CHUNK_BYTES * 4),
            AudioTrack.MODE_STREAM,
            AudioManager.AUDIO_SESSION_ID_GENERATE
        )

        running = true
        audioRecord?.startRecording()
        audioTrack?.play()

        captureThread = Thread({ captureLoop() }, "tg-audio-capture").apply { start() }
    }

    private fun captureLoop() {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO)
        val buffer = ByteArray(CHUNK_BYTES)
        while (running) {
            val record = audioRecord ?: break
            val read = record.read(buffer, 0, CHUNK_BYTES)
            if (read > 0) {
                onCaptureChunk(buffer.copyOf(read))
            }
        }
    }

    /** Writes one incoming PCM chunk to the streaming AudioTrack. */
    fun playChunk(chunk: ByteArray) {
        val track = audioTrack ?: return
        runCatching { track.write(chunk, 0, chunk.size) }
    }

    /**
     * Routes playback to the built-in loudspeaker (or back to the default
     * earpiece route when [on] is false). No-op without a [context].
     */
    fun setLoudspeaker(on: Boolean) {
        val track = audioTrack ?: return
        val appContext = context ?: return
        runCatching {
            val manager = appContext.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            val speaker = manager
                ?.getDevices(AudioManager.GET_DEVICES_OUTPUTS)
                ?.firstOrNull { it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER }
            track.preferredDevice = if (on) speaker else null
        }
    }

    /** Stops capture/playback and releases hardware. Idempotent. */
    fun stop() {
        running = false
        captureThread?.let { thread ->
            runCatching { thread.join(500) }
        }
        captureThread = null
        audioRecord?.let { record ->
            runCatching { record.stop() }
            runCatching { record.release() }
        }
        audioRecord = null
        audioTrack?.let { track ->
            runCatching { track.stop() }
            runCatching { track.release() }
        }
        audioTrack = null

        // Restore normal audio routing and drop the call's audio focus.
        context?.let { appContext ->
            runCatching {
                val manager = appContext.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
                focusRequest?.let { manager?.abandonAudioFocusRequest(it) }
                focusRequest = null
                manager?.mode = AudioManager.MODE_NORMAL
            }
        }
    }
}
