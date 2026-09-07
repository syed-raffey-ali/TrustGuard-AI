import type { HealthInfo, Stats } from '../types';
import { fmtMs, fmtPct } from '../format';

function LatencyBadge({ label, value }: { label: string; value: number | null }) {
  const cls = value == null ? 'lat-none' : value < 4000 ? 'lat-good' : 'lat-warn';
  return (
    <div className="lat-item">
      <span className="lat-kind">{label}</span>
      <span className={`badge ${cls}`}>{fmtMs(value)}</span>
    </div>
  );
}

/** Top telemetry strip. Data is owned by App (5s poll + WS-event refresh). */
export default function MetricsBar({ stats, health }: { stats: Stats | null; health: HealthInfo | null }) {
  const gs = stats?.golden_set_badge ?? null;
  const mlCount = health?.ml_count;
  const tier = health?.tier;

  return (
    <section className="metrics-bar" aria-label="Gateway metrics">
      <div className="metric-card">
        <span className="metric-label">Sessions analyzed</span>
        <span className="metric-value">{stats ? stats.sessions_analyzed : '—'}</span>
      </div>

      <div className="metric-card">
        <span className="metric-label">Active devices</span>
        <span className="metric-value">{stats ? stats.active_devices : '—'}</span>
      </div>

      <div className="metric-card">
        <span className="metric-label">Median Tier-2 latency</span>
        <div className="lat-row">
          <LatencyBadge label="local" value={stats?.median_tier2_latency_ms_local ?? null} />
          <LatencyBadge label="cloud" value={stats?.median_tier2_latency_ms_cloud ?? null} />
        </div>
      </div>

      <div className="metric-card">
        <span className="metric-label">JSON parse failures</span>
        <span className="metric-value">{stats ? fmtPct(stats.json_parse_failure_rate) : '—'}</span>
      </div>

      <div className="metric-card">
        <span className="metric-label">ML tier</span>
        {mlCount != null || tier ? (
          <div className="chips-row">
            {tier && <span className="chip gs-chip">{tier}</span>}
            {mlCount != null && <span className="chip gs-chip">{mlCount} model{mlCount === 1 ? '' : 's'}</span>}
          </div>
        ) : (
          <span className="chip gs-pending">—</span>
        )}
      </div>

      <div className="metric-card">
        <span className="metric-label">Golden set eval</span>
        {gs ? (
          <div className="chips-row">
            <span className="chip gs-chip" title={`Precision ${fmtPct(gs.precision)}`}>P {fmtPct(gs.precision, 0)}</span>
            <span className="chip gs-chip" title={`Recall ${fmtPct(gs.recall)}`}>R {fmtPct(gs.recall, 0)}</span>
            <span className="chip gs-chip" title={`F1 ${fmtPct(gs.f1)}`}>F1 {fmtPct(gs.f1, 0)}</span>
            <span className="chip gs-sub" title="band_correct / injection_pass">
              bands {gs.band_correct} &middot; inj {gs.injection_pass}
            </span>
          </div>
        ) : (
          <span className="chip gs-pending">eval pending</span>
        )}
      </div>
    </section>
  );
}
