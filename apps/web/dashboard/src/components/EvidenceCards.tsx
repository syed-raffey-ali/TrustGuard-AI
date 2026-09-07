import type { Signal } from '../types';
import { fmtConfidence, fmtPoints } from '../format';
import { TierBadge } from './common';

/** One evidence card: label, tier, confidence, quoted evidence, contribution. */
export default function EvidenceCard({ signal, live }: { signal: Signal; live?: boolean }) {
  const quote = typeof signal.evidence?.quote === 'string' ? signal.evidence.quote : '';
  const explanation = typeof signal.explanation === 'string' ? signal.explanation : '';
  const msgIds = Array.isArray(signal.evidence?.message_ids) ? signal.evidence.message_ids : [];

  return (
    <article className="evidence-card">
      <header className="ev-head">
        <span className="ev-type">{signal.type.replaceAll('_', ' ')}</span>
        <TierBadge tier={signal.tier} />
        {live && <span className="chip ev-live">live delta</span>}
        <span className="spacer" />
        <span className="chip ev-conf">{fmtConfidence(signal.confidence)} conf</span>
        <span className="chip ev-pts">{fmtPoints(signal.contribution)} pts</span>
      </header>
      {quote ? (
        <blockquote className="ev-quote">&ldquo;{quote}&rdquo;</blockquote>
      ) : explanation ? (
        <p className="ev-exp">{explanation}</p>
      ) : null}
      {(msgIds.length > 0 || signal.instances != null) && (
        <footer className="ev-foot">
          {msgIds.length > 0 && <span>msgs: {msgIds.join(', ')}</span>}
          {signal.instances != null && <span>instances: {String(signal.instances)}</span>}
        </footer>
      )}
    </article>
  );
}
