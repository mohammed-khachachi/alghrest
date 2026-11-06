import { useLanguage, tr } from "../../i18n";
import type { TerminalResearch } from '@/lib/terminalResearch';
import { qualityEvidence, qualityLabel, qualityReasons } from '@/lib/terminalQuality';

export function TerminalQuality({report}: {report: TerminalResearch}) {
  useLanguage();
  const q = report.data_quality;
  const tone = q?.status === 'usable' ? 'text-emerald-200' : q?.status === 'unavailable' ? 'text-red-200' : 'text-amber-200';
  return <div aria-label={tr("جودة بيانات الشموع")} className="space-y-2 rounded-lg border border-white/15 p-3">
    <h4 className={`font-semibold ${tone}`}>{tr("جودة الشموع: ")}{tr(qualityLabel(q))}</h4>
    <p className="text-xs text-white/60">{tr("فحص سلامة السلسلة وصلاحيتها للحسابات؛ حداثة السوق واكتمال التغطية غير معتمدتين.")}</p>
    <ul className="space-y-1 text-sm text-white/80">{qualityReasons(q).map(r => <li key={r}>{tr(r)}</li>)}</ul>
    {q && <>
      <div className="grid grid-cols-2 gap-2 text-xs md:grid-cols-3">{qualityEvidence(q).map(([label, value]) => <p key={label}><span className="text-white/50">{tr(label)}: </span>{tr(value)}</p>)}</div>
      <p className="text-xs text-white/60">{tr("الاستنتاجات: ")}{tr(([['trend', 'الاتجاه'], ['momentum', 'الزخم'], ['volatility', 'التذبذب']] as const).map(([key, label]) => `${label} ${q[key].allowed ? 'متاح' : 'محجوب'}`).join(' · '))}</p>
    </>}
  </div>;
}
