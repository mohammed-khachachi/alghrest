import { useState } from 'react';
import { MAX_BACKUP_BYTES,researchBackupDownload,researchRestore,type RestoreResult } from '@/lib/researchBackup';

export function ResearchBackup({onRestored}:{onRestored:()=>Promise<void>}) {
 const [busy,setBusy]=useState(false),[raw,setRaw]=useState<string|null>(null),[preview,setPreview]=useState<RestoreResult|null>(null),[message,setMessage]=useState('');
 async function download(){setBusy(true);setMessage('');try{const file=await researchBackupDownload();const url=URL.createObjectURL(file.blob);const a=document.createElement('a');a.href=url;a.download=file.filename;a.click();window.setTimeout(()=>URL.revokeObjectURL(url),60000);setMessage('بدأ تنزيل نسخة البحث. احفظها في مكان خاص وآمن.');}catch(e){setMessage(e instanceof Error?e.message:'تعذر التنزيل.');}finally{setBusy(false);}}
 async function select(file:File|undefined){setRaw(null);setPreview(null);setMessage('');if(!file)return;if(file.size>MAX_BACKUP_BYTES){setMessage('تجاوز الملف حد 32 ميغابايت.');return;}setBusy(true);try{const text=await file.text();const result=await researchRestore(text,true);setRaw(text);setPreview(result);}catch(e){setMessage(e instanceof Error?e.message:'تعذر فحص الملف.');}finally{setBusy(false);}}
 async function restore(){if(!raw||!preview)return;setBusy(true);setMessage('');try{const result=await researchRestore(raw,false);setPreview(null);setRaw(null);setMessage(`اكتملت الاستعادة: أُضيفت ${result.snapshots_added} لقطة و${result.watches_added} رموز؛ ${result.snapshots_unchanged} لقطة موجودة دون تغيير.`);try{await onRestored();}catch{setMessage('اكتملت الاستعادة؛ أعد تحميل السجل لعرض الأعداد الجديدة.');}}catch(e){setMessage(e instanceof Error?e.message:'تعذرت الاستعادة.');}finally{setBusy(false);}}
 return <details aria-label="نسخ البحث واستعادته" className="rounded-lg border border-white/10 p-3 space-y-3">
 <summary className="cursor-pointer text-sm text-indigo-200">نسخ البحث احتياطيًا واستعادته</summary>
 <p className="text-xs text-white/60">يشمل رموز البحث واللقطات فقط. لا يشمل حساباتك أو مفاتيح الوصول. الاستعادة تضيف السجلات دون حذف أو استبدال الموجود، وتُرفض الهوية المتعارضة. بصمة الملف تكشف التلف ولا تثبت أنه صادر من مزوّد البيانات.</p>
 <div className="flex flex-wrap gap-3"><button disabled={busy} onClick={()=>void download()} className="rounded border border-white/15 px-3 py-2 text-sm disabled:opacity-40">تنزيل نسخة البحث</button>
 <label className="text-sm">اختيار نسخة للاستعادة<input aria-label="ملف نسخة البحث" type="file" accept=".json,application/json" disabled={busy} onChange={event=>{void select(event.target.files?.[0]);event.currentTarget.value='';}} className="mt-2 block text-xs" /></label></div>
 {preview&&<div className="text-sm space-y-2"><p>الملف: {preview.watches_in_file} رموز و{preview.snapshots_in_file} لقطات. ستُضاف {preview.watches_added} رموز و{preview.snapshots_added} لقطات؛ الموجود دون تغيير {preview.snapshots_unchanged}.</p>
 <button disabled={busy} onClick={()=>void restore()} className="rounded bg-violet-600 px-3 py-2 disabled:opacity-40">استعادة السجلات الإضافية</button></div>}
 {message&&<p role="status" className="text-sm text-amber-200">{message}</p>}
 </details>;
}
