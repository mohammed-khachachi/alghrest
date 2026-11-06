"use client";
import { useLanguage, tr } from "../../i18n";

import { useQuery } from "@tanstack/react-query";
import { apiGet, fmt, fmtBig } from "../../lib/api";
import { useWidgetSymbol, type WidgetInstance } from "../../store/terminal";

type InsiderTransaction = {
  filingDate: string;
  transactionDate: string;
  ownerName: string;
  ownerTitle: string | null;
  isDirector: boolean;
  isOfficer: boolean;
  isTenPercentOwner: boolean;
  transactionCode: string;
  acquiredDisposed: "A" | "D" | null;
  shares: number | null;
  pricePerShare: number | null;
  value: number | null;
  sharesOwnedAfter: number | null;
};

// SEC's single-letter transaction codes, the ones that actually show up in practice.
const CODE_LABEL: Record<string, string> = {
  P: "Open market buy",
  S: "Open market sale",
  A: "Grant/award",
  M: "Option exercise",
  G: "Gift",
  F: "Tax withholding",
  C: "Conversion",
  D: "Disposition to issuer",
};

export default function InsiderWidget({ widget }: { widget: WidgetInstance }) {
  useLanguage();
  const symbol = useWidgetSymbol(widget);
  const { data = [], isLoading, error } = useQuery({
    queryKey: ["insider", symbol],
    queryFn: () => apiGet<InsiderTransaction[]>(`/api/insider/${encodeURIComponent(symbol)}`),
    staleTime: 3_600_000,
  });

  if (error) return <div className="p-2 down">{tr("Error: ")}{tr((error as Error).message)}</div>;
  if (isLoading) return <div className="p-2 dim">{tr("Loading insider transactions for ")}{tr(symbol)}…</div>;

  return (
    <div>
      <table className="data-table">
        <thead>
          <tr>
            <th>{tr("Date")}</th>
            <th>{tr("Insider")}</th>
            <th>{tr("Title")}</th>
            <th>{tr("Type")}</th>
            <th>{tr("Shares")}</th>
            <th>{tr("Price")}</th>
            <th>{tr("Value")}</th>
            <th>{tr("Owned After")}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((t, i) => (
            <tr key={`${t.ownerName}-${t.transactionDate}-${i}`}>
              <td className="!text-start dim whitespace-nowrap">{tr(t.transactionDate)}</td>
              <td className="!text-start">{tr(t.ownerName)}</td>
              <td className="!text-start dim truncate max-w-[140px]" title={tr(t.ownerTitle ?? "")}>
                {tr(t.ownerTitle ?? (t.isDirector ? "Director" : t.isTenPercentOwner ? "10%+ Owner" : "—"))}
              </td>
              <td className={t.acquiredDisposed === "A" ? "up" : t.acquiredDisposed === "D" ? "down" : "dim"}>
                {tr(CODE_LABEL[t.transactionCode] ?? t.transactionCode)}
              </td>
              <td>{tr(fmtBig(t.shares))}</td>
              <td>{tr(fmt(t.pricePerShare))}</td>
              <td>{tr(fmtBig(t.value))}</td>
              <td className="dim">{tr(fmtBig(t.sharesOwnedAfter))}</td>
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={8} className="dim p-3">{tr("No recent open-market insider transactions for ")}{tr(symbol)}.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
