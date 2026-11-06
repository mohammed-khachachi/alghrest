"use client";
import { useLanguage, currentLocale, tr } from "../../i18n";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiGet } from "../../lib/api";
import { isSafeHttpUrl } from "../../lib/links";
import { useWidgetSymbol, type WidgetInstance } from "../../store/terminal";

type NewsItem = { title: string; link: string; publisher: string; publishedAt: string | null };

export default function NewsWidget({ widget }: { widget: WidgetInstance }) {
  useLanguage();
  const symbol = useWidgetSymbol(widget);
  const [mode, setMode] = useState<"symbol" | "global">("symbol");

  const { data = [], isLoading } = useQuery({
    queryKey: ["news", mode, symbol],
    queryFn: () => apiGet<NewsItem[]>(mode === "symbol" ? `/api/news?symbol=${encodeURIComponent(symbol)}` : "/api/news"),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <div className="flex gap-1 p-1">
        <button className={`term-btn ${mode === "symbol" ? "active" : ""}`} onClick={() => setMode("symbol")}>
          {tr(symbol)}
        </button>
        <button className={`term-btn ${mode === "global" ? "active" : ""}`} onClick={() => setMode("global")}>{tr("GLOBAL")}</button>
      </div>
      {isLoading && <div className="p-2 dim">{tr("Loading news…")}</div>}
      {data.map((n, i) => {
        const body = (
          <>
            <div className="truncate">{n.title}</div>
            <div className="dim text-[10px]">
              {n.publisher}
              {tr(n.publishedAt ? " · " + new Date(n.publishedAt).toLocaleString(currentLocale()) : "")}
            </div>
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
  );
}
