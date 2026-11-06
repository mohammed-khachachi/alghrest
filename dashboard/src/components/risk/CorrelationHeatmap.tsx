import { useLanguage, tr } from "../../i18n";
const STRATEGIES = [
  'Trend', 'MeanRev', 'Momentum', 'StatArb',
  'ML', 'Options', 'MacroRot', 'Breakout',
];

// Seeded correlation matrix (triangular, realistic values)
const BASE_CORR: number[][] = [
  [1.00, 0.12, 0.45, -0.08,  0.33,  0.05,  0.38, 0.51],
  [0.12, 1.00, -0.22, 0.60, -0.14,  0.18, -0.09, 0.07],
  [0.45,-0.22,  1.00, 0.15,  0.58,  0.02,  0.44, 0.62],
  [-0.08, 0.60, 0.15, 1.00, -0.03,  0.21,  0.10,-0.05],
  [0.33,-0.14,  0.58,-0.03,  1.00,  0.09,  0.27, 0.49],
  [0.05, 0.18,  0.02, 0.21,  0.09,  1.00,  0.35, 0.08],
  [0.38,-0.09,  0.44, 0.10,  0.27,  0.35,  1.00, 0.41],
  [0.51, 0.07,  0.62,-0.05,  0.49,  0.08,  0.41, 1.00],
];

function corrColor(v: number): string {
  // -1 → red (#ef4444), 0 → neutral (#1e293b), +1 → green (#22c55e)
  if (v >= 0) {
    const t = v;
    const r = Math.round(34 + (34 - 34) * t);
    const g = Math.round(41 + (197 - 41) * t);
    const b = Math.round(55 + (94 - 55) * t);
    return `rgb(${r},${g},${b})`;
  } else {
    const t = -v;
    const r = Math.round(34 + (239 - 34) * t);
    const g = Math.round(41 + (68 - 41) * t);
    const b = Math.round(55 + (68 - 55) * t);
    return `rgb(${r},${g},${b})`;
  }
}

export function CorrelationHeatmap() {
  useLanguage();
  const n = STRATEGIES.length;

  return (
    <div className="overflow-x-auto">
      <table className="text-xs font-mono border-separate border-spacing-0.5">
        <thead>
          <tr>
            <th className="w-16" />
            {STRATEGIES.map((s) => (
              <th
                key={s}
                className="text-text-muted font-medium text-center px-1 py-1 whitespace-nowrap"
                style={{ minWidth: 56 }}
              >
                {tr(s)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: n }).map((_, row) => (
            <tr key={row}>
              <td className="text-text-muted font-medium pr-2 text-end whitespace-nowrap">
                {tr(STRATEGIES[row])}
              </td>
              {Array.from({ length: n }).map((_, col) => {
                const v = BASE_CORR[row][col];
                const bg = corrColor(v);
                return (
                  <td
                    key={col}
                    style={{ backgroundColor: bg }}
                    className="text-center rounded transition-all duration-300"
                    title={tr(`${STRATEGIES[row]} × ${STRATEGIES[col]}: ${v.toFixed(2)}`)}
                  >
                    <span
                      className="block px-1 py-2 text-center"
                      style={{
                        color: Math.abs(v) > 0.5 ? '#fff' : '#94a3b8',
                        fontSize: '10px',
                      }}
                    >
                      {tr(v === 1.0 ? '1.0' : v.toFixed(2))}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      {/* Legend */}
      <div className="mt-4 flex items-center gap-3 text-xs text-text-muted">
        <span>-1.0</span>
        <div
          className="h-2 flex-1 rounded"
          style={{
            background: 'linear-gradient(to right, #ef4444, #1e293b, #22c55e)',
          }}
        />
        <span>+1.0</span>
      </div>
    </div>
  );
}
