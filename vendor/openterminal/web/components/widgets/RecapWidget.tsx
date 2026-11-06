"use client";
import { useLanguage, currentLocale, tr } from "../../i18n";

import { useQuery } from "@tanstack/react-query";
import { apiGet, fmt, pctClass } from "../../lib/api";
import { isSafeHttpUrl } from "../../lib/links";
import { useTerminal } from "../../store/terminal";
import Flash from "../Flash";

type RecapRow = { symbol: string; name: string; changePercent: number | null };
type RecapIndex = { symbol: string; label: string; price: number | null; changePercent: number | null };
type RecapSector = { sector: string; avgChangePercent: number };
type RecapNews = { title: string; link: string; publisher: string; publishedAt: string | null };

type Recap = {
  summary: string;
  updatedAt: string;
  indexes: RecapIndex[];
  vix: number | null;
  gainers: RecapRow[];
  losers: RecapRow[];
  sectors: RecapSector[];
  news: RecapNews[];
};

export default function RecapWidget() {
  useLanguage();
  const setActiveSymbol = useTerminal((s) => s.setActiveSymbol);
  const { data, error } = useQuery({
    queryKey: ["recap"],
    queryFn: () => apiGet<Recap>("/api/recap"),
    refetchInterval: 15_000,
  });

  if (error) return <div className="p-2 down">{tr("Error: ")}{tr((error as Error).message)}</div>;
  if (!data) return <div className="p-2 dim">{tr("Loading market recap…")}</div>;

  return (
    <div>
      <div className="px-2 py-1 flex justify-between items-baseline">
        <span className="dim text-[10px] uppercase">{tr("Market Recap")}</span>
        <span className="dim text-[9px]">{tr("Updated ")}{tr(new Date(data.updatedAt).toLocaleTimeString(currentLocale()))}
        </span>
      </div>

      <div className="px-2 pb-2 text-[12px] leading-relaxed border-b border-[#161616]">{data.summary}</div>

      <table className="data-table">
        <thead>
          <tr>
            <th>{tr("Index")}</th>
            <th>{tr("Last")}</th>
            <th>{tr("Chg%")}</th>
          </tr>
        </thead>
        <tbody>
          {data.indexes.map((q) => (
            <tr key={q.symbol} onClick={() => setActiveSymbol(q.symbol)}>
              <td>{tr(q.label)}</td>
              <td>
                <Flash value={q.price}>{tr(fmt(q.price))}</Flash>
              </td>
              <td className={pctClass(q.changePercent)}>
                <Flash value={q.changePercent}>{tr(fmt(q.changePercent))}%</Flash>
              </td>
            </tr>
          ))}
          {data.vix !== null && (
            <tr className="cursor-pointer" onClick={() => setActiveSymbol("^VIX")}>
              <td>{tr("VIX")}</td>
              <td colSpan={2}>
                <Flash value={data.vix} className="amber">
                  {tr(fmt(data.vix, 2))}
                </Flash>
              </td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="grid grid-cols-2 gap-x-2 px-2 py-1">
        <div>
          <div className="dim text-[10px] uppercase mb-1">{tr("Top gainers")}</div>
          {data.gainers.map((r) => (
            <div key={r.symbol} className="flex justify-between cursor-pointer hover:bg-[#161616]" onClick={() => setActiveSymbol(r.symbol)}>
              <span className="truncate mr-1">{r.symbol}</span>
              <span className={pctClass(r.changePercent)}>
                <Flash value={r.changePercent}>{tr(fmt(r.changePercent))}%</Flash>
              </span>
            </div>
          ))}
        </div>
        <div>
          <div className="dim text-[10px] uppercase mb-1">{tr("Top losers")}</div>
          {data.losers.map((r) => (
            <div key={r.symbol} className="flex justify-between cursor-pointer hover:bg-[#161616]" onClick={() => setActiveSymbol(r.symbol)}>
              <span className="truncate mr-1">{r.symbol}</span>
              <span className={pctClass(r.changePercent)}>
                <Flash value={r.changePercent}>{tr(fmt(r.changePercent))}%</Flash>
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="px-2 py-1 border-t border-[#161616]">
        <div className="dim text-[10px] uppercase mb-1">{tr("Sector performance")}</div>
        {data.sectors.map((s) => (
          <div key={s.sector} className="flex justify-between">
            <span className="truncate mr-1">{tr(s.sector)}</span>
            <span className={pctClass(s.avgChangePercent)}>{tr(fmt(s.avgChangePercent))}%</span>
          </div>
        ))}
      </div>

      <div className="border-t border-[#161616]">
        <div className="dim text-[10px] uppercase px-2 pt-1">{tr("Headlines")}</div>
        {data.news.map((n, i) => {
          const body = (
            <>
              <div className="truncate">{n.title}</div>
              <div className="dim text-[10px]">{n.publisher}</div>
            </>
          );
          const className = "block px-2 py-1 border-b border-[#161616] hover:bg-[#161616]";
          return isSafeHttpUrl(n.link) ? (
            <a key={i} href={n.link} target="_blank" rel="noreferrer" className={className}>
              {tr(body)}
            </a>
          ) : (
            <div key={i} className={className}>
              {tr(body)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
