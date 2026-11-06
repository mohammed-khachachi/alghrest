import { useLanguage, tr } from "../../i18n";
import {useEffect,useState} from 'react';
import {advisoryApi} from '@/lib/advisoryApi';
import {researchDiagnostics,diagnosticFailure,diagnosticClock,type DiagnosticResult} from '@/lib/researchDiagnostics';
import {sourceTime} from '@/lib/terminalDataStatus';

export function ProviderDiagnostics({symbol,revision}:{symbol:string;revision:string}) {
  useLanguage();
  const [value,setValue]=useState<DiagnosticResult|null>(null);
  const [error,setError]=useState('');
  useEffect(()=>{
    let active=true;setValue(null);setError('');
    void advisoryApi<unknown>(`research-diagnostics/${encodeURIComponent(symbol)}`).then(raw=>{
      const parsed=researchDiagnostics(raw,symbol);if(active)setValue(parsed);
    }).catch(()=>{if(active)setError('تعذر تحميل تشخيص المصادر؛ حدّث التحليل لإعادة المحاولة.');});
    return ()=>{active=false;};
  },[symbol,revision]);
  return <details className="rounded-lg border border-white/10 p-3" aria-label={tr("تشخيص مزودي البيانات")}><summary className="cursor-pointer font-medium">{tr("تشخيص مزودي البيانات")}</summary>
    <p className="mt-2 text-xs text-white/50">{tr("آخر محاولات السعر والشموع والأخبار المرصودة منذ بدء خدمة OpenTerminal فقط. آخر نجاح يعني نجاح الطلب؛ لا يثبت حداثة سعر السوق. تُعرض مصادر RSS للأخبار منفصلة؛ نجاح الطلب لا يعني اكتمال التغطية أو وجود عناوين صالحة. لا يراقب هذا القسم المصادر في الخلفية.")}</p>
    {error&&<p role="alert" className="mt-2 text-sm text-amber-200">{tr(error)}</p>}
    {value&&value.symbol===symbol&&<>
      <p className="mt-2 text-xs text-white/50">{tr("قراءة التشخيص: ")}{tr(sourceTime(value.checked_at))}{tr(" · بدء الخدمة: ")}{tr(sourceTime(value.diagnostics?.started_at))}</p>
      {value.state!=='available'?<p className="text-sm text-amber-200">{tr(value.state==='invalid'?'رفض التشخيص لعدم اتساق بياناته.':'خدمة التشخيص غير متاحة.')}</p>:value.diagnostics?.observations.length===0?<p className="text-sm text-white/60">{tr("لا توجد محاولات مرصودة لهذا الرمز منذ بدء الخدمة؛ قد تكون القراءة من نسخة مؤقتة.")}</p>:
      <ul className="mt-3 space-y-3 text-sm">{value.diagnostics?.observations.map(o=><li key={`${o.feed}:${o.provider}`} className="rounded bg-white/5 p-3">
        <p>{o.provider} · {tr(o.feed==='history'?'الشموع':o.feed==='news'?'الأخبار':'السعر')} · {tr(o.state==='available'?'نجحت آخر محاولة':'فشلت آخر محاولة')}</p>
        <p className="mt-1 text-xs text-white/60">{tr("آخر نجاح: ")}{tr(sourceTime(o.last_success))}{tr(" · آخر فشل: ")}{tr(sourceTime(o.last_failure))}</p>
        {o.failure&&<p className="text-xs text-amber-200">{tr("سبب آخر فشل: ")}{tr(diagnosticFailure[o.failure])} {tr(o.http_status??'')}{tr(o.state==='available'?' · تعافى الطلب بعدها':'')}</p>}
        {o.clock&&<p className="mt-1 text-xs text-white/60">{tr(diagnosticClock[o.clock.basis])}: <bdi>{tr(o.clock.value)}</bdi>{tr(o.state==='unavailable'?' · من آخر نجاح سابق':'')}</p>}
      </li>)}</ul>}
    </>}
  </details>;
}
