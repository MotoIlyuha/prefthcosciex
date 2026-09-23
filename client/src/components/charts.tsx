// Hand-drawn SVG charts: no chart library in the main bundle (300 KB budget, 11.10).
import type { ProgressDay } from "../lib/types";

export function CoinsChart({ days, threshold, cap }: { days: ProgressDay[]; threshold: number; cap: number }) {
  const width = 320;
  const height = 140;
  const top = Math.max(cap, ...days.map((d) => d.coins)) || cap;
  const barWidth = width / Math.max(1, days.length);
  const y = (v: number) => height - (v / top) * (height - 8);
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="Монеты по дням">
      {days.map((d, i) => {
        const h = height - y(d.coins);
        const cls = d.today ? "bar-today" : d.vacation || d.easy ? "bar-grey" : d.threshold_met ? "bar-met" : "bar-miss";
        return (
          <rect key={d.date} x={i * barWidth + 1} y={y(d.coins)} width={Math.max(1, barWidth - 2)} height={h} className={cls}>
            <title>{`${d.date}: ${d.coins} 🪙`}</title>
          </rect>
        );
      })}
      <line x1={0} x2={width} y1={y(threshold)} y2={y(threshold)} className="line-threshold" />
      <line x1={0} x2={width} y1={y(cap)} y2={y(cap)} className="line-cap" />
    </svg>
  );
}

export function Heatmap({ days }: { days: ProgressDay[] }) {
  const size = 14;
  const gap = 3;
  const weeks = Math.ceil(days.length / 7);
  return (
    <svg viewBox={`0 0 ${weeks * (size + gap)} ${7 * (size + gap)}`} className="heatmap" role="img" aria-label="Календарь серии">
      {days.map((d, i) => {
        const col = Math.floor(i / 7);
        const row = i % 7;
        const cls = d.threshold_met ? "hm-met" : d.vacation ? "hm-vac" : d.coins > 0 ? "hm-some" : "hm-none";
        return (
          <rect key={d.date} x={col * (size + gap)} y={row * (size + gap)} width={size} height={size} rx={3} className={cls}>
            <title>{d.date}</title>
          </rect>
        );
      })}
    </svg>
  );
}

export function LineChart({ points, max }: { points: { label: string; value: number }[]; max: number }) {
  const width = 320;
  const height = 120;
  if (points.length < 2) return null;
  const step = width / (points.length - 1);
  const path = points
    .map((p, i) => `${i ? "L" : "M"}${(i * step).toFixed(1)},${(height - (p.value / max) * (height - 10)).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="Сравнение экзаменов">
      <path d={path} className="line-main" fill="none" />
      {points.map((p, i) => (
        <circle key={p.label + i} cx={i * step} cy={height - (p.value / max) * (height - 10)} r={3} className="dot">
          <title>{`${p.label}: ${p.value}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function Ring({ value, threshold, cap }: { value: number; threshold: number; cap: number }) {
  const r = 22;
  const c = 2 * Math.PI * r;
  const pct = Math.min(1, value / cap);
  const mark = (threshold / cap) * 360 - 90;
  const mx = 28 + r * Math.cos((mark * Math.PI) / 180);
  const my = 28 + r * Math.sin((mark * Math.PI) / 180);
  return (
    <svg viewBox="0 0 56 56" className="ring" role="img" aria-label={`${value} из ${cap}, порог ${threshold}`}>
      <circle cx={28} cy={28} r={r} className="ring-bg" />
      <circle
        cx={28}
        cy={28}
        r={r}
        className={value >= threshold ? "ring-fg ring-met" : "ring-fg"}
        strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 28 28)"
      />
      <circle cx={mx} cy={my} r={3} className="ring-mark" />
      <text x={28} y={32} textAnchor="middle" className="ring-text">{value}</text>
    </svg>
  );
}
