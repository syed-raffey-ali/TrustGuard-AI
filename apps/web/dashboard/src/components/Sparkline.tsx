import type { ScorePoint } from '../types';
import { coerceNumber } from '../format';

const W = 600;
const H = 90;
const PAD = 8;

/** Hand-rolled SVG sparkline over the 0-100 score domain. */
export default function Sparkline({ points }: { points: ScorePoint[] }) {
  const scores = points.map((p) => Math.max(0, Math.min(100, coerceNumber(p.score) ?? 0)));
  if (scores.length < 2) {
    return <div className="spark-empty">Collecting score history&hellip;</div>;
  }
  const stepX = (W - PAD * 2) / (scores.length - 1);
  const pts = scores.map((s, i) => [PAD + i * stepX, PAD + (H - PAD * 2) * (1 - s / 100)] as const);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${PAD},${H - PAD} ${line} ${(W - PAD).toFixed(1)},${H - PAD}`;
  const [lx, ly] = pts[pts.length - 1];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="spark" role="img" aria-label="Score history sparkline">
      <polygon points={area} fill="rgba(56,189,248,0.12)" />
      <polyline
        points={line}
        fill="none"
        stroke="#38bdf8"
        strokeWidth="2.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={lx} cy={ly} r="4" fill="#38bdf8" />
    </svg>
  );
}
