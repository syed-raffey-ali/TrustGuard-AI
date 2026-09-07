import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { GATEWAY_URL, WS_BASE } from './config';
import { coerceNumber, isHighRisk } from './format';
import { useGatewaySocket } from './ws';
import type {
  ChatMessage,
  DeltaSignal,
  HealthInfo,
  RiskPush,
  SafeAction,
  ScorePoint,
  SessionDetail,
  SessionTimelineEvent,
  Signal,
  Stats,
  ToastItem,
} from './types';
import MetricsBar from './components/MetricsBar';
import LiveTab from './components/LiveTab';
import EvidenceTab from './components/EvidenceTab';
import ModelRaceTab from './components/ModelRaceTab';
import ProvidersTab from './components/ProvidersTab';
import PasteAnalyzerTab from './components/PasteAnalyzerTab';
import PrivacyTab from './components/PrivacyTab';
import Toasts from './components/Toasts';
import { ConnDot } from './components/common';

type TabId = 'live' | 'evidence' | 'race' | 'providers' | 'paste' | 'privacy';

const TABS: { id: TabId; label: string }[] = [
  { id: 'live', label: 'Live' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'race', label: 'Model Race' },
  { id: 'providers', label: 'Providers' },
  { id: 'paste', label: 'Paste Analyzer' },
  { id: 'privacy', label: 'Privacy' },
];

const TELEMETRY_POLL_MS = 5000;
const TELEMETRY_BUMP_MIN_GAP_MS = 2500;

export default function App() {
  const [tab, setTab] = useState<TabId>('live');

  // ---- gateway telemetry ---------------------------------------------------
  const [stats, setStats] = useState<Stats | null>(null);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [offline, setOffline] = useState(false);

  const refreshTelemetry = useCallback(async () => {
    const [statsRes, healthRes] = await Promise.allSettled([api.stats(), api.health()]);
    let successes = 0;
    if (statsRes.status === 'fulfilled') {
      successes += 1;
      setStats(statsRes.value);
    }
    if (healthRes.status === 'fulfilled') {
      successes += 1;
      setHealth(healthRes.value);
    }
    setOffline(successes === 0);
  }, []);

  useEffect(() => {
    void refreshTelemetry();
    const t = window.setInterval(() => void refreshTelemetry(), TELEMETRY_POLL_MS);
    return () => window.clearInterval(t);
  }, [refreshTelemetry]);

  const lastTelemetryRef = useRef(0);
  const bumpTelemetry = useCallback(() => {
    if (Date.now() - lastTelemetryRef.current > TELEMETRY_BUMP_MIN_GAP_MS) {
      lastTelemetryRef.current = Date.now();
      void refreshTelemetry();
    }
  }, [refreshTelemetry]);

  // ---- toasts / risk alerts --------------------------------------------------
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastSeq = useRef(1);
  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);
  const addToast = useCallback((t: Omit<ToastItem, 'id'>) => {
    const id = toastSeq.current++;
    setToasts((prev) => [...prev.slice(-4), { ...t, id }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((x) => x.id !== id)), 7000);
  }, []);
  const lastAlertRef = useRef<Map<string, string>>(new Map());
  const maybeAlert = useCallback(
    (sid: string, score: number, band: string) => {
      if (!isHighRisk(band)) return;
      if (lastAlertRef.current.get(sid) === band) return;
      lastAlertRef.current.set(sid, band);
      const critical = band.trim().toLowerCase() === 'critical';
      addToast({
        kind: critical ? 'critical' : 'high',
        title: `${critical ? 'Critical' : 'High'} risk detected`,
        body: `session ${sid} · score ${Math.round(score)} · band ${band}`,
      });
    },
    [addToast],
  );

  // ---- dashboard event stream (/ws/dashboard) ---------------------------------
  const [sessionsSeen, setSessionsSeen] = useState<string[]>([]);
  const [dashRisk, setDashRisk] = useState<Record<string, { score: number; band: string }>>({});
  const [timelineEvents, setTimelineEvents] = useState<Record<string, SessionTimelineEvent[]>>({});

  const addTimelineEvent = useCallback((sid: string, evt: SessionTimelineEvent) => {
    setTimelineEvents((prev) => ({
      ...prev,
      [sid]: [...(prev[sid] ?? []).slice(-49), evt],
    }));
  }, []);

  const registerSession = useCallback((id: unknown) => {
    if (typeof id !== 'string' || id === '') return;
    setSessionsSeen((prev) => (prev.includes(id) ? prev : [id, ...prev]));
  }, []);

  const dashStatus = useGatewaySocket(`${WS_BASE}/ws/dashboard`, {
    onMessage: (data) => {
      if (!data || typeof data !== 'object') return;
      const msg = data as Record<string, unknown>;
      const type = typeof msg.type === 'string' ? msg.type : '';
      const nested =
        msg.risk_update && typeof msg.risk_update === 'object'
          ? (msg.risk_update as Record<string, unknown>)
          : null;
      const sid =
        typeof nested?.session_id === 'string'
          ? nested.session_id
          : typeof msg.session_id === 'string'
            ? msg.session_id
            : null;
      const score = coerceNumber(nested?.score ?? msg.score);
      const band = String(nested?.band ?? msg.band ?? '');

      if (sid) registerSession(sid);

      if (type === 'risk_update' && sid != null) {
        if (score != null) {
          setDashRisk((prev) => ({ ...prev, [sid]: { score, band } }));
          maybeAlert(sid, score, band);
          addTimelineEvent(sid, { ts: Date.now(), kind: 'risk_update', detail: `score ${Math.round(score)} · band ${band}`, band, score });
        }
        bumpTelemetry();
      }
      if (type === 'alert_dismissed' && sid != null) {
        addTimelineEvent(sid, { ts: Date.now(), kind: 'alert_dismissed', detail: `alert dismissed (band ${band})`, band });
      }
      if (type === 'session_started' && sid != null) {
        addTimelineEvent(sid, { ts: Date.now(), kind: 'session_started', detail: 'session started' });
      }
      if (type === 'bank_action' && sid != null) {
        addTimelineEvent(sid, { ts: Date.now(), kind: 'bank_action', detail: `bank action: ${(msg.action as string) ?? 'freeze'}` });
      }
      if (type === 'device_registered' || type === 'session_started' || type === 'bank_action') {
        bumpTelemetry();
      }
    },
  });

  // ---- selected session ---------------------------------------------------------
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const selectSession = useCallback((id: string | null) => {
    setSelectedId(id && id !== '' ? id : null);
  }, []);

  const startChatSession = useCallback(async () => {
    setStarting(true);
    try {
      const res = await api.startSession('chat');
      if (typeof res.session_id === 'string' && res.session_id !== '') {
        registerSession(res.session_id);
        setSelectedId(res.session_id);
      }
    } catch (err) {
      addToast({
        kind: 'error',
        title: 'Could not start chat session',
        body: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setStarting(false);
    }
  }, [addToast, registerSession]);

  // ---- per-session state ----------------------------------------------------------
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [riskPush, setRiskPush] = useState<RiskPush | null>(null);
  const [riskHistory, setRiskHistory] = useState<ScorePoint[]>([]);
  const [seedSignals, setSeedSignals] = useState<Record<string, Signal>>({});
  const [liveSignals, setLiveSignals] = useState<Record<string, Signal>>({});
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Session snapshot from REST (messages/transcript, score history, signals).
  const loadDetail = useCallback(async () => {
    if (!selectedId) return;
    setDetailLoading(true);
    setDetailError(null);
    try {
      const d = await api.getSession(selectedId);
      setDetail(d);
      setSeedSignals((prev) => {
        const seed: Record<string, Signal> = {};
        for (const s of d.signals ?? []) {
          if (s && typeof s.type === 'string') seed[s.type] = { ...s };
        }
        // Keep live deltas the REST snapshot does not know about yet.
        for (const [k, v] of Object.entries(prev)) {
          if (!(k in seed)) seed[k] = v;
        }
        return seed;
      });
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : String(err));
    } finally {
      setDetailLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    setChatMessages([]);
    setRiskPush(null);
    setRiskHistory([]);
    setSeedSignals({});
    setLiveSignals({});
    setDetail(null);
    setDetailError(null);
    void loadDetail();
  }, [loadDetail]);

  // ---- per-session chat socket (/ws/chat/{id}) -------------------------------------
  const chatStatus = useGatewaySocket(
    selectedId ? `${WS_BASE}/ws/chat/${encodeURIComponent(selectedId)}` : null,
    {
      onOpen: (sock) => {
        sock.send({ type: 'register', device_id: 'dashboard-viewer' });
      },
      onMessage: (data) => {
        if (!data || typeof data !== 'object') return;
        const msg = data as Record<string, unknown>;
        if (msg.type !== 'message') return;
        const cm: ChatMessage = {
          speaker: typeof msg.speaker === 'string' ? msg.speaker : undefined,
          text: typeof msg.text === 'string' ? msg.text : undefined,
          message_id:
            typeof msg.message_id === 'string' || typeof msg.message_id === 'number'
              ? msg.message_id
              : undefined,
          timestamp: typeof msg.timestamp === 'string' ? msg.timestamp : undefined,
        };
        setChatMessages((prev) => [...prev, cm]);
      },
    },
  );

  // ---- per-session risk socket (/ws/session/{id}/risk) ------------------------------
  const riskStatus = useGatewaySocket(
    selectedId ? `${WS_BASE}/ws/session/${encodeURIComponent(selectedId)}/risk` : null,
    {
      onMessage: (data) => {
        if (!data || typeof data !== 'object') return;
        const msg = data as Record<string, unknown>;
        const score = coerceNumber(msg.score);
        if (score == null) return;
        const band = String(msg.band ?? 'unknown');
        const push: RiskPush = {
          score,
          band,
          delta_signals: Array.isArray(msg.delta_signals) ? (msg.delta_signals as DeltaSignal[]) : [],
          stage: typeof msg.stage === 'string' ? msg.stage : undefined,
          safe_actions: Array.isArray(msg.safe_actions) ? (msg.safe_actions as SafeAction[]) : undefined,
        };
        setRiskPush(push);
        setRiskHistory((prev) => [...prev, { ts: Date.now(), score, band }]);
        if (selectedId) maybeAlert(selectedId, score, band);

        setLiveSignals((prev) => {
          const next = { ...prev };
          for (const d of push.delta_signals ?? []) {
            if (!d || typeof d.type !== 'string') continue;
            const severity = coerceNumber(d.severity) ?? coerceNumber(d.contribution) ?? 0;
            const confidence = coerceNumber(d.confidence) ?? 0;
            const existing = next[d.type];
            if (!existing || severity >= (coerceNumber(existing.contribution) ?? 0)) {
              next[d.type] = {
                type: d.type,
                contribution: severity,
                confidence,
                tier: 2,
                explanation:
                  typeof d.explanation === 'string' ? d.explanation : existing?.explanation,
                evidence:
                  typeof d.evidence_ref === 'string'
                    ? { quote: d.evidence_ref }
                    : existing?.evidence,
              };
            }
          }
          return next;
        });
      },
    },
  );

  // ---- derived view data ---------------------------------------------------------------
  const selectedDashRisk = selectedId ? dashRisk[selectedId] ?? null : null;
  const hist = detail?.score_history ?? [];
  const lastHist = hist.length > 0 ? hist[hist.length - 1] : null;

  const gaugeScore = riskPush?.score ?? selectedDashRisk?.score ?? (lastHist ? coerceNumber(lastHist.score) : null);
  const gaugeBand = riskPush?.band ?? selectedDashRisk?.band ?? lastHist?.band ?? 'unknown';

  const liveSignalList = useMemo(() => Object.values(liveSignals), [liveSignals]);
  const mergedSignals = useMemo(() => {
    const out: Record<string, Signal> = {};
    for (const s of Object.values(seedSignals)) out[s.type] = s;
    for (const s of Object.values(liveSignals)) {
      const existing = out[s.type];
      if (
        !existing ||
        (coerceNumber(s.contribution) ?? 0) >= (coerceNumber(existing.contribution) ?? 0)
      ) {
        out[s.type] = s;
      }
    }
    return Object.values(out);
  }, [seedSignals, liveSignals]);

  const mergedHistory = useMemo<ScorePoint[]>(() => {
    const rest = (detail?.score_history ?? []).map((p) => ({
      ts: p.ts,
      score: coerceNumber(p.score) ?? 0,
      band: p.band,
    }));
    return [...rest, ...riskHistory];
  }, [detail, riskHistory]);

  // ---- render ---------------------------------------------------------------------------
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">TG</span>
          <div>
            <h1>TrustGuard AI</h1>
            <span className="brand-sub">mission control dashboard</span>
          </div>
        </div>
        <div className="top-meta">
          <span className="chip mono primary-chip" title="PRIMARY_MODEL from /health">
            PRIMARY_MODEL: {health?.primary_model ?? '—'}
          </span>
          <span className="chip mono muted-chip" title="Gateway base URL">{GATEWAY_URL}</span>
          <ConnDot status={offline ? 'closed' : dashStatus} label="events" />
        </div>
      </header>

      {offline && (
        <div className="offline-banner" role="alert">
          <span>
            Gateway offline — no response from <code>{GATEWAY_URL}</code>. Retrying automatically every{' '}
            {TELEMETRY_POLL_MS / 1000}s.
          </span>
          <button type="button" className="btn btn-small" onClick={() => void refreshTelemetry()}>
            Retry now
          </button>
        </div>
      )}

      <MetricsBar stats={stats} health={health} />

      <nav className="tabs" role="tablist" aria-label="Dashboard panels">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === 'live' && (
          <LiveTab
            sessions={sessionsSeen}
            dashRisk={dashRisk}
            timelineEvents={selectedId ? timelineEvents[selectedId] ?? [] : []}
            selectedId={selectedId}
            onSelect={(id) => selectSession(id)}
            onStartChat={() => void startChatSession()}
            starting={starting}
            chatStatus={chatStatus}
            riskStatus={riskStatus}
            chatMessages={chatMessages}
            segments={detail?.transcript_segments ?? []}
            gaugeScore={gaugeScore}
            gaugeBand={gaugeBand}
            stage={riskPush?.stage ?? null}
            signals={mergedSignals}
          />
        )}
        {tab === 'evidence' && (
          <EvidenceTab
            sessionId={selectedId}
            detail={detail}
            loading={detailLoading}
            error={detailError}
            onRefresh={() => void loadDetail()}
            liveSignals={liveSignalList}
            scoreHistory={mergedHistory}
          />
        )}
        {tab === 'race' && (
          <ModelRaceTab
            sessions={sessionsSeen}
            suggestedSessionId={selectedId}
            primaryModel={health?.primary_model ?? null}
          />
        )}
        {tab === 'providers' && <ProvidersTab />}
        {tab === 'paste' && <PasteAnalyzerTab />}
        {tab === 'privacy' && <PrivacyTab />}
      </main>

      <Toasts toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
