// Shared API / WebSocket types for the TrustGuard AI dashboard.
// Fields the backend may omit are optional so the UI degrades gracefully.

export type Band = string;

export interface HealthInfo {
  status: string;
  cloud_providers: string[];
  local_model: string | null;
  primary_model: string | null;
  ml_count?: number;
  tier?: string;
}

export interface GoldenSetBadge {
  precision: number;
  recall: number;
  f1: number;
  band_correct: number;
  injection_pass: number;
}

export interface Stats {
  sessions_analyzed: number;
  active_devices: number;
  median_tier2_latency_ms_local: number | null;
  median_tier2_latency_ms_cloud: number | null;
  json_parse_failure_rate: number;
  tier2_cycles: number;
  golden_set_badge: GoldenSetBadge | null;
}

export interface ProviderInfo {
  name: string;
  base_url: string;
  model: string;
  kind: string; // 'cloud' | 'local'
  priority: number;
  enabled: boolean;
  has_key: boolean;
  key_hint: string | null;
}

export interface ProvidersResponse {
  providers: ProviderInfo[];
  note: string;
}

export interface ProviderUpsert {
  name: string;
  base_url: string;
  model: string;
  api_key?: string;
  priority?: number;
  enabled?: boolean;
}

export interface ProviderTestResult {
  provider: string;
  model: string;
  ok: boolean;
  latency_ms: number | null;
  signals_found: string[];
  error: string | null;
}

export interface SignalEvidence {
  message_ids?: Array<string | number>;
  quote?: string;
}

export interface Signal {
  type: string;
  family?: string;
  severity_norm?: number;
  confidence: number;
  instances?: number;
  contribution: number;
  tier: number | string;
  explanation?: string;
  evidence?: SignalEvidence;
}

/** delta_signals pushed on /ws/session/{id}/risk */
export interface DeltaSignal {
  type: string;
  severity?: number;
  confidence?: number;
  evidence_ref?: string;
  explanation?: string;
  /** tolerated alternative field name */
  contribution?: number;
}

export type SafeAction = string | Record<string, unknown>;

export interface RiskPush {
  score: number;
  band: Band;
  delta_signals?: DeltaSignal[];
  stage?: string;
  safe_actions?: SafeAction[];
}

export interface ScorePoint {
  ts: string | number;
  score: number;
  band: Band;
}

export interface ChatMessage {
  speaker?: string;
  text?: string;
  message_id?: string | number;
  timestamp?: string;
  [key: string]: unknown;
}

export interface TranscriptSegment {
  speaker?: string;
  text?: string;
  [key: string]: unknown;
}

export interface SessionDetail {
  messages: ChatMessage[] | null;
  transcript_segments: TranscriptSegment[] | null;
  score_history: ScorePoint[];
  signals: Signal[];
}

export interface SessionReport {
  score: number;
  band: Band;
  signals: Signal[];
  stage: string;
  safe_actions: SafeAction[];
}

export interface ModelRun {
  model: string;
  provider: string;
  latency_ms: number | null;
  signals: string[] | number | null;
  error: string | null;
}

export interface ComparisonCycle {
  cycle_ts: string | number;
  primary_model: string;
  results: ModelRun[];
}

export interface ModelComparisonResponse {
  results: ComparisonCycle[];
}

export interface ModelSummaryItem {
  model?: string;
  provider?: string;
  latency_ms?: number | null;
  ok?: boolean;
  error?: string | null;
  [key: string]: unknown;
}

export interface AnalyzeResponse {
  session_id: string;
  score: number;
  band: Band;
  stage: string;
  safe_actions: SafeAction[];
  signals: Signal[];
  tier1_hits: number;
  model_comparison_summary: ModelSummaryItem[];
  analysis_latency_ms: number;
  message_count: number;
  messages_preview: ChatMessage[];
}

export interface SessionTimelineEvent {
  ts: number;
  kind: 'risk_update' | 'alert_dismissed' | 'session_started' | 'bank_action' | 'device_registered';
  detail: string;
  band?: string;
  score?: number;
}

export type SocketStatus = 'connecting' | 'open' | 'retrying' | 'closed';

export interface ToastItem {
  id: number;
  kind: 'high' | 'critical' | 'info' | 'success' | 'error';
  title: string;
  body?: string;
}
