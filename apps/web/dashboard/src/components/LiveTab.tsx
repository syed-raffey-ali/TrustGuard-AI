import { useEffect, useRef } from 'react';
import type { Band, ChatMessage, SessionTimelineEvent, Signal, SocketStatus, TranscriptSegment } from '../types';
import { bandColor, coerceNumber, fmtConfidence, fmtPoints, timeShort } from '../format';
import RiskGauge from './RiskGauge';
import { BandChip, ConnDot, EmptyState, TierBadge } from './common';

interface ThreadItem {
  key: string;
  speaker: string;
  text: string;
  ts?: string;
}

interface LiveTabProps {
  sessions: string[];
  dashRisk: Record<string, { score: number; band: string }>;
  timelineEvents: SessionTimelineEvent[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onStartChat: () => void;
  starting: boolean;
  chatStatus: SocketStatus;
  riskStatus: SocketStatus;
  chatMessages: ChatMessage[];
  segments: TranscriptSegment[];
  gaugeScore: number | null;
  gaugeBand: Band;
  stage: string | null;
  signals: Signal[];
}

function SignalBreakdown({ signals }: { signals: Signal[] }) {
  if (signals.length === 0) {
    return <EmptyState>No signals yet — waiting for analysis cycles.</EmptyState>;
  }
  const sorted = [...signals].sort(
    (a, b) => Math.abs(coerceNumber(b.contribution) ?? 0) - Math.abs(coerceNumber(a.contribution) ?? 0),
  );
  const max = Math.max(...sorted.map((s) => Math.abs(coerceNumber(s.contribution) ?? 0)), 1);

  return (
    <ul className="signal-list">
      {sorted.map((s, i) => {
        const c = Math.abs(coerceNumber(s.contribution) ?? 0);
        const width = Math.max(3, Math.round((c / max) * 100));
        return (
          <li key={`${s.type}-${i}`} className="signal-item">
            <div className="signal-head">
              <span className="signal-type">{s.type.replaceAll('_', ' ')}</span>
              <TierBadge tier={s.tier} />
              <span className="spacer" />
              <span className="signal-conf">{fmtConfidence(s.confidence)} conf</span>
              <span className="signal-points">{fmtPoints(s.contribution)} pts</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill" style={{ width: `${width}%` }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}

const TIMELINE_KIND_LABEL: Record<string, string> = {
  risk_update: 'Risk',
  alert_dismissed: 'Dismissed',
  session_started: 'Started',
  bank_action: 'Bank',
  device_registered: 'Device',
};

function SessionTimeline({ events }: { events: SessionTimelineEvent[] }) {
  if (events.length === 0) {
    return <EmptyState>No timeline events yet.</EmptyState>;
  }
  return (
    <ul className="timeline-list">
      {events.slice().reverse().map((evt, i) => (
        <li key={`${evt.ts}-${i}`} className="timeline-item">
          <span className="timeline-ts">{timeShort(evt.ts)}</span>
          <span
            className={`timeline-kind timeline-kind-${evt.kind}`}
            style={evt.band ? { '--kind-color': bandColor(evt.band) } as React.CSSProperties : undefined}
          >
            {TIMELINE_KIND_LABEL[evt.kind] ?? evt.kind}
          </span>
          <span className="timeline-detail">{evt.detail}</span>
        </li>
      ))}
    </ul>
  );
}

export default function LiveTab(props: LiveTabProps) {
  const {
    sessions, dashRisk, timelineEvents, selectedId, onSelect, onStartChat, starting,
    chatStatus, riskStatus, chatMessages, segments,
    gaugeScore, gaugeBand, stage, signals,
  } = props;

  const thread: ThreadItem[] = [
    ...chatMessages.map((m, i) => ({
      key: `m-${i}-${String(m.message_id ?? '')}`,
      speaker: String(m.speaker ?? 'unknown'),
      text: String(m.text ?? m.content ?? ''),
      ts: typeof m.timestamp === 'string' ? m.timestamp : undefined,
    })),
    ...segments.map((s, i) => ({
      key: `s-${i}`,
      speaker: String(s.speaker ?? s.role ?? 'caller'),
      text: String(s.text ?? ''),
    })),
  ];

  const feedRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [thread.length]);

  return (
    <div className="tab-body">
      <div className="toolbar">
        <button type="button" className="btn btn-primary" onClick={onStartChat} disabled={starting}>
          {starting ? 'Starting…' : 'Start Chat Session'}
        </button>
        <span className="toolbar-dots">
          <ConnDot status={chatStatus} label="chat" />
          <ConnDot status={riskStatus} label="risk" />
        </span>
      </div>

      {/* ---- Session list with live score/band ---- */}
      <section className="panel session-list-panel">
        <header className="panel-head">
          <h2>Live sessions</h2>
          <span className="muted small">{sessions.length} session{sessions.length === 1 ? '' : 's'}</span>
        </header>
        {sessions.length === 0 ? (
          <EmptyState>No sessions seen yet. Start a chat session or wait for gateway events.</EmptyState>
        ) : (
          <ul className="session-card-list">
            {sessions.map((id) => {
              const risk = dashRisk[id];
              const color = risk ? bandColor(risk.band) : '#64748b';
              const isSelected = id === selectedId;
              return (
                <li key={id}>
                  <button
                    type="button"
                    className={`session-card ${isSelected ? 'session-card-active' : ''}`}
                    onClick={() => onSelect(isSelected ? null : id)}
                    style={{ '--card-accent': color } as React.CSSProperties}
                  >
                    <span className="session-card-id">{id}</span>
                    {risk ? (
                      <span className="session-card-meta">
                        <span className="session-card-score">{Math.round(risk.score)}</span>
                        <BandChip band={risk.band} />
                      </span>
                    ) : (
                      <span className="session-card-meta muted small">no risk data</span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {!selectedId ? (
        <EmptyState>
          Select a session above to view its transcript, risk gauge, and signal breakdown.
        </EmptyState>
      ) : (
        <>
          {/* ---- Session timeline ---- */}
          <section className="panel timeline-panel">
            <header className="panel-head">
              <h2>Session timeline</h2>
              <span className="mono small muted">{selectedId}</span>
            </header>
            <SessionTimeline events={timelineEvents} />
          </section>

          <div className="live-grid">
            <section className="panel transcript-panel">
              <header className="panel-head">
                <h2>Transcript</h2>
                <span className="mono small muted">{selectedId}</span>
              </header>
              <div className="transcript-feed" ref={feedRef}>
                {thread.length === 0 ? (
                  <EmptyState>
                    Waiting for messages&hellip; the dashboard is registered as{' '}
                    <code>dashboard-viewer</code> on this session&apos;s chat channel.
                  </EmptyState>
                ) : (
                  thread.map((item) => {
                    const self = /\b(me|customer|user|you|agent)\b/i.test(item.speaker);
                    return (
                      <div key={item.key} className={`bubble-row ${self ? 'bubble-self' : ''}`}>
                        <div className="bubble">
                          <div className="bubble-meta">
                            <span className="bubble-speaker">{item.speaker}</span>
                            {item.ts && <span className="bubble-ts">{item.ts}</span>}
                          </div>
                          <div className="bubble-text">{item.text}</div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </section>

            <section className="side-col">
              <div className="panel gauge-panel">
                <header className="panel-head">
                  <h2>Risk</h2>
                  {stage && <span className="chip stage-chip" title="Analysis stage">{stage}</span>}
                </header>
                <RiskGauge score={gaugeScore} band={gaugeBand} />
              </div>

              <div className="panel">
                <header className="panel-head">
                  <h2>Signal breakdown</h2>
                  <span className="muted small">{signals.length} signal{signals.length === 1 ? '' : 's'}</span>
                </header>
                <SignalBreakdown signals={signals} />
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
