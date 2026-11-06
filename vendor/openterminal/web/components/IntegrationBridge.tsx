"use client";
import { languageMessage, setLanguage, isLanguage } from "../i18n/core";

import { useEffect, useRef } from "react";
import { useTerminal } from "../store/terminal";

const PARENTS = new Set(["http://127.0.0.1:5173", "http://localhost:5173"]);

/** Shares only the public symbol selection, never tokens or portfolio entries. */
export default function IntegrationBridge() {
  const parentOrigin = useRef<string | null>(null);
  const symbol = useTerminal(state => state.activeSymbol);
  const setSymbol = useTerminal(state => state.setActiveSymbol);
  useEffect(() => {
    if (window.parent === window) return;
    try {
      const origin = new URL(document.referrer).origin;
      if (!PARENTS.has(origin)) return;
      parentOrigin.current = origin;
    } catch { return; }
    function receive(event: MessageEvent<unknown>) {
      if (event.source !== window.parent || event.origin !== parentOrigin.current) return;
      const choice = languageMessage(event.data, 'alghrest:language');
      if (choice) { setLanguage(choice); return; }
      const data = event.data;
      if (typeof data !== "object" || data === null || Array.isArray(data)) return;
      const message = data as Record<string, unknown>;
      if (Object.keys(message).length !== 2 || message.type !== "alghrest:select-symbol"
        || typeof message.symbol !== "string"
        || !/^(?=.*[A-Z0-9])[A-Z0-9.\-^=&]{1,20}$/.test(message.symbol)) return;
      setSymbol(message.symbol);
    }
    function languageChoice(event: Event) {
      const choice: unknown = (event as CustomEvent<unknown>).detail;
      if (parentOrigin.current && isLanguage(choice)) window.parent.postMessage({type: 'openterminal:language', language: choice}, parentOrigin.current);
    }
    window.addEventListener('alghrest:language-choice', languageChoice);
    window.addEventListener("message", receive);
    window.parent.postMessage({type: "openterminal:ready", symbol}, parentOrigin.current);
    return () => {
      window.removeEventListener("message", receive);
      window.removeEventListener('alghrest:language-choice', languageChoice);
    };
  }, [setSymbol]);
  useEffect(() => {
    if (window.parent === window) return;
    if (parentOrigin.current) window.parent.postMessage({type: "openterminal:symbol", symbol}, parentOrigin.current);
  }, [symbol]);
  return null;
}
