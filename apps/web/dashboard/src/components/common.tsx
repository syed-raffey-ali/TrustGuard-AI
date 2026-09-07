import type { ReactNode } from 'react';
import type { CSSProperties } from 'react';
import type { Band, SocketStatus } from '../types';
import { bandColor, normalizeBand, tierLabel } from '../format';

export function BandChip({ band }: { band: Band }) {
  const b = normalizeBand(band) || 'unknown';
  return (
    <span className="chip band-chip" style={{ '--chip-color': bandColor(b) } as CSSProperties}>
      {b}
    </span>
  );
}

export function TierBadge({ tier }: { tier: number | string | undefined }) {
  const label = tierLabel(tier);
  const cls = label.startsWith('T1') ? 'tier-t1' : label.startsWith('T2') ? 'tier-t2' : 'tier-other';
  return <span className={`chip ${cls}`}>{label}</span>;
}

const STATUS_TEXT: Record<SocketStatus, string> = {
  connecting: 'connecting',
  open: 'live',
  retrying: 'reconnecting',
  closed: 'off',
};

export function ConnDot({ status, label }: { status: SocketStatus; label?: string }) {
  return (
    <span className="conn-dot-wrap" title={`${label ?? 'socket'}: ${status}`}>
      <span className={`conn-dot conn-${status}`} />
      <span className="conn-label">{label ?? STATUS_TEXT[status]}</span>
    </span>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="empty-state">{children}</div>;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="error-note">{children}</div>;
}
