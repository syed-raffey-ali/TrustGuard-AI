import { useState } from 'react';
import type { FormEvent } from 'react';
import { api } from '../api';
import type { AnalyzeResponse } from '../types';
import { coerceNumber, errorMessage, fmtMs, fmtPoints, safeActionLabel } from '../format';
import RiskGauge from './RiskGauge';
import EvidenceCard from './EvidenceCards';
import { BandChip, EmptyState, ErrorNote } from './common';
import { SAMPLE_PASTE } from '../samplePaste';

// Backend returns model_comparison_summary either as an object keyed by
// provider or (defensively) an array of entries — normalize before rendering.
function modelSummaryEntries(mcs: unknown): Array<{ provider?: string; model?: string; latency_ms?: number; error?: string | null }> {
  if (Array.isArray(mcs)) return mcs as Array<{ provider?: string; model?: string; latency_ms?: number; error?: string | null }>;
  if (mcs && typeof mcs === 'object') {
    return Object.entries(mcs as Record<string, { latency_ms?: number; ok?: boolean; error?: string | null; signal_count?: number }>)
      .map(([provider, v]) => ({ provider, latency_ms: v?.latency_ms, error: v?.error ?? null }));
  }
  return [];
}

export default function PasteAnalyzerTab() {
  const [text, setText] = useState('');
  const [format, setFormat] = useState<'plain' | 'whatsapp_export'>('whatsapp_export');
  const [unknownCaller, setUnknownCaller] = useState(false);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const prefillSample = () => {
    setText(SAMPLE_PASTE);
    setFormat('whatsapp_export');
  };

  const analyze = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    if (!text.trim()) {
      setError('Paste some transcript text first.');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzePaste({
        text,
        format,
        unknown_caller: unknownCaller || undefined,
      });
      setResult(res);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="tab-body">
      <div className="toolbar">
        <h2 className="toolbar-title">Paste Analyzer</h2>
        <span className="spacer" />
        <button type="button" className="btn" onClick={prefillSample}>
          Load sample scam transcript
        </button>
      </div>

      <form className="panel paste-form" onSubmit={(e) => void analyze(e)}>
        <textarea
          className="input paste-textarea"
          rows={9}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'Paste a call transcript or chat export here…\nSupports plain text or WhatsApp export format ([dd/mm/yy, hh:mm:ss] Speaker: message).'}
        />
        <div className="paste-controls">
          <label className="inline-label" htmlFor="paste-format">Format</label>
          <select
            id="paste-format"
            className="input"
            value={format}
            onChange={(e) => setFormat(e.target.value === 'plain' ? 'plain' : 'whatsapp_export')}
          >
            <option value="plain">plain</option>
            <option value="whatsapp_export">WhatsApp export</option>
          </select>
          <label className="check-wrap">
            <input
              type="checkbox"
              checked={unknownCaller}
              onChange={(e) => setUnknownCaller(e.target.checked)}
            />
            <span>Unknown caller</span>
          </label>
          <span className="spacer" />
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze'}
          </button>
        </div>
        {error && <ErrorNote>{error}</ErrorNote>}
      </form>

      {!result ? (
        <EmptyState>
          Analysis report will appear here: risk gauge, band, stage, safe actions and quoted evidence.
        </EmptyState>
      ) : (
        <>
          <div className="panel paste-report">
            <header className="panel-head">
              <h2>Report</h2>
              <span className="mono small muted">{result.session_id}</span>
            </header>
            <div className="report-grid">
              <RiskGauge score={result.score} band={result.band} />
              <div className="report-facts">
                <div className="fact-row">
                  <span className="fact-label">Band</span>
                  <BandChip band={result.band} />
                </div>
                <div className="fact-row">
                  <span className="fact-label">Stage</span>
                  <span className="chip stage-chip">{result.stage ?? '—'}</span>
                </div>
                <div className="fact-row">
                  <span className="fact-label">Analysis latency</span>
                  <span className={`badge ${coerceNumber(result.analysis_latency_ms) != null && coerceNumber(result.analysis_latency_ms)! >= 4000 ? 'lat-warn' : 'lat-good'}`}>
                    {fmtMs(result.analysis_latency_ms)}
                  </span>
                </div>
                <div className="fact-row">
                  <span className="fact-label">Messages</span>
                  <span>{result.message_count ?? result.messages_preview?.length ?? '—'}</span>
                </div>
                <div className="fact-row">
                  <span className="fact-label">T1 rule hits</span>
                  <span>{result.tier1_hits ?? 0}</span>
                </div>
              </div>
              <div className="report-actions">
                <h3>Safe actions</h3>
                <div className="chips-row">
                  {(result.safe_actions ?? []).map((a, i) => (
                    <span key={i} className="pill action-pill">{safeActionLabel(a)}</span>
                  ))}
                  {(result.safe_actions ?? []).length === 0 && <span className="muted small">none reported</span>}
                </div>

                <h3>Model comparison summary</h3>
                <div className="chips-row">
                  {modelSummaryEntries(result.model_comparison_summary).map((item, i) => {
                    const label = item.provider || item.model || `model ${i + 1}`;
                    const failed = item.error != null && item.error !== '';
                    return (
                      <span key={i} className={`chip ${failed ? 'summary-err' : 'summary-ok'} mono`} title={item.error ?? ''}>
                        {label}: {failed ? 'ERR' : fmtMs(item.latency_ms)}
                      </span>
                    );
                  })}
                  {modelSummaryEntries(result.model_comparison_summary).length === 0 && (
                    <span className="muted small">no comparison data</span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {(result.signals ?? []).length > 0 && (
            <section className="panel">
              <header className="panel-head">
                <h2>Evidence</h2>
                <span className="muted small">
                  total contribution{' '}
                  {fmtPoints((result.signals ?? []).reduce((acc, s) => acc + (coerceNumber(s.contribution) ?? 0), 0))} pts
                </span>
              </header>
              <div className="evidence-grid">
                {(result.signals ?? []).map((s, i) => (
                  <EvidenceCard key={`${s.type}-${i}`} signal={s} />
                ))}
              </div>
            </section>
          )}

          {(result.messages_preview ?? []).length > 0 && (
            <section className="panel">
              <header className="panel-head">
                <h2>Parsed messages</h2>
                <span className="muted small">{result.messages_preview.length} parsed</span>
              </header>
              <ul className="preview-list">
                {result.messages_preview.map((m, i) => (
                  <li key={String(m.message_id ?? i)}>
                    <span className="bubble-speaker">{String(m.speaker ?? '?')}</span>
                    <span className="preview-text">{String(m.text ?? '')}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
