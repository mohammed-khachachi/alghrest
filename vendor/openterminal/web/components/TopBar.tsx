"use client";
import { LanguageSwitch } from "../i18n";
import { useLanguage, tr } from "../i18n";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import { useTerminal } from "../store/terminal";

type Status = {
  ok: boolean;
  providers: Array<{ name: string; ok: number; failed: number; lastLatencyMs: number | null }>;
  ai: boolean;
};

function Clock({ tz, label }: { tz: string; label: string }) {
  useLanguage();
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!now) return null;
  return (
    <span className="dim">
      {tr(label)}{tr(" ")}
      <span className="text-[var(--text)]">
        {tr(now.toLocaleTimeString("en-GB", { timeZone: tz, hour12: false }))}
      </span>
    </span>
  );
}

function marketStateNY(): { label: string; open: boolean } {
  const ny = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
  const day = ny.getDay();
  const mins = ny.getHours() * 60 + ny.getMinutes();
  const open = day >= 1 && day <= 5 && mins >= 570 && mins < 960; // 09:30–16:00
  return { label: open ? "NYSE OPEN" : "NYSE CLOSED", open };
}

export default function TopBar() {
  useLanguage();
  const setCommandOpen = useTerminal((s) => s.setCommandOpen);
  const activeSymbol = useTerminal((s) => s.activeSymbol);
  const { data: status } = useQuery({
    queryKey: ["status"],
    queryFn: () => apiGet<Status>("/api/status"),
    refetchInterval: 30_000,
  });

  const market = marketStateNY();
  const healthy = status?.providers.filter((p) => p.ok > 0) ?? [];

  return (
    <header className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-1 min-h-8 bg-[var(--panel-2)] border-b border-[var(--border)] text-[11px] shrink-0">
      <span className="amber font-bold tracking-widest">{tr("OPENTERMINAL")}</span>
      <span className={market.open ? "up" : "down"}>● {tr(market.label)}</span>
      <Clock tz="America/New_York" label={tr("NY")} />
      <Clock tz="Europe/Rome" label={tr("MIL")} />
      <Clock tz="Europe/London" label={tr("LDN")} />
      <Clock tz="Asia/Tokyo" label={tr("TYO")} />
      <button
        className="term-btn flex-1 max-w-md text-start dim"
        onClick={() => setCommandOpen(true)}
      >
        {tr(activeSymbol)}{tr(" — search symbol… ")}<span className="float-end">{tr("⌘K")}</span>
      </button>
      <span className="dim ms-auto">{tr("feeds:")}{tr(" ")}
        {tr(healthy.length > 0
          ? healthy.map((p) => `${p.name} ${p.lastLatencyMs ?? "—"}ms`).join(" · ")
          : "connecting…")}
      </span>
      <LanguageSwitch />
      <span className={status?.ai ? "up" : "dim"}>{tr("AI ")}{tr(status?.ai ? "●" : "○")}</span>
    </header>
  );
}
