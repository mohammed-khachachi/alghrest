import { GeminiChatbot } from '@/components/chat/GeminiChatbot';
import {
  Brain,
  Sliders,
  Zap,
  ShieldCheck,
  Cpu,
  Lock,
  Layers,
} from 'lucide-react';
import { tr, useLanguage } from '@/i18n';

export function GeminiChat() {
  useLanguage();

  return (
    <div className="space-y-4">
      {/* ── HEADER BANNER ─────────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-bg-surface border border-border rounded-xl p-4 sm:p-5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="flex h-2 w-2 rounded-full bg-indigo-400 animate-pulse" />
            <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
              <Brain className="text-indigo-400" size={20} />
              {tr("Gemini Quantitative AI Analyst")}
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-white/50">
            {tr(
              "تحليل استثماري كمي مدعوم بنماذج Gemini المتعددة (Argon للتحليل المعقد، 3.8 Flash للاستدلال العام، 3.1 Flash-Lite للاستجابة السريعة) مع حفظ سجل المحادثة وقواعد حوكمة ALGHREST.",
            )}
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto font-mono text-xs">
          <div className="px-3 py-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 flex items-center gap-1.5">
            <Layers size={13} />
            <span>{tr("7 Tiers · 32 Agents")}</span>
          </div>
          <div className="px-3 py-1.5 rounded-lg bg-profit/10 border border-profit/20 text-profit flex items-center gap-1.5">
            <ShieldCheck size={13} />
            <span>{tr("1% Max Risk Rail")}</span>
          </div>
        </div>
      </div>

      {/* ── MAIN LAYOUT: CHAT + SIDEBAR INFO ──────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Chat Interface (3 cols) */}
        <div className="xl:col-span-3">
          <GeminiChatbot />
        </div>

        {/* Quant Intelligence & Role Guide (1 col) */}
        <div className="space-y-4">
          {/* Persona Descriptions */}
          <div className="bg-bg-surface border border-border rounded-xl p-4 space-y-3">
            <h2 className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-2">
              <Cpu size={14} className="text-indigo-400" />
              {tr("Active Persona Capabilities")}
            </h2>

            <div className="space-y-2.5 text-xs">
              <div className="p-2.5 rounded-lg bg-bg-elevated/60 border border-purple-500/20 space-y-1">
                <div className="font-semibold text-purple-300 flex items-center gap-1.5">
                  <Brain size={13} />
                  <span>{tr("CIO Agent (Chief Investment Officer)")}</span>
                </div>
                <p className="text-white/60 leading-relaxed">
                  {tr("توزيع الأصول الكلية بين الكريبتو والأسهم، ومراقبة سقف التراجع الأقصى للمحفظة 25% مع الالتزام الصارم بسقف 1% مخاطرة للصفقة.")}
                </p>
                <div className="font-mono text-[10px] text-purple-400/80">
                  {tr("Engine:")} gemini-4-argon ({tr("Deep Reasoning")})
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-bg-elevated/60 border border-indigo-500/20 space-y-1">
                <div className="font-semibold text-indigo-300 flex items-center gap-1.5">
                  <Sliders size={13} />
                  <span>{tr("Lead Quant Strategist")}</span>
                </div>
                <p className="text-white/60 leading-relaxed">
                  {tr("مصفوفات الارتباط، نماذج التقلب المشروط GARCH(1,1)، اختبارات التكامل المشترك للمراجحة الإحصائية (Stat-Arb z-score)، وتجزئة أوامر TWAP/VWAP.")}
                </p>
                <div className="font-mono text-[10px] text-indigo-400/80">
                  {tr("Engine:")} gemini-3.8-flash ({tr("General Quant")})
                </div>
              </div>

              <div className="p-2.5 rounded-lg bg-bg-elevated/60 border border-amber-500/20 space-y-1">
                <div className="font-semibold text-amber-300 flex items-center gap-1.5">
                  <Zap size={13} />
                  <span>{tr("Market Scout & Execution Sentinel")}</span>
                </div>
                <p className="text-white/60 leading-relaxed">
                  {tr("تتبع فوري لفروق الأسعار، مراقبة زمن استجابة Kafka (lag < 5ms)، وتنبيهات السيولة واختلال تدفق الأوامر في الوقت الفعلي.")}
                </p>
                <div className="font-mono text-[10px] text-amber-400/80">
                  {tr("Engine:")} gemini-3.1-flash-lite ({tr("Low Latency")})
                </div>
              </div>
            </div>
          </div>

          {/* Hard Risk Rules Card */}
          <div className="bg-bg-surface border border-border rounded-xl p-4 space-y-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-white/50 flex items-center gap-2">
              <Lock size={14} className="text-loss" />
              {tr("Systemic Risk Rails")}
            </h2>
            <div className="space-y-2 text-xs font-mono">
              <div className="flex justify-between items-center p-2 rounded bg-black/30 border border-white/5">
                <span className="text-white/60">{tr("Max Risk / Trade")}</span>
                <span className="text-profit font-bold">1.0%</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-black/30 border border-white/5">
                <span className="text-white/60">{tr("Max Drawdown Cap")}</span>
                <span className="text-warning font-bold">25.0%</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-black/30 border border-white/5">
                <span className="text-white/60">{tr("Consecutive Losses")}</span>
                <span className="text-white/80 font-bold">{tr("Max 5 (Auto-Pause)")}</span>
              </div>
              <div className="flex justify-between items-center p-2 rounded bg-black/30 border border-white/5">
                <span className="text-white/60">{tr("Hot Wallet Reserve")}</span>
                <span className="text-indigo-300 font-bold">&le; 5.0%</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
export default GeminiChat;
