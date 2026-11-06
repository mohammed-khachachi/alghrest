"use client";
import { useLanguage, tr } from "../../i18n";

import { useQuery } from "@tanstack/react-query";
import { apiGet, fmt, fmtBig, pctClass } from "../../lib/api";
import Flash from "../Flash";
import { useTerminal } from "../../store/terminal";

type CryptoRow = {
  id: string; symbol: string; name: string; price: number | null;
  changePercent24h: number | null; marketCap: number | null; volume24h: number | null;
  rank: number | null; sparkline: number[];
};
type GlobalStats = { totalMarketCap: number; btcDominance: number; ethDominance: number };

// Feeds can report a null/NaN price for newly-listed or delisted assets.
function fmtPrice(p: number | null): string {
  if (p === null || !isFinite(p)) return "—";
  return p >= 1 ? fmt(p) : p.toPrecision(4);
}

function Sparkline({ data }: { data: number[] }) {
  useLanguage();
  if (data.length < 2) return null;
  const w = 60;
  const h = 16;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const pts = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / (max - min || 1)) * h}`)
    .join(" ");
  const upTrend = data[data.length - 1] >= data[0];
  return (
    <svg width={w} height={h}>
      <polyline points={pts} fill="none" stroke={upTrend ? "#00c853" : "#ff3d3d"} strokeWidth={1} />
    </svg>
  );
}

export default function CryptoWidget() {
  useLanguage();
  const setActiveSymbol = useTerminal((s) => s.setActiveSymbol);
  const { data = [], error } = useQuery({
    queryKey: ["crypto"],
    queryFn: () => apiGet<CryptoRow[]>("/api/crypto"),
    refetchInterval: 1_000,
  });
  const { data: global } = useQuery({
    queryKey: ["crypto-global"],
    queryFn: () => apiGet<GlobalStats>("/api/crypto/global"),
    refetchInterval: 30_000,
  });

  if (error) return <div className="p-2 down">{tr("Error: ")}{tr((error as Error).message)}</div>;

  return (
    <div>
      {global && (
        <div className="flex gap-4 px-2 py-1 border-b border-[var(--border)] dim">
          <span>{tr("Total MCap ")}<span className="text-[var(--text)]">{tr(fmtBig(global.totalMarketCap))}</span></span>
          <span>{tr("BTC.D ")}<span className="amber">{tr(fmt(global.btcDominance, 1))}%</span></span>
          <span>{tr("ETH.D ")}<span className="amber">{tr(fmt(global.ethDominance, 1))}%</span></span>
        </div>
      )}
      <table className="data-table">
        <thead>
          <tr><th>#</th><th>{tr("Asset")}</th><th>{tr("Price")}</th><th>{tr("24h%")}</th><th>{tr("MCap")}</th><th>{tr("Vol 24h")}</th><th>{tr("7d")}</th></tr>
        </thead>
        <tbody>
          {data.map((c) => (
            <tr key={c.id} onClick={() => setActiveSymbol(c.symbol)}>
              <td className="dim">{tr(c.rank ?? "—")}</td>
              <td className="!text-start"><span className="font-bold">{c.symbol}</span> <span className="dim">{c.name}</span></td>
              <td><Flash value={c.price}>{tr(fmtPrice(c.price))}</Flash></td>
              <td className={pctClass(c.changePercent24h)}>
                <Flash value={c.changePercent24h}>{tr(fmt(c.changePercent24h))}%</Flash>
              </td>
              <td>{tr(fmtBig(c.marketCap))}</td>
              <td>{tr(fmtBig(c.volume24h))}</td>
              <td><Sparkline data={c.sparkline.filter((_, i) => i % 4 === 0)} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
