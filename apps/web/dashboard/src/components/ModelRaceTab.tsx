import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ComparisonCycle, ModelComparisonResponse, ModelRun } from '../types';
import { coerceNumber, fmtMs, signalCount, timeShort } from '../format';
import { EmptyState, ErrorNote } from './common';

interface ModelRaceTabProps {
  sessions: string[];
  /** Session to follow until the viewer picks one manually. */
  suggestedSessionId: string | null;
  primaryModel: string | null;
}

function cellForCycle(cycle: ComparisonCycle, providerKey: string): ModelRun | undefined {
  const matches = (cycle.results ?? []).filter((r) => (r.provider || r.model) === providerKey);
  if (matches.length === 0) return undefined;
  const okRuns = matches.filter((r) => !r.error);
  if (okRuns.length > 0) {
    return okRuns.sort(
      (a, b) => (coerceNumber(a.latency_ms) ?? Infinity) - (coerceNumber(b.latency_ms) ?? Infinity),
    )[0];
  }
  return matches[0];
}

export default function ModelRaceTab({ sessions, suggestedSessionId, primaryModel }: ModelRaceTabProps) {
  const [sessionId, setSessionId] = useState('');
  const [data, setData] = useState<ModelComparisonResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const followedRef = useRef(true);

  // Follow the shared selection until the user picks a session explicitly.
  useEffect(() => {
    if (followedRef.current && suggestedSessionId) setSessionId(suggestedSessionId);
  }, [suggestedSessionId]);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    setLoading(true);
    try {
      const res = await api.getModelComparison(id);
      setData(res);
      setError(null);
      setUpdatedAt(new Date().toLocaleTimeString([], { hour12: false }));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessionId) void load(sessionId);
  }, [sessionId, load]);

  useEffect(() => {
    if (!auto || !sessionId) return;
    const t = window.setInterval(() => void load(sessionId), 3000);
    return () => window.clearInterval(t);
  }, [auto, sessionId, load]);

  const cycles = data?.results ?? [];
  const providers: string[] = [];
  for (const cyc of cycles) {
    for (const run of cyc.results ?? []) {
      const key = run.provider || run.model;
      if (key && !providers.includes(key)) providers.push(key);
    }
  }

  return (
    <div className="tab-body">
      <div className="toolbar">
        <span className="chip mono primary-chip" title="Current PRIMARY_MODEL from /health">
          PRIMARY_MODEL: {primaryModel ?? '—'}
        </span>
        <label className="inline-label" htmlFor="race-session">Session</label>
        <select
          id="race-session"
          className="input select-grow"
          value={sessionId}
          onChange={(e) => {
            followedRef.current = false;
            setSessionId(e.target.value);
          }}
        >
          <option value="">— pick a session —</option>
          {(sessions.includes(sessionId) || !sessionId
            ? sessions
            : [sessionId, ...sessions]
          ).map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <label className="switch-wrap">
          <label className="switch">
            <input
              type="checkbox"
              checked={auto}
              onChange={(e) => setAuto(e.target.checked)}
            />
            <span className="slider" />
          </label>
          <span>Auto-refresh (3 s)</span>
        </label>
        <button type="button" className="btn" onClick={() => void load(sessionId)} disabled={!sessionId || loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
        {updatedAt && <span className="muted small">updated {updatedAt}</span>}
      </div>

      {error && <ErrorNote>Model comparison failed: {error}</ErrorNote>}

      {!sessionId ? (
        <EmptyState>Pick a session to inspect its Tier-2 model comparison cycles.</EmptyState>
      ) : cycles.length === 0 && !error ? (
        <EmptyState>{loading ? 'Loading comparison cycles…' : 'No comparison cycles recorded for this session yet.'}</EmptyState>
      ) : (
        <div className="panel table-panel">
          <table className="tbl race-table">
            <thead>
              <tr>
                <th>Cycle</th>
                {providers.map((p) => (
                  <th key={p}>{p}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...cycles].reverse().map((cycle, idx) => (
                <tr key={`${String(cycle.cycle_ts)}-${idx}`}>
                  <th scope="row">{timeShort(cycle.cycle_ts)}</th>
                  {providers.map((p) => {
                    const run = cellForCycle(cycle, p);
                    if (!run) return <td key={p} className="muted">—</td>;
                    if (run.error) {
                      return (
                        <td key={p} className="race-err" title={run.error}>
                          ERR
                        </td>
                      );
                    }
                    const lat = coerceNumber(run.latency_ms);
                    return (
                      <td key={p} className={lat != null && lat >= 4000 ? 'lat-warn-text' : 'lat-good-text'}>
                        <span className="race-lat">{fmtMs(lat)}</span>
                        <span className="race-count">{signalCount(run.signals)} sig</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
