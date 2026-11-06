"use client";
import { useLanguage, tr } from "../i18n";

import { useTerminal, type WidgetType } from "../store/terminal";

const ITEMS: Array<{ type: WidgetType; label: string; key: string }> = [
  { type: "chart", label: "CHART", key: "⌥1" },
  { type: "quote", label: "QUOTE", key: "⌥2" },
  { type: "news", label: "NEWS", key: "⌥3" },
  { type: "screener", label: "SCREENER", key: "⌥4" },
  { type: "heatmap", label: "HEATMAP", key: "⌥5" },
  { type: "crypto", label: "CRYPTO", key: "⌥6" },
  { type: "options", label: "OPTIONS", key: "⌥7" },
  { type: "portfolio", label: "PORTFOLIO", key: "⌥8" },
  { type: "ai", label: "AI ASSIST", key: "⌥9" },
  { type: "watchlist", label: "WATCHLIST", key: "" },
  { type: "macro", label: "MACRO", key: "" },
  { type: "calendar", label: "CALENDAR", key: "" },
  { type: "insider", label: "INSIDER", key: "" },
  { type: "tv", label: "LIVE TV", key: "" },
  { type: "recap", label: "MARKET RECAP", key: "" },
];

export default function Sidebar() {
  useLanguage();
  const addWidget = useTerminal((s) => s.addWidget);
  const resetWorkspace = useTerminal((s) => s.resetWorkspace);

  return (
    <nav className="w-full md:w-32 bg-[var(--panel)] border-b md:border-b-0 md:border-e border-[var(--border)] flex flex-row md:flex-col shrink-0 overflow-x-auto md:overflow-x-visible">
      <div className="dim px-2 py-1 text-[10px] uppercase tracking-wider md:border-b border-[var(--border)] shrink-0 whitespace-nowrap">{tr("Add widget")}</div>
      {ITEMS.map((item) => (
        <button
          key={item.type}
          onClick={() => addWidget(item.type)}
          className="text-start px-2 py-1.5 text-[11px] hover:bg-[#1a1a1a] hover:text-[var(--amber)] flex justify-between gap-2 shrink-0 whitespace-nowrap"
        >
          <span>{tr(item.label)}</span>
          <span className="dim text-[9px]">{tr(item.key)}</span>
        </button>
      ))}
      <div className="md:mt-auto md:border-t border-[var(--border)] shrink-0">
        <button
          onClick={resetWorkspace}
          className="w-full text-start px-2 py-1.5 text-[11px] dim hover:text-[var(--down)] whitespace-nowrap"
        >{tr("RESET LAYOUT")}</button>
      </div>
    </nav>
  );
}
