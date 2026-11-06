import { useLanguage, tr } from "../../i18n";
import { useEffect, useRef, useState } from 'react';
import { researchBriefPDF } from '@/lib/researchBrief';

export function ResearchBriefExport({ enabled }: { enabled: boolean }) {
  useLanguage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [file, setFile] = useState<{url: string; filename: string} | null>(null);
  const mounted = useRef(false);
  const working = useRef(false);
  useEffect(() => { mounted.current = true; return () => {mounted.current = false;}; }, []);
  useEffect(() => () => {if (file) URL.revokeObjectURL(file.url);}, [file]);
  async function generate() {
    if (working.current) return;
    working.current = true; setBusy(true); setError(''); setFile(null);
    try {
      const value = await researchBriefPDF();
      if (!mounted.current) return;
      const url = URL.createObjectURL(value.blob);
      setFile({url, filename: value.filename});
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = value.filename;
      anchor.hidden = true; document.body.append(anchor); anchor.click(); anchor.remove();
    } catch (reason) {
      if (mounted.current) setError(reason instanceof Error ? reason.message : 'تعذر إنشاء التقرير.');
    } finally { working.current = false; if (mounted.current) setBusy(false); }
  }
  return <section aria-label={tr("تصدير موجز البحث")} className="space-y-2 rounded-lg border border-white/10 p-3">
    <div className="flex flex-wrap items-center gap-3"><button disabled={!enabled || busy} onClick={() => void generate()} className="rounded border border-violet-400/50 px-3 py-2 text-sm text-violet-200 disabled:opacity-40">{tr(busy ? 'جارٍ إنشاء التقرير…' : 'تحميل موجز البحث PDF')}</button>
      {file && <a href={file.url} download={file.filename} className="text-sm text-indigo-300 underline">{tr("تنزيل التقرير الجاهز مجددًا")}</a>}
    </div>
    <p className="text-xs text-white/50">{tr("يشمل كل رموز المتابعة وأحدث لقطاتها المحفوظة، مع المقارنة والمصادر وأوقات المغرب. قراءات «تحديث الكل» غير المحفوظة لا تدخل التقرير؛ احفظ لقطة لتضمينها. الرموز بلا لقطة تظهر كبيانات غير متاحة.")}</p>
    {busy && <p role="status" className="text-sm text-white/60">{tr("نُنشئ تقريرًا مؤرخًا من السجل المحلي…")}</p>}
    {file && <p role="status" className="text-sm text-indigo-200">{tr("أُنشئ التقرير وبدأ التنزيل. يمكنك تنزيل النسخة نفسها من الرابط أعلاه.")}</p>}
    {error && <p role="alert" className="text-sm text-red-300">{tr(error)}</p>}
  </section>;
}
