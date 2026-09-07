import type { SafeAction } from './types';

/** Best-effort numeric coercion for loosely typed gateway payloads. */
export function coerceNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

const BAND_COLORS: Record<string, string> = {
  low: '#22c55e',
  medium: '#eab308',
  med: '#eab308',
  high: '#f97316',
  critical: '#ef4444',
  crit: '#ef4444',
};

export function normalizeBand(band: unknown): string {
  return String(band ?? '').trim().toLowerCase();
}

export function bandColor(band: unknown): string {
  return BAND_COLORS[normalizeBand(band)] ?? '#64748b';
}

export function isHighRisk(band: unknown): boolean {
  const b = normalizeBand(band);
  return b === 'high' || b === 'critical';
}

export function fmtMs(v: unknown): string {
  const n = coerceNumber(v);
  return n == null ? '—' : `${Math.round(n)} ms`;
}

/** Accepts fractions (0.02) or percents (2) and renders a percentage. */
export function fmtPct(v: unknown, digits = 1): string {
  const n = coerceNumber(v);
  if (n == null) return '—';
  const pct = n > 0 && n <= 1 ? n * 100 : n;
  return `${pct.toFixed(digits)}%`;
}

export function fmtConfidence(v: unknown): string {
  const n = coerceNumber(v);
  if (n == null) return '—';
  const pct = n > 0 && n <= 1 ? n * 100 : n;
  return `${Math.round(pct)}%`;
}

export function fmtPoints(v: unknown): string {
  const n = coerceNumber(v);
  if (n == null) return '—';
  return Number.isInteger(n) ? `${n}` : n.toFixed(2);
}

export function timeShort(ts: string | number | undefined | null): string {
  if (ts == null || ts === '') return '—';
  let d: Date;
  if (typeof ts === 'number') {
    d = new Date(ts > 1e12 ? ts : ts * 1000);
  } else {
    d = new Date(ts);
    if (Number.isNaN(d.getTime())) return String(ts);
  }
  return d.toLocaleTimeString([], { hour12: false });
}

export function signalCount(signals: string[] | number | null | undefined): number {
  if (Array.isArray(signals)) return signals.length;
  return coerceNumber(signals) ?? 0;
}

export function safeActionLabel(action: SafeAction): string {
  if (typeof action === 'string') return action.replaceAll('_', ' ');
  if (action && typeof action === 'object') {
    const rec = action as Record<string, unknown>;
    for (const key of ['label', 'action', 'name', 'title', 'id']) {
      const v = rec[key];
      if (typeof v === 'string' && v.trim() !== '') return v.replaceAll('_', ' ');
    }
    const firstString = Object.values(rec).find((v): v is string => typeof v === 'string');
    return firstString ?? JSON.stringify(action);
  }
  return String(action);
}

export function tierLabel(tier: number | string | undefined): string {
  if (tier == null || tier === '') return '—';
  const t = String(tier).toLowerCase();
  if (t === '1' || t === 't1' || t.includes('rule')) return 'T1 rules';
  if (t === '2' || t === 't2' || t.includes('llm')) return 'T2 LLM';
  return `T${tier}`;
}

export function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}
