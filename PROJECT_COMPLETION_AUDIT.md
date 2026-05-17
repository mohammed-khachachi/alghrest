# PROJECT_COMPLETION_AUDIT.md

> تقرير معماري — Senior Architect Review  
> التاريخ: 2026-05-16  
> الجهاز المستهدف: Windows 11 ضعيف الموارد (بدون Docker كامل)  
> الحالة الافتراضية: `ENVIRONMENT=development` ، `ENABLE_DEFI_AGENTS=false`  
> هذا التقرير **لا ينفذ أي تعديل** — هو خريطة طريق فقط.

---

## A. الملخص التنفيذي

### حالة المشروع الحالية
ALGHREST مشروع **متقدم معماريًا** لكنه **غير جاهز للإنتاج**. البنية الكلية (7 طبقات، 36 خدمة في `docker-compose.yml`، 8 ملفات integration tests بإجمالي ~4400 سطر، 9 ملفات unit tests بإجمالي ~1500 سطر) موجودة، لكن المشروع يقف على ثلاث ركائز غير متساوية النضج:

| الركيزة | النضج | ملاحظة |
|---|---|---|
| البنية التحتية (Kafka + Redis + Timescale + 20 agent container) | متوسط — تعمل لكن تحتاج جهاز قوي | docker-compose.yml يطلب 25 خدمة (3 brokers Kafka + Zookeeper + Timescale + Redis + Prometheus + Grafana + ~20 agent) |
| منطق التداول (Tiers 1–5 + 7) | عالٍ هيكليًا، **غير مُتحقَّق سلوكيًا** | الـ unit tests تغطي الرياضيات والـ kill switch، لكن لا توجد backtest tests نشطة (`tests/backtests/` فارغ) |
| طبقة الـ Dashboard + Market Data REST | **الأعلى نضجًا والأنسب للجهاز الضعيف** | TanStack Query + Zod + Zustand + `useLiveQuotes` كمصدر بيانات موحّد + mocks مُحكمة |

### هل هو جاهز لـ live trading؟
**لا. قطعًا لا.** الأسباب:
1. `connectors/data_providers/{crypto,forex,equity}_provider.py` كلها **mocks** بـ random walk حتمي — لا اتصال فعلي بأي منصة.
2. `/api/holdings` ledger ثابت من 8 مراكز (`holdings.py:_RAW`) بدون أي persistence layer.
3. لا يوجد order ↔ holdings wiring مع agent fabric.
4. Tier 6 DeFi agents skeletons — والـ `core/config.py` يضع `enable_defi_agents=False` كافتراضي صحيح.
5. `options_strategist` (Tier 4) غير مُنفّذ.
6. لا توجد backtest validation runs نشطة على استراتيجيات Tier 4.
7. CI `.github/workflows/tests.yml` لا يشغّل سوى نسخة `[full-test]` يدويًا، والـ backtest job معطّل افتراضيًا.

### أقرب هدف عملي حاليًا
**"Lightweight Dev Mode المستقر"** — أن يصبح المسار `api/mock_server.py` + `dashboard/` بديلًا موثوقًا 100% للـ docker stack أثناء التطوير، مع توافق كامل بين WebSocket schema الذي يبثّه الـ backend والذي يستهلكه الـ frontend (هناك عدم تطابق فعلي — راجع القسم C.2).

> **القاعدة الذهبية**: لا تنتقل لأي شيء قبل أن يدور `scripts/run_lite.ps1` بدون أخطاء طوال جلسة عمل كاملة.

---

## B. ما هو مكتمل

### B.1 Dashboard (React 18 + Vite + Tailwind + Zustand)
- **8 صفحات** كاملة: `Overview`, `Agents`, `Positions`, `Risk`, `Kafka`, `AuditorDashboard`, `BacktestSimulation`, `InvestorPitch`.
- **بنية بيانات موحّدة**: `dashboard/src/lib/useLiveQuotes.ts` هو المصدر الوحيد لـ polling `/api/quotes` كل 3 ثوانٍ، يتشاركه `MarketDataPanel` + `HoldingsPanel` + `PortfolioOverview`.
- **Zod validation** على كل payload يدخل من الـ API (`dashboard/src/lib/api.ts`، `dashboard/src/types/quotes.ts`).
- **State**: Zustand store موحّد (`store/useStore.ts`) + TanStack Query للـ caching.
- **UI primitives جاهزة**: `Skeleton`, `ErrorBoundary`, `Toast`, `SymbolSelector` مع fallback catalog.
- **Vite proxy** يحوّل `/api/*` إلى `http://localhost:8000` افتراضيًا (`vite.config.ts:17`).

### B.2 Mock API (`api/mock_server.py` + `api/routes/quotes.py`)
- **FastAPI app** يعمل على `:8000`، يبث 5 channels عبر `/ws/dashboard` (portfolio, agents, system, positions, risk).
- **يقلّد 32 وكيلًا** بـ status + memory + error rate + latency p99 — كافٍ لاختبار صفحة `Agents` بصريًا.
- **يُضمّن `api/routes/quotes.py`** الذي يخدم 4 endpoints حقيقية: `/api/symbols`, `/api/quotes`, `/api/history`, `/api/holdings`.

### B.3 Data Providers (`connectors/data_providers/`)
- **QuoteProvider ABC نظيف** (`base.py`) مع `Quote` و `HistoricalBar` كـ frozen dataclasses.
- **Random walk حتمي** (`random_walk_history`) مرتبط بـ `ANCHOR_DATE = 2025-05-11` — السبب أن sparklines + entry prices في holdings تتطابق رياضيًا.
- **3 mocks**: crypto (8 رموز)، forex (8 أزواج)، equity (8 أسهم) — كل واحد بـ `_BASE_PRICES`/`_BASE_RATES` كنقطة ارتكاز.
- **`QuoteRouter`** يقرأ كتالوج ثابت من 24 رمزًا ويمرّر لكل provider حسب `AssetClass`.
- **Holdings**: 8 مراكز ثابتة (`holdings.py:_RAW`)، entry price محسوبة من نفس bars الـ history (تطابق ضموني).

### B.4 Risk modules (`core/`)
- `core/risk/kill_switch.py`، `core/risk/position_limits.py`، `core/risk/risk_engine.py` — كلها مُنفّذة ومغطاة بـ unit tests.
- `core/orchestrator/message_bus.py` (`AlghrestProducer/AlghrestConsumer`) و `state_manager.py` (Redis singleton).
- `core/config.py::Settings` مركز موحّد لكل البيئة (pydantic-settings).
- `core/telegram/bot.py` — Telegram alerts للـ Tier 7.

### B.5 Tests الموجودة

**Unit tests** (تعمل بدون أي خدمة خارجية — `pytest -m unit`):
| الملف | عدد الأسطر | يغطي |
|---|---|---|
| `test_exchange_executor.py` | 228 | order lifecycle + cancel-on-kill |
| `test_kill_switch_cancel.py` | 140 | RISK_ALERTS → cancel path |
| `test_models.py` | 139 | Pydantic models + KafkaTopic enum |
| `test_portfolio_tracker.py` | 401 | الأطول، PnL math |
| `test_price_publisher.py` | 174 | Redis price caching |
| `test_prompt_caching.py` | 218 | Anthropic prompt caching contract |
| `test_risk_engine.py` | 108 | drawdown limits + circuit breaker |
| `test_imports.py` | 95 | يضمن أن كل agent module يستورد بدون أخطاء |

**Integration tests** (تحتاج `docker compose up -d` كاملًا — ⚠️ لا تشغّلها على جهازك):
- 8 ملفات، ~4400 سطر، تغطي: execution pipeline, kafka messaging, redis state, agent coordination, market crash kill switch, ML failover, API/dashboard integration, backtesting validation.

**Backtests** (`tests/backtests/`): **فارغ تمامًا**. هذه ثغرة كبيرة لأن `pyproject.toml` يعرّف الـ marker لكن لا توجد اختبارات فعلية.

### B.6 Scripts الموجودة (`scripts/`)
| السكربت | الغرض | مناسب للجهاز الضعيف؟ |
|---|---|---|
| `run_lite.ps1` | يطلق mock backend + dashboard فقط | ✅ نعم — هذا هو خطك الرئيسي |
| `test_lite.ps1` | `ruff check .` + `pytest -m unit` | ✅ نعم |
| `validate_agent_ids.py` | يكشف تصادمات AGENT_ID | ✅ نعم |
| `validate_news_feeds.py` | يفحص RSS feeds الـ news_analyst | ✅ نعم |
| `seed_redis.py` | يحضّر Redis للتطوير | ❌ يحتاج Redis |
| `mock_ml_server.py` | بديل خفيف لـ ml/inference/server.py | ⚠️ ربما، اختياري |
| `demo_kill_switch.py` | عرض تفاعلي للـ kill switch (UI عربي) | ⚠️ يحتاج Redis |
| `run_kill_switch_stress_test.py` | اختبار ضغط | ❌ يحتاج docker stack |
| `run_tests.py` | wrapper لـ pytest يستخدمه CI أيضًا | ✅ بشكل جزئي |

### B.7 Documentation
- `CLAUDE.md` (canonical) و `AGENTS.md` (سيبلنغ Codex، يتأخر أحيانًا — راجع القسم F).
- `docs/LIGHTWEIGHT_DEV.md` — دليل venv-lite الكامل.
- `docs/kill_switch_testing_guide.md` — سيناريوهات QA للـ kill switch (عربي).
- `README.md` — overview عام.
- 3 تقارير قديمة في الجذر: `INTEGRATION_TESTS_SUMMARY.md`, `ML_FAILOVER_NEWS_FIXES_SUMMARY.md`, `SECURITY_FIXES_SUMMARY.md` (مرجعية، ليست living docs).

---

## C. ما هو ناقص (مرتّب حسب الأولوية)

### الأولوية 1 — Lightweight Dev Mode Stability
- `dashboard/src/lib/socket.ts` يستخدم `socket.io-client` على `/socket.io/`، بينما `api/mock_server.py` يبث على `/ws/dashboard` بـ FastAPI WebSocket الخام → **عدم تطابق بروتوكول**. النتيجة العملية: قد لا تصل بيانات الـ WebSocket للـ dashboard عند تشغيل lite mode.
- لا يوجد `tsc --noEmit` في `test_lite.ps1` — يمكن أن يكسر الـ frontend بدون أن نلاحظ.
- لا يوجد `dashboard/.env.example` يوثّق `VITE_API_URL` و `VITE_WS_URL`.
- `run_lite.ps1` لا يفحص أن البورتات 8000/5173 شاغرة قبل التشغيل (يفشل برسالة غامضة).

### الأولوية 2 — Dashboard + mock_server reliability
- `MockDashboardManager.run_loops` يبث *دائمًا* `status: "PAPER"` + `kill_switch_active: false` — لا توجد طريقة لتجربة kill switch بصريًا.
- `api/mock_server.py` لا يحدّث `holdings`/`quotes` بشكل متّسق مع الـ WebSocket — قد يظهر للمستخدم PnL لا يطابق `/api/holdings` × `/api/quotes`.
- لا يوجد endpoint للـ replay (مثلاً `POST /mock/scenario?name=flash_crash`) — كل القيم عشوائية وغير قابلة للتكرار.

### الأولوية 3 — Market Data Providers (real implementations)
- الـ 3 providers `mocks` كاملة. الـ contract نظيف لكن البديل الحقيقي غير موجود.
- لا توجد طبقة rate limiting / caching بين الـ providers والـ HTTP layer.
- لا يوجد credentials handling في `Settings` للـ data providers (مفاتيح Glassnode/Nansen/FRED موجودة لكن لا تُستخدم في الـ data_providers الحالية).

### الأولوية 4 — Holdings Persistence
- `connectors/data_providers/holdings.py` يولّد 8 مراكز من قائمة `_RAW` ثابتة، ويخزّنها في `_cached` global.
- لا توجد طبقة persistence (SQLite / file / Timescale).
- إعادة تشغيل السيرفر تُعيد نفس المراكز الـ 8.

### الأولوية 5 — Order ↔ Holdings Wiring
- لا يوجد ربط بين `ORDERS_EXECUTED` (Kafka) و `/api/holdings`.
- في الـ live system، تنفيذ أمر يجب أن يحدّث ledger الـ holdings — حاليًا لا يحدث.
- يحتاج تصميم: هل الـ holdings layer هو snapshot من portfolio_tracker (الذي يستهلك FILLS_CONFIRMED) أم ledger مستقل؟

### الأولوية 6 — Backtesting Validation
- `tests/backtests/` فارغ.
- `backtesting/engine.py::BacktestEngine.validate_all` معرّف ومذكور في CLAUDE.md (≥5y data، Sharpe ≥1.0، MC ruin <1%…) لكن لا اختبارات فعلية تطبّقه.
- بدون هذا، **أي ادعاء أن استراتيجية Tier 4 جاهزة هو ادعاء غير مُتحقَّق**.

### الأولوية 7 — Integration Testing على البنية الكاملة
- 8 ملفات integration tests موجودة (~4400 سطر) لكنها تحتاج كل الـ stack.
- يجب تحويل بعضها — على الأقل `test_api_dashboard_integration.py` و `test_redis_state_management.py` — إلى نسخ "lite" تعمل بـ in-memory fakes.

### الأولوية 8 — `options_strategist` (Tier 4)
- مذكور في `api/mock_server.py:39` ضمن `AGENTS` لكن **لا يوجد ملف** `agents/tier4_strategies/options_strategist.py`.
- منتظر Deribit delta-neutral logic.

### الأولوية 9 — ML Inference Deployment
- `ml/inference/server.py` موجود ويعمل على :8080.
- `agents/tier4_strategies/ml_predictor.py` (Agent 16) يعتمد عليه كـ HTTP client.
- لا يوجد deployment story (Dockerfile منفصل؟ PM2؟ systemd؟).
- `scripts/mock_ml_server.py` بديل خفيف لكن غير موثّق في الـ ML predictor.

### الأولوية 10 — Infra/K8s/Terraform
- `infra/k8s/` و `infra/terraform/` scaffolds فقط.
- ليست عائقًا حاليًا لكنها ستكون عائقًا عند الانتقال للـ VPS.

### الأولوية 11 — DeFi Agents (Tier 6)
- 4 ملفات skeleton (`yield_farmer`, `dex_arbitrageur`, `mev_hunter`, `bridge_strategist`) بدون منطق حقيقي.
- **لا تلمسها الآن**. راجع القسم D.

---

## D. ما يجب عدم لمسه الآن

### حدود صلبة (لا تتجاوزها أبدًا في هذه المرحلة)
1. **`ENVIRONMENT=live`** — اتركه `development` أو `paper_trading` فقط. `core/config.py:22` و `.env.example:9` كلاهما يحترم هذا.
2. **`ENABLE_DEFI_AGENTS=true`** — احتفظ بـ `false`. `core/config.py:29`.
3. **`docker-compose.yml` كاملًا** — لا تشغّل `docker compose up`. الـ stack يطلب 25 خدمة + 3 Kafka brokers + Zookeeper + Timescale. جهازك لا يحتمل.
4. **Tier 6 DeFi agents** — لا تضف منطقًا، لا تكتب tests لها، لا تستوردها من أي مكان جديد.
5. **Real exchange orders** — `ccxt`, `alpaca-py`, `ib-insync` موجودة كـ dependencies لكن لا تستخدمها للاتصال الفعلي.
6. **ML inference server (`ml/inference/server.py`)** — يحمّل torch + opencv + numpy ثقيل. اتركه. استخدم `scripts/mock_ml_server.py` لو احتجت endpoint وهمي.
7. **Integration tests** (`pytest -m integration`) — تحتاج Kafka + Redis + Timescale.
8. **Backtest tests** (`pytest -m backtest`) — بطيئة جدًا، تحتاج `--with backtesting` group.

### حدود طرية (لا تعدّلها إلا بطلب صريح)
- `core/config.py` — Settings schema. إضافة حقل جديد قد يكسر الـ env loading لكل الـ agents.
- `agents/**/*.py` — منطق التداول. أي تعديل فيها يحتاج integration tests للتحقق.
- `docker-compose.yml` — لو احتجت تعطيل خدمة، استخدم `docker compose --profile lite up` (يحتاج إضافة profiles لاحقًا) بدلًا من حذف blocks.
- `infra/init/kafka-init.sh` — أي تعديل يجب أن يقابله تحديث في `core/data/models.py::KafkaTopic`.
- `core/orchestrator/message_bus.py` — يستخدمه كل agent. تغيير الـ signature يكسر الـ stack.

---

## E. خريطة الطريق — 5 مراحل

### المرحلة 1 — تثبيت Lightweight Dev Mode

**الهدف**: أن يدور `scripts/run_lite.ps1` بدون أي خطأ، مع dashboard يستقبل WebSocket بنجاح ولا يلجأ للـ `dummy_socket.ts`.

**الملفات المتوقع تعديلها**:
- `api/mock_server.py` (تطابق بروتوكول WebSocket مع الـ frontend).
- `dashboard/src/lib/socket.ts` *أو* (الأفضل) جعل الـ backend يستخدم socket.io.
- `scripts/run_lite.ps1` (فحص بورتات قبل التشغيل، رسائل خطأ أوضح).
- `scripts/test_lite.ps1` (إضافة `tsc --noEmit` على dashboard).
- إنشاء `dashboard/.env.example`.

**ما يجب عدم لمسه**:
- `connectors/data_providers/*` — يعمل بشكل صحيح.
- `api/routes/quotes.py` — مستقر.
- أي ملف في `agents/`.

**أوامر اختبار خفيفة**:
```powershell
.\scripts\test_lite.ps1
.\scripts\run_lite.ps1
# ثم في متصفح: http://localhost:5173 → افتح DevTools → Network → تأكد من WS connected
```

**معيار القبول**:
- `pytest -m unit` ينجح 100%.
- `ruff check .` نظيف.
- الـ dashboard يعرض `WebSocket: connected` (وليس `disconnected/error`).
- إغلاق `run_lite.ps1` بـ Ctrl+C يقتل العمليتين معًا بدون zombie processes.

**جهاز ضعيف؟** ✅ نعم — هذه المرحلة كلها على الجهاز الضعيف.

---

### المرحلة 2 — موثوقية Mock Server + Scenario Replay

**الهدف**: جعل `api/mock_server.py` قابلًا للتحكم (kill switch toggle، scenario replay) ومتّسقًا داخليًا (holdings × quotes = portfolio).

**الملفات المتوقع تعديلها**:
- `api/mock_server.py` (إضافة scenario endpoints، توحيد مصدر بيانات portfolio).
- ربما `api/routes/quotes.py` (إضافة `/api/holdings` لو لم يكن موجودًا — موجود فعلًا).
- إضافة `tests/unit/test_mock_server.py` جديدة.

**ما يجب عدم لمسه**:
- `connectors/data_providers/*` — استخدم الـ router عبر import فقط.
- `agents/`.
- منطق Kafka/Redis.

**أوامر اختبار خفيفة**:
```powershell
pytest tests/unit/test_mock_server.py -v
.\scripts\run_lite.ps1
# في terminal ثانٍ:
curl http://localhost:8000/api/holdings
curl http://localhost:8000/api/quotes?symbols=BTC,ETH
```

**معيار القبول**:
- مجموع `holdings × quotes.price` = `portfolio_value` المبثوث على WS (ضمن 0.5% tolerance).
- `POST /mock/scenario?name=flash_crash` يفعّل kill switch لـ 60s.
- لا regression في الـ unit tests.

**جهاز ضعيف؟** ✅ نعم.

---

### المرحلة 3 — Real Data Provider (واحد فقط — Crypto)

**الهدف**: استبدال `MockCryptoProvider` بـ implementation حقيقي عبر CoinGecko Public API (لا يحتاج مفتاح للـ tier المجاني، لا rate limit صارم على القراءة).

**الملفات المتوقع تعديلها**:
- `connectors/data_providers/crypto_provider.py` — إعادة كتابة `quote()` و `history()` فقط. اترك `_BASE_PRICES` كـ fallback.
- `core/config.py` — إضافة `coingecko_base_url` و timeout settings.
- إنشاء `connectors/data_providers/_http.py` — httpx client مع retry/timeout (مرة واحدة، يُعاد استخدامه لاحقًا للـ forex/equity).
- `tests/unit/test_crypto_provider.py` جديد، مع `respx` أو `httpx.MockTransport`.

**ما يجب عدم لمسه**:
- `QuoteProvider` ABC.
- `QuoteRouter`.
- `MockForexProvider` و `MockEquityProvider` (في مرحلة لاحقة).
- `holdings.py` — يقرأ من الـ router فقط.

**أوامر اختبار خفيفة**:
```powershell
pytest tests/unit/test_crypto_provider.py -v
pytest -m unit
.\scripts\run_lite.ps1
# تحقق أن أسعار BTC/ETH تتغيّر حسب السوق الفعلي وليس random walk
```

**معيار القبول**:
- `GET /api/quotes?symbols=BTC` يعيد سعرًا واقعيًا (ضمن ±5% من Binance spot).
- لو CoinGecko انقطع، fallback إلى `_BASE_PRICES` بدون 5xx.
- mocks الـ forex/equity تبقى كما هي.

**جهاز ضعيف؟** ✅ نعم — مكالمات HTTP خارجية فقط.

---

### المرحلة 4 — Holdings Persistence (SQLite)

**الهدف**: نقل `/api/holdings` من ledger ثابت في الذاكرة إلى SQLite محلي خفيف (لا Postgres، لا Timescale).

**الملفات المتوقع تعديلها**:
- `connectors/data_providers/holdings.py` — إضافة طبقة `SQLiteHoldingsStore` خلف الـ API الحالي.
- `api/routes/quotes.py` — endpoint جديد `POST /api/holdings` (للاختبار يدويًا).
- إنشاء `tests/unit/test_holdings_store.py`.
- ربما migration script بسيط في `scripts/seed_holdings.py`.

**ما يجب عدم لمسه**:
- `alembic/` — هذا لـ Timescale، لا تخلط.
- `agents/` — الـ holdings layer لا يجب أن يستورد من agents.
- `core/orchestrator/` — لا Kafka هنا.

**أوامر اختبار خفيفة**:
```powershell
pytest tests/unit/test_holdings_store.py -v
.\scripts\run_lite.ps1
# في terminal ثانٍ:
curl -X POST http://localhost:8000/api/holdings -d '{"symbol":"BTC","volume":0.1}'
curl http://localhost:8000/api/holdings   # يجب أن يعكس الإضافة بعد إعادة تشغيل السيرفر
```

**معيار القبول**:
- إعادة تشغيل `mock_server.py` لا تُعيد ledger افتراضي — يُحافظ على الـ holdings المحفوظة.
- ملف SQLite في `.local/holdings.db` (موجود في `.gitignore`).
- لا يوجد global mutable state في `holdings.py`.

**جهاز ضعيف؟** ✅ نعم — SQLite بدون Postgres/Redis.

---

### المرحلة 5 — Backtesting Test Suite (الحد الأدنى)

**الهدف**: ملء `tests/backtests/` بـ 2–3 اختبارات حقيقية تطبّق `BacktestEngine.validate_all` على استراتيجية واحدة (مثلاً `TrendFollower` على بيانات synthetic).

**الملفات المتوقع تعديلها**:
- `tests/backtests/test_trend_follower_backtest.py` (جديد).
- `tests/backtests/conftest.py` (fixtures للبيانات synthetic).
- إضافة `pyproject.toml` group هل يحتاج توسعة؟ — لا، `backtesting` group موجود بالفعل.

**ما يجب عدم لمسه**:
- `backtesting/engine.py` — استهلكه كما هو.
- `agents/tier4_strategies/trend_follower.py` — استورده كما هو.
- باقي استراتيجيات Tier 4.

**أوامر اختبار خفيفة**:
```powershell
poetry install --with backtesting
pytest -m backtest -v
```

**معيار القبول**:
- اختبار واحد يحقق Sharpe ≥1.0 على بيانات synthetic.
- اختبار آخر يفشل عمدًا على بيانات سيئة (negative control).
- الـ CI tag `[full-test]` في رسالة commit يشغّلها.

**جهاز ضعيف؟** ⚠️ بحدود — مرة في كل دفعة فقط، ليس بشكل متكرر. الـ `vectorbt` و `quantstats` ثقيلة. لو الجهاز اختنق، انقل هذه المرحلة للـ VPS.

---

## F. تقسيم العمل: Claude Code Pro vs Codex Pro

### الفلسفة العامة
- **Claude Code Pro**: الأقوى في **التحليل المعماري، الـ refactor المُحدَّد، كتابة tests معقّدة، فهم cross-file invariants**. استخدمه لما يحتاج "قراءة 3 ملفات قبل تعديل سطر واحد".
- **Codex Pro**: الأقوى في **mechanical edits، إضافة boilerplate، توليد scaffolds، إكمال autocomplete-style**. استخدمه لما يكون التعديل محصورًا في ملف واحد ومحدد المعالم.

### ما يُعطى لـ Claude Code Pro
1. كل issue يحتاج قراءة `CLAUDE.md` بالكامل + ≥2 ملف قبل البدء.
2. توحيد بروتوكول WebSocket بين mock_server و socket.ts (يلزم فهم الجانبين).
3. تصميم holdings persistence layer (قرار معماري قبل الكود).
4. كتابة scenario replay engine في mock_server (يلزم فهم كيف يتدفق الـ state عبر 5 channels).
5. مراجعة أي PR من Codex قبل الـ merge.
6. كتابة integration test "lite" (تحويل integration tests إلى in-memory).

### ما يُعطى لـ Codex Pro
1. إنشاء `dashboard/.env.example`.
2. إضافة `tsc --noEmit` في `test_lite.ps1`.
3. كتابة `connectors/data_providers/_http.py` (httpx client بسيط مع retry).
4. إنشاء `tests/unit/test_crypto_provider.py` بعد ما يحدد Claude الـ contract.
5. كتابة `scripts/seed_holdings.py` (mechanical: قراءة CSV، insert في SQLite).
6. إنشاء stub files للـ `options_strategist` (skeleton فقط، لا منطق).

### متى تستخدم كل واحد
| الموقف | الأداة |
|---|---|
| "هذا الـ bug يحدث في 3 ملفات ولا أعرف لماذا" | Claude Code |
| "أكمل هذه الدالة بناءً على docstring" | Codex |
| "هل التعديل في X يكسر Y؟" | Claude Code |
| "أنشئ ملف اختبار جديد بنفس نمط الملف الموجود" | Codex |
| "صمّم API جديد" | Claude Code |
| "نفّذ API بعد ما اعتمدنا التصميم" | Codex |

### كيف تتجنّب تضارب التعديلات بينهما
1. **branch مختلف لكل أداة**: `claude/<task>` و `codex/<task>`.
2. **قاعدة الملفات الحصرية**: في كل issue (راجع G)، حدّد بوضوح "الملفات المسموح تعديلها". لو Codex لمس ملفًا خارج النطاق → reject الـ PR.
3. **AGENTS.md + CLAUDE.md متطابقان**: حاليًا `AGENTS.md` يتأخر على `CLAUDE.md`. حدّث `AGENTS.md` يدويًا (أو عبر Claude Code) قبل كل جلسة Codex، وإلا سيعمل بمعلومات قديمة.
4. **commit واحد لكل issue**: لا تخلط مهام في نفس الـ commit.
5. **اعمل `git stash` قبل التبديل** بين الأدوات إذا لم تنته من مهمة.
6. **لا تشغّل الأداتين على نفس الملف في نفس الوقت** — اختر واحدة، انتظر، ثم بدّل.

---

## G. أول 10 Issues صغيرة قابلة للتنفيذ

> كل issue مصمّم ليأخذ ≤2 ساعة على جهاز ضعيف. كلها بدون Docker.

---

### Issue #1 — مزامنة WebSocket protocol بين mock_server و dashboard

**الهدف**: حل عدم التطابق بين `/ws/dashboard` (FastAPI) و `socket.io-client` (الـ frontend يتوقع `/socket.io/`).

**الملفات المسموح تعديلها**:
- `dashboard/src/lib/socket.ts`
- `dashboard/src/main.tsx` (إن لزم لـ wire-up)
- `dashboard/src/lib/websocket.ts` (إن وجد بديل أبسط للـ socket.io)

**الملفات الممنوع لمسها**:
- `api/mock_server.py` — اجعل الـ frontend يطابق الـ backend الحالي (أبسط).
- `api/routes/quotes.py`.
- أي ملف Python آخر.

**خطوات التنفيذ**:
1. اقرأ `socket.ts` و `dummy_socket.ts` و `useStore.ts` لفهم channels.
2. أنشئ `dashboard/src/lib/websocket.ts` يستخدم `WebSocket` الأصلي (لا socket.io)، يفك JSON ويُحوّل channel → store update.
3. غيّر `main.tsx` ليستدعي الـ WebSocket client الجديد عند mount.
4. اترك `dummy_socket.ts` كـ fallback لـ Storybook فقط.

**أوامر التحقق**:
```powershell
Set-Location dashboard; npm run build
.\scripts\run_lite.ps1
# في DevTools: WebSocket connection يجب أن يكون 101 Switching Protocols
```

**معيار القبول**: PnL يتحدّث تلقائيًا كل ثانية على صفحة Overview دون تدخل يدوي.

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #2 — إنشاء `dashboard/.env.example`

**الهدف**: توثيق المتغيرات `VITE_API_URL` و `VITE_WS_URL` لتسهيل deployment.

**الملفات المسموح تعديلها**:
- إنشاء `dashboard/.env.example` فقط.

**الملفات الممنوع لمسها**:
- `.env.example` (في الجذر).
- أي شيء آخر.

**خطوات التنفيذ**: ملف من 5 أسطر مع تعليقات.

**أوامر التحقق**:
```powershell
Get-Content dashboard\.env.example
```

**معيار القبول**: الملف موجود في git، يحتوي `VITE_API_URL`, `VITE_WS_URL` بقيم افتراضية.

**مناسب للجهاز الضعيف؟** ✅ نعم. **مرشّح لـ Codex.**

---

### Issue #3 — إضافة `tsc --noEmit` إلى `test_lite.ps1`

**الهدف**: كشف type errors في الـ dashboard قبل الـ deploy.

**الملفات المسموح تعديلها**:
- `scripts/test_lite.ps1` فقط.

**الملفات الممنوع لمسها**: أي شيء آخر.

**خطوات التنفيذ**: إضافة بلوك يدخل لـ `dashboard/` ويشغّل `npm run -s build:check` أو `npx tsc --noEmit`.

**أوامر التحقق**:
```powershell
.\scripts\test_lite.ps1
```

**معيار القبول**: السكربت يفشل لو dashboard فيه type error.

**مناسب للجهاز الضعيف؟** ✅ نعم. **مرشّح لـ Codex.**

---

### Issue #4 — Port availability check في `run_lite.ps1`

**الهدف**: رسالة واضحة لو 8000 أو 5173 مشغولة، بدلًا من crash غامض.

**الملفات المسموح تعديلها**:
- `scripts/run_lite.ps1` فقط.

**الملفات الممنوع لمسها**: أي شيء آخر.

**خطوات التنفيذ**: `Test-NetConnection -ComputerName localhost -Port 8000` قبل تشغيل العمليات، رمي خطأ مفهوم.

**أوامر التحقق**:
```powershell
# في terminal: python -m http.server 8000
# ثم في terminal آخر:
.\scripts\run_lite.ps1
```

**معيار القبول**: يفشل برسالة واضحة "Port 8000 already in use".

**مناسب للجهاز الضعيف؟** ✅ نعم. **مرشّح لـ Codex.**

---

### Issue #5 — توحيد PnL في mock_server مع `/api/holdings × /api/quotes`

**الهدف**: portfolio_value المبثوث على WS = sum(holdings.volume × quotes.price). حاليًا عشوائي.

**الملفات المسموح تعديلها**:
- `api/mock_server.py` فقط (داخل `MockDashboardManager.run_loops`).

**الملفات الممنوع لمسها**:
- `connectors/data_providers/`.
- `api/routes/quotes.py`.

**خطوات التنفيذ**:
1. داخل الـ loop، استدعِ `get_holdings(default_router)` + `default_router.quote_many([...])`.
2. احسب `portfolio_value` و `unrealized_pnl` من بيانات حقيقية.
3. اترك `pnl_history` كقائمة من الـ snapshots المحسوبة.

**أوامر التحقق**:
```powershell
.\scripts\run_lite.ps1
# تحقق يدويًا أن portfolio_value ≈ holdings × current prices
```

**معيار القبول**: لا تباعد >0.5% بين WS payload والحساب اليدوي. **يحتاج Claude Code** (cross-file logic).

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #6 — Unit test لـ `holdings.py`

**الهدف**: اختبار أن `get_holdings()` ينتج 8 holdings بـ entry_price يطابق `bars[0].close`.

**الملفات المسموح تعديلها**:
- إنشاء `tests/unit/test_holdings.py`.

**الملفات الممنوع لمسها**:
- `connectors/data_providers/holdings.py` (هذه trust-but-verify فقط).

**خطوات التنفيذ**:
1. mark الملف بـ `pytestmark = pytest.mark.unit`.
2. استخدم `default_router` مباشرة (in-memory).
3. تحقق من `len(holdings) == 8` و `holdings[0].entry_price == (await router.history("BTC", 17))[0].close`.
4. اختبر `reset_cache()` ثم `get_holdings()` مرتين — نفس النتيجة.

**أوامر التحقق**:
```powershell
pytest tests/unit/test_holdings.py -v
```

**معيار القبول**: ينجح، coverage على `holdings.py` ≥80%. **مرشّح لـ Codex** بعد ما Claude يكتب الـ skeleton.

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #7 — Scenario endpoint في mock_server

**الهدف**: `POST /mock/scenario?name=flash_crash` يفعّل kill switch لـ 60 ثانية على WebSocket.

**الملفات المسموح تعديلها**:
- `api/mock_server.py` فقط.

**الملفات الممنوع لمسها**:
- `core/risk/kill_switch.py` (هذا للـ real system).
- `connectors/data_providers/`.

**خطوات التنفيذ**:
1. أضف `@app.post("/mock/scenario")` يأخذ `name` و `duration`.
2. أضف state داخلي `_active_scenario` للـ manager.
3. في `run_loops`، لو scenario نشط، عدّل `system.status.kill_switch_active=True` و `system.status.kill_switch_reason="<name>"`.
4. بعد `duration`، أعد للـ default.

**أوامر التحقق**:
```powershell
.\scripts\run_lite.ps1
# في terminal آخر:
curl -X POST "http://localhost:8000/mock/scenario?name=flash_crash&duration=30"
# Dashboard يجب أن يعرض kill switch banner لـ 30s
```

**معيار القبول**: الـ dashboard يعكس الـ scenario خلال ≤1.5s من الـ POST. **يحتاج Claude Code**.

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #8 — تحديث `AGENTS.md` ليطابق `CLAUDE.md`

**الهدف**: AGENTS.md يتأخر على CLAUDE.md في عدة نقاط (18 vs 19 topics، عدم ذكر CI، عدم ذكر docs/...). يجب مزامنتهما.

**الملفات المسموح تعديلها**:
- `AGENTS.md` فقط.

**الملفات الممنوع لمسها**:
- `CLAUDE.md` (canonical).
- أي كود.

**خطوات التنفيذ**:
1. `git diff CLAUDE.md AGENTS.md` (يدويًا، diff للمحتوى الفعلي).
2. انقل التحديثات الناقصة إلى AGENTS.md.
3. احتفظ بالـ tone موجّهًا لـ Codex.

**أوامر التحقق**: مراجعة بصرية + spot check 5 أقسام.

**معيار القبول**: لا تباين معلوماتي بين الملفين. **مرشّح لـ Codex** بعد توجيه دقيق.

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #9 — Unit test لـ `QuoteRouter.quote_many` (unknown symbols dropped)

**الهدف**: التحقق أن `quote_many(["BTC", "FAKE", "ETH"])` يعيد 2 quotes (يتجاهل FAKE).

**الملفات المسموح تعديلها**:
- إنشاء `tests/unit/test_quote_router.py`.

**الملفات الممنوع لمسها**:
- `connectors/data_providers/router.py`.

**خطوات التنفيذ**:
1. استورد `default_router`.
2. اختبر 3 سيناريوهات: كلها معروفة، كلها مجهولة، خليط.
3. اختبر `history("FAKE", 30)` → `UnknownSymbolError`.

**أوامر التحقق**:
```powershell
pytest tests/unit/test_quote_router.py -v
```

**معيار القبول**: ينجح. **مرشّح لـ Codex.**

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

### Issue #10 — Skeleton لـ `options_strategist` (بدون منطق)

**الهدف**: إنشاء `agents/tier4_strategies/options_strategist.py` كـ skeleton فقط ليتطابق ذكره في `api/mock_server.py:39` مع وجوده فعليًا.

**الملفات المسموح تعديلها**:
- إنشاء `agents/tier4_strategies/options_strategist.py`.
- (اختياري) تحديث `agents/tier4_strategies/__init__.py`.

**الملفات الممنوع لمسها**:
- باقي agents/.
- `api/mock_server.py`.
- `core/`.

**خطوات التنفيذ**:
1. ابدأ بـ class `OptionsStrategist(BaseStrategy)` مع `AGENT_ID` فريد (شغّل `python scripts/validate_agent_ids.py` بعدها).
2. `generate_signal()` يعيد `None` (لا يولّد إشارات).
3. `should_exit()` يعيد `False`.
4. أضف docstring يوضّح "Skeleton — Deribit delta-neutral not yet implemented".
5. تحقق أن `tests/unit/test_imports.py` يمرّ بعد إضافة الـ tuple الجديد (إن لزم).

**أوامر التحقق**:
```powershell
python scripts/validate_agent_ids.py
pytest tests/unit/test_imports.py -v
```

**معيار القبول**: الـ import يمرّ، الـ agent ID لا يتصادم، لا منطق تداول. **مرشّح لـ Codex** بعد ما Claude يحدد الـ AGENT_ID + الـ contract.

**مناسب للجهاز الضعيف؟** ✅ نعم.

---

## ملاحظة ختامية

كل ما سبق **خريطة طريق فقط**. لا يوجد ملف كود تم تعديله أثناء كتابة هذا التقرير. لا Docker، لا Kafka، لا Redis، لا agents، لا ML server، لا integration tests، لا backtests.

استمر بـ `ENVIRONMENT=development` و `ENABLE_DEFI_AGENTS=false` إلى أن تكمل المراحل 1–4 على الأقل.
