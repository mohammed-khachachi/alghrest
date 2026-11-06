"use client";
import { useLanguage, tr } from "../../i18n";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet, fmt, fmtBig } from "../../lib/api";
import { useWidgetSymbol, type WidgetInstance } from "../../store/terminal";

type OptionRow = {
  strike: number | null; lastPrice: number | null; bid: number | null; ask: number | null;
  volume: number | null; openInterest: number | null; impliedVolatility?: number | null; inTheMoney: boolean;
};
type Chain = {
  symbol: string; underlyingPrice: number | null; expirationDates: string[];
  selectedDate: string | null; calls: OptionRow[]; puts: OptionRow[];
};

export default function OptionsWidget({ widget }: { widget: WidgetInstance }) {
  useLanguage();
  const symbol = useWidgetSymbol(widget);
  const [expiry, setExpiry] = useState<string | undefined>();

  const { data, error, isLoading } = useQuery({
    queryKey: ["options", symbol, expiry],
    queryFn: () => apiGet<Chain>(`/api/options/${encodeURIComponent(symbol)}${expiry ? `?expiry=${encodeURIComponent(expiry)}` : ""}`),
    refetchInterval: 20_000,
    retry: 0,
  });

  if (error)
    return (
      <div className="p-2">
        <div className="down">{tr("Option chain unavailable for ")}{tr(symbol)}</div>
        <div className="dim">{tr((error as Error).message)}</div>
      </div>
    );
  if (isLoading || !data) return <div className="p-2 dim">{tr("Loading option chain…")}</div>;

  const byStrike = new Map<number, { call?: OptionRow; put?: OptionRow }>();
  for (const c of data.calls) if (c.strike !== null) byStrike.set(c.strike, { ...byStrike.get(c.strike), call: c });
  for (const p of data.puts) if (p.strike !== null) byStrike.set(p.strike, { ...byStrike.get(p.strike), put: p });
  const strikes = [...byStrike.keys()].sort((a, b) => a - b);

  return (
    <div>
      <div className="flex gap-2 items-center p-1">
        <span className="dim">{tr("Underlying")}</span>
        <span className="amber font-bold">{tr(fmt(data.underlyingPrice))}</span>
        <span className="dim ml-2">{tr("Expiry")}</span>
        <select
          value={expiry ?? data.selectedDate ?? ""}
          onChange={(e) => setExpiry(e.target.value)}
        >
          {data.expirationDates.map((d) => (
            <option key={d} value={d}>{tr(d)}</option>
          ))}
        </select>
      </div>
      <table className="data-table">
        <thead>
          <tr>
            <th colSpan={5} className="!text-center up">{tr("CALLS")}</th>
            <th className="!text-center">{tr("STRIKE")}</th>
            <th colSpan={5} className="!text-center down">{tr("PUTS")}</th>
          </tr>
          <tr>
            <th>{tr("Last")}</th><th>{tr("Bid")}</th><th>{tr("Ask")}</th><th>{tr("Vol")}</th><th>{tr("OI · IV")}</th>
            <th></th>
            <th>{tr("Last")}</th><th>{tr("Bid")}</th><th>{tr("Ask")}</th><th>{tr("Vol")}</th><th>{tr("OI · IV")}</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((strike) => {
            const { call, put } = byStrike.get(strike)!;
            return (
              <tr key={strike}>
                <td className={call?.inTheMoney ? "bg-[#0d2010]" : ""}>{tr(fmt(call?.lastPrice))}</td>
                <td className={call?.inTheMoney ? "bg-[#0d2010]" : ""}>{tr(fmt(call?.bid))}</td>
                <td className={call?.inTheMoney ? "bg-[#0d2010]" : ""}>{tr(fmt(call?.ask))}</td>
                <td className={call?.inTheMoney ? "bg-[#0d2010]" : ""}>{tr(fmtBig(call?.volume))}</td>
                <td className={call?.inTheMoney ? "bg-[#0d2010]" : ""}>
                  {tr(fmtBig(call?.openInterest))} · {tr(call?.impliedVolatility ? fmt(call.impliedVolatility * 100, 0) + "%" : "—")}
                </td>
                <td className="!text-center font-bold amber">{tr(fmt(strike))}</td>
                <td className={put?.inTheMoney ? "bg-[#200d0d]" : ""}>{tr(fmt(put?.lastPrice))}</td>
                <td className={put?.inTheMoney ? "bg-[#200d0d]" : ""}>{tr(fmt(put?.bid))}</td>
                <td className={put?.inTheMoney ? "bg-[#200d0d]" : ""}>{tr(fmt(put?.ask))}</td>
                <td className={put?.inTheMoney ? "bg-[#200d0d]" : ""}>{tr(fmtBig(put?.volume))}</td>
                <td className={put?.inTheMoney ? "bg-[#200d0d]" : ""}>
                  {tr(fmtBig(put?.openInterest))} · {tr(put?.impliedVolatility ? fmt(put.impliedVolatility * 100, 0) + "%" : "—")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
