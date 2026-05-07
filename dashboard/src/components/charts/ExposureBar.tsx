interface ExposureBarProps {
  long: number;
  short: number;
}

function fmtUsd(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (abs >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

export function ExposureBar({ long, short }: ExposureBarProps) {
  const total = long + short;
  const longPct = total > 0 ? (long / total) * 100 : 50;
  const shortPct = total > 0 ? (short / total) * 100 : 50;
  const net = long - short;

  return (
    <div className="space-y-3">
      <div className="flex justify-between text-sm font-mono">
        <span className="text-green-400">L {fmtUsd(long)}</span>
        <span className="text-red-400">S {fmtUsd(short)}</span>
      </div>

      {/* Stacked bar */}
      <div className="flex h-4 rounded-full overflow-hidden">
        <div
          className="bg-green-500 transition-all duration-500"
          style={{ width: `${longPct}%` }}
        />
        <div
          className="bg-red-500 transition-all duration-500"
          style={{ width: `${shortPct}%` }}
        />
      </div>

      <div className="flex justify-between text-xs text-text-muted">
        <span>{longPct.toFixed(0)}% Long</span>
        <span
          className={
            net >= 0 ? 'text-green-400 font-mono' : 'text-red-400 font-mono'
          }
        >
          Δ {net >= 0 ? '+' : ''}{fmtUsd(net)}
        </span>
        <span>{shortPct.toFixed(0)}% Short</span>
      </div>
    </div>
  );
}
