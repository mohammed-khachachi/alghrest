import { useEffect, useRef, useState } from 'react';
import { advisoryApi } from '@/lib/advisoryApi';
import { researchHistory, type ResearchWatchEntry } from '@/lib/researchJournal';
import { terminalResearch } from '@/lib/terminalResearch';
import { emptyOverviewEntry, overviewReading, watchlistBatch, type OverviewEntry } from '@/lib/watchlistOverview';
import { sourceTime, dataAge } from '@/lib/terminalDataStatus';
import { qualityLabel } from '@/lib/terminalQuality';

export function WatchlistOverview({ watches, selectedSymbol, onSelect }: {
  watches: ResearchWatchEntry[]; selectedSymbol: string; onSelect: (symbol: string) => void;
}) {
  const [entries, setEntries] = useState<Record<string, OverviewEntry>>({});
  const [now, setNow] = useState(Date.now());
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({total: 0, done: 0, errors: 0, skipped: 0});
  const mounted = useRef(false);
  const activeRun = useRef(false);
  const stop = useRef(false);
  const members = useRef(new Set(watches.map(w => w.symbol)));
  members.current = new Set(watches.map(w => w.symbol));
  const memberKey = watches.map(w => w.symbol).join(',');

  useEffect(() => {
    mounted.current = true;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { mounted.current = false; stop.current = true; window.clearInterval(timer); };
  }, []);
  useEffect(() => { if (activeRun.current) stop.current = true; }, [memberKey]);
  useEffect(() => {
    let cancelled = false;
    const symbols = watches.map(w => w.symbol);
    setEntries(previous => Object.fromEntries(symbols.map(s => [s, {...previous[s] ?? emptyOverviewEntry(), history: null, historyError: ''}])));
    void watchlistBatch(symbols, async symbol => researchHistory(await advisoryApi<unknown>(
      `research-snapshots/${encodeURIComponent(symbol)}?limit=2`), symbol), event => {
      if (cancelled || !mounted.current || !members.current.has(event.symbol)) return;
      if (event.phase === 'done' || event.phase === 'error') setEntries(previous => ({...previous,
        [event.symbol]: {...previous[event.symbol] ?? emptyOverviewEntry(),
          history: event.phase === 'done' ? event.value : null,
          historyError: event.phase === 'error' ? 'تعذر تحميل اللقطات؛ المقارنة غير متاحة.' : ''},
      }));
    }, () => cancelled);
    return () => { cancelled = true; };
  }, [watches]);

  async function refresh(symbols: string[]) {
    if (activeRun.current || !symbols.length) return;
    activeRun.current = true; stop.current = false; setRunning(true);
    setProgress({total: symbols.length, done: 0, errors: 0, skipped: 0});
    setEntries(previous => {
      const next = {...previous};
      for (const symbol of symbols) next[symbol] = {...next[symbol] ?? emptyOverviewEntry(), phase: 'queued', error: ''};
      return next;
    });
    try {
      await watchlistBatch(symbols, async symbol => {
        const raw = await advisoryApi<unknown>(`openterminal-research/${encodeURIComponent(symbol)}`);
        const report = terminalResearch(raw, symbol);
        if (!report) throw new Error('Invalid research response');
        return report;
      }, event => {
        if (!mounted.current) return;
        if (event.phase !== 'loading') setProgress(p => ({...p,
          done: p.done + Number(event.phase === 'done'), errors: p.errors + Number(event.phase === 'error'),
          skipped: p.skipped + Number(event.phase === 'skipped'),
        }));
        if (!members.current.has(event.symbol)) return;
        setNow(Date.now());
        setEntries(previous => ({...previous, [event.symbol]: {...previous[event.symbol] ?? emptyOverviewEntry(),
          phase: event.phase, error: event.phase === 'error' ? event.error : '',
          reading: event.phase === 'done' ? event.value : previous[event.symbol]?.reading ?? null,
        }}));
      }, () => stop.current || !mounted.current);
    } finally {
      activeRun.current = false;
      if (mounted.current) setRunning(false);
    }
  }
  const phases = {idle: '', queued: 'في الانتظار', loading: 'جارٍ التحديث', done: 'وصلت استجابة', error: 'فشل التحديث', skipped: 'لم يُحدّث'};
  return <section aria-label="نظرة عامة على قائمة البحث" className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3"><h3 className="font-semibold">نظرة عامة على قائمة البحث</h3>
      <div className="flex gap-2"><button disabled={running || !watches.length} onClick={() => void refresh(watches.map(w => w.symbol))} className="rounded bg-violet-600 px-3 py-2 text-sm disabled:opacity-40">تحديث الكل</button>
        {running && <button onClick={() => { stop.current = true; }} className="rounded border border-white/15 px-3 py-2 text-sm">إيقاف المتبقي</button>}</div>
    </div>
    <p className="text-xs text-white/50">تُعرض آخر لقطة محفوظة أولًا. التحديث يدوي، برمزين في الوقت نفسه، ولا يحفظ لقطات جديدة. بعد 90 ثانية تنتهي صلاحية القراءة الحالية ويعود العرض إلى اللقطة المحفوظة إن وجدت.</p>
    {progress.total > 0 && <div role="status" className="text-sm text-white/70">
      {running ? 'جارٍ تحديث القائمة' : 'انتهى الطلب'} · استجابات {progress.done}/{progress.total} · أخطاء طلب {progress.errors} · لم يُحدّث {progress.skipped}
      <progress aria-label="تقدم تحديث القائمة" className="mt-2 block w-full accent-violet-500" value={progress.done + progress.errors + progress.skipped} max={progress.total} />
      <p className="mt-1 text-xs text-white/50">وصول الاستجابة لا يعني اكتمال البيانات. إيقاف المتبقي يترك الطلبات الجارية حتى تنتهي.</p>
    </div>}
    {watches.length === 0 ? <p className="text-sm text-white/50">أضف رموزًا للمتابعة لعرض المقارنة هنا.</p> : <div className="overflow-x-auto">
      <table className="w-full min-w-[950px] text-right text-sm"><thead><tr className="text-white/50">
        {['الرمز والقراءة','الاتجاه','الزخم · RSI 14','التذبذب · ATR 14','منذ اللقطة السابقة','حالة البيانات','فتح البحث'].map(h => <th key={h} className="p-3 font-medium">{h}</th>)}
      </tr></thead><tbody>{watches.map(w => {
        const entry = entries[w.symbol] ?? emptyOverviewEntry();
        const row = overviewReading(w.symbol, entry, now);
        const a = row.report?.analysis;
        const trendChange = row.comparison?.rows.find(r => r.label === 'الاتجاه');
        const rsiChange = row.comparison?.rows.find(r => r.label === 'الزخم · RSI 14');
        const atrChange = row.comparison?.rows.find(r => r.label === 'التذبذب · ATR 14');
        return <tr key={w.symbol} aria-label={`ملخص ${w.symbol}`} className={`border-t border-white/10 align-top ${w.symbol === selectedSymbol ? 'bg-indigo-500/5' : ''}`}>
          <th className="p-3 font-normal"><p dir="ltr" className="text-right font-semibold">{w.symbol}</p><p className={`mt-1 text-xs ${row.origin === 'قراءة حالية' ? 'text-indigo-200' : 'text-amber-200'}`}>{row.origin}</p>
            <p className="mt-1 text-xs text-white/50">{sourceTime(row.report?.assessed_at)}</p><p className="text-xs text-white/40">عمر القراءة: {dataAge(row.report?.assessed_at, now)}</p><p className="mt-1 text-xs text-white/40">{w.snapshots} لقطة محفوظة</p>
            {row.expired && <p className="mt-1 text-xs text-amber-200">انتهت صلاحية آخر تحديث؛ اضغط تحديث.</p>}
          </th>
          <td className="p-3">{row.trend}{trendChange?.changed && <p className="mt-1 text-xs text-amber-200">سابقًا: {trendChange.before}</p>}</td>
          <td className="p-3">{row.momentum}{rsiChange?.changed && <p className="mt-1 text-xs text-amber-200">سابقًا: {rsiChange.before}</p>}</td>
          <td className="p-3">{row.volatility}<p className="mt-1 text-xs text-white/40">بوحدة السعر (% من الإغلاق)</p>{atrChange?.changed && <p className="mt-1 text-xs text-amber-200">ATR سابقًا: {atrChange.before}</p>}</td>
          <td className="p-3 text-xs"><p>{row.changed === null ? 'لا توجد مقارنة متاحة' : `${row.changed} بنود تغيرت`}</p>
            <p className="mt-1">{row.newHeadlines === null ? 'العناوين الجديدة: غير معلوم' : `${row.newHeadlines} عناوين ظهرت في النتائج`}</p>
            {row.previous && <p className="mt-1 text-white/40">السابقة: {sourceTime(row.previous.report.assessed_at)}</p>}
            {row.comparison && !row.comparison.comparable && <p className="mt-1 text-amber-200">المزوّد أو الإطار غير متطابق/غير معلن؛ قابلية المقارنة غير مؤكدة.</p>}
            <p className="mt-1 text-white/40">ظهور عنوان لا يعني أنه خبر نُشر للتو.</p>
          </td>
          <td className="p-3 text-xs"><p className={entry.phase === 'error' ? 'text-red-300' : 'text-indigo-200'}>{phases[entry.phase]}</p>
            {entry.error && <p role="alert" className="mt-1 text-red-300">{entry.error} {row.report ? 'المعروض قراءة سابقة ناجحة.' : ''}</p>}
            {entry.historyError && <p role="alert" className="mt-1 text-amber-200">{entry.historyError} استخدم إعادة تحميل السجل.</p>}
            {!entry.history && !entry.historyError && <p className="text-white/50">جارٍ تحميل اللقطات…</p>}
            {row.status.map(s => <p key={s.kind} className={`mt-1 ${s.tone === 'neutral' ? 'text-white/60' : 'text-amber-200'}`}>{s.title}: {s.status}</p>)}
            {row.report && <p className="mt-1 text-amber-200">جودة الشموع: {qualityLabel(row.report.data_quality)}</p>}
            <p className="mt-1 text-white/40">مزوّد الشموع: {a && a.history_provider !== 'UNKNOWN' ? a.history_provider : 'غير معلن'}</p>
            <p className="text-white/40">عمر آخر شمعة: {dataAge(a?.last_time, now)}</p>
          </td>
          <td className="space-y-2 p-3"><button aria-label={`فتح بحث ${w.symbol}`} onClick={() => onSelect(w.symbol)} className="block rounded border border-indigo-400/40 px-3 py-2 text-indigo-200">التفاصيل</button>
            <button aria-label={`تحديث ${w.symbol}`} disabled={running} onClick={() => void refresh([w.symbol])} className="block rounded border border-white/15 px-3 py-2 disabled:opacity-40">{entry.phase === 'error' ? 'إعادة المحاولة' : 'تحديث'}</button></td>
        </tr>;
      })}</tbody></table>
    </div>}
  </section>;
}
