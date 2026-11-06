import { useLanguage, languageDirection, tr, currentLocale } from "../../i18n";
import { useEffect, useRef, useState } from 'react';
import { advisoryApi } from '@/lib/advisoryApi';
import { linkedInstrument, terminalContext, type TerminalContext } from '@/lib/terminalBridge';

const directions = { proxy_up: 'المؤشر السياقي مرتفع', proxy_down: 'المؤشر السياقي منخفض', proxy_unchanged: 'دون تغير معلن', unknown: 'الاتجاه غير معلوم' };

export function OpenTerminalContextPanel({ instrument }: { instrument: string }) {
  useLanguage();
  const linked = linkedInstrument(instrument);
  const [context, setContext] = useState<TerminalContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const revision = useRef(0);
  const current = useRef(instrument); current.current = instrument;

  async function refresh() {
    if (!linked) return;
    const request = ++revision.current;
    const root = linked;
    setContext(null); setError(''); setBusy(true);
    try {
      const raw = await advisoryApi<unknown>(`openterminal-context/${root}`);
      if (request !== revision.current || current.current !== root) return;
      const value = terminalContext(raw, root);
      if (!value) throw new Error('استجابة السياق غير صالحة أو قديمة.');
      setContext(value);
    } catch (reason) {
      if (request === revision.current && current.current === root) {
        setError(reason instanceof Error ? reason.message : 'تعذر قراءة سياق OpenTerminal.');
      }
    } finally { if (request === revision.current) setBusy(false); }
  }

  useEffect(() => {
    revision.current += 1; setContext(null); setError(''); setBusy(false);
    if (linked) void refresh();
    return () => { revision.current += 1; };
  }, [instrument]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  const visible = linked && context ? terminalContext(context, linked, now) : null;

  return <section dir={languageDirection()} className="rounded-xl border border-amber-500/20 bg-bg-surface p-5 space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-semibold text-amber-200">{tr("سياق السوق من OpenTerminal")}</h2>
      <button disabled={!linked || busy} onClick={() => void refresh()} className="rounded bg-amber-400/10 px-4 py-2 text-sm text-amber-200 disabled:opacity-40">{tr(busy ? 'جارٍ جلب السياق…' : 'تحديث السياق')}</button>
    </div>
    <p className="text-sm text-white/60">{tr("المساعد يقرأ الأسعار الإرشادية والأخبار من OpenTerminal. SPY سياق لـMES، وQQQ سياق لـMNQ؛ ليست أسعار عقود الفيوتشر ولا تُملأ بها حقول الدخول أو المخاطر.")}</p>
    {!linked && <p className="text-sm text-amber-200">{tr("لم يُعرّف ربط سياقي لهذه الأداة بعد. تبقى أدوات المساعد الحالية متاحة.")}</p>}
    {error && <p role="alert" className="text-sm text-red-300">{tr(error)}</p>}
    {visible && <>
      <div className="flex flex-wrap gap-4 text-sm">
        <span>{tr(visible.proxy_symbol)}: <strong dir="ltr">{tr(visible.quote?.price ?? 'غير متاح')}</strong> {tr(visible.quote ? 'USD' : '')}</span>
        <span>{tr(directions[visible.direction])}</span>
        <span>{tr("المصدر المعلن: ")}{tr(visible.quote?.provider ?? 'غير متاح')}</span>
      </div>
      <p className="text-xs text-white/40">{tr("وقت قراءة السياق: ")}{tr(new Date(visible.assessed_at).toLocaleString(currentLocale()))}{tr(" · وقت السعر لدى المصدر: ")}{tr(visible.quote?.market_time ? new Date(visible.quote.market_time).toLocaleString(currentLocale()) : 'غير معلوم')}{tr(" · حداثة السعر وتغطية الأحداث غير معتمدتين.")}</p>
      {visible.sources.some(row => row.state !== 'available') && <p role="status" className="text-sm text-amber-200">{tr("بعض بيانات OpenTerminal غير متاحة أو غير صالحة؛ لا تُستبدل بقيم مخترعة.")}</p>}
      <ul className="space-y-2 text-sm">{visible.headlines.map(row => <li key={row.url}><a href={row.url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:underline">{row.title}</a><span className="mr-2 text-xs text-white/40">{row.publisher}</span></li>)}</ul>
      {!visible.headlines.length && <p className="text-sm text-white/40">{tr("لا توجد عناوين صالحة في هذه الاستجابة. هذا لا يعني غياب أحداث مؤثرة.")}</p>}
    </>}
    {context && !visible && <p role="status" className="text-sm text-amber-200">{tr("انتهت صلاحية عرض السياق؛ حدّثه للحصول على قراءة جديدة.")}</p>}
    <p className="text-xs text-white/40">{tr("سياق بحثي فقط · لا إذن تداول · لا تحديث تلقائي للحساب · حساب المخاطر يعتمد بيانات الأداة الفعلية وملاحظتك المراجعة.")}</p>
  </section>;
}
