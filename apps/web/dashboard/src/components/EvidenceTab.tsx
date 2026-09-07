import type { ScorePoint, SessionDetail, Signal } from '../types';
import Sparkline from './Sparkline';
import EvidenceCard from './EvidenceCards';
import { EmptyState, ErrorNote } from './common';

interface EvidenceTabProps {
  sessionId: string | null;
  detail: SessionDetail | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  liveSignals: Signal[];
  scoreHistory: ScorePoint[];
}

export default function EvidenceTab(props: EvidenceTabProps) {
  const { sessionId, detail, loading, error, onRefresh, liveSignals, scoreHistory } = props;

  if (!sessionId) {
    return (
      <div className="tab-body">
        <EmptyState>Select a session in the Live tab to inspect its evidence.</EmptyState>
      </div>
    );
  }

  const staticSignals = detail?.signals ?? [];

  return (
    <div className="tab-body">
      <div className="toolbar">
        <h2 className="toolbar-title">Evidence</h2>
        <span className="mono small muted">{sessionId}</span>
        <span className="spacer" />
        <button type="button" className="btn" onClick={onRefresh} disabled={loading}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>

      {error && <ErrorNote>Failed to load session: {error}</ErrorNote>}

      <section className="panel">
        <header className="panel-head">
          <h2>Score history</h2>
          <span className="muted small">{scoreHistory.length} point{scoreHistory.length === 1 ? '' : 's'}</span>
        </header>
        <Sparkline points={scoreHistory} />
      </section>

      {staticSignals.length === 0 && liveSignals.length === 0 && !loading ? (
        <EmptyState>No evidence recorded for this session yet.</EmptyState>
      ) : (
        <div className="evidence-grid">
          {staticSignals.map((s, i) => (
            <EvidenceCard key={`static-${s.type}-${i}`} signal={s} />
          ))}
          {liveSignals.map((s, i) => (
            <EvidenceCard key={`live-${s.type}-${i}`} signal={s} live />
          ))}
        </div>
      )}
    </div>
  );
}
