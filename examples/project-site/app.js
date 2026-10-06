const menuButton = document.querySelector("#menuButton");
const mainNav = document.querySelector("#mainNav");
const navLinks = [...document.querySelectorAll(".nav a")];
const topbar = document.querySelector(".topbar");
const pageLoader = document.querySelector("#pageLoader");
const scrollProgress = document.querySelector("#scrollProgress");
const backTop = document.querySelector("#backTop");
const revealItems = [...document.querySelectorAll(".reveal")];
const counters = [...document.querySelectorAll("[data-count]")];
const langToggle = document.querySelector("#langToggle");
let currentLang = localStorage.getItem("alghrest-lang") || "ar";

const copy = {
  ar: {
    title: "ALGHREST | شرح المشروع",
    brandSub: "نظام تداول ذاتي متعدد الوكلاء",
    menuLabel: "فتح القائمة",
    nav: ["الرئيسية", "الحالة", "القدرات", "الوكلاء", "شيما التفاعل", "كيف يشتغل", "البيانات", "الأمان"],
    heroEyebrow: "تحديث مستند README",
    heroTitle: "ALGHREST منصة تداول ذاتية متعددة الوكلاء مبنية حول Kafka والمخاطر والمراقبة.",
    heroLead:
      "المشروع يعمل كبنية event-driven من 7 طبقات و37 خدمة تقريبا: وكلاء ذكاء واستراتيجيات وتنفيذ يتواصلون عبر Kafka، يشاركون الحالة عبر Redis، ويحفظون بيانات الزمن الحقيقي في TimescaleDB.",
    profitCta: "استعرض حالة التنفيذ",
    runtimeCta: "شاهد مسار التشغيل",
    stats: ["طبقات تشغيل", "خدمة ووكيل ضمن المنظومة", "Kafka topics جاهزة", "حد أقصى للمخاطرة في الصفقة"],
    statusEyebrow: "حالة التنفيذ من README",
    statusTitle: "الإصدار الحالي يجمع بين وكلاء مكتملين، واجهة بيانات جديدة، ومناطق لا تزال محمية من التشغيل الحقيقي.",
    statusCopy:
      "حسب README: Tiers 1-5 وTier 7 تعمل كمنظومة مكتملة نسبيا، بينما Tier 6 DeFi ما زال هيكلا أوليا، وv0.3 يركز على market-data API والـ Dashboard وتبديل مزودي البيانات الوهمية بمزودين حقيقيين.",
    statusCards: [
      ["v0.2.0", "طبقات الإنتاج الأساسية مكتملة", "Tiers 1-5 مع Tier 7 monitoring تغطي CIO، المخاطر، التحليل، الاستراتيجيات، التنفيذ، التنبيهات، التدقيق، والقناة الاجتماعية."],
      ["v0.3.0", "Dashboard وMarket Data قيد التطوير", "تمت إضافة REST endpoints للرموز والأسعار والتاريخ والحيازات، مع Overview page وذاكرة TanStack Query مشتركة."],
      ["Agent 16", "ML Predictor منفصل عن خادم النماذج", "الوكيل يبني نافذة OHLCV من 64 فترة ثم يطلب التوقعات من FastAPI inference server على المنفذ 8080."],
      ["حماية", "DeFi وOptions ليست جاهزة للإنتاج", "وكلاء DeFi skeleton فقط، وAgent 20 Options Strategist ما زال pending؛ اترك ENABLE_DEFI_AGENTS=false."],
    ],
    statusRibbon: [
      "Python 3.12 + Poetry",
      "Kafka 7.6 / Redis 7 / TimescaleDB PG16",
      "FastAPI + WebSocket",
      "React 18 + Vite + Tailwind + Zustand",
    ],
    investorEyebrow: "عرض للمستثمر",
    investorTitle: "ALGHREST ليس روبوت تداول بسيط، بل منصة وكلاء قابلة للتوسع ومبنية حول المخاطر.",
    investorCopy:
      "هذه الصفحة تعرض المشروع كرؤية قابلة للاستثمار: بيانات تدخل، وكلاء يحللون، Kafka ينسق، المخاطر توافق، والتنفيذ يحدث مع مراقبة كاملة.",
    investorSchemaCta: "شاهد خريطة الوكلاء",
    investorProfitCta: "اعرض سيناريو العائد",
    investorMessages: [
      ["قابلية الاستثمار", "النظام مقسم إلى خدمات ووكلاء، ما يسمح بالتوسع وإضافة قدرات جديدة دون إعادة بناء كل شيء."],
      ["مخاطر واضحة", "كل قرار تداول يمر عبر طبقة مخاطر وحدود رأس مال قبل الوصول إلى التنفيذ."],
      ["قابلية العرض", "يمكن تحويل كل heartbeat وقرار ورسالة Kafka إلى لوحة مراقبة مقنعة للمستثمر."],
    ],
    capabilitiesEyebrow: "ماذا يمكنه أن يفعل؟",
    capabilitiesTitle: "النظام مصمم ليغطي دورة التداول كاملة من جمع البيانات إلى تنفيذ الأوامر.",
    features: [
      ["أسواق ومزودون متنوعون", "يغطي crypto spot/perps/options، الأسهم الأمريكية، DeFi on-chain، وواجهات Binance وAlpaca وDeribit وIBKR وغيرها."],
      ["استراتيجيات Tier 4", "يدعم trend، mean reversion، momentum، stat arb، breakout، macro rotation، cross-exchange arb، وML predictor."],
      ["مخاطر قبل التنفيذ", "كل مقترح يمر عبر ProposalApprover وPositionLimitChecker مع حد 1% للصفقة وkill switch على Redis."],
      ["تنفيذ متعدد المراحل", "OrderRouter يختار المسار، FeeOptimizer يحسن الرسوم، SlippageMinimizer يقسم الأوامر، وExchangeExecutor يؤكد fills."],
      ["Dashboard وAPI", "FastAPI يقدم REST وWebSocket، والواجهة React/Vite تعرض الأسعار والحيازات وحالة النظام."],
      ["DeFi غير جاهز للإنتاج", "وكلاء yield farmer وDEX arbitrageur وMEV hunter وbridge strategist هياكل أولية فقط."],
    ],
    agentsEyebrow: "الوكلاء أثناء العمل",
    agentsTitle: "لوحة حية توضح كيف تتحرك الوكلاء داخل النظام.",
    agentsCopy:
      "هذا العرض يحاكي التشغيل الحقيقي: كل وكيل يرسل heartbeat، يقرأ أو ينشر رسائل، ويتغير حمله حسب نوع المهمة. عند تشغيل النظام فعليا يمكن ربط هذه الخانة ببيانات API أو WebSocket.",
    liveSimulation: "محاكاة مباشرة",
    pause: "إيقاف مؤقت",
    resume: "تشغيل المحاكاة",
    eventsTitle: "آخر الأحداث",
    schemaEyebrow: "شيما تفاعل الوكلاء",
    schemaTitle: "كيف تتحول فكرة تداول إلى قرار منظم داخل شبكة ALGHREST.",
    schemaCopy:
      "هذا المخطط مصمم للعرض أمام مستثمر: يوضح أن النظام ليس سكربت تداول بسيط، بل شبكة وكلاء مستقلة تتواصل برسائل، تمر عبر حوكمة المخاطر، ثم تصل إلى التنفيذ والمراقبة.",
    schemaNodes: [
      ["Intelligence", "أسعار، أخبار، sentiment، macro، on-chain"],
      ["Strategies", "Trend، Momentum، Stat Arb، ML Predictor"],
      ["Risk Governor", "حدود رأس المال، kill switch، drawdown"],
      ["Proposal Approver", "يفحص المقترحات قبل السماح بالتنفيذ"],
      ["Execution", "Order Router، Fee Optimizer، Slippage، Executor"],
      ["Monitoring", "Dashboard، Alerts، Audit، Portfolio Tracker"],
    ],
    investorPoints: [
      ["قابلية التوسع", "إضافة وكيل جديد تتم دون كسر الباقي لأنه يتصل عبر Kafka topic واضح."],
      ["تحكم في المخاطر", "كل مقترح يمر عبر الموافقة وحدود المركز قبل أن يصبح أمرًا قابلا للتنفيذ."],
      ["شفافية للمراقبة", "كل heartbeat ورسالة وتنفيذ يمكن عرضه في Dashboard أو Grafana."],
    ],
    runtimeEyebrow: "كيف يكون المشروع وهو يشتغل؟",
    runtimeTitle: "عند التشغيل يتحول المشروع إلى شبكة خدمات تتكلم عبر Kafka وتراقب نفسها باستمرار.",
    runtimeCopy:
      "يبدأ Docker Compose بتشغيل Kafka، Redis، TimescaleDB، API، Dashboard، Prometheus، Grafana، ثم الوكلاء. كل وكيل يعمل في حلقة async، يفحص kill switch، وينشر أو يقرأ رسائل من المواضيع المناسبة.",
    pipelineEyebrow: "مسار الصفقة",
    pipelineTitle: "من فكرة الاستراتيجية إلى تنفيذ الصفقة.",
    pipelineLabels: [
      "Strategy → PROPOSALS_BUS",
      "ProposalApprover",
      "OrderRouter",
      "Fee + Slippage",
      "ExchangeExecutor",
    ],
    pipelineDescriptions: [
      "الاستراتيجية تولد مقترح تداول من Tier 4.",
      "يفحص PositionLimitChecker ثم ينشر إلى PROPOSALS_APPROVED.",
      "يختار البورصة والخوارزمية ثم يرسل إلى ORDERS_PENDING.",
      "FeeOptimizer يضيف _optimised وSlippageMinimizer يقسم TWAP/VWAP بعلامة _child.",
      "ينفذ الأمر وينشر ORDERS_EXECUTED وFILLS_CONFIRMED.",
    ],
    calculatorEyebrow: "حاسبة تقديرية",
    calculatorTitle: "نسبة أرباح متوقعة حسب رأس المال المستثمر.",
    calculatorCopy:
      "هذه الحاسبة تعرض سيناريوهات افتراضية فقط. التداول قد يربح أو يخسر، ولا توجد نسبة مضمونة حتى مع وجود نظام آلي ومخاطر محدودة.",
    labels: ["رأس المال بالدولار", "مدة الاستثمار بالأشهر", "إضافة شهرية للاستثمار", "السيناريو", "نسبة مخاطرة الصفقة"],
    options: ["محافظ - 2% شهريا", "متوازن - 5% شهريا", "مرتفع المخاطرة - 10% شهريا"],
    riskText: "كحد أقصى لكل صفقة",
    resultLabels: ["القيمة المتوقعة بعد المدة", "الربح التقديري", "إجمالي المبالغ المضافة", "العائد الكلي", "خسارة شهر سيء محتملة"],
    solEyebrow: "مثال SOL لمدة سنتين",
    solTitle: "كيف يمكن شرح سيناريو استثمار منظم في عملة SOL لمستثمر؟",
    solCopy:
      "المثال التالي يفترض رأس مال أولي مع إضافة شهرية منتظمة لمدة 24 شهرًا. الهدف هو توضيح قوة الانضباط وإعادة الاستثمار، وليس توقع سعر SOL الحقيقي.",
    solCards: ["رأس مال أولي", "إضافة شهرية", "المدة", "قيمة تقديرية"],
    monthUnit: "شهر",
    marketDataEyebrow: "واجهة البيانات والداشبورد",
    marketDataTitle: "README يحدد مسار تطوير Dashboard بدون تشغيل كل البنية الثقيلة.",
    marketDataCopy:
      "للتطوير السريع يمكن تشغيل mock backend على المنفذ 8000 وواجهة Vite على 5173. بيانات العرض الافتراضية تشمل BTC وETH وSOL وEUR/USD وAAPL وTSLA، والتاريخ التجريبي مثبت على 2025-05-11.",
    endpoints: [
      ["GET", "/api/symbols", "كتالوج من 24 رمزا بين crypto وforex وequity."],
      ["GET", "/api/quotes?symbols=BTC,AAPL", "أسعار OHLC وbid/ask وتغير 24h وحجم التداول."],
      ["GET", "/api/history?symbol=X&days=N", "شموع OHLC حتمية تنتهي في 2025-05-11."],
      ["GET", "/api/holdings", "دفتر حيازات تجريبي، والـ P&L يحسب في الواجهة."],
    ],
    services: [
      "API :8000",
      "Docs :8000/docs",
      "Dashboard :5173",
      "Grafana :3000",
      "Kafka UI :8080",
      "Prometheus :9090",
    ],
    safetyEyebrow: "حدود الأمان",
    safetyTitle: "المشروع يحتوي على حواجز أمان يجب احترامها.",
    safety: [
      ["ابدأ ببيئة development أو paper_trading", "النظام يرفض الأوامر الحقيقية إلا إذا تم ضبط ENVIRONMENT=live صراحة."],
      ["لا تشغل DeFi بأموال حقيقية", "وكلاء yield farmer و dex arbitrageur و mev hunter و bridge strategist غير جاهزين للإنتاج."],
      ["احم المفاتيح السرية", "ملف .env لا يجب رفعه إلى Git، ومفاتيح البورصات يجب أن تكون دون صلاحية سحب."],
      ["اختبر قبل live", "الاستراتيجيات يجب أن تمر عبر backtesting و paper trading قبل أي تشغيل حقيقي."],
      ["لا تلين حدود المخاطر", "حد المخاطرة 1% للصفقة، الإيقاف بعد 5 خسائر متتالية، drawdown أقصى 25%، والمحفظة الساخنة لا تتجاوز 5%."],
      ["بوابة backtesting إلزامية", "أي استراتيجية Tier 4 تحتاج 5 سنوات بيانات، 50 صفقة سنويا، Sharpe وProfit Factor وMonte Carlo ضمن الحدود."],
    ],
    footer: "ALGHREST Project Explainer - صفحة ثابتة محدثة من README.",
    top: "العودة للأعلى",
    agentLabels: { load: "الحمل", messages: "الرسائل", topic: "Topic:" },
    status: { active: "يعمل", busy: "مشغول", halted: "متوقف" },
    events: [
      "أرسل heartbeat إلى Redis",
      "قرأ رسالة جديدة من Kafka",
      "نشر تحديثا إلى Dashboard",
      "حدث حالة الصحة الداخلية",
      "أكمل دورة async بدون أخطاء",
      "راجع kill switch قبل المتابعة",
    ],
  },
  fr: {
    title: "ALGHREST | Présentation du projet",
    brandSub: "Système de trading autonome multi-agents",
    menuLabel: "Ouvrir le menu",
    nav: ["Accueil", "Statut", "Capacités", "Agents", "Schéma", "Fonctionnement", "Données", "Sécurité"],
    heroEyebrow: "Mise à jour README",
    heroTitle: "ALGHREST est une plateforme de trading autonome multi-agents centrée sur Kafka, le risque et le monitoring.",
    heroLead:
      "Le projet fonctionne comme une architecture event-driven en 7 couches et environ 37 services : agents d'intelligence, stratégies et exécution communiquent via Kafka, partagent l'état via Redis et stockent les séries temporelles dans TimescaleDB.",
    profitCta: "Voir le statut",
    runtimeCta: "Voir le flux d'exécution",
    stats: ["Couches opérationnelles", "Services et agents", "Kafka topics prêts", "Risque maximal par trade"],
    statusEyebrow: "Statut depuis le README",
    statusTitle: "La version actuelle combine des agents avancés, une surface de données récente et des zones gardées hors production.",
    statusCopy:
      "D'après le README : les Tiers 1-5 et le Tier 7 forment un socle relativement complet, tandis que le Tier 6 DeFi reste un squelette, et v0.3 se concentre sur l'API market-data, le Dashboard et le remplacement des fournisseurs mock.",
    statusCards: [
      ["v0.2.0", "Les couches principales sont complètes", "Les Tiers 1-5 avec le Tier 7 monitoring couvrent CIO, risque, analyse, stratégies, exécution, alertes, audit et canal social."],
      ["v0.3.0", "Dashboard et Market Data en cours", "Les endpoints REST pour symboles, quotes, historique et holdings sont ajoutés, avec une Overview page et un cache TanStack Query partagé."],
      ["Agent 16", "ML Predictor séparé du serveur modèles", "L'agent construit une fenêtre OHLCV de 64 périodes puis demande les prédictions au serveur FastAPI d'inférence sur le port 8080."],
      ["Sécurité", "DeFi et Options ne sont pas prêts", "Les agents DeFi sont des squelettes et l'Agent 20 Options Strategist reste pending ; gardez ENABLE_DEFI_AGENTS=false."],
    ],
    statusRibbon: [
      "Python 3.12 + Poetry",
      "Kafka 7.6 / Redis 7 / TimescaleDB PG16",
      "FastAPI + WebSocket",
      "React 18 + Vite + Tailwind + Zustand",
    ],
    investorEyebrow: "Présentation investisseur",
    investorTitle: "ALGHREST n'est pas un simple robot de trading, mais une plateforme multi-agents scalable et centrée sur le risque.",
    investorCopy:
      "Cette page présente le projet comme une vision investissable : les données entrent, les agents analysent, Kafka orchestre, le risque valide, puis l'exécution se fait avec une surveillance complète.",
    investorSchemaCta: "Voir la carte des agents",
    investorProfitCta: "Afficher le scénario de rendement",
    investorMessages: [
      ["Potentiel d'investissement", "Le système est découpé en services et agents, ce qui permet d'étendre les capacités sans tout reconstruire."],
      ["Risque lisible", "Chaque décision de trading passe par une couche de risque et des limites de capital avant l'exécution."],
      ["Démonstration claire", "Chaque heartbeat, décision et message Kafka peut devenir un tableau de bord convaincant pour l'investisseur."],
    ],
    capabilitiesEyebrow: "Que peut-il faire ?",
    capabilitiesTitle: "Le système couvre tout le cycle de trading, de la collecte des données à l'exécution des ordres.",
    features: [
      ["Marchés et fournisseurs variés", "Couvre crypto spot/perps/options, actions US, DeFi on-chain, et les intégrations Binance, Alpaca, Deribit, IBKR et autres."],
      ["Stratégies Tier 4", "Prend en charge trend, mean reversion, momentum, stat arb, breakout, macro rotation, cross-exchange arb et ML predictor."],
      ["Risque avant exécution", "Chaque proposition passe par ProposalApprover et PositionLimitChecker avec risque de 1% par trade et kill switch Redis."],
      ["Exécution en plusieurs étapes", "OrderRouter choisit la route, FeeOptimizer réduit les frais, SlippageMinimizer découpe les ordres et ExchangeExecutor confirme les fills."],
      ["Dashboard et API", "FastAPI fournit REST et WebSocket, tandis que l'interface React/Vite affiche prix, holdings et santé système."],
      ["DeFi non prêt pour la production", "Les agents yield farmer, DEX arbitrageur, MEV hunter et bridge strategist restent des squelettes."],
    ],
    agentsEyebrow: "Agents en action",
    agentsTitle: "Un panneau vivant qui montre comment les agents évoluent dans le système.",
    agentsCopy:
      "Cette vue simule l'exécution réelle : chaque agent envoie un heartbeat, lit ou publie des messages, et sa charge évolue selon la tâche. En production, ce panneau peut être relié à l'API ou au WebSocket.",
    liveSimulation: "Simulation en direct",
    pause: "Pause",
    resume: "Relancer la simulation",
    eventsTitle: "Derniers événements",
    schemaEyebrow: "Schéma d'interaction des agents",
    schemaTitle: "Comment une idée de trade devient une décision structurée dans ALGHREST.",
    schemaCopy:
      "Ce schéma est pensé pour une présentation investisseur : il montre que le système n'est pas un simple script de trading, mais un réseau d'agents indépendants qui communiquent par messages, passent par la gouvernance du risque, puis arrivent à l'exécution et au monitoring.",
    schemaNodes: [
      ["Intelligence", "Prix, actualités, sentiment, macro, on-chain"],
      ["Strategies", "Trend, Momentum, Stat Arb, ML Predictor"],
      ["Risk Governor", "Limites de capital, kill switch, drawdown"],
      ["Proposal Approver", "Valide les propositions avant l'exécution"],
      ["Execution", "Order Router, Fee Optimizer, Slippage, Executor"],
      ["Monitoring", "Dashboard, Alerts, Audit, Portfolio Tracker"],
    ],
    investorPoints: [
      ["Scalabilité", "Un nouvel agent peut être ajouté sans casser le reste, car il se connecte via un Kafka topic clair."],
      ["Maîtrise du risque", "Chaque proposition passe par l'approbation et les limites de position avant de devenir exécutable."],
      ["Transparence opérationnelle", "Chaque heartbeat, message et exécution peut être exposé dans le Dashboard ou Grafana."],
    ],
    runtimeEyebrow: "Comment le projet fonctionne ?",
    runtimeTitle: "Au lancement, le projet devient un réseau de services qui communiquent via Kafka et se surveillent en continu.",
    runtimeCopy:
      "Docker Compose démarre Kafka, Redis, TimescaleDB, l'API, le Dashboard, Prometheus, Grafana puis les agents. Chaque agent tourne dans une boucle async, vérifie le kill switch et publie ou lit les topics adaptés.",
    pipelineEyebrow: "Flux d'un trade",
    pipelineTitle: "De l'idée de stratégie jusqu'à l'exécution.",
    pipelineLabels: [
      "Strategy → PROPOSALS_BUS",
      "ProposalApprover",
      "OrderRouter",
      "Fee + Slippage",
      "ExchangeExecutor",
    ],
    pipelineDescriptions: [
      "La stratégie Tier 4 génère une proposition de trade.",
      "PositionLimitChecker valide puis publie vers PROPOSALS_APPROVED.",
      "Choisit l'exchange et l'algorithme, puis envoie vers ORDERS_PENDING.",
      "FeeOptimizer ajoute _optimised et SlippageMinimizer découpe TWAP/VWAP avec _child.",
      "Exécute l'ordre et publie ORDERS_EXECUTED et FILLS_CONFIRMED.",
    ],
    calculatorEyebrow: "Calculateur indicatif",
    calculatorTitle: "Rendement attendu selon le capital investi.",
    calculatorCopy:
      "Ce calculateur présente uniquement des scénarios hypothétiques. Le trading peut générer des gains ou des pertes, et aucun rendement n'est garanti même avec un système automatisé.",
    labels: ["Capital en dollars", "Durée d'investissement en mois", "Ajout mensuel investi", "Scénario", "Risque par trade"],
    options: ["Conservateur - 2% par mois", "Équilibré - 5% par mois", "Risque élevé - 10% par mois"],
    riskText: "maximum par trade",
    resultLabels: ["Valeur estimée à la fin", "Profit estimé", "Total des apports ajoutés", "Rendement total", "Perte possible lors d'un mauvais mois"],
    solEyebrow: "Exemple SOL sur deux ans",
    solTitle: "Comment présenter un scénario d'investissement structuré sur SOL à un investisseur ?",
    solCopy:
      "L'exemple suivant suppose un capital initial et un ajout mensuel régulier pendant 24 mois. Il illustre la discipline et le réinvestissement, pas une prévision réelle du prix de SOL.",
    solCards: ["Capital initial", "Ajout mensuel", "Durée", "Valeur estimée"],
    monthUnit: "mois",
    marketDataEyebrow: "API données et Dashboard",
    marketDataTitle: "Le README précise comment développer le Dashboard sans lancer toute l'infrastructure.",
    marketDataCopy:
      "Pour le développement rapide, lancez le mock backend sur le port 8000 et l'interface Vite sur 5173. Les symboles par défaut sont BTC, ETH, SOL, EUR/USD, AAPL et TSLA, avec des données de démo ancrées au 2025-05-11.",
    endpoints: [
      ["GET", "/api/symbols", "Catalogue de 24 symboles crypto, forex et equity."],
      ["GET", "/api/quotes?symbols=BTC,AAPL", "OHLC, bid/ask, variation 24h et volume."],
      ["GET", "/api/history?symbol=X&days=N", "Barres OHLC déterministes terminant le 2025-05-11."],
      ["GET", "/api/holdings", "Ledger mock ; le P&L est calculé côté interface."],
    ],
    services: [
      "API :8000",
      "Docs :8000/docs",
      "Dashboard :5173",
      "Grafana :3000",
      "Kafka UI :8080",
      "Prometheus :9090",
    ],
    safetyEyebrow: "Garde-fous",
    safetyTitle: "Le projet contient des limites de sécurité qu'il faut respecter.",
    safety: [
      ["Commencer en development ou paper_trading", "Le système refuse les ordres réels sauf si ENVIRONMENT=live est défini explicitement."],
      ["Ne pas activer DeFi avec de l'argent réel", "Les agents yield farmer, dex arbitrageur, mev hunter et bridge strategist ne sont pas prêts pour la production."],
      ["Protéger les secrets", "Le fichier .env ne doit jamais être envoyé sur Git, et les clés d'exchange ne doivent pas permettre les retraits."],
      ["Tester avant le live", "Les stratégies doivent passer par le backtesting et le paper trading avant toute utilisation réelle."],
      ["Ne pas assouplir les limites", "Risque de 1% par trade, pause après 5 pertes, drawdown maximal de 25% et hot wallet limité à 5% du capital."],
      ["Backtesting obligatoire", "Toute stratégie Tier 4 requiert 5 ans de données, 50 trades/an, Sharpe, Profit Factor et Monte Carlo dans les limites."],
    ],
    footer: "ALGHREST Project Explainer - site statique mis à jour depuis le README.",
    top: "Retour en haut",
    agentLabels: { load: "Charge", messages: "Messages", topic: "Topic :" },
    status: { active: "Actif", busy: "Occupé", halted: "Arrêté" },
    events: [
      "a envoyé un heartbeat à Redis",
      "a lu un nouveau message Kafka",
      "a publié une mise à jour vers le Dashboard",
      "a mis à jour son état de santé interne",
      "a terminé un cycle async sans erreur",
      "a vérifié le kill switch avant de continuer",
    ],
  },
};

menuButton.addEventListener("click", () => {
  const isOpen = mainNav.classList.toggle("open");
  menuButton.setAttribute("aria-expanded", String(isOpen));
  document.body.classList.toggle("menu-lock", isOpen);
});

navLinks.forEach((link) => {
  link.addEventListener("click", () => {
    mainNav.classList.remove("open");
    menuButton.setAttribute("aria-expanded", "false");
    document.body.classList.remove("menu-lock");
  });
});

langToggle.addEventListener("click", () => {
  currentLang = currentLang === "ar" ? "fr" : "ar";
  localStorage.setItem("alghrest-lang", currentLang);
  applyLanguage();
  pushEvent(agents[0]);
});

const sections = [...document.querySelectorAll("main section[id]")];
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      navLinks.forEach((link) => {
        link.classList.toggle("active", link.getAttribute("href") === `#${entry.target.id}`);
      });
    });
  },
  { rootMargin: "-40% 0px -50% 0px", threshold: 0.01 }
);

sections.forEach((section) => observer.observe(section));

window.addEventListener("load", () => {
  window.setTimeout(() => {
    document.body.classList.add("loaded");
    window.setTimeout(() => pageLoader.setAttribute("hidden", ""), 520);
  }, 450);
});

function updateScrollUi() {
  const scrollTop = window.scrollY;
  const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
  const progress = maxScroll > 0 ? (scrollTop / maxScroll) * 100 : 0;
  scrollProgress.style.width = `${progress}%`;
  topbar.classList.toggle("scrolled", scrollTop > 16);
  backTop.classList.toggle("visible", scrollTop > 620);
}

window.addEventListener("scroll", updateScrollUi, { passive: true });
updateScrollUi();

backTop.addEventListener("click", () => {
  window.scrollTo({ top: 0, behavior: "smooth" });
});

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.12 }
);

revealItems.forEach((item) => revealObserver.observe(item));

function animateCounter(element) {
  const target = Number(element.dataset.count);
  const suffix = element.dataset.suffix || "";
  const duration = 950;
  const start = performance.now();

  function frame(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = `${Math.round(target * eased)}${suffix}`;
    if (progress < 1) requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
}

const counterObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting || entry.target.dataset.done) return;
      entry.target.dataset.done = "true";
      animateCounter(entry.target);
    });
  },
  { threshold: 0.6 }
);

counters.forEach((counter) => counterObserver.observe(counter));

const networkCanvas = document.querySelector("#networkCanvas");
const networkCtx = networkCanvas.getContext("2d");

function drawNetwork(time = 0) {
  const width = networkCanvas.width;
  const height = networkCanvas.height;
  networkCtx.clearRect(0, 0, width, height);

  const nodes = [
    { x: width * 0.78, y: height * 0.2, r: 38, label: "A1", color: "#0f7a5f" },
    { x: width * 0.54, y: height * 0.47, r: 50, label: "K", color: "#d5962c" },
    { x: width * 0.78, y: height * 0.72, r: 34, label: "R", color: "#b9433f" },
    { x: width * 0.24, y: height * 0.78, r: 42, label: "UI", color: "#2f68a1" },
    { x: width * 0.27, y: height * 0.25, r: 30, label: "DB", color: "#0a4f42" },
  ];

  networkCtx.lineWidth = 3;
  nodes.forEach((node, index) => {
    nodes.slice(index + 1).forEach((other) => {
      const alpha = 0.16 + Math.sin(time / 600 + index) * 0.05;
      networkCtx.strokeStyle = `rgba(10, 79, 66, ${alpha})`;
      networkCtx.beginPath();
      networkCtx.moveTo(node.x, node.y);
      networkCtx.lineTo(other.x, other.y);
      networkCtx.stroke();
    });
  });

  nodes.forEach((node, index) => {
    const pulse = Math.sin(time / 500 + index) * 4;
    networkCtx.beginPath();
    networkCtx.arc(node.x, node.y, node.r + pulse + 14, 0, Math.PI * 2);
    networkCtx.fillStyle = `${node.color}18`;
    networkCtx.fill();

    networkCtx.beginPath();
    networkCtx.arc(node.x, node.y, node.r, 0, Math.PI * 2);
    networkCtx.fillStyle = node.color;
    networkCtx.fill();

    networkCtx.fillStyle = "#ffffff";
    networkCtx.font = "bold 22px Arial";
    networkCtx.textAlign = "center";
    networkCtx.textBaseline = "middle";
    networkCtx.fillText(node.label, node.x, node.y);
  });

  requestAnimationFrame(drawNetwork);
}

requestAnimationFrame(drawNetwork);

const agentGrid = document.querySelector("#agentGrid");
const eventFeed = document.querySelector("#eventFeed");
const eventCount = document.querySelector("#eventCount");
const toggleAgents = document.querySelector("#toggleAgents");

const agents = [
  {
    name: "CIO Agent",
    tier: "Tier 1 - Executive",
    topic: "proposals.approved",
    action: {
      ar: "يراجع المقترحات عالية التأثير",
      fr: "analyse les propositions à fort impact",
    },
    load: 64,
    messages: 18,
    status: "active",
  },
  {
    name: "Proposal Approver",
    tier: "Tier 1 - Executive",
    topic: "proposals.bus",
    action: {
      ar: "يفحص حدود المركز قبل الموافقة",
      fr: "vérifie les limites de position avant validation",
    },
    load: 39,
    messages: 12,
    status: "active",
  },
  {
    name: "Market Data Hub",
    tier: "Tier 2 - Intelligence",
    topic: "market.data",
    action: {
      ar: "ينشر أسعار السوق اللحظية",
      fr: "publie les prix de marché en temps réel",
    },
    load: 52,
    messages: 44,
    status: "active",
  },
  {
    name: "Price Publisher",
    tier: "Tier 2 - Intelligence",
    topic: "prices:{symbol}",
    action: {
      ar: "يبث الأسعار إلى Redis مع TTL لمدة 60 ثانية",
      fr: "publie les prix dans Redis avec un TTL de 60 secondes",
    },
    load: 48,
    messages: 32,
    status: "active",
  },
  {
    name: "News Analyst",
    tier: "Tier 2 - Intelligence",
    topic: "news.signals",
    action: {
      ar: "يلخص الأخبار ويقيس المعنويات",
      fr: "résume l'actualité et mesure le sentiment",
    },
    load: 47,
    messages: 13,
    status: "active",
  },
  {
    name: "Risk Governor",
    tier: "Tier 1 - Executive",
    topic: "risk.alerts",
    action: {
      ar: "يراقب السحب والمخاطر",
      fr: "surveille le drawdown et les risques",
    },
    load: 35,
    messages: 7,
    status: "active",
  },
  {
    name: "ML Predictor",
    tier: "Tier 4 - Strategy",
    topic: "proposals.bus",
    action: {
      ar: "يطلب توقعات من خادم ML",
      fr: "demande des prédictions au serveur ML",
    },
    load: 71,
    messages: 11,
    status: "busy",
  },
  {
    name: "Macro Rotator",
    tier: "Tier 4 - Strategy",
    topic: "strategy.signals",
    action: {
      ar: "ينقل رأس المال حسب نظام risk-on/risk-off",
      fr: "fait tourner le capital selon le régime risk-on/risk-off",
    },
    load: 55,
    messages: 8,
    status: "active",
  },
  {
    name: "Order Router",
    tier: "Tier 5 - Execution",
    topic: "orders.pending",
    action: {
      ar: "يختار البورصة وخوارزمية التنفيذ",
      fr: "choisit l'exchange et l'algorithme d'exécution",
    },
    load: 58,
    messages: 21,
    status: "active",
  },
  {
    name: "Fee Optimizer",
    tier: "Tier 5 - Execution",
    topic: "orders.pending",
    action: {
      ar: "يحسن نوع الأمر لتقليل الرسوم",
      fr: "optimise le type d'ordre pour réduire les frais",
    },
    load: 43,
    messages: 16,
    status: "active",
  },
  {
    name: "Exchange Executor",
    tier: "Tier 5 - Execution",
    topic: "orders.executed",
    action: {
      ar: "ينفذ الأوامر ويتابع التأكيدات",
      fr: "exécute les ordres et suit les confirmations",
    },
    load: 62,
    messages: 9,
    status: "active",
  },
  {
    name: "Portfolio Tracker",
    tier: "Tier 7 - Monitoring",
    topic: "portfolio.state",
    action: {
      ar: "يحدث PnL والسحب وSharpe للداشبورد",
      fr: "met à jour PnL, drawdown et Sharpe pour le Dashboard",
    },
    load: 46,
    messages: 19,
    status: "active",
  },
  {
    name: "Compliance Agent",
    tier: "Tier 7 - Monitoring",
    topic: "orders.filled",
    action: {
      ar: "يسجل التداولات ويراقب حدود الامتثال",
      fr: "journalise les trades et surveille les limites de conformité",
    },
    load: 33,
    messages: 6,
    status: "active",
  },
  {
    name: "Bridge Strategist",
    tier: "Tier 6 - Disabled",
    topic: "defi.opportunities",
    action: {
      ar: "متوقف لأن DeFi غير جاهز للإنتاج",
      fr: "arrêté car DeFi n'est pas prêt pour la production",
    },
    load: 0,
    messages: 0,
    status: "halted",
  },
];

let agentsRunning = true;
let totalEvents = 0;

function setText(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function setParagraph(selector, value) {
  const element = document.querySelector(selector);
  if (element) element.textContent = value;
}

function applyLanguage() {
  const text = copy[currentLang];
  const isArabic = currentLang === "ar";

  document.documentElement.lang = currentLang;
  document.documentElement.dir = isArabic ? "rtl" : "ltr";
  document.title = text.title;
  langToggle.textContent = isArabic ? "FR" : "AR";
  langToggle.setAttribute("aria-label", isArabic ? "Changer la langue en français" : "Passer en arabe");
  menuButton.setAttribute("aria-label", text.menuLabel);
  mainNav.setAttribute("aria-label", isArabic ? "التنقل الرئيسي" : "Navigation principale");
  backTop.setAttribute("aria-label", text.top);

  setText(".brand small", text.brandSub);
  navLinks.forEach((link, index) => {
    link.textContent = text.nav[index];
  });

  setText(".hero .eyebrow", text.heroEyebrow);
  setText(".hero h1", text.heroTitle);
  setParagraph(".hero .lead", text.heroLead);
  setText(".hero-actions .primary", text.profitCta);
  setText(".hero-actions .ghost", text.runtimeCta);

  document.querySelectorAll(".stats-strip span").forEach((item, index) => {
    item.textContent = text.stats[index];
  });

  setText("#status .eyebrow", text.statusEyebrow);
  setText("#status h2", text.statusTitle);
  setParagraph("#status .section-copy", text.statusCopy);
  document.querySelectorAll("#status .status-card").forEach((card, index) => {
    card.querySelector("span").textContent = text.statusCards[index][0];
    card.querySelector("h3").textContent = text.statusCards[index][1];
    card.querySelector("p").textContent = text.statusCards[index][2];
  });
  document.querySelectorAll("#status .status-ribbon span").forEach((item, index) => {
    item.textContent = text.statusRibbon[index];
  });

  setText("#investor .eyebrow", text.investorEyebrow);
  setText("#investor h2", text.investorTitle);
  setParagraph("#investor .section-copy", text.investorCopy);
  setText("#investor .investor-primary", text.investorSchemaCta);
  setText("#investor .investor-ghost", text.investorProfitCta);
  document.querySelectorAll("#investor .investor-messages article").forEach((article, index) => {
    article.querySelector("strong").textContent = text.investorMessages[index][0];
    article.querySelector("p").textContent = text.investorMessages[index][1];
  });

  setText("#capabilities .eyebrow", text.capabilitiesEyebrow);
  setText("#capabilities h2", text.capabilitiesTitle);
  document.querySelectorAll("#capabilities .feature-card").forEach((card, index) => {
    card.querySelector("h3").textContent = text.features[index][0];
    card.querySelector("p").textContent = text.features[index][1];
  });

  setText("#agents .eyebrow", text.agentsEyebrow);
  setText("#agents h2", text.agentsTitle);
  setParagraph("#agents .section-copy", text.agentsCopy);
  setText(".agent-toolbar strong", text.liveSimulation);
  toggleAgents.textContent = agentsRunning ? text.pause : text.resume;
  setText(".feed-head h3", text.eventsTitle);
  if (eventFeed) {
    eventFeed.innerHTML = "";
    totalEvents = 0;
    eventCount.textContent = "0";
  }

  setText("#schema .eyebrow", text.schemaEyebrow);
  setText("#schema h2", text.schemaTitle);
  setParagraph("#schema .section-copy", text.schemaCopy);
  document.querySelectorAll("#schema .map-node").forEach((node, index) => {
    node.querySelector("strong").textContent = text.schemaNodes[index][0];
    node.querySelector("p").textContent = text.schemaNodes[index][1];
  });
  document.querySelectorAll("#schema .investor-points article").forEach((point, index) => {
    point.querySelector("strong").textContent = text.investorPoints[index][0];
    point.querySelector("p").textContent = text.investorPoints[index][1];
  });

  setText("#runtime .eyebrow", text.runtimeEyebrow);
  setText("#runtime h2", text.runtimeTitle);
  setParagraph("#runtime .section-copy", text.runtimeCopy);

  setText(".timeline-section .eyebrow", text.pipelineEyebrow);
  setText(".timeline-section h2", text.pipelineTitle);
  document.querySelectorAll(".pipeline-step span").forEach((item, index) => {
    item.textContent = text.pipelineLabels[index];
  });
  document.querySelectorAll(".pipeline-step p").forEach((item, index) => {
    item.textContent = text.pipelineDescriptions[index];
  });

  setText(".calculator-copy .eyebrow", text.calculatorEyebrow);
  setText(".calculator-copy h2", text.calculatorTitle);
  setParagraph(".calculator-copy p:not(.eyebrow)", text.calculatorCopy);
  document.querySelectorAll(".calculator label").forEach((label, index) => {
    label.childNodes[0].nodeValue = `\n            ${text.labels[index]}\n            `;
  });
  document.querySelectorAll("#scenarioInput option").forEach((option, index) => {
    option.textContent = text.options[index];
  });
  const rangeValue = document.querySelector(".range-value");
  if (rangeValue && rangeValue.childNodes[1]) {
    rangeValue.childNodes[1].nodeValue = `% ${text.riskText}`;
  }
  setText(".result-main span", text.resultLabels[0]);
  document.querySelectorAll(".result-grid span").forEach((item, index) => {
    item.textContent = text.resultLabels[index + 1];
  });
  setText(".sol-copy .eyebrow", text.solEyebrow);
  setText(".sol-copy h3", text.solTitle);
  setParagraph(".sol-copy p", text.solCopy);
  document.querySelectorAll(".sol-grid span").forEach((item, index) => {
    item.textContent = text.solCards[index];
  });
  setText("#solDuration", `24 ${text.monthUnit}`);

  setText("#market-data .eyebrow", text.marketDataEyebrow);
  setText("#market-data h2", text.marketDataTitle);
  setParagraph("#market-data .section-copy", text.marketDataCopy);
  document.querySelectorAll("#market-data .endpoint-grid article").forEach((endpoint, index) => {
    endpoint.querySelector("span").textContent = text.endpoints[index][0];
    endpoint.querySelector("strong").textContent = text.endpoints[index][1];
    endpoint.querySelector("p").textContent = text.endpoints[index][2];
  });
  document.querySelectorAll("#market-data .service-grid a").forEach((service, index) => {
    service.textContent = text.services[index];
  });

  setText("#safety .eyebrow", text.safetyEyebrow);
  setText("#safety h2", text.safetyTitle);
  document.querySelectorAll(".safety-list article").forEach((article, index) => {
    article.querySelector("h3").textContent = text.safety[index][0];
    article.querySelector("p").textContent = text.safety[index][1];
  });

  setText(".footer p", text.footer);
  setText(".footer a", text.top);

  renderAgents();
}

function renderAgents(updatedName = "") {
  const text = copy[currentLang];
  agentGrid.innerHTML = agents
    .map((agent) => {
      const statusClass = agent.status === "active" ? "" : agent.status;
      const updatingClass = agent.name === updatedName ? "updating" : "";
      return `
        <article class="agent-card ${statusClass} ${updatingClass}">
          <div class="agent-title">
            <div>
              <strong>${agent.name}</strong>
              <span>${agent.tier}</span>
            </div>
            <span class="status-pill ${statusClass}">${text.status[agent.status]}</span>
          </div>
          <div class="metric-row">
            <span>${text.agentLabels.load}</span>
            <div class="bar"><span style="width:${agent.load}%"></span></div>
            <strong>${agent.load}%</strong>
          </div>
          <div class="metric-row">
            <span>${text.agentLabels.messages}</span>
            <div class="bar"><span style="width:${Math.min(agent.messages * 2, 100)}%"></span></div>
            <strong>${agent.messages}</strong>
          </div>
          <div class="agent-topic">
            <div><strong>${text.agentLabels.topic}</strong> ${agent.topic}</div>
            <div>${agent.action[currentLang]}</div>
          </div>
        </article>
      `;
    })
    .join("");
}

function pushEvent(agent) {
  const item = document.createElement("article");
  item.className = "feed-item";
  const now = new Date();
  const templates = copy[currentLang].events;
  const message = templates[Math.floor(Math.random() * templates.length)];
  const locale = currentLang === "ar" ? "ar-MA" : "fr-FR";
  const eventLine =
    currentLang === "ar" ? `${message} - ${agent.topic}` : `${agent.name} ${message} - ${agent.topic}`;
  item.innerHTML = `
    <time>${now.toLocaleTimeString(locale)}</time>
    <strong>${agent.name}</strong>
    <p>${eventLine}</p>
  `;
  eventFeed.prepend(item);
  totalEvents += 1;
  eventCount.textContent = totalEvents.toString();

  while (eventFeed.children.length > 12) {
    eventFeed.lastElementChild.remove();
  }
}

function tickAgents() {
  if (!agentsRunning) return;

  agents.forEach((agent) => {
    if (agent.status === "halted") return;
    const movement = Math.round(Math.random() * 18 - 8);
    agent.load = Math.min(96, Math.max(12, agent.load + movement));
    agent.messages += Math.random() > 0.45 ? 1 : 0;
    agent.status = agent.load > 76 ? "busy" : "active";
  });

  const activeAgents = agents.filter((agent) => agent.status !== "halted");
  const selected = activeAgents[Math.floor(Math.random() * activeAgents.length)];
  pushEvent(selected);
  renderAgents(selected.name);
}

toggleAgents.addEventListener("click", () => {
  agentsRunning = !agentsRunning;
  toggleAgents.textContent = agentsRunning ? copy[currentLang].pause : copy[currentLang].resume;
  if (agentsRunning) tickAgents();
});

applyLanguage();
pushEvent(agents[0]);
setInterval(tickAgents, 2200);

const capitalInput = document.querySelector("#capitalInput");
const monthsInput = document.querySelector("#monthsInput");
const monthlyInput = document.querySelector("#monthlyInput");
const scenarioInput = document.querySelector("#scenarioInput");
const riskInput = document.querySelector("#riskInput");
const riskValue = document.querySelector("#riskValue");
const futureValue = document.querySelector("#futureValue");
const estimatedProfit = document.querySelector("#estimatedProfit");
const totalContributions = document.querySelector("#totalContributions");
const totalReturn = document.querySelector("#totalReturn");
const badMonth = document.querySelector("#badMonth");
const solInitial = document.querySelector("#solInitial");
const solMonthly = document.querySelector("#solMonthly");
const solProjected = document.querySelector("#solProjected");
const chart = document.querySelector("#profitChart");
const chartCtx = chart.getContext("2d");

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

function calculateSeries(capital, months, monthlyRate, monthlyContribution = 0) {
  const values = [capital];
  for (let month = 1; month <= months; month += 1) {
    values.push(values[month - 1] * (1 + monthlyRate) + monthlyContribution);
  }
  return values;
}

function drawProfitChart(values) {
  const width = chart.width;
  const height = chart.height;
  const padding = 34;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);

  chartCtx.clearRect(0, 0, width, height);
  chartCtx.fillStyle = "#fbfaf5";
  chartCtx.fillRect(0, 0, width, height);

  chartCtx.strokeStyle = "#d8ddcf";
  chartCtx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = padding + ((height - padding * 2) / 3) * i;
    chartCtx.beginPath();
    chartCtx.moveTo(padding, y);
    chartCtx.lineTo(width - padding, y);
    chartCtx.stroke();
  }

  chartCtx.beginPath();
  values.forEach((value, index) => {
    const x = padding + ((width - padding * 2) / (values.length - 1 || 1)) * index;
    const y = height - padding - ((value - min) / range) * (height - padding * 2);
    if (index === 0) chartCtx.moveTo(x, y);
    else chartCtx.lineTo(x, y);
  });
  chartCtx.strokeStyle = "#0f7a5f";
  chartCtx.lineWidth = 4;
  chartCtx.stroke();

  const gradient = chartCtx.createLinearGradient(0, padding, 0, height - padding);
  gradient.addColorStop(0, "rgba(15, 122, 95, 0.22)");
  gradient.addColorStop(1, "rgba(15, 122, 95, 0)");

  chartCtx.lineTo(width - padding, height - padding);
  chartCtx.lineTo(padding, height - padding);
  chartCtx.closePath();
  chartCtx.fillStyle = gradient;
  chartCtx.fill();

  chartCtx.fillStyle = "#61706a";
  chartCtx.font = "14px Arial";
  chartCtx.textAlign = "left";
  chartCtx.fillText(moneyFormatter.format(max), 12, 22);
  chartCtx.fillText(moneyFormatter.format(min), 12, height - 12);
}

function updateCalculator() {
  const capital = Math.max(Number(capitalInput.value) || 0, 0);
  const months = Math.min(Math.max(Number(monthsInput.value) || 1, 1), 60);
  const monthlyContribution = Math.max(Number(monthlyInput.value) || 0, 0);
  const monthlyRate = Number(scenarioInput.value);
  const risk = Number(riskInput.value);
  const series = calculateSeries(capital, months, monthlyRate, monthlyContribution);
  const finalValue = series.at(-1);
  const contributed = capital + monthlyContribution * months;
  const addedOnly = monthlyContribution * months;
  const profit = finalValue - contributed;
  const returnPercent = contributed > 0 ? (profit / contributed) * 100 : 0;
  const badMonthEstimate = capital * (risk / 100) * 5;
  const solSeries = calculateSeries(5000, 24, monthlyRate, monthlyContribution);
  const solValue = solSeries.at(-1);

  riskValue.textContent = risk.toString();
  futureValue.textContent = moneyFormatter.format(finalValue);
  estimatedProfit.textContent = moneyFormatter.format(profit);
  totalContributions.textContent = moneyFormatter.format(addedOnly);
  totalReturn.textContent = `${returnPercent.toFixed(1)}%`;
  badMonth.textContent = moneyFormatter.format(badMonthEstimate);
  solInitial.textContent = moneyFormatter.format(5000);
  solMonthly.textContent = moneyFormatter.format(monthlyContribution);
  solProjected.textContent = moneyFormatter.format(solValue);

  drawProfitChart(series);
}

[capitalInput, monthsInput, monthlyInput, scenarioInput, riskInput].forEach((input) => {
  input.addEventListener("input", updateCalculator);
});

updateCalculator();
