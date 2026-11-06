import { useState, useRef, useEffect } from 'react';
import {
  Sparkles,
  Send,
  Trash2,
  Copy,
  Check,
  Brain,
  Sliders,
  Zap,
  Activity,
  Shield,
  HelpCircle,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react';
import { clsx } from 'clsx';
import { tr, useLanguage } from '@/i18n';

export interface ChatMessage {
  id: string;
  role: 'user' | 'model';
  content: string;
  timestamp: string;
  model?: string;
  roleId?: 'cio' | 'quant' | 'scout';
  isSimulated?: boolean;
}

export type PersonaId = 'cio' | 'quant' | 'scout';
export type GeminiModel = 'gemini-4-argon' | 'gemini-3.8-flash' | 'gemini-3.1-flash-lite';

interface PersonaConfig {
  id: PersonaId;
  name: string;
  nameAr: string;
  title: string;
  defaultModel: GeminiModel;
  icon: LucideIcon;
  accentColor: string;
  badgeBg: string;
  description: string;
  descriptionAr: string;
}

const PERSONAS: Record<PersonaId, PersonaConfig> = {
  cio: {
    id: 'cio',
    name: 'Chief Investment Officer (CIO)',
    nameAr: 'كبير مسؤولي الاستثمار (CIO)',
    title: 'Macro Allocation & Risk Governance',
    defaultModel: 'gemini-4-argon',
    icon: Brain,
    accentColor: 'text-purple-400',
    badgeBg: 'bg-purple-500/10 border-purple-500/30 text-purple-300',
    description: 'Macroeconomic regimes, cross-asset capital distribution, and 1% risk rail governance.',
    descriptionAr: 'النظام الاقتصادي الكلي، توزيع رأس المال، وحوكمة سقف المخاطرة 1%.',
  },
  quant: {
    id: 'quant',
    name: 'Lead Quant Strategist',
    nameAr: 'كبير الاستراتيجيين الكميين',
    title: 'Stat-Arb, Volatility & Microstructure',
    defaultModel: 'gemini-3.8-flash',
    icon: Sliders,
    accentColor: 'text-indigo-400',
    badgeBg: 'bg-indigo-500/10 border-indigo-500/30 text-indigo-300',
    description: 'Statistical arbitrage, GARCH(1,1) volatility modeling, TWAP/VWAP execution.',
    descriptionAr: 'المراجحة الإحصائية، نمذجة تقلبات GARCH، وخوارزميات تنفيذ TWAP/VWAP.',
  },
  scout: {
    id: 'scout',
    name: 'Market Scout & Sentinel',
    nameAr: 'مستكشف السوق وحارس التنفيذ',
    title: 'Rapid Ticks, Spreads & Flow Alerts',
    defaultModel: 'gemini-3.1-flash-lite',
    icon: Zap,
    accentColor: 'text-amber-400',
    badgeBg: 'bg-amber-500/10 border-amber-500/30 text-amber-300',
    description: 'Low-latency order book imbalance, spread monitoring, and instant tick diagnostics.',
    descriptionAr: 'مراقبة فورية لفروق الأسعار، اختلالات دفتر الأوامر، وتنبيهات السيولة.',
  },
};

const SUGGESTED_PROMPTS: Record<PersonaId, string[]> = {
  cio: [
    'Assess current portfolio risk across crypto, forex, and equities',
    'Explain the 1% risk-per-trade rail and 25% drawdown circuit breaker',
    'What is ALGHREST’s macroeconomic thesis for BTC and Tech equities?',
    'Review the 7-tier multi-agent orchestration architecture',
  ],
  quant: [
    'Analyze BTC/ETH statistical arbitrage spread and z-score trigger',
    'Calculate current GARCH(1,1) volatility forecast for Bitcoin',
    'How do FeeOptimizer and SlippageMinimizer split TWAP child orders?',
    'Verify Tier 4 strategy backtest validation requirements (Sharpe ≥ 1.0)',
  ],
  scout: [
    'Check current BTC, ETH, and SOL real-time order book liquidity',
    'Any latency anomalies detected on prices.realtime Kafka topic?',
    'Scan for liquidity sweeps and immediate support levels on MES/BTC',
    'Quick check: Are any exchange execution slippages elevated?',
  ],
};

export function GeminiChatbot({ isDrawer = false }: { isDrawer?: boolean }) {
  useLanguage();
  const [selectedPersona, setSelectedPersona] = useState<PersonaId>('quant');
  const [selectedModel, setSelectedModel] = useState<GeminiModel>('gemini-3.8-flash');
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    {
      id: 'init-msg',
      role: 'model',
      content: `مرحبًا بك في منصة التحليل الكمي الذكي **ALGHREST Gemini AI Analyst**.\n\nأنا هنا لتقديم تحليلات معمقة لمحافظ التداول الآلية، وفحص مؤشرات المراجحة الإحصائية (Stat-Arb)، وتقييم المخاطر وفق قواعد ALGHREST الصارمة (سقف مخاطرة 1% للصفقة ودائرة إيقاف الخسائر عند 25%).\n\nاختر الشخصية المناسبة من الأعلى (كبير مسؤولي الاستثمار CIO، كبير الخبراء الكميين Quant، أو مستكشف السوق السريع Scout) وابدأ المحادثة.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: 'gemini-3.8-flash',
      roleId: 'quant',
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Adjust model when persona changes if user hasn't explicitly customized
  const handlePersonaSelect = (personaId: PersonaId) => {
    setSelectedPersona(personaId);
    setSelectedModel(PERSONAS[personaId].defaultModel);
  };

  const handleSend = async (customPrompt?: string) => {
    const textToSend = customPrompt || input.trim();
    if (!textToSend || loading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const newHistory = [...messages, userMessage];
    setMessages(newHistory);
    setInput('');
    setLoading(true);

    try {
      // Send conversation history to server
      const payloadMessages = newHistory.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: payloadMessages,
          model: selectedModel,
          roleId: selectedPersona,
        }),
      });

      if (!res.ok) {
        throw new Error(`Server returned ${res.status}: ${res.statusText}`);
      }

      const data = await res.json();
      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'model',
        content: data.content || 'لم يتم استلام رد من النموذج.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: data.model || selectedModel,
        roleId: data.roleId || selectedPersona,
        isSimulated: Boolean(data.simulated || data.fallback),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'model',
        content: `⚠️ **تعذر إكمال الطلب**: ${err?.message || 'حدث خطأ غير متوقع'}.\n\nتأكد من عمل الخادم وحاول مجددًا.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        roleId: selectedPersona,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleClear = () => {
    setMessages([
      {
        id: `init-${Date.now()}`,
        role: 'model',
        content: `تم مسح سجل المحادثة. كيف يمكنني مساعدتك في تحليل السوق أو استراتيجيات ALGHREST اليوم؟`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        roleId: selectedPersona,
      },
    ]);
  };

  const activePersonaConfig = PERSONAS[selectedPersona];

  return (
    <div
      className={clsx(
        'flex flex-col bg-bg-surface border border-border rounded-xl overflow-hidden shadow-xl',
        isDrawer ? 'h-full' : 'h-[calc(100vh-140px)] min-h-[600px]',
      )}
    >
      {/* ── TOP CONTROL BAR: PERSONA & MODEL SELECTORS ────────────────────── */}
      <div className="p-4 border-b border-border bg-bg-elevated/40 flex flex-wrap items-center justify-between gap-3">
        {/* Personas */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {(Object.keys(PERSONAS) as PersonaId[]).map((key) => {
            const p = PERSONAS[key];
            const Icon = p.icon;
            const isSelected = selectedPersona === key;
            return (
              <button
                key={key}
                onClick={() => handlePersonaSelect(key)}
                className={clsx(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all border',
                  isSelected
                    ? `${p.badgeBg} font-semibold ring-1 ring-inset ring-white/10 shadow-sm`
                    : 'bg-white/5 border-border text-white/60 hover:text-white hover:bg-white/10',
                )}
              >
                <Icon size={14} className={p.accentColor} />
                <span>{tr(p.name)}</span>
              </button>
            );
          })}
        </div>

        {/* Model selector & Clear action */}
        <div className="flex items-center gap-2">
          {/* Model toggle */}
          <div className="flex items-center bg-black/40 border border-border rounded-lg p-0.5 text-xs font-mono">
            {(
              [
                { id: 'gemini-4-argon', label: 'Argon', tag: 'Deep Quant' },
                { id: 'gemini-3.8-flash', label: '3.8 Flash', tag: 'General' },
                { id: 'gemini-3.1-flash-lite', label: '3.1 Lite', tag: 'Fast' },
              ] as const
            ).map((m) => (
              <button
                key={m.id}
                onClick={() => setSelectedModel(m.id)}
                title={`${m.id} (${m.tag})`}
                className={clsx(
                  'px-2.5 py-1 rounded-md transition-all text-[11px]',
                  selectedModel === m.id
                    ? 'bg-indigo-600 text-white font-bold shadow-sm'
                    : 'text-white/50 hover:text-white hover:bg-white/5',
                )}
              >
                {m.label}
              </button>
            ))}
          </div>

          {/* Reset button */}
          <button
            onClick={handleClear}
            title={tr("Clear Chat History")}
            className="p-1.5 rounded-lg bg-white/5 border border-border text-white/40 hover:text-white hover:bg-white/10 transition-colors"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* ── LIVE TELEMETRY BAR ────────────────────────────────────────────── */}
      <div className="px-4 py-2 bg-black/30 border-b border-border/60 flex items-center justify-between text-[11px] font-mono text-white/60 overflow-x-auto">
        <div className="flex items-center gap-4 flex-nowrap">
          <span className="flex items-center gap-1.5 text-profit">
            <Activity size={12} />
            <span>{tr("PORTFOLIO:")} $102,840.45 (+2.84%)</span>
          </span>
          <span className="hidden sm:inline-block text-white/30">•</span>
          <span className="text-white/70">{tr("ACTIVE AGENTS: 32/32 (Tiers 1-7)")}</span>
          <span className="hidden sm:inline-block text-white/30">•</span>
          <span className="flex items-center gap-1 text-indigo-300">
            <Shield size={12} />
            <span>{tr("RISK RAIL: 0.85% / 1.00% MAX")}</span>
          </span>
        </div>
        <div className="text-white/40 ps-2 whitespace-nowrap">
          <span>{tr(activePersonaConfig.title)}</span>
        </div>
      </div>

      {/* ── CONVERSATION THREAD ───────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => {
          const isUser = msg.role === 'user';
          const pConfig = msg.roleId ? PERSONAS[msg.roleId] : activePersonaConfig;
          const Icon = pConfig.icon;

          return (
            <div
              key={msg.id}
              className={clsx('flex gap-3 max-w-4xl', isUser ? 'ms-auto flex-row-reverse' : 'me-auto')}
            >
              {/* Avatar */}
              <div
                className={clsx(
                  'w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 text-xs font-bold border',
                  isUser
                    ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-300'
                    : 'bg-bg-elevated border-border text-white/80',
                )}
              >
                {isUser ? (
                  <span>YOU</span>
                ) : (
                  <Icon size={16} className={pConfig.accentColor} />
                )}
              </div>

              {/* Message Bubble */}
              <div
                className={clsx(
                  'rounded-xl p-3.5 text-sm leading-relaxed border space-y-2 max-w-[85%] sm:max-w-[78%]',
                  isUser
                    ? 'bg-indigo-600/15 border-indigo-500/30 text-indigo-50'
                    : 'bg-bg-elevated/70 border-border text-white/90 shadow-md',
                )}
              >
                {/* Header info for assistant */}
                {!isUser && (
                  <div className="flex items-center justify-between border-b border-white/5 pb-1.5 text-[11px] font-mono text-white/40">
                    <div className="flex items-center gap-2">
                      <span className={clsx('font-semibold', pConfig.accentColor)}>
                        {tr(pConfig.name)}
                      </span>
                      {msg.model && (
                        <span className="px-1.5 py-0.5 rounded bg-black/40 border border-border text-[10px] text-white/60">
                          {msg.model}
                        </span>
                      )}
                      {msg.isSimulated && (
                        <span className="px-1.5 py-0.5 rounded bg-amber-500/10 border border-amber-500/30 text-[9px] text-amber-300">
                          {tr("DEMO SYNTHESIS")}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span>{msg.timestamp}</span>
                      <button
                        onClick={() => handleCopy(msg.id, msg.content)}
                        className="text-white/30 hover:text-white transition-colors"
                        title={tr("Copy response")}
                      >
                        {copiedId === msg.id ? (
                          <Check size={12} className="text-profit" />
                        ) : (
                          <Copy size={12} />
                        )}
                      </button>
                    </div>
                  </div>
                )}

                {/* Message Body with clean styling */}
                <div className="whitespace-pre-wrap font-sans space-y-2 selection:bg-indigo-500/30">
                  {msg.content}
                </div>
              </div>
            </div>
          );
        })}

        {/* Loading / Thinking indicator */}
        {loading && (
          <div className="flex gap-3 me-auto max-w-xl animate-fade-in">
            <div className="w-8 h-8 rounded-lg bg-bg-elevated border border-border flex items-center justify-center flex-shrink-0">
              <Sparkles size={16} className="text-indigo-400 animate-spin" />
            </div>
            <div className="rounded-xl p-3.5 bg-bg-elevated/70 border border-border text-sm flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 rounded-full bg-indigo-400 animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs font-mono text-white/50">
                {tr("Analyzing quantitative metrics via")} {selectedModel}...
              </span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── SUGGESTED PROMPTS BAR ─────────────────────────────────────────── */}
      <div className="px-4 py-2 border-t border-border/70 bg-bg-elevated/20 overflow-x-auto">
        <div className="flex items-center gap-1.5 flex-nowrap">
          <span className="text-[11px] font-mono text-white/40 whitespace-nowrap flex items-center gap-1 me-1">
            <HelpCircle size={12} /> {tr("Quick Prompts:")}
          </span>
          {SUGGESTED_PROMPTS[selectedPersona].map((prompt, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(prompt)}
              disabled={loading}
              className="text-xs whitespace-nowrap px-2.5 py-1 rounded-full bg-white/5 hover:bg-white/10 border border-border text-white/70 hover:text-white transition-all text-start"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      {/* ── INPUT FORM ───────────────────────────────────────────────────── */}
      <div className="p-3 bg-bg-surface border-t border-border">
        <div className="flex gap-2 items-end bg-bg-elevated rounded-xl border border-border p-2 focus-within:border-indigo-500/50 focus-within:ring-1 focus-within:ring-indigo-500/30 transition-all">
          <textarea
            ref={textareaRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={tr(
              `اسأل ${PERSONAS[selectedPersona].nameAr} حول استراتيجيات التداول، المخاطر، أو السوق... (Enter للإرسال)`,
            )}
            className="flex-1 bg-transparent border-0 text-sm text-white placeholder-white/30 focus:outline-none resize-none px-2 py-1 leading-relaxed"
          />
          <button
            onClick={() => handleSend()}
            disabled={!input.trim() || loading}
            className={clsx(
              'px-4 py-2 rounded-lg font-medium text-xs flex items-center gap-1.5 transition-all flex-shrink-0',
              input.trim() && !loading
                ? 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-md'
                : 'bg-white/5 text-white/30 cursor-not-allowed border border-white/5',
            )}
          >
            {loading ? <RefreshCw size={14} className="animate-spin" /> : <Send size={14} />}
            <span>{tr("إرسال")}</span>
          </button>
        </div>
        <div className="flex items-center justify-between mt-2 px-1 text-[10px] text-white/30">
          <span>{tr("Press Enter to send, Shift+Enter for new line")}</span>
          <span className="font-mono">
            {tr("Current Engine:")} {selectedModel}
          </span>
        </div>
      </div>
    </div>
  );
}
