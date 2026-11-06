import { useLanguage, tr } from "../../i18n";
import { useMemo } from 'react';
import { clsx } from 'clsx';
import { Eye, Filter } from 'lucide-react';
import { useLiveQuotes } from '@/lib/useLiveQuotes';
import { DEFAULT_SELECTED_SYMBOLS } from '@/store/useStore';
import { type Holding } from '@/types/quotes';
import { Skeleton } from '@/components/common/Skeleton';

interface Props {
  selectedSymbols: string[];
  onClearFilter: () => void;
}

interface EnrichedHolding extends Holding {
  current_price: number | null;
  invested: number;
  current_value: number | null;
  pnl_usd: number | null;
  pnl_pct: number | null;
}

interface BrokerGroup {
  broker: string;
  rows: EnrichedHolding[];
  invested: number;
  current: number;
  pnl: number;
  pnlPct: number;
  hasAll: boolean;
}

function fmtUsd(n: number, signed = false): string {
  const sign = signed && n > 0 ? '+' : n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function fmtPct(n: number): string {
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

function priceFmt(value: number, ac: Holding['asset_class'], symbol: string): string {
  if (ac === 'forex') {
    const d = symbol.startsWith('XAU') || symbol.startsWith('XAG') ? 2 : 5;
    return value.toFixed(d);
  }
  if (ac === 'equity') return `$${value.toFixed(2)}`;
  return `$${value.toLocaleString('en-US', { maximumFractionDigits: value < 1 ? 4 : 2 })}`;
}

function volFmt(volume: number, ac: Holding['asset_class']): string {
  if (ac === 'forex') return volume.toLocaleString('en-US', { maximumFractionDigits: 0 });
  return volume.toLocaleString('en-US', { maximumFractionDigits: 4 });
}

function PnlText({ value, pct = false }: { value: number; pct?: boolean }) {
  useLanguage();
  const positive = value > 0;
  const flat = value === 0;
  const text = pct ? fmtPct(value) : fmtUsd(value, true);
  return (
    <span
      className={clsx(
        'font-mono',
        flat && 'text-text-muted',
        positive && 'text-green-400',
        !flat && !positive && 'text-red-400',
      )}
    >
      {tr(text)}
    </span>
  );
}

const ASSET_HINT: Record<Holding['asset_class'], string> = {
  crypto: 'Crypto',
  forex: 'Forex',
  equity: 'Equities',
};

function BrokerSection({ group }: { group: BrokerGroup }) {
  useLanguage();
  const assetClasses = Array.from(new Set(group.rows.map((r) => ASSET_HINT[r.asset_class])));
  return (
    <div className="overflow-hidden rounded-xl border border-white/8 bg-bg-surface">
      <div className="flex items-center justify-between border-b border-white/8 bg-white/[0.02] px-4 py-2">
        <div className="flex items-baseline gap-2">
          <span className="text-sm font-semibold">{tr(group.broker)}</span>
          <span className="text-[10px] uppercase tracking-wider text-text-muted">
            {tr(assetClasses.join(' · '))}
          </span>
        </div>
        <span className="font-mono text-[11px] text-text-muted">
          {tr(group.rows.length)}{tr(" position")}{tr(group.rows.length === 1 ? '' : 's')}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-start font-mono text-xs">
          <thead>
            <tr className="border-b border-white/5 text-[10px] uppercase tracking-wider text-text-muted">
              <th className="px-3 py-2 font-medium">{tr("Symbol")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("Volume")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("Entry")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("Current")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("Invested")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("Value")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("P&L $")}</th>
              <th className="px-3 py-2 text-end font-medium">{tr("P&L %")}</th>
              <th className="px-3 py-2 font-medium">{tr("Opened")}</th>
            </tr>
          </thead>
          <tbody>
            {group.rows.map((h) => (
              <tr
                key={`${h.symbol}-${h.opened_at}`}
                className="border-b border-white/5 last:border-b-0 hover:bg-white/[0.02]"
              >
                <td className="px-3 py-2 font-semibold">{h.symbol}</td>
                <td className="px-3 py-2 text-end">{tr(volFmt(h.volume, h.asset_class))}</td>
                <td className="px-3 py-2 text-end">
                  {priceFmt(h.entry_price, h.asset_class, h.symbol)}
                </td>
                <td className="px-3 py-2 text-end">
                  {tr(h.current_price != null
                    ? priceFmt(h.current_price, h.asset_class, h.symbol)
                    : '—')}
                </td>
                <td className="px-3 py-2 text-end">{tr(fmtUsd(h.invested))}</td>
                <td className="px-3 py-2 text-end">
                  {tr(h.current_value != null ? fmtUsd(h.current_value) : '—')}
                </td>
                <td className="px-3 py-2 text-end">
                  {h.pnl_usd != null ? <PnlText value={h.pnl_usd} /> : '—'}
                </td>
                <td className="px-3 py-2 text-end">
                  {h.pnl_pct != null ? <PnlText value={h.pnl_pct} pct /> : '—'}
                </td>
                <td className="px-3 py-2 text-text-muted">{tr(h.opened_at)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-white/10 bg-white/[0.02] font-semibold">
              <td className="px-3 py-2" colSpan={4}>{tr("Subtotal")}</td>
              <td className="px-3 py-2 text-end">{tr(fmtUsd(group.invested))}</td>
              <td className="px-3 py-2 text-end">
                {tr(group.hasAll ? fmtUsd(group.current) : '—')}
              </td>
              <td className="px-3 py-2 text-end">
                {group.hasAll ? <PnlText value={group.pnl} /> : '—'}
              </td>
              <td className="px-3 py-2 text-end">
                {group.hasAll ? <PnlText value={group.pnlPct} pct /> : '—'}
              </td>
              <td />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export function HoldingsPanel({ selectedSymbols, onClearFilter }: Props) {
  useLanguage();
  const {
    holdings,
    quotesBySymbol,
    holdingsLoading: hLoading,
    holdingsError: hError,
    quotesLoading: qLoading,
    quotesError: qError,
  } = useLiveQuotes();

  const groups: BrokerGroup[] = useMemo(() => {
    if (!holdings) return [];
    const picked = new Set(selectedSymbols.map((s) => s.toUpperCase()));
    const isFiltered = picked.size > 0;

    const enriched: EnrichedHolding[] = holdings
      .filter((h) => !isFiltered || picked.has(h.symbol.toUpperCase()))
      .map((h) => {
        const q = quotesBySymbol.get(h.symbol.toUpperCase());
        const invested = h.volume * h.entry_price;
        if (!q) {
          return {
            ...h,
            current_price: null,
            invested,
            current_value: null,
            pnl_usd: null,
            pnl_pct: null,
          };
        }
        const currentValue = h.volume * q.price;
        const pnlUsd = currentValue - invested;
        const pnlPct = invested > 0 ? (pnlUsd / invested) * 100 : 0;
        return {
          ...h,
          current_price: q.price,
          invested,
          current_value: currentValue,
          pnl_usd: pnlUsd,
          pnl_pct: pnlPct,
        };
      });

    const byBroker = new Map<string, EnrichedHolding[]>();
    for (const e of enriched) {
      const arr = byBroker.get(e.broker) ?? [];
      arr.push(e);
      byBroker.set(e.broker, arr);
    }

    return Array.from(byBroker.entries()).map(([broker, rows]) => {
      let invested = 0;
      let current = 0;
      let hasAll = true;
      for (const r of rows) {
        invested += r.invested;
        if (r.current_value == null) hasAll = false;
        else current += r.current_value;
      }
      const pnl = current - invested;
      const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;
      return { broker, rows, invested, current, pnl, pnlPct, hasAll };
    });
  }, [holdings, quotesBySymbol, selectedSymbols]);

  if (hError) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-300">{tr("Failed to load holdings. Start ")}<code className="font-mono">{tr("python api/mock_server.py")}</code>.
      </div>
    );
  }

  if (hLoading || (qLoading && quotesBySymbol.size === 0)) {
    return <Skeleton className="h-64 rounded-xl" />;
  }

  const isFiltered = selectedSymbols.length > 0;
  const totalHoldings = holdings?.length ?? 0;
  const shownCount = groups.reduce((acc, g) => acc + g.rows.length, 0);
  const defaultCount = DEFAULT_SELECTED_SYMBOLS.length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-col">
          <h2 className="text-sm font-medium uppercase tracking-wider text-text-muted">{tr("Holdings by Broker")}</h2>
          <span className="text-[11px] text-text-muted">
            {tr(isFiltered
              ? `Showing ${shownCount} of ${totalHoldings} available holdings · filtered by ${selectedSymbols.length} symbol${selectedSymbols.length === 1 ? '' : 's'}`
              : `All ${totalHoldings} holdings across ${groups.length} broker${groups.length === 1 ? '' : 's'}`)}
          </span>
        </div>

        {isFiltered && (
          <button
            type="button"
            onClick={onClearFilter}
            title={tr(`Reset filter to the ${defaultCount} default symbols (${totalHoldings} total holdings exist)`)}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white transition hover:border-white/20 hover:bg-white/10"
          >
            <Eye size={12} />{tr("View all holdings (")}{tr(totalHoldings)})
          </button>
        )}
      </div>

      {qError && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-2 text-[11px] text-amber-300">{tr("Live prices stale — using last known quotes.")}</div>
      )}

      {groups.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-white/8 bg-bg-surface p-8 text-center">
          <Filter size={20} className="text-text-muted" />
          <div className="flex flex-col gap-1 text-sm text-text-muted">
            <span>{tr("None of the ")}{tr(totalHoldings)}{tr(" available holdings match the current filter.")}</span>
            <span className="text-[11px]">{tr("Reset to the ")}{tr(defaultCount)}{tr(" default holdings to continue.")}</span>
          </div>
          <button
            type="button"
            onClick={onClearFilter}
            className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-white transition hover:border-white/20 hover:bg-white/10"
          >
            <Eye size={12} />{tr("View all available holdings (")}{tr(totalHoldings)})
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          {groups.map((g) => (
            <BrokerSection key={g.broker} group={g} />
          ))}
        </div>
      )}
    </div>
  );
}
