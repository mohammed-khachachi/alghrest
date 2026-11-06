"use client";
import { useLanguage, tr } from "../i18n";

import { useEffect, useRef, useState } from "react";
import GridLayout, { WidthProvider } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import { normalizeSymbol } from "../lib/symbol";
import { projectWorkspaceLayout } from "../lib/workspaceLayout";
import { useTerminal, type WidgetInstance } from "../store/terminal";
import QuoteWidget from "./widgets/QuoteWidget";
import ChartWidget from "./widgets/ChartWidget";
import WatchlistWidget from "./widgets/WatchlistWidget";
import NewsWidget from "./widgets/NewsWidget";
import HeatmapWidget from "./widgets/HeatmapWidget";
import ScreenerWidget from "./widgets/ScreenerWidget";
import CryptoWidget from "./widgets/CryptoWidget";
import MacroWidget from "./widgets/MacroWidget";
import OptionsWidget from "./widgets/OptionsWidget";
import PortfolioWidget from "./widgets/PortfolioWidget";
import AiWidget from "./widgets/AiWidget";
import CalendarWidget from "./widgets/CalendarWidget";
import InsiderWidget from "./widgets/InsiderWidget";
import TvWidget from "./widgets/TvWidget";
import RecapWidget from "./widgets/RecapWidget";
import WidgetErrorBoundary from "./WidgetErrorBoundary";

const Grid = WidthProvider(GridLayout);

function WidgetBody({ widget }: { widget: WidgetInstance }) {
  useLanguage();
  switch (widget.type) {
    case "quote": return <QuoteWidget widget={widget} />;
    case "chart": return <ChartWidget widget={widget} />;
    case "watchlist": return <WatchlistWidget />;
    case "news": return <NewsWidget widget={widget} />;
    case "heatmap": return <HeatmapWidget />;
    case "screener": return <ScreenerWidget />;
    case "crypto": return <CryptoWidget />;
    case "macro": return <MacroWidget />;
    case "options": return <OptionsWidget widget={widget} />;
    case "portfolio": return <PortfolioWidget />;
    case "ai": return <AiWidget />;
    case "calendar": return <CalendarWidget />;
    case "insider": return <InsiderWidget widget={widget} />;
    case "tv": return <TvWidget />;
    case "recap": return <RecapWidget />;
  }
}

function SymbolTag({ widget, activeSymbol }: { widget: WidgetInstance; activeSymbol: string }) {
  useLanguage();
  const setWidgetSymbol = useTerminal((s) => s.setWidgetSymbol);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const shown = widget.linked ? activeSymbol : widget.symbol ?? activeSymbol;

  useEffect(() => {
    if (!editing) return;
    setDraft(shown);
    requestAnimationFrame(() => inputRef.current?.select());
  }, [editing]); // eslint-disable-line react-hooks/exhaustive-deps

  if (editing) {
    return (
      <input
        dir="ltr"
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value.toUpperCase())}
        onMouseDown={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            const v = normalizeSymbol(draft);
            if (v) setWidgetSymbol(widget.id, v);
            setEditing(false);
          }
          if (e.key === "Escape") setEditing(false);
        }}
        onBlur={() => setEditing(false)}
        className="ms-2 w-16 !border-0 !border-b !border-[var(--amber-dim)] bg-transparent text-[var(--text)] px-0 py-0 text-[13px] leading-none"
      />
    );
  }

  return (
    <span
      className="ms-2 text-[var(--text)] cursor-pointer hover:text-[var(--amber)]"
      title={tr("Click to set this widget's ticker")}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={() => setEditing(true)}
    >
      {shown}
    </span>
  );
}

const TITLES: Record<string, string> = {
  quote: "Quote", chart: "Chart", watchlist: "Watchlist", news: "News",
  heatmap: "Heatmap", screener: "Screener", crypto: "Crypto",
  macro: "Macro / Indexes", options: "Option Chain", portfolio: "Portfolio", ai: "AI Assistant",
  calendar: "Calendar", insider: "Insider Transactions", tv: "Live TV", recap: "Market Recap",
};

export default function Workspace() {
  useLanguage();
  const widgets = useTerminal((s) => s.widgets);
  const layout = useTerminal((s) => s.layout);
  const setLayout = useTerminal((s) => s.setLayout);
  const removeWidget = useTerminal((s) => s.removeWidget);
  const toggleLinked = useTerminal((s) => s.toggleLinked);
  const activeSymbol = useTerminal((s) => s.activeSymbol);
  const [narrow, setNarrow] = useState(false);
  const narrowRef = useRef(false);

  useEffect(() => {
    const screen = window.matchMedia("(width < 768px)");
    const update = () => {
      narrowRef.current = screen.matches;
      setNarrow(screen.matches);
    };
    update();
    screen.addEventListener("change", update);
    return () => screen.removeEventListener("change", update);
  }, []);

  const symbolAware = new Set(["quote", "chart", "news", "options", "insider"]);

  return (
    <Grid
      className="layout"
      layout={projectWorkspaceLayout(layout, narrow)}
      cols={12}
      rowHeight={30}
      margin={[4, 4]}
      draggableHandle=".panel-title"
      isDraggable={!narrow}
      isResizable={!narrow}
      onLayoutChange={(l) => {
        // Width/layout callbacks also fire during viewport changes; only desktop edits persist.
        if (narrow || narrowRef.current || window.matchMedia("(width < 768px)").matches) return;
        setLayout(l.map(({ i, x, y, w, h }) => ({ i, x, y, w, h })));
      }}
    >
      {widgets.map((w) => (
        <div key={w.id}>
          <div className="terminal-panel">
            <div className="panel-title">
              <span>
                {tr(TITLES[w.type])}
                {symbolAware.has(w.type) && <SymbolTag widget={w} activeSymbol={activeSymbol} />}
              </span>
              <span className="flex gap-2 items-center">
                {symbolAware.has(w.type) && (
                  <button
                    title={tr(w.linked ? "Linked to active symbol (click to unlink)" : "Unlinked (click to link)")}
                    onMouseDown={(e) => e.stopPropagation()}
                    onClick={() => toggleLinked(w.id)}
                    className={w.linked ? "text-[var(--amber)]" : "dim"}
                  >
                    ⛓
                  </button>
                )}
                <button
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={() => removeWidget(w.id)}
                  className="dim hover:text-[var(--down)]"
                >
                  ✕
                </button>
              </span>
            </div>
            <div className="flex-1 overflow-auto min-h-0">
              <WidgetErrorBoundary name={TITLES[w.type]}>
                <WidgetBody widget={w} />
              </WidgetErrorBoundary>
            </div>
          </div>
        </div>
      ))}
    </Grid>
  );
}
