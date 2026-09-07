import type { Band } from '../types';
import { bandColor, coerceNumber } from '../format';
import { BandChip } from './common';

const CX = 110;
const CY = 112;
const R = 86;
const ARC_LEN = Math.PI * R;

function tick(angleDeg: number): { x1: number; y1: number; x2: number; y2: number } {
  const rad = (angleDeg * Math.PI) / 180;
  const c = Math.cos(rad);
  const s = Math.sin(rad);
  return {
    x1: CX + c * (R - 14),
    y1: CY - s * (R - 14),
    x2: CX + c * (R + 2),
    y2: CY - s * (R + 2),
  };
}

/** Semicircular SVG risk gauge for a 0-100 score. */
export default function RiskGauge({ score, band }: { score: unknown; band: Band }) {
  const n = coerceNumber(score) ?? 0;
  const clamped = Math.max(0, Math.min(100, n));
  const arcPath = `M ${CX - R} ${CY} A ${R} ${R} 0 0 1 ${CX + R} ${CY}`;
  const offset = ARC_LEN * (1 - clamped / 100);

  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 220 128" role="img" aria-label={`Risk score ${Math.round(clamped)} of 100`}>
        {[180, 135, 90, 45, 0].map((a) => {
          const t = tick(a);
          return <line key={a} {...t} stroke="var(--border)" strokeWidth="2" />;
        })}
        <path d={arcPath} fill="none" stroke="var(--track)" strokeWidth="15" strokeLinecap="round" />
        <path
          d={arcPath}
          fill="none"
          stroke={bandColor(band)}
          strokeWidth="15"
          strokeLinecap="round"
          strokeDasharray={`${ARC_LEN} ${ARC_LEN}`}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.6s ease, stroke 0.3s ease' }}
        />
        <text x={CX} y={CY - 16} textAnchor="middle" className="gauge-num">
          {Math.round(clamped)}
        </text>
        <text x={CX} y={CY + 4} textAnchor="middle" className="gauge-sub">
          / 100
        </text>
      </svg>
      <div className="gauge-band">
        <BandChip band={band} />
      </div>
    </div>
  );
}
