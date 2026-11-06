import { useLanguage, languageDirection, tr } from "../../i18n";
import { useEffect,useRef,useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';
import { observationView,type ObservationView } from '../../lib/observations';
import { briefingAge,briefingReason,briefingGate,briefingRequestSchema,briefingView,capabilityLabel,capabilityState,type BriefingView } from '../../lib/briefings';

const field='w-full bg-slate-900 border border-white/20 rounded p-2';
export function BriefingPanel({evaluation,dirty}:{evaluation:{profile:{id:string};account_revision?:string}|null;dirty:boolean}){
  useLanguage();
 const [observations,setObservations]=useState<ObservationView[]>([]),[selected,setSelected]=useState(''),[result,setResult]=useState<BriefingView|null>(null),[history,setHistory]=useState<{id:string;created:string}[]>([]),[error,setError]=useState(''),[busy,setBusy]=useState(false),[now,setNow]=useState(Date.now());
 const gate=useRef(briefingGate());const identity=JSON.stringify([evaluation?.profile.id,evaluation?.account_revision,dirty,selected]);const current=useRef(identity);current.current=identity;const [resultKey,setResultKey]=useState('');
 useEffect(()=>{gate.current.next();setBusy(false);setResult(null);setError('');},[identity]);
 useEffect(()=>{const t=window.setInterval(()=>setNow(Date.now()),1000);return ()=>{clearInterval(t);gate.current.next();};},[]);
 async function work(action:(ticket:number,key:string)=>Promise<void>){const ticket=gate.current.next(),key=identity;setBusy(true);setError('');try{await action(ticket,key);}catch(e){if(gate.current.current(ticket)&&current.current===key)setError(e instanceof Error?e.message:'تعذر التقرير؛ لا توجد توصية مؤهلة.');}finally{if(gate.current.current(ticket)&&current.current===key)setBusy(false);}}
 async function load(){await work(async(t,key)=>{const raw=await api<unknown>('observations');if(!Array.isArray(raw))throw new Error('سجل غير صالح.');const rows=raw.map(observationView);if(gate.current.current(t)&&current.current===key)setObservations(rows.filter(v=>v.reviewed_at!==null&&v.record.revision===v.latest_revision));});}
 async function create(){await work(async(t,key)=>{const observation=observations.find(v=>v.record.id===selected);if(!evaluation?.account_revision||dirty||!observation)throw new Error('اختر حسابًا محفوظًا ونسخة ملاحظة مراجعة أولًا.');const request=briefingRequestSchema.parse({observation_id:observation.record.id,observation_revision:observation.record.revision,evaluation_id:evaluation.profile.id,account_revision:evaluation.account_revision});const value=briefingView(await api('briefings',{method:'POST',body:JSON.stringify(request)}),request);if(gate.current.current(t)&&current.current===key){setResult(value);setResultKey(key);}});}
 async function loadHistory(){await work(async(t,key)=>{const raw=await api<unknown>('briefings');if(!Array.isArray(raw)||raw.some(r=>!r||typeof r.id!=='string'||typeof r.created!=='string'))throw new Error('سجل تقارير غير صالح.');if(gate.current.current(t)&&current.current===key)setHistory(raw as {id:string;created:string}[]);});}
 async function open(id:string){await work(async(t,key)=>{const value=briefingView(await api(`briefings/${id}`));if(value.record.id!==id)throw new Error('هوية التقرير لا تطابق المطلوب.');if(gate.current.current(t)&&current.current===key){setResult(value);setResultKey(key);}});}
 const visible=resultKey===identity?result:null;
 return <section data-testid="briefing-panel" dir={languageDirection()} className="mt-6 rounded-xl border border-cyan-400/30 bg-white/5 p-5 text-sm min-w-0 break-words">
  <h2 className="text-lg font-semibold">{tr("تقرير جلسة التقييم — قدرات وأدلة مترابطة")}</h2>
  <p className="text-amber-200 my-3">{tr("تقرير بحثي محفوظ؛ لا يصدر توصية شراء/بيع مؤهلة أو إذن تداول. يجمع نسخة محفوظة راجعتها صراحةً؛ لا يقرأ مسودة الإدخال غير المحفوظة. انتظار أو عدم تداول لا يعني تنبؤًا بالسوق.")}</p>
  <div className="flex flex-wrap gap-3 my-3"><button className="border rounded p-2" disabled={busy} onClick={()=>void load()}>{tr("تحميل النسخ المراجعة")}</button><button className="border rounded p-2" disabled={busy} onClick={()=>void loadHistory()}>{tr("سجل تقارير الجلسة")}</button></div>
  <label>{tr("نسخة الملاحظة")}<select aria-label={tr("نسخة التقرير")} className={field} value={selected} onChange={e=>setSelected(e.target.value)}><option value="">{tr("اختر نسخة محفوظة مراجعة")}</option>{observations.map(v=><option key={v.record.id} value={v.record.id}>{tr(v.record.packet.instrument_id)} · {tr(v.record.packet.contract??'عقد غير معلوم')} · {tr(v.record.id.slice(0,8))} / {tr(v.record.revision.slice(0,8))}</option>)}</select></label>
  <p className="text-white/60 my-2">{tr("الحساب المختار: ")}{tr(evaluation?.profile.id??'لا يوجد')} · {tr(dirty?'تعديلات حساب غير محفوظة؛ احفظها أولًا':'يُعاد فحص نسخته قبل الحفظ')}</p>
  <button className="bg-cyan-900 rounded p-2" disabled={busy||dirty||!evaluation?.account_revision||!selected} onClick={()=>void create()}>{tr(busy?'جمع وفحص الأدلة…':'بناء وحفظ تقرير الجلسة')}</button>
  {error&&<p role="alert" className="text-red-300 my-3">{tr(error)}</p>}
  <div className="flex flex-wrap gap-2 my-3">{history.map(h=><button key={h.id} className="border rounded p-2" disabled={busy} onClick={()=>void open(h.id)}>{tr("فتح تقرير ")}{tr(h.id.slice(0,8))} · {tr(h.created)}</button>)}</div>
  {visible&&<div data-testid="briefing-result" className="space-y-3 mt-4">
   <p className="text-amber-200">{tr(briefingAge(visible.record.inputs.assessed_at,now))} · {tr(visible.record.result.decision==='WAIT'?'انتظار — لا إشارة مؤهلة':'عدم تداول — توجد قيود أو أدلة متعارضة')}</p>
   <p>{tr("الأداة: ")}{tr(visible.record.inputs.observation.record.packet.instrument_id)}{tr(" · العقد: ")}{tr(visible.record.inputs.observation.record.packet.contract??'غير معلوم')}{tr(" · الحساب: ")}{tr(visible.record.inputs.profile.id)}</p>
   <p>{tr("نسخة السعر: ")}{tr(visible.record.inputs.observation.record.revision.slice(0,12))}{tr(" · وقت التقرير UTC: ")}{tr(visible.record.inputs.assessed_at)}{tr(" · وقت إعادة الفتح: ")}{tr(visible.reopened_at)}</p>
   <h3 className="font-semibold">{tr("ما ساهم فعليًا")}</h3>
   <div className="grid sm:grid-cols-2 gap-2">{visible.record.result.capabilities.map(c=><div key={c.name} className="border border-white/15 rounded p-2"><strong>{tr(capabilityLabel[c.name]??c.name)}</strong> — {tr(capabilityState[c.state])}<p className="text-white/50">{tr(c.reasons.map(briefingReason).join(' · '))}</p></div>)}</div>
   <h3 className="font-semibold">{tr("الأسعار والمؤشرات المطبوعة — مصدر معلن")}</h3>
   {visible.record.inputs.observation.record.packet.frames.map(f=><div key={f.image_id} className="border border-white/15 rounded p-3"><p>{tr(f.interval)}{tr(" · وقت السعر: ")}{tr(f.observed_at??'غير معلوم')}{tr(" · آخر سعر: ")}{tr(f.last??'غير معلوم')}{tr(" · Bid/Ask: ")}{tr(f.bid??'؟')} / {tr(f.ask??'؟')}</p><p>{tr("موضع قراءة السعر: ")}{tr(f.price_evidence)}</p>{f.indicators.map((v,i)=><p key={i}>{tr("مؤشر مطبوع: ")}{tr(v.label)} = {tr(v.value??'غير معلوم')} · {tr(v.evidence)}</p>)}{f.printed_levels.map((v,i)=><p key={i}>{tr("مستوى مطبوع: ")}{tr(v.label)} = {tr(v.value??'غير معلوم')} · {tr(v.evidence)}</p>)}{f.hypotheses.map((h,i)=><p key={i}>{tr("فرضية مستخدم: ")}{tr(h)}</p>)}</div>)}
   <p>{tr("مقارنة أسعار اللحظة نفسها: ")}{tr(visible.record.result.frame_comparison==='NOT_COMPARABLE'?'لا تجوز المقارنة المباشرة بين الأوقات/القيم المتاحة':visible.record.result.frame_comparison==='SAME_TIME_CONFLICT'?'أسعار متعارضة في الوقت نفسه':'آخر سعر متوافق في الوقت نفسه؛ ليس إجماع استراتيجية')}</p>
   <h3 className="font-semibold">{tr("الحساب الشخصي — من سجلك")}</h3>
   <p>{tr("الرصيد: ")}{tr(String(visible.record.result.account_status.balance))}{tr(" · المتبقي للهدف: ")}{tr(String(visible.record.result.account_status.profit_remaining))}{tr(" · هامش خسارة اليوم: ")}{tr(String(visible.record.result.account_status.daily_loss_remaining))}{tr(" · هامش التراجع: ")}{tr(String(visible.record.result.account_status.drawdown_remaining))}</p>
   <p>{tr("التعرض Micro: ")}{tr(String(visible.record.result.cap?.gross_micro_contracts??'غير معلوم'))}{tr(" · فحص السقف ليس حجم صفقة جديدة. بيانات الوقف والتكاليف للحجم تبقى في ورقة المخاطر الحالية.")}</p>
   <h3 className="font-semibold">{tr("الأخبار والأحداث عند إنشاء التقرير")}</h3>
   {visible.record.result.context.headlines.map(h=><p key={h.item.id}><a className="text-sky-300 underline" href={h.item.url} target="_blank" rel="noopener noreferrer">{h.item.title}</a> · {h.item.source}{tr(" · نشر UTC: ")}{tr(h.item.published_at)}</p>)}
   <p>{tr("العناوين: ")}{tr(visible.record.result.context.headlines.length)}{tr(" · الأحداث: ")}{tr(visible.record.result.context.events.length)}{tr(" · التغطية جزئية ومخاطر الأحداث غير معلومة.")}</p>
   <details><summary>{tr("تفاصيل مصادر الأخبار والأحداث")}</summary><pre dir="ltr" className="whitespace-pre-wrap break-all text-xs">{tr(JSON.stringify(visible.record.result.context,null,2))}</pre></details>
   <details open><summary>{tr("لماذا الانتظار وما ينقص؟")}</summary>{[...visible.record.result.reasons,...visible.current_warnings].map((r,i)=><p key={i} className="text-amber-100/80">{tr(briefingReason(r))}</p>)}</details>
   <details><summary>{tr("سياق الوكلاء المعلن — لا إذن دخول")}</summary>{visible.record.result.agent_context.map((r,i)=><p key={i}>{tr(r.topic)} · {tr(r.timestamp)} · {r.summary}</p>)}</details>
   <p className="text-white/60">{tr("الفرضيات والمعلومات المنقولة ليست شموعًا موثقة. فرص الاجتياز UNKNOWN، وتنفيذ التداول معطل.")}</p>
  </div>}
 </section>;
}
