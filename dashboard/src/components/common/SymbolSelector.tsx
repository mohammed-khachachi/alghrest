import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { clsx } from 'clsx';
import { AlertCircle, Check, ChevronDown, Search, X } from 'lucide-react';
import { fetchSymbols } from '@/lib/api';
import {
  ASSET_CLASS_LABEL,
  FALLBACK_SYMBOL_CATALOG,
  type AssetClass,
  type SymbolEntry,
} from '@/types/quotes';
import { Skeleton } from '@/components/common/Skeleton';

interface Props {
  value: string[];
  onChange: (symbols: string[]) => void;
}

export function SymbolSelector({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);

  const { data: symbols, isLoading, error } = useQuery({
    queryKey: ['symbols'],
    queryFn: fetchSymbols,
    staleTime: 60 * 60 * 1000, // catalog rarely changes
    retry: 1,
  });

  // If /api/symbols is down (mock_server.py not running), fall back to the
  // built-in catalog so the dropdown is still usable for dashboard demos.
  const effectiveSymbols = symbols ?? (error ? FALLBACK_SYMBOL_CATALOG : undefined);
  const usingFallback = !!error && !symbols;

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  const grouped = useMemo(() => {
    if (!effectiveSymbols) return new Map<AssetClass, SymbolEntry[]>();
    const q = query.trim().toLowerCase();
    const filtered = q
      ? effectiveSymbols.filter(
          (s) =>
            s.symbol.toLowerCase().includes(q) ||
            s.name.toLowerCase().includes(q),
        )
      : effectiveSymbols;
    const m = new Map<AssetClass, SymbolEntry[]>();
    for (const s of filtered) {
      const arr = m.get(s.asset_class) ?? [];
      arr.push(s);
      m.set(s.asset_class, arr);
    }
    return m;
  }, [symbols, query]);

  const selected = new Set(value);

  const toggle = (sym: string) => {
    const next = new Set(selected);
    if (next.has(sym)) next.delete(sym);
    else next.add(sym);
    onChange(Array.from(next));
  };

  const clear = () => onChange([]);

  const label =
    value.length === 0
      ? 'Select symbols…'
      : value.length <= 3
        ? value.join(', ')
        : `${value.slice(0, 2).join(', ')} +${value.length - 2}`;

  return (
    <div ref={panelRef} className="relative w-full md:w-80">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={clsx(
          'flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm transition',
          'bg-bg-surface border-white/8 hover:border-white/20',
          open && 'border-white/30',
        )}
      >
        <span className={clsx(value.length === 0 && 'text-text-muted')}>{label}</span>
        <div className="flex items-center gap-2">
          {value.length > 0 && (
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                clear();
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  e.stopPropagation();
                  clear();
                }
              }}
              className="rounded p-0.5 text-text-muted hover:bg-white/10 hover:text-white"
              aria-label="Clear selection"
            >
              <X size={14} />
            </span>
          )}
          <ChevronDown size={16} className="text-text-muted" />
        </div>
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-full rounded-lg border border-white/10 bg-bg-surface shadow-xl">
          <div className="flex items-center gap-2 border-b border-white/8 px-3 py-2">
            <Search size={14} className="text-text-muted" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search BTC, EUR/USD, AAPL…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-text-muted"
            />
          </div>

          {usingFallback && (
            <div className="flex items-start gap-2 border-b border-white/8 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-300">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span>
                API unreachable — showing offline catalog. Start{' '}
                <code className="font-mono">python api/mock_server.py</code> for
                live quotes.
              </span>
            </div>
          )}
          <div className="max-h-72 overflow-y-auto py-1">
            {isLoading && (
              <div className="space-y-2 p-3">
                <Skeleton className="h-6 rounded" />
                <Skeleton className="h-6 rounded" />
                <Skeleton className="h-6 rounded" />
              </div>
            )}
            {!isLoading && grouped.size === 0 && (
              <div className="px-3 py-4 text-center text-xs text-text-muted">
                No matches
              </div>
            )}
            {(['crypto', 'forex', 'equity'] as AssetClass[]).map((cls) => {
              const entries = grouped.get(cls);
              if (!entries || entries.length === 0) return null;
              return (
                <div key={cls} className="py-1">
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
                    {ASSET_CLASS_LABEL[cls]}
                  </div>
                  {entries.map((e) => {
                    const isSel = selected.has(e.symbol);
                    return (
                      <button
                        type="button"
                        key={e.symbol}
                        onClick={() => toggle(e.symbol)}
                        className={clsx(
                          'flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm transition',
                          'hover:bg-white/5',
                          isSel && 'bg-white/5',
                        )}
                      >
                        <div className="flex min-w-0 flex-col">
                          <span className="font-mono">{e.symbol}</span>
                          <span className="truncate text-[11px] text-text-muted">
                            {e.name}
                          </span>
                        </div>
                        <Check
                          size={14}
                          className={clsx(
                            'shrink-0 transition',
                            isSel ? 'text-green-400 opacity-100' : 'opacity-0',
                          )}
                        />
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
