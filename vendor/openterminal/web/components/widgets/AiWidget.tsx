"use client";
import { useLanguage, tr } from "../../i18n";

import { useMutation } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { apiGet, apiPost, type Quote } from "../../lib/api";
import { useTerminal } from "../../store/terminal";

type Msg = { role: "user" | "assistant"; content: string };

export default function AiWidget() {
  useLanguage();
  const activeSymbol = useTerminal((s) => s.activeSymbol);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const chat = useMutation({
    mutationFn: async (userText: string) => {
      let context: unknown = null;
      try {
        context = { activeSymbol, quote: (await apiGet<Quote[]>(`/api/quotes?symbols=${encodeURIComponent(activeSymbol)}`))[0] };
      } catch {
        // context is best-effort
      }
      const next = [...messages, { role: "user" as const, content: userText }];
      const res = await apiPost<{ text: string }>("/api/ai/chat", { messages: next, context });
      return { next, reply: res.text };
    },
    onSuccess: ({ next, reply }) => {
      setMessages([...next, { role: "assistant", content: reply }]);
      setTimeout(() => scrollRef.current?.scrollTo({ top: 1e9 }), 50);
    },
  });

  const send = () => {
    const text = input.trim();
    if (!text || chat.isPending) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    chat.mutate(text);
  };

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-auto p-2 space-y-2 min-h-0">
        {messages.length === 0 && (
          <div className="dim">{tr("Ask about ")}{activeSymbol}{tr(", the market, an indicator, or a headline. The current quote is shared as context.")}</div>
        )}
        {messages.map((m, i) => (
          <div key={i}>
            <span className={m.role === "user" ? "amber" : "up"}>{tr(m.role === "user" ? "YOU" : "AI")} ›</span>{tr(" ")}
            <span className="whitespace-pre-wrap">{m.content}</span>
          </div>
        ))}
        {chat.isPending && <div className="dim">{tr("thinking…")}</div>}
        {chat.error && <div className="down">{tr((chat.error as Error).message)}</div>}
      </div>
      <div className="flex gap-1 p-1 border-t border-[var(--border)] shrink-0">
        <input
          className="flex-1"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder={tr(`Ask about ${activeSymbol}…`)}
        />
        <button className="term-btn" onClick={send}>{tr("SEND")}</button>
      </div>
    </div>
  );
}
