import { useLanguage, tr } from "../../i18n";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import type { PnlPoint } from '@/types/ws';

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number }>;
  label?: string;
}

function CustomTooltip({ active, payload, label }: TooltipProps) {
  useLanguage();
  if (!active || !payload?.length) return null;
  const val = payload[0].value;
  return (
    <div className="bg-bg-surface border border-white/10 rounded-lg px-3 py-2 text-xs font-mono">
      <div className="text-text-muted mb-1">{tr(label)}</div>
      <div className={val >= 0 ? 'text-green-400' : 'text-red-400'}>
        {tr(val >= 0 ? '+' : '')}${tr(val.toLocaleString('en-US', { minimumFractionDigits: 2 }))}
      </div>
    </div>
  );
}

export function PnlChart() {
  useLanguage();
  const portfolio = useDashboardStore((s) => s.portfolioSnapshot);

  if (!portfolio) {
    return <Skeleton className="h-48 rounded-lg" />;
  }

  const data: PnlPoint[] = portfolio.pnl_history;

  const isPositive =
    data.length > 0 ? data[data.length - 1].value >= 0 : true;
  const lineColor = isPositive ? '#4ade80' : '#f87171';

  const minVal = Math.min(...data.map((d) => d.value), 0);
  const maxVal = Math.max(...data.map((d) => d.value), 0);

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={lineColor} stopOpacity={0.2} />
            <stop offset="95%" stopColor={lineColor} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="rgba(255,255,255,0.05)"
          vertical={false}
        />
        <XAxis
          dataKey="time"
          tick={{ fill: '#64748b', fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[minVal * 1.05 || -100, maxVal * 1.05 || 100]}
          tick={{ fill: '#64748b', fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) =>
            v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`
          }
          width={60}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />
        <Line
          type="monotone"
          dataKey="value"
          stroke={lineColor}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, fill: lineColor }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
