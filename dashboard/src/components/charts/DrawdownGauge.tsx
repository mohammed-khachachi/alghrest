interface DrawdownGaugeProps {
  value: number;
  max: number;
  warnAt: number;
  unit?: string;
  color?: string;
}

export function DrawdownGauge({
  value,
  max,
  warnAt,
  unit = '%',
  color,
}: DrawdownGaugeProps) {
  const pct = Math.min(value / max, 1);
  const warnPct = warnAt / max;
  const isWarning = value >= warnAt;

  const barColor = color ?? (isWarning ? '#ef4444' : '#4ade80');

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <span className="text-2xl font-bold font-mono" style={{ color: barColor }}>
          {value.toFixed(1)}{unit}
        </span>
        <span className="text-xs text-text-muted">
          / {max}{unit}
        </span>
      </div>

      {/* Bar */}
      <div className="relative h-3 rounded-full bg-white/8 overflow-hidden">
        {/* Warn zone overlay */}
        <div
          className="absolute top-0 right-0 h-full bg-red-900/40 rounded-r-full"
          style={{ width: `${(1 - warnPct) * 100}%` }}
        />
        {/* Fill */}
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
          style={{ width: `${pct * 100}%`, backgroundColor: barColor }}
        />
      </div>

      <div className="flex justify-between text-xs text-text-muted">
        <span>0</span>
        <span className="text-amber-500">{warnAt}{unit}</span>
        <span className="text-red-500">{max}{unit}</span>
      </div>
    </div>
  );
}
