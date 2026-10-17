import { useEffect, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { TerminalResearchPanel } from '@/components/advisory/TerminalResearchPanel';
import { ResearchJournalPanel } from '@/components/advisory/ResearchJournalPanel';
import type { TerminalResearch } from '@/lib/terminalResearch';
import { TERMINAL_ORIGIN, selectTerminalSymbol, terminalMessage } from '@/lib/terminalBridge';

export function ResearchTerminal() {
  const frame = useRef<HTMLIFrameElement>(null);
  const detail = useRef<HTMLDivElement>(null);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const [symbol, setSymbol] = useState('');
  const [frameSymbol, setFrameSymbol] = useState('');
  const [draft, setDraft] = useState('');
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<TerminalResearch | null>(null);
  useEffect(() => {
    function receive(event: MessageEvent<unknown>) {
      if (!frame.current?.contentWindow || event.source !== frame.current.contentWindow) return;
      const message = terminalMessage(event.origin, event.data);
      if (!message) return;
      setReady(true); setSymbol(message.symbol); setFrameSymbol(message.symbol);
      setDraft(message.symbol); setError('');
    }
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, []);
  function choose(value = draft) {
    const message = selectTerminalSymbol(value);
    if (!message) { setError('أدخل رمزًا صالحًا كما يظهر في OpenTerminal، مثل AAPL أو SPY.'); return; }
    setError(''); setSymbol(message.symbol); setDraft(message.symbol);
    frame.current?.contentWindow?.postMessage(message, TERMINAL_ORIGIN);
  }
  function openResearch(value: string) {
    choose(value);
    setDetailRefresh(revision => revision + 1);
    window.requestAnimationFrame(() => detail.current?.scrollIntoView({behavior: 'smooth', block: 'start'}));
  }
  return <div className="space-y-5">
    <div dir="rtl" className="flex flex-wrap items-center justify-between gap-3">
      <div><h1 className="text-2xl font-semibold">ALGHREST × OpenTerminal</h1><p className="mt-2 text-sm text-white/60">اختر أي رمز يوفّره OpenTerminal؛ يحلّله ALGHREST من بياناته مباشرة.</p></div>
      <a href={TERMINAL_ORIGIN} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 text-sm text-amber-200">فتح الشارت منفصلًا <ExternalLink size={15} /></a>
    </div>
    <form dir="rtl" onSubmit={event => {event.preventDefault(); choose();}} className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-bg-surface p-4">
      <label className="space-y-2"><span className="block text-sm">رمز OpenTerminal</span><input aria-label="رمز OpenTerminal" dir="ltr" value={draft} onChange={event => setDraft(event.target.value)} placeholder="AAPL / SPY / BTC-USD" maxLength={20} className="rounded-lg border border-white/15 bg-bg-dark px-3 py-2" /></label>
      <button className="rounded-lg bg-violet-600 px-4 py-2">اختيار وتحليل الرمز</button>
      <p role="status" className="text-sm text-white/60">{ready ? `التحليل: ${symbol} · الشارت: ${frameSymbol}` : 'بانتظار OpenTerminal؛ يمكنك اختيار الرمز هنا أيضًا.'}</p>
      {error && <p role="alert" className="w-full text-sm text-red-300">{error}</p>}
    </form>
    <ResearchJournalPanel symbol={symbol} currentReport={report} onSelect={openResearch} />
    <iframe ref={frame} src={TERMINAL_ORIGIN} title="OpenTerminal market workspace" referrerPolicy="origin"
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-top-navigation-by-user-activation"
      className="h-[620px] w-full rounded-xl border border-border bg-black" />
    <div ref={detail} className="scroll-mt-16">{symbol && <TerminalResearchPanel symbol={symbol} onReport={setReport} refreshToken={detailRefresh} />}</div>
    <p dir="rtl" className="text-sm text-white/50">للإدخال اليدوي ودفتر حسابك السابق: <Link to="/assistant" className="text-indigo-300 hover:underline">فتح المساعد اليدوي</Link></p>
  </div>;
}
