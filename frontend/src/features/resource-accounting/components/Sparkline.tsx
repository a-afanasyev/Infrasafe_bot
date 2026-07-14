/**
 * Лёгкий inline-SVG мини-график (без recharts — в таблице десятки строк, по одному
 * recharts-контейнеру на строку было бы тяжело). Рисует ломаную расхода + точку
 * последнего значения. Цвет — бренд-акцент (var(--accent)).
 */
interface SparklineProps {
  values: number[];
  unit?: string;
  width?: number;
  height?: number;
}

export function Sparkline({ values, unit = '', width = 104, height = 30 }: SparklineProps) {
  const nums = values.filter((v) => Number.isFinite(v));
  if (nums.length < 2) {
    return <span className="small muted">—</span>;
  }

  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const pad = 3;
  const stepX = (width - pad * 2) / (nums.length - 1);
  const yFor = (v: number) => pad + (height - pad * 2) * (1 - (v - min) / span);

  const points = nums.map((v, i) => `${(pad + i * stepX).toFixed(1)},${yFor(v).toFixed(1)}`);
  const lastX = pad + (nums.length - 1) * stepX;
  const lastY = yFor(nums[nums.length - 1]);
  const title = `${nums.length} мес: ${nums.map((v) => Math.round(v)).join(' → ')} ${unit}`.trim();

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={title}
      style={{ display: 'block' }}
    >
      <title>{title}</title>
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke="var(--accent)"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={lastX} cy={lastY} r={2.2} fill="var(--accent)" />
    </svg>
  );
}
