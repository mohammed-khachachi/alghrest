import { useMemo, useState } from 'react';
import {
  ArrowRight,
  BarChart3,
  Bot,
  Brain,
  CheckCircle2,
  CircleDollarSign,
  Cpu,
  Database,
  Gauge,
  Globe2,
  Languages,
  Lock,
  Radio,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

type Lang = 'ar' | 'fr';

const copy = {
  ar: {
    switch: 'FR',
    title: 'ALGHREST',
    subtitle: 'منظومة تداول ذاتية متعددة الوكلاء، مصممة لتشرح للمستثمر كيف يتحول الذكاء إلى قرار قابل للتنفيذ.',
    cta: 'شاهد شيما التفاعل',
    live: 'النظام يعمل الآن',
    stats: ['طبقات تشغيل', 'خدمة', 'وكيل تقريبا', 'مخاطرة قصوى/صفقة'],
    capabilitiesTitle: 'ما الذي يميز المشروع؟',
    schemaTitle: 'شيما تفاعل الوكلاء',
    schemaText:
      'كل وكيل يعمل باستقلالية، لكنه لا يتصل مباشرة بالآخرين. Kafka هو قلب التواصل، وطبقة المخاطر تفحص القرار قبل التنفيذ.',
    agentsTitle: 'الوكلاء وهم يعملون',
    calculatorTitle: 'حاسبة عائد تقديرية للمستثمر',
    capital: 'رأس المال',
    months: 'المدة بالأشهر',
    scenario: 'سيناريو شهري',
    conservative: 'محافظ 2%',
    balanced: 'متوازن 5%',
    aggressive: 'مرتفع 10%',
    expectedValue: 'القيمة المتوقعة',
    expectedProfit: 'الربح التقديري',
    riskNote: 'الأرقام افتراضية للعرض فقط وليست وعدا بالربح.',
    investorTitle: 'رسائل قوية للمستثمر',
    footer: 'هذا العرض يشرح الرؤية التقنية والتجارية، وليس توصية مالية.',
  },
  fr: {
    switch: 'AR',
    title: 'ALGHREST',
    subtitle:
      "Un système de trading autonome multi-agents, conçu pour montrer à un investisseur comment l'intelligence devient une décision exécutable.",
    cta: "Voir le schéma d'interaction",
    live: 'Système en activité',
    stats: ['Couches', 'Services', 'Agents environ', 'Risque max/trade'],
    capabilitiesTitle: 'Pourquoi le projet est remarquable ?',
    schemaTitle: "Schéma d'interaction des agents",
    schemaText:
      "Chaque agent travaille de façon indépendante. Les agents ne s'appellent pas directement : Kafka orchestre les messages et le risque valide avant exécution.",
    agentsTitle: 'Agents en action',
    calculatorTitle: 'Calculateur indicatif pour investisseur',
    capital: 'Capital',
    months: 'Durée en mois',
    scenario: 'Scénario mensuel',
    conservative: 'Conservateur 2%',
    balanced: 'Équilibré 5%',
    aggressive: 'Élevé 10%',
    expectedValue: 'Valeur estimée',
    expectedProfit: 'Profit estimé',
    riskNote: 'Ces chiffres sont hypothétiques et ne garantissent aucun rendement.',
    investorTitle: 'Messages clés pour investisseur',
    footer: "Cette présentation explique la vision technique et commerciale. Ce n'est pas un conseil financier.",
  },
};

const capabilities = [
  {
    icon: Brain,
    titleAr: 'تحليل متعدد المصادر',
    titleFr: 'Analyse multi-source',
    textAr: 'أسعار، أخبار، مؤشرات اقتصادية، sentiment، on-chain، ومخاطر جيوسياسية.',
    textFr: 'Prix, actualités, macro, sentiment, on-chain et risques géopolitiques.',
  },
  {
    icon: ShieldCheck,
    titleAr: 'حوكمة مخاطر قبل التنفيذ',
    titleFr: 'Risque avant exécution',
    textAr: 'المقترحات تمر عبر حدود رأس المال، drawdown، kill switch، وموافقة صريحة.',
    textFr: 'Les propositions passent par capital limits, drawdown, kill switch et approbation.',
  },
  {
    icon: Cpu,
    titleAr: 'بنية قابلة للتوسع',
    titleFr: 'Architecture scalable',
    textAr: 'إضافة وكيل جديد تتم عبر topic دون كسر باقي النظام.',
    textFr: 'Un nouvel agent se branche via un topic sans casser le reste du système.',
  },
  {
    icon: BarChart3,
    titleAr: 'شفافية تشغيلية',
    titleFr: 'Transparence opérationnelle',
    textAr: 'كل heartbeat ورسالة وتنفيذ يمكن مراقبته في Dashboard أو Grafana.',
    textFr: 'Chaque heartbeat, message et exécution peut être suivi dans le Dashboard ou Grafana.',
  },
];

const nodes = [
  { id: 'intel', icon: Globe2, label: 'Intelligence', x: '8%', y: '16%', color: 'from-cyan-400 to-blue-500' },
  { id: 'strategy', icon: TrendingUp, label: 'Strategies', x: '8%', y: '62%', color: 'from-fuchsia-400 to-pink-500' },
  { id: 'risk', icon: Lock, label: 'Risk Governor', x: '40%', y: '78%', color: 'from-amber-300 to-orange-500' },
  { id: 'approval', icon: CheckCircle2, label: 'Approver', x: '72%', y: '16%', color: 'from-emerald-300 to-teal-500' },
  { id: 'execution', icon: Zap, label: 'Execution', x: '72%', y: '62%', color: 'from-indigo-300 to-violet-500' },
];

const agents = [
  ['CIO Agent', 'proposals.approved', 82],
  ['Market Data Hub', 'market.data', 67],
  ['Risk Governor', 'risk.alerts', 74],
  ['ML Predictor', 'proposals.bus', 89],
  ['Order Router', 'orders.pending', 63],
  ['Exchange Executor', 'fills.confirmed', 71],
];

const investorMessages = [
  {
    ar: 'ليس سكربت تداول، بل منصة وكلاء قابلة للتوسع.',
    fr: "Ce n'est pas un script de trading, mais une plateforme multi-agents scalable.",
  },
  {
    ar: 'المخاطر ليست إضافة لاحقة، بل موجودة داخل مسار القرار.',
    fr: "Le risque n'est pas ajouté après coup : il est intégré au flux de décision.",
  },
  {
    ar: 'يمكن عرض الأداء والصحة والقرارات بشفافية كاملة.',
    fr: 'La performance, la santé système et les décisions restent observables.',
  },
];

export function InvestorPitch() {
  const [lang, setLang] = useState<Lang>('ar');
  const [capital, setCapital] = useState(10000);
  const [months, setMonths] = useState(12);
  const [rate, setRate] = useState(0.05);
  const t = copy[lang];
  const isAr = lang === 'ar';

  const chartData = useMemo(() => {
    let value = capital;
    return Array.from({ length: months + 1 }, (_, month) => {
      if (month > 0) value *= 1 + rate;
      return { month, value: Math.round(value) };
    });
  }, [capital, months, rate]);

  const finalValue = chartData[chartData.length - 1]?.value ?? capital;
  const profit = finalValue - capital;
  const money = new Intl.NumberFormat(lang === 'ar' ? 'ar-MA' : 'fr-FR', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });

  return (
    <div dir={isAr ? 'rtl' : 'ltr'} className="min-h-full overflow-hidden rounded-xl bg-[#060708] text-white">
      <section className="relative min-h-[86vh] overflow-hidden px-5 py-8 sm:px-8 lg:px-10">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_20%,rgba(16,185,129,0.18),transparent_30%),radial-gradient(circle_at_80%_40%,rgba(99,102,241,0.2),transparent_32%)]" />
        <div className="absolute inset-0 investor-grid opacity-30" />

        <div className="relative z-10 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-lg bg-emerald-400/15 ring-1 ring-emerald-300/30">
              <Sparkles size={20} className="text-emerald-300" />
            </div>
            <div>
              <div className="text-lg font-black tracking-[0.28em]">{t.title}</div>
              <div className="font-mono text-xs text-white/45">INVESTOR PRESENTATION</div>
            </div>
          </div>
          <button
            onClick={() => setLang(isAr ? 'fr' : 'ar')}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm font-bold text-white/80 transition hover:-translate-y-0.5 hover:bg-white/10"
          >
            <Languages size={16} />
            {t.switch}
          </button>
        </div>

        <div className="relative z-10 grid min-h-[70vh] items-center gap-10 pt-10 lg:grid-cols-[0.9fr_1.1fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-300/10 px-4 py-2 text-sm font-semibold text-emerald-200">
              <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.9)]" />
              {t.live}
            </div>
            <h1 className="max-w-4xl text-5xl font-black leading-tight sm:text-6xl lg:text-7xl">
              {t.title}
              <span className="block bg-gradient-to-r from-emerald-200 via-cyan-200 to-indigo-200 bg-clip-text text-transparent">
                Autonomous Trading Intelligence
              </span>
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-white/62">{t.subtitle}</p>
            <a
              href="#investor-schema"
              className="mt-8 inline-flex items-center gap-3 rounded-lg bg-emerald-300 px-5 py-3 font-black text-slate-950 transition hover:-translate-y-1 hover:shadow-[0_20px_70px_rgba(52,211,153,0.28)]"
            >
              {t.cta}
              <ArrowRight size={18} className={isAr ? 'rotate-180' : ''} />
            </a>
          </div>

          <div className="relative min-h-[460px] rounded-xl border border-white/10 bg-white/[0.04] p-5 shadow-2xl backdrop-blur-xl">
            <div className="absolute inset-5 rounded-xl border border-emerald-300/10" />
            <div className="relative h-[420px]">
              <div className="absolute left-1/2 top-1/2 grid h-36 w-36 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-gradient-to-br from-emerald-400 to-cyan-500 shadow-[0_0_80px_rgba(45,212,191,0.35)]">
                <div className="absolute inset-[-28px] rounded-full border border-emerald-300/20 animate-ping-slow" />
                <div className="text-center">
                  <Database className="mx-auto mb-1" size={28} />
                  <div className="text-2xl font-black">Kafka</div>
                  <div className="font-mono text-xs text-white/75">BUS</div>
                </div>
              </div>

              {nodes.map(({ id, icon: Icon, label, x, y, color }, index) => (
                <div
                  key={id}
                  className="absolute w-40 rounded-lg border border-white/10 bg-slate-950/70 p-3 shadow-xl backdrop-blur-md transition hover:-translate-y-1 hover:border-emerald-300/40"
                  style={{ left: x, top: y, animationDelay: `${index * 160}ms` }}
                >
                  <div className={`mb-3 grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br ${color}`}>
                    <Icon size={18} />
                  </div>
                  <div className="font-bold">{label}</div>
                  <div className="mt-1 font-mono text-[10px] text-white/40">agent.cluster.{id}</div>
                </div>
              ))}

              {Array.from({ length: 12 }).map((_, index) => (
                <span
                  key={index}
                  className="investor-packet absolute left-1/2 top-1/2 h-2 w-2 rounded-full bg-emerald-200 shadow-[0_0_16px_rgba(167,243,208,0.95)]"
                  style={{
                    ['--angle' as string]: `${index * 30}deg`,
                    ['--distance' as string]: `${150 + (index % 3) * 46}px`,
                    animationDelay: `${index * 180}ms`,
                  }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="relative z-10 grid gap-3 pt-2 sm:grid-cols-4">
          {[7, 37, 20, 1].map((value, index) => (
            <div key={t.stats[index]} className="rounded-lg border border-white/10 bg-white/[0.04] p-4 backdrop-blur">
              <div className="text-3xl font-black text-emerald-200">
                {value}
                {index === 2 ? '+' : index === 3 ? '%' : ''}
              </div>
              <div className="text-sm text-white/50">{t.stats[index]}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="px-5 py-10 sm:px-8 lg:px-10">
        <h2 className="mb-6 text-3xl font-black">{t.capabilitiesTitle}</h2>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {capabilities.map(({ icon: Icon, titleAr, titleFr, textAr, textFr }) => (
            <article key={titleFr} className="rounded-xl border border-white/10 bg-white/[0.04] p-5 transition hover:-translate-y-1 hover:border-emerald-300/30">
              <Icon className="mb-5 text-emerald-300" size={28} />
              <h3 className="mb-2 text-lg font-black">{isAr ? titleAr : titleFr}</h3>
              <p className="text-sm leading-6 text-white/55">{isAr ? textAr : textFr}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="investor-schema" className="grid gap-6 px-5 py-10 sm:px-8 lg:grid-cols-[1fr_0.82fr] lg:px-10">
        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-6">
          <div className="mb-2 flex items-center gap-2 text-emerald-200">
            <Radio size={18} />
            <span className="font-mono text-xs uppercase tracking-[0.24em]">Interaction Map</span>
          </div>
          <h2 className="text-3xl font-black">{t.schemaTitle}</h2>
          <p className="mt-4 max-w-3xl leading-7 text-white/58">{t.schemaText}</p>

          <div className="mt-8 grid gap-3">
            {['Strategy → PROPOSALS_BUS', 'Approver → PROPOSALS_APPROVED', 'Router → ORDERS_PENDING', 'Executor → FILLS_CONFIRMED'].map((step, index) => (
              <div key={step} className="flex items-center gap-4 rounded-lg border border-white/10 bg-slate-950/40 p-4">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-emerald-300/10 font-mono text-sm text-emerald-200">
                  {index + 1}
                </span>
                <span className="font-mono text-sm text-white/72">{step}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-6">
          <h2 className="mb-5 text-2xl font-black">{t.agentsTitle}</h2>
          <div className="space-y-3">
            {agents.map(([name, topic, load]) => (
              <div key={name} className="rounded-lg border border-white/10 bg-slate-950/50 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Bot size={18} className="text-cyan-300" />
                    <div>
                      <div className="font-bold">{name}</div>
                      <div className="font-mono text-xs text-white/35">{topic}</div>
                    </div>
                  </div>
                  <span className="rounded-full bg-emerald-300/10 px-2 py-1 font-mono text-xs text-emerald-200">LIVE</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-white/10">
                  <div className="h-full rounded-full bg-gradient-to-r from-emerald-300 to-cyan-300" style={{ width: `${load}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-6 px-5 py-10 sm:px-8 lg:grid-cols-[0.75fr_1.25fr] lg:px-10">
        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-6">
          <h2 className="mb-5 text-2xl font-black">{t.calculatorTitle}</h2>
          <label className="mb-4 block text-sm font-semibold text-white/60">
            {t.capital}
            <input className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-3 text-white outline-none focus:border-emerald-300/50" type="number" value={capital} onChange={(event) => setCapital(Number(event.target.value))} />
          </label>
          <label className="mb-4 block text-sm font-semibold text-white/60">
            {t.months}
            <input className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-3 text-white outline-none focus:border-emerald-300/50" type="number" min={1} max={60} value={months} onChange={(event) => setMonths(Number(event.target.value))} />
          </label>
          <label className="block text-sm font-semibold text-white/60">
            {t.scenario}
            <select className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950 px-3 py-3 text-white outline-none focus:border-emerald-300/50" value={rate} onChange={(event) => setRate(Number(event.target.value))}>
              <option value={0.02}>{t.conservative}</option>
              <option value={0.05}>{t.balanced}</option>
              <option value={0.1}>{t.aggressive}</option>
            </select>
          </label>
        </div>

        <div className="rounded-xl border border-white/10 bg-white/[0.04] p-6">
          <div className="mb-5 grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg bg-emerald-300/10 p-4">
              <div className="text-sm text-emerald-100/70">{t.expectedValue}</div>
              <div className="mt-1 text-3xl font-black text-emerald-200">{money.format(finalValue)}</div>
            </div>
            <div className="rounded-lg bg-cyan-300/10 p-4">
              <div className="text-sm text-cyan-100/70">{t.expectedProfit}</div>
              <div className="mt-1 text-3xl font-black text-cyan-200">{money.format(profit)}</div>
            </div>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs>
                  <linearGradient id="profitGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#34d399" stopOpacity={0.42} />
                    <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" stroke="rgba(255,255,255,0.35)" />
                <YAxis stroke="rgba(255,255,255,0.35)" />
                <Tooltip formatter={(value) => money.format(Number(value))} />
                <Area type="monotone" dataKey="value" stroke="#34d399" fill="url(#profitGradient)" strokeWidth={3} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-4 text-sm text-white/45">{t.riskNote}</p>
        </div>
      </section>

      <section className="px-5 py-10 sm:px-8 lg:px-10">
        <h2 className="mb-6 text-3xl font-black">{t.investorTitle}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {investorMessages.map((message, index) => (
            <article key={message.fr} className="rounded-xl border border-white/10 bg-gradient-to-br from-white/[0.08] to-white/[0.03] p-6">
              <CircleDollarSign className="mb-5 text-amber-200" size={28} />
              <div className="mb-3 font-mono text-sm text-white/35">0{index + 1}</div>
              <p className="text-lg font-bold leading-7">{isAr ? message.ar : message.fr}</p>
            </article>
          ))}
        </div>
        <div className="mt-8 rounded-lg border border-amber-300/20 bg-amber-300/10 p-4 text-sm text-amber-100/80">
          <Gauge className="mb-2 inline-block" size={18} /> {t.footer}
        </div>
      </section>
    </div>
  );
}
