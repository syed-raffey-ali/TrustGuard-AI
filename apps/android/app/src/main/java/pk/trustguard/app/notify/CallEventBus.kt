package pk.trustguard.app.notify

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow

/**
 * In-process bus bridging the notification socket / broadcast receivers and
 * the Compose UI (outgoing-call ringing screen, incoming-call route).
 */
object CallEventBus {

    data class CallAccepted(val inviteId: String, val sessionId: String)
    data class CallRejected(val inviteId: String)
    data class IncomingCall(val inviteId: String, val fromUser: String, val sessionId: String)

    private val _accepted = MutableSharedFlow<CallAccepted>(extraBufferCapacity = 8)
    private val _rejected = MutableSharedFlow<CallRejected>(extraBufferCapacity = 8)
    private val _incoming = MutableSharedFlow<IncomingCall>(extraBufferCapacity = 8)

    /** The remote peer accepted our outgoing call. */
    val accepted: SharedFlow<CallAccepted> = _accepted

    /** The remote peer rejected our outgoing call. */
    val rejected: SharedFlow<CallRejected> = _rejected

    /** Someone is calling us (emitted by the notification service). */
    val incoming: SharedFlow<IncomingCall> = _incoming

    fun emitAccepted(inviteId: String, sessionId: String) {
        _accepted.tryEmit(CallAccepted(inviteId, sessionId))
    }

    fun emitRejected(inviteId: String) {
        _rejected.tryEmit(CallRejected(inviteId))
    }

    fun emitIncoming(inviteId: String, fromUser: String, sessionId: String) {
        _incoming.tryEmit(IncomingCall(inviteId, fromUser, sessionId))
    }
}
