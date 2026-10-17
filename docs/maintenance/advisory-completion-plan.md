## Capability mission registry — VERIFICATION PASSED; DOCKER RESTORATION PENDING (2026-10-13T09:50:34.090864+00:00)

The approved **23 paths** are implemented: five existing files changed, three new source/test files and fifteen archive/evidence files. Exact paths and before/after identities are in `artifacts/advisory-capability-registry-v1/source-manifest.json`; commands, diagnostics, replay and containment results are in `verification.json`. The five originals were archived byte-for-byte before edits and tests.

A single static mission registry covers all **40 non-package agent/helper source files**: **25 PLANNED, 5 CONTEXT_ONLY, 2 SUPPORT_ONLY and 8 EXCLUDED**. Each entry names its intended report role, required inputs, planned output and acceptance criteria. These states describe a migration contract, not observed runtime or completed adaptation. The existing five read-only context topics remain unchanged. Unsuitable on-chain and cross-exchange analysis, execution, copying and all four DeFi roles are explicitly excluded; suitable execution-path calculations are only candidates for later isolated extraction.

Authenticated `GET /assistant-api/capabilities` reads current source identities without importing or starting agents, using the existing middleware. Its registry always states `NOT_OBSERVED`, `NOT_ASSESSED`, `all_agents_integrated=false`, `trade_permitted=false` and `execution_enabled=false`. Missing, redirected, unmapped or changed source evidence is rejected; stale envelopes are preserved rather than patched. Renamed/duplicated roles, reconstructed positive flags and hypothetical confirmation cannot convert the catalog to a qualified signal. Verification repeats whole-file source checks per request; there is no persistent verification cache. Pre-existing API function bodies/signatures and test fixtures are unchanged; financial arithmetic, briefing evidence fields, the MES/MNQ-only **20 Micro total cap**, current **$1,100 daily-loss setting**, and official TCP50 blocked eligibility remain unchanged.

Verification: **2746 full-suite tests passed, zero failures/errors/skips, 562 warnings; coverage 84.47% against the unchanged 70% gate**. Focused tests: **400 passed, zero skips, 36 warnings**, overlapping with the full suite and not added to it. Ruff, Black check, isort check, strict MyPy (130 source files), all six architecture packages and TypeScript passed. isort's 13 configured file exclusions are disclosed. Dashboard source is unchanged; no new frontend/browser functionality was introduced or certified. Initial focused tests stalled in sandbox TestClient setup; a bounded 20-second diagnostic failed there, and the same API case passed outside the sandbox in 1.09 seconds. The focused and full receipts are the final successful runs; original diagnostics remain in /tmp and their details/commands are preserved in this receipt.

Fresh public verification passed for existing futures run/edge/walk envelopes with path replay, strict source hashes and exact comparison. The three legacy TCP25 outcomes remain separately **PASS, FAIL and CENSORED — SYNTHETIC MECHANICS ONLY**. Three unchanged briefing examples reopened and independently replayed successfully; their source identity set is unaffected, so they were not regenerated or rewritten. The new registry was serialized, reopened and independently verified. The inventory is a code/migration map, not trading-edge evidence.

All **1570 prior public artifact files**, five original archives and **137 existing htmlcov/.coverage files** were preserved. The monitored public-file inventory records only the approved 23 paths as changed/created. Credentials, private root data, private dependency/tool directories and database sidecars are excluded; this public inventory is not a claim of byte-level preservation of private mutable databases. Coverage data, explicit HTML destination `/tmp/alghrest-capability-registry/htmlcov`, JSON/XML reports, test temporary files, Hypothesis storage and tool caches stayed in /tmp; bytecode and pytest cache writes were disabled. Published JUnit copies remove hostname attributes and redact userinfo in one synthetic URL parameter from an existing redirect-denial test; originals remain in /tmp. The first independent secret-pattern scan flagged that synthetic parameter, which was redacted before final re-verification. The historical htmlcov exception cannot be certified retroactively because its earlier bytes were not hashed; earlier missing SQLite WAL/SHM files remain unreconciled. This increment does not hide either limitation.

After renewed explicit user authorization, only existing isolated PostgreSQL/Redis/Kafka quality services were started, then stopped. Docker service is still active/socket active; restoring its prior inactive service state requires the user’s local sudo stop command. The automated noninteractive stop failed because a password was required; test ports15432/16379/19092 are closed. Existing assistant8011/dashboard5173 remain available and were not restarted. The new API was tested in isolated TestClient applications; the user's existing API is not certified as reloaded. No broker mutation, order/cancellation/liquidation/copying, purchase, external message, paid model call, .env edit, failed-soak restart or new holdout access occurred.

Code, tests and evidence verification passed; this capability-registry increment is not fully closed until Docker restoration is independently confirmed. It does not complete adaptation of all agents, qualify a 5m/15m strategy, resolve permitted market-data coverage, or complete forward Paper evaluations. The staged mission remains evidence-led MES/MNQ reports for human decisions; current session briefings remain WAIT/NO_TRADE. Passing probability **UNKNOWN**. The compatible broader Goal remains **BLOCKED** in the tool, with no unsupported resume or completion claimed. **Stop for human review before further implementation or deployment.** The next bounded proposal should define qualified 5m/15m conditional-analysis inputs and deterministic invalidation/target rules before adapting strategy contributions.

---

Exact approved paths for this increment:

1. `src/api/advisor.py`
2. `tests/unit/test_advisory_api.py`
3. `docs/maintenance/architecture-unification-plan.md`
4. `docs/maintenance/advisory-completion-plan.md`
5. `docs/maintenance/earn2trade-50k-readiness.md`
6. `src/core/advisory/capability_registry.py`
7. `src/api/routes/advisory_capabilities.py`
8. `tests/unit/test_advisory_capability_registry.py`
9. `artifacts/advisory-capability-registry-v1/before/advisor.py`
10. `artifacts/advisory-capability-registry-v1/before/test_advisory_api.py`
11. `artifacts/advisory-capability-registry-v1/before/architecture-unification-plan.md`
12. `artifacts/advisory-capability-registry-v1/before/advisory-completion-plan.md`
13. `artifacts/advisory-capability-registry-v1/before/earn2trade-50k-readiness.md`
14. `artifacts/advisory-capability-registry-v1/source-manifest.json`
15. `artifacts/advisory-capability-registry-v1/verification.json`
16. `artifacts/advisory-capability-registry-v1/capability-inventory.json`
17. `artifacts/advisory-capability-registry-v1/research.md`
18. `artifacts/advisory-capability-registry-v1/focused-tests.xml`
19. `artifacts/advisory-capability-registry-v1/focused-tests.log`
20. `artifacts/advisory-capability-registry-v1/full-tests.xml`
21. `artifacts/advisory-capability-registry-v1/full-tests.log`
22. `artifacts/advisory-capability-registry-v1/coverage.json`
23. `artifacts/advisory-capability-registry-v1/checks.log`

---

## Workflow unification — VERIFIED; review checkpoint (2026-10-13T01:56:45.552958+00:00)

The approved **33 paths** are implemented: nine existing files changed, one new application module and 23 new evidence/archive files. The exact scope, before/after identities and preservation checks are in `artifacts/architecture-workflow-unification-v1/source-manifest.json`; exact commands and results are in `verification.json`. The nine original files were archived byte-for-byte **before edits and tests**. Historical sections below describe their own dated increments.

`src/api/services/briefings.py` now owns context collection and the report workflow: capture selected reviewed observation/account revisions, collect read-only context, recheck, calculate and save. Existing HTTP functions and signatures remain compatible adapters, including `_collect_context`. No route imports another route's helper. Financial arithmetic, source clocks, serialized evidence fields, the MES/MNQ-only **20 Micro total cap** and the current **$1,100** daily-loss setting are unchanged; the later $1,200 example has not been substituted.

Root cause corrected: cancelling `asyncio.to_thread` did not stop its SQLite writer. Three deterministic before probes returned “not saved” and then committed a report. The original regression failed before the correction. A request-local commit guard now cancels/rolls back a write that has not crossed its commit decision and checks its original monotonic deadline at that decision. A commit already underway is not claimed to be interruptible: its response explicitly reports an uncertain outcome and directs the user to history. A known committed record whose display fails is reported as saved. Each request gets a fresh guard; it is neither reusable evidence nor a persistent verification cache. The existing commit-time revision checks remain inside the transaction.

Verification: **2719 full-suite tests passed, zero failures/errors/skips, 562 warnings; coverage 84.43% with the unchanged 70% gate**. Focused regressions: **74 passed**, overlapping with the full suite, not added to it. All six frontend suites passed **110 cases**. Ruff, Black check, isort check, strict MyPy (**128 source files**), six-package architecture, TypeScript and production build passed. Browser checks: **12 passed** against the actual isolated API/store, including pre-commit timeout, commit uncertainty, delivery failure, preserved selection/history, authentication and mobile layout. The mobile screenshot was inspected. Browser inputs, empty context, fixed source clock, shortened test deadline and fault barriers were synthetic instrumentation; production remains at its existing 30-second deadline. The first browser harness attempt observed an old result before the retry finished; it was corrected to await the actual POST response and re-run successfully. Its failed receipt is retained in controls; the production build retains the Browserslist age warning.

Fresh public replay passed for the existing futures **run, edge and walk** artifacts. Legacy TCP25 outcomes were independently verified and reported separately as **PASS, FAIL and CENSORED — SYNTHETIC MECHANICS ONLY**. Three briefing examples were regenerated from their exact original inputs, clocks and cost/configuration/result fields; only new IDs and current source identities differ. Old changed-source envelopes are rejected, preserved and never patched. Three new envelopes and six actual temporary saved records were independently reopened in a separate process with strict source checks and exact replay. Trade and execution permission remained false; historical age was displayed without renewing the source price time.

Only the approved paths were written in the monitored public-file inventory; previous artifacts and current htmlcov/.coverage were preserved by byte comparison. Credentials, root private data, database sidecars, dependency/tool private directories are excluded from that public inventory. Coverage data, explicit HTML destination `/tmp/alghrest-workflow-unification/htmlcov`, JSON/XML reports, test temporary files, Hypothesis storage, build/browser files and caches stayed in /tmp; bytecode and pytest cache writes were disabled. Published JUnit copies remove hostname attributes; originals remain in /tmp. The **historical htmlcov exception cannot be certified retroactively** because earlier bytes were not captured. Earlier disappeared SQLite WAL/SHM files remain unreconciled. Current preservation does not erase either limitation.

Cleanup was independently checked after the user's stop: Docker service **inactive**, socket **active**, matching its baseline; PostgreSQL/Redis/Kafka test ports and temporary API18114/UI15176 ports closed. Existing assistant8011/dashboard5173 remain available and were not restarted. Verification used isolated servers; the already-running user API has not been certified as reloaded with this change. No orders, broker mutations, purchases, external messages, paid-model calls, .env changes, failed-soak restart or new holdout access occurred.

This is engineering completion of this increment only. The report still offers **WAIT/NO_TRADE**, official TCP50 positive eligibility remains blocked, and no complete agent integration, qualified 5m/15m strategy, live-data entitlement, forward evaluation or trading edge is certified. Passing probability **UNKNOWN**. Goal tool status remains **BLOCKED**; no unsupported resume or overall completion is claimed. **Stop for human review before further implementation or deployment.** Next work needs a separate bounded scope: define qualified 5m/15m conditional analysis and acceptance evidence, then integrate only useful read-only capabilities.

---

# Workflow unification — exact authorized 33-path scope

Authorized 2026-10-13; now verified as recorded above. The original scope remains below for review. Before identities and nine archives were captured before implementation.

Exact scope:

1. `src/api/routes/advisory_context.py`
2. `src/api/routes/advisory_briefings.py`
3. `src/connectors/advisory/briefing_store.py`
4. `src/core/advisory/briefing.py`
5. `tests/unit/test_advisory_context.py`
6. `tests/unit/test_advisory_briefings.py`
7. `docs/maintenance/architecture-unification-plan.md`
8. `docs/maintenance/advisory-completion-plan.md`
9. `docs/maintenance/earn2trade-50k-readiness.md`
10. `src/api/services/briefings.py`
11. `artifacts/architecture-workflow-unification-v1/before/advisory_context.py`
12. `artifacts/architecture-workflow-unification-v1/before/advisory_briefings.py`
13. `artifacts/architecture-workflow-unification-v1/before/briefing_store.py`
14. `artifacts/architecture-workflow-unification-v1/before/briefing.py`
15. `artifacts/architecture-workflow-unification-v1/before/test_advisory_context.py`
16. `artifacts/architecture-workflow-unification-v1/before/test_advisory_briefings.py`
17. `artifacts/architecture-workflow-unification-v1/before/architecture-unification-plan.md`
18. `artifacts/architecture-workflow-unification-v1/before/advisory-completion-plan.md`
19. `artifacts/architecture-workflow-unification-v1/before/earn2trade-50k-readiness.md`
20. `artifacts/architecture-workflow-unification-v1/source-manifest.json`
21. `artifacts/architecture-workflow-unification-v1/verification.json`
22. `artifacts/architecture-workflow-unification-v1/focused-tests.xml`
23. `artifacts/architecture-workflow-unification-v1/focused-tests.log`
24. `artifacts/architecture-workflow-unification-v1/full-tests.xml`
25. `artifacts/architecture-workflow-unification-v1/full-tests.log`
26. `artifacts/architecture-workflow-unification-v1/coverage.json`
27. `artifacts/architecture-workflow-unification-v1/checks.log`
28. `artifacts/architecture-workflow-unification-v1/frontend-tests.log`
29. `artifacts/architecture-workflow-unification-v1/browser-checks.json`
30. `artifacts/architecture-workflow-unification-v1/regenerated-briefings.json`
31. `artifacts/architecture-workflow-unification-v1/before-after-parity.json`
32. `artifacts/architecture-workflow-unification-v1/timeout-reproduction.json`
33. `artifacts/architecture-workflow-unification-v1/controls.json`

---

# Evaluation-focused briefing — VERIFIED; stopped for human review

## Evaluation-focused briefing — verified review checkpoint (2026-10-13T00:44:38.545693+00:00)

The approved **29 paths** are implemented: five existing files updated and 24 new files. This increment joins a selected, saved and reviewed chart observation with its exact revision, a personal account revision, published news/events and a capability contribution map in one append-only session briefing. It does not claim that all agents ran. The API rechecks the observation, review and account before committing; changed inputs are rejected. Saved records retain full inputs, source clocks and code identities. Reopening repeats strict whole-file source hashes and exact deterministic replay; mismatched records are rejected without rewriting their provenance or using a persistent verification cache.

The report offers **WAIT/NO_TRADE only**, with explicit reasons. REVIEWABLE means the captured evidence can be reviewed, not market readiness or trade permission. Printed prices, indicators, levels and user hypotheses remain separate; only same-contract, same-time printed prices are compared for conflict. Missing candle history is not invented. News/calendar coverage remains partial and event risk UNKNOWN. Agent summaries are bounded, timestamped, instrument-related read-only context; no confidence score or consensus is inferred from the number of agents. Execution, DeFi and copying remain disabled. Personal rules, existing calculations and the total **20 Micro MES/MNQ** exposure cap are unchanged. The existing daily-loss calculation remains **$1,100**; the user's later $1,200 example is not silently substituted. Official TCP50 eligibility remains separate and blocked.

Verification: **2708 full-suite tests passed, 0 failures/errors/skips, 562 warnings; coverage 84.38% against the unchanged 70% gate**. Focused regressions: **193 passed**, overlapping with the full suite and not added to it. Frontend suites: 15 briefing, 12 news/events, 10 observations, 30 user-policy and 26 user-risk cases passed, without skips. Ruff, Black check, isort check, strict MyPy (127 source files), six-package architecture checks, TypeScript and the production build passed. Build retained its Browserslist age warning. Final browser workflow: 12 checks passed, plus a fresh real-clock mobile check with the menu fully closed and actual pointer access to the saved report. Browser inputs and empty published context were injected synthetic fixtures, not a live market connection. Earlier harness/style/command transcription failures are disclosed in the receipt.

Fresh public replay verified existing futures run, edge and walk envelopes with source checks and exact comparison. Legacy TCP25 simulation outcomes remain separately **PASS, FAIL and CENSORED**, all synthetic mechanics only. Three new briefing fixtures (current WAIT, stale INCOMPLETE/WAIT, same-time conflict NO_TRADE) were reopened and independently replayed; saved stores were reopened in a separate process. All prior public artifact bytes and the five byte-for-byte before archives are checked in the final source manifest. Existing htmlcov (136 files) and .coverage are compared to the current before baseline. The historical htmlcov exception cannot be certified retroactively because prior bytes were not captured; the earlier missing SQLite WAL/SHM bytes remain unreconciled. Neither limitation is repaired or hidden by this increment.

Coverage data and HTML/JSON/XML reporters, pytest temporary files, Hypothesis storage, build/browser outputs and tool caches were redirected to /tmp; bytecode and pytest cache writes disabled. Only approved evidence files are published. JUnit hostname attributes are removed from published copies, with original receipts retained in /tmp. Exact commands, source identities, output containment and secret scan results are in `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/verification.json` and `source-manifest.json`.

Cleanup verified: isolated PostgreSQL/Redis/Kafka and temporary API18112/UI15174 ports closed. Docker service inactive/socket active, matching the initial state. Existing user assistant8011/dashboard5173 remain available and were not restarted. The new workflow was verified on isolated servers; the already-running user API does not expose new routes until a later restart after review. No orders, broker mutations, purchases, external messages, paid model calls, .env edits, failed-soak restart or new holdout access occurred.

**Review checkpoint:** stop before further implementation or activation. The smallest next proposal is a separately scoped conditional-analysis stage with defined 5m/15m inputs, invalidation/target rules and honest gaps; financial changes and agent adaptations need their own scopes. Passing probability **UNKNOWN**. Tests, synthetic replay and this research briefing do not prove trading edge or guarantee passing. Goal was newly created after lookup returned null; no unsupported resume or overall completion is claimed.

---

# نطاق مقترح — المساعد الموجه لتقييم التمويل، المرحلة الأولى

الجذر: `/home/xsabo/Projects/MY project/alghrest-main`. التاريخ UTC: 2026-10-13T00:15:25.118902+00:00.
**29 ملفًا بالضبط: 5 قائمة + 24 جديدة؛ 12 مصدر/اختبار/توثيق + 17 أرشفة/أدلة.**
هذا مقترح للموافقة، وليس تنفيذًا. كل الوجهات الجديدة غير موجودة. فحص هويات المرحلة السابقة نجح. لا تعديل للمستودع، ولا اختبارات/خدمات جديدة خلال إعداد المقترح. Goal lookup=null، لا ادعاء استئناف أو اكتمال.

## لماذا هذه المرحلة أولًا

الملاحظات المراجعة، الأخبار، الحساب، ورقة المخاطر وسياق الوكلاء موجودة في مسارات منفصلة. الوكلاء العامة ليست كلها مكيّفة لفيوتشر أو لقواعد المستخدم؛ جسر Kafka اختياري ولا يحول مجرد نص الوكيل إلى دليل. الاستراتيجية المسجلة الحالية volume breakout تفترض1d، فلا تُعاد تسميتها كاستراتيجية5m/15m. الوكلاء التي تحتاج OHLCV لا تُشغل على قيم من صور باعتبارها سلسلة شموع.

الناتج: **تقرير جلسة بحثي واحد محفوظ** يربط نسخة ملاحظة محددة راجعتها، سياق الأخبار الفعلي، حسابًا محددًا ومراجعته، وحالة مساهمة كل قدرة. يعرض الوقائع والمستويات المطبوعة وفرضيات المستخدم منفصلة، اتفاق/تعارض الأدلة عندما تكون مقارنتها صالحة، النواقص، سبب الانتظار/عدم التداول، ونتائج الحساب الشخصي القائم عند تطابق أدلته. لا يُعلن أن كل الوكلاء شُغّلت.

## الناتج والحدود

1. أداة واحدة تجمع الأدلة خلف واجهة صغيرة: اختيار observation ID/revision + evaluation ID/current revision. إعادة القراءة والتحقق وتحديد الوقت/الهوية قبل تكوين التقرير؛ إعادة فحص النسخة والحساب بعد الجلب وقبل الحفظ حتى لا يخفي تأخر الشبكة تغيّر المدخلات.
2. قراءة نسخة ملاحظة محفوظة ومراجعة، باستخدام ObservationStore القائم. يختار المستخدم هذه النسخة صراحةً؛ التقرير لا يقرأ مسودة شاشة الإدخال غير المحفوظة ولا يدعي أنها النسخة المختارة. لا تجديد وقت السعر عند تجديد الخبر، ولا تحويل مراجعة المستخدم إلى تحقق مستقل. رد غير محفوظ/نسخة قديمة أو خلاف هوية يبقى غير كافٍ؛ تعرض الأسباب.
3. إعادة استخدام FeedCache/CalendarCache وbuild_context عبر helper داخلي في route الحالي؛ الحفاظ على GETcontext القديم ومدخلاته ومخرجاته. جلب عناوين/جدول محدود فقط؛ لا LLM مدفوع أو تحميل مقال أو رابط وارد من المستخدم.
4. عرض5m/15m/1h ومصادر المستويات/المؤشرات كما أُدخلت؛ لا حساب ATR/RSI/حجم أو ملء فراغات دون سجل شموع صالح. اختلاف أسعار فريمات مختلفة ليس تناقضًا تلقائيًا، ويمنع القياس عندما تختلف أزمنة السعر/العقد.
5. عرض بيانات الحساب باستخدام الوظائف الشخصية الحالية دون تغيير حساباتها. الربط لا ينشئ حسابًا أو مراكز/أوامر، ولا يغير حد1,100$ إلى1,200$. يظهر الاختلاف المطلوب حسمه في مرحلة القواعد التالية. لا حساب مخاطر المراكز المفتوحة من دون وقفها؛ تأهيل حجم جديد يبقى ضمن شرط الحساب الخالي القائم وتكاليفه المراجعة.
6. **لن تنتج هذه المرحلة توصية شراء/بيع مؤهلة جديدة.** القرار الافتراضي WAIT/NO_TRADE مع أسباب فعلية. يمكن عرض سيناريو بحثي قائم فقط إن اجتاز شروطه الأصلية ومصادره؛ لا تحويلUNKNOWNإلىCLEAR ولا فك حارس السوق/الأحداث أو سياسةTCP50. تبقى trade_permitted=false وexecution_enabled=false، واحتمال الاجتيازUNKNOWN.
7. خريطة القدرات منجزة/غير موصولة/تحتاج بيانات/غير ملائمة/معطلة. تُعرض مساهمة فعلية فقط مع مصدر ووقت وأداة؛ وجود ملفات أو تعدد وكلاء ليس إجماعًا ولا درجة ثقة رقمية. جسر المخرجات القائم فقط، دون توسيع topics أو تشغيلfabric أو نموذج أو وسيط.
8. حفظ append-only في جدول جديد داخل قاعدة المساعد المعزولة عبر AdvisoryStore.connect القائم، لا تعديلات لسجلات الملاحظات أو الحساب القديمة. حفظ كامل المدخلات والنسخ/المراجعات والسياق ومخرجات التقرير وهوية الكود. إعادة فتح التقرير تعيد strict whole-file source checks والمقارنة الدقيقة؛ لا historical-version verification أو persistent verification cache، ولا إعادة ترميز أدلة قديمة لتجاوز mismatch.
9. واجهة عربية واحدة لا تربك الملاحظات القديمة: نموذج اختيار النسخة والحساب، بناء/حفظ وفتح السجل، وقت السعر/الخبر/الحساب منفصلة، حماية ردود متأخرة/تغيير الاختيار/تعديلات غير محفوظة/مصدر متعذر/عرض الهاتف.

## المسارات الدقيقة

| # | المسار | الحالة |
|---|---|---|
| 1 | `src/api/advisor.py` | قائم |
| 2 | `src/api/routes/advisory_context.py` | قائم |
| 3 | `dashboard/src/pages/ManualAssistant.tsx` | قائم |
| 4 | `docs/maintenance/advisory-completion-plan.md` | قائم |
| 5 | `docs/maintenance/earn2trade-50k-readiness.md` | قائم |
| 6 | `src/core/advisory/briefing.py` | جديد |
| 7 | `src/connectors/advisory/briefing_store.py` | جديد |
| 8 | `src/api/routes/advisory_briefings.py` | جديد |
| 9 | `dashboard/src/components/advisory/BriefingPanel.tsx` | جديد |
| 10 | `dashboard/src/lib/briefings.ts` | جديد |
| 11 | `tests/unit/test_advisory_briefings.py` | جديد |
| 12 | `dashboard/tests/briefings.test.ts` | جديد |
| 13 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/before/advisor.py` | جديد |
| 14 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/before/advisory_context.py` | جديد |
| 15 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/before/ManualAssistant.tsx` | جديد |
| 16 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/before/completion-plan.md` | جديد |
| 17 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/before/readiness.md` | جديد |
| 18 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/source-manifest.json` | جديد |
| 19 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/verification.json` | جديد |
| 20 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/focused-tests.xml` | جديد |
| 21 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/focused-tests.log` | جديد |
| 22 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/full-tests.xml` | جديد |
| 23 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/full-tests.log` | جديد |
| 24 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/coverage.json` | جديد |
| 25 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/checks.log` | جديد |
| 26 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/frontend-tests.log` | جديد |
| 27 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/browser-checks.json` | جديد |
| 28 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/capability-map.json` | جديد |
| 29 | `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/briefing-fixtures.json` | جديد |

## تحقق القبول

- اختبارات جوهرية عبر واجهة التقرير: نسخة غير مراجعة/مستبدلة، حساب أوعقد مختلف، مصدر قديم/مستقبلي/ناقص، تأخر الشبكة وتغيّر المراجعة قبل الحفظ، فشل مصدر جزئي/كامل، مؤشرات ونصوص مزورة، مخرجات وكيل مبهمة/غير ملائمة، أرشيف مصدر-hash-mismatched، مقارنة محفوظة دقيقة، وعدم فتح BUY/SELL أو إذن تنفيذ من UNKNOWN.
- API مصادق، bounded payloads، عدم لمس وسيط/تنفيذ/Kafka order topics أو .env. حفظ منفصل append-only، انقطاع/إعادة فتح قاعدة، concurrent revision conflict. interfaces والحسابات القديمة تعمل دون تغيير.
- الواجهة والمتصفح: تدفق اختيار/جمع/حفظ/إعادة فتح، ربط الهويات، رد متأخر، الأسعار لا تتجدد بالأخبار، حالات غياب المعلومات، العرض الضيق، ونصوص واردة غير قابلة للتنفيذ.
- المركزة ثم المجموعة الكاملة ببوابة70% كما هي، Ruff/Black/isort/MyPy strict/architecture، frontend tests/types/build/browser. تقرير التحذيرات والتخطي والفشل، وعدم جمع الأعداد المتداخلة.
- قبل التعديل: byte baseline للملفات العامة وhtmlcov/.coverage، أرشفة الخمسة القائمة. كل caches/reports/data/pytest/Hypothesis/build/browser في/tmp، وHTMLoverrideصريح. خدمات الاختبار المعزولة فقط عند الحاجة، دون إعادة تشغيل تجربةsoak، واستعادة الحالة. لا تغيير خدمات المستخدم القائمة دون سبب/تفويض.
- fresh public replay لأدلة futuresrun/edge/walk وlegacyPASS/FAIL/CENSORED، مع sourcechecks/exactcomparison لكل طلب verification، وحفظ القديم. لا تغيير financial/evidence modules في هذه المرحلة؛ إن احتاج التحقق regeneration خارج29ملفًا يعرض السبب والتوسعة قبل الكتابة.
- حفظ كامل old artifacts/receipts، إفصاح عن ملفيSQLiteالمساعدين المفقودين والاستثناء التاريخيhtmlcov؛ عدم الادعاء بإصلاحهما أو استعادة تاريخ لم يعد موجودًا.
- تحقق source-manifest/receipts بعد إعادة الفتح وفحص أي out-of-scopewrite، ثم توقف للمراجعة. احتمال الاجتيازUNKNOWN، ولا trading-edge claim.

## المراحل التالية — تخطيط فقط، ليست موافقة على مساراتها

2. تحليل وخطة مشروطة: اختيار قواعد قابلة للفحص للفريمات، ربط أدلة الأسعار والأخبار ومساهمة التحليل الفني/الاقتصادي/المعنويات/التقلب، وأسعار دخول/إلغاء/أهداف من مدخلات مثبتة مع علاقةمخاطرة/عائد؛ لا تشغيل خوارزمية محتاجة شموع على صورتين فقط. تحديد استراتيجية قبل اختبارها؛ لا ادعاء صفقة ممتازة أو احتمالات معايرة بلا نتائج.
3. حسم حد1,100/1,200 وتعريف drawdown، وربط الحساب والتكاليف ومخاطر الوقف للمراكز القائمة. اعتماد نطاق مستقل قبل أي تغيير مالي. سقف20Microوفصل قواعد المستخدم عن الشركة محفوظان.
4. تكييف مخرجات الوكلاء المناسبة واحدة واحدة بوصلات قراءة فقط عندما يوجد مصدر ومدخلات مسموحة؛ لا تفعيل جميع الوكلاء لأجل عددهم. لا شراء/رسائل/اشتراكات مدفوعة أو تشغيل LLM بلا تفويض إضافي.
5. تقييمDEMOمستقبلي: حفظ النص والخطة قبل معرفة النتيجة، التنفيذ البشري، تكاليف ووقت وأسبابFAIL/PASS/CENSORED، مع تجاربOOSومنهجية مسبقة وقياس خطأ/نتائج وعدم يقين. استقرار التشغيل المالي الطويل وfailedsoakمسار منفصل يحتاج reconciliationوتفويضًا.

إنشاء مشروعChatGPTمؤجل. التداول الآلي، الإلغاء، التصفية، النسخ وDeFiخارج المسار. لا ضمان اجتياز أو نسبة تقدم مصطنعة.


---

## Cleanup follow-up — RESTORED (2026-10-12T23:21:49.764698+00:00)

After the user's local stop command, independent systemctl verification confirms
Docker service **inactive** and socket **active**, matching the captured prior state.
All isolated test/API/UI ports are closed. No Docker API was called during verification.
The separately requested assistant API8011 and UI5173 remain listening without Docker.
Cleanup is complete; stop for human review. Earlier authentication blockers below are
historical and retained. Test results, source identities and readiness limitations are
unchanged; passing probability UNKNOWN. No source edits or Goal lifecycle changes.

---

# News/events stage — IMPLEMENTED_VERIFIED_STOPPED_FOR_REVIEW; Docker restoration pending

## News/events context — 2026-10-12 review checkpoint

The authorized **29-path** increment is implemented. An authenticated read-only
MES/MNQ context endpoint and an independent Arabic panel show headline publication,
actual retrieval/attempt clocks, deterministic relevance reasons, source failures,
and partial official schedules. Manual refresh and optional visible-page 5/15-minute
refresh do not modify observation prices or their timestamps. Late responses cannot
replace a newer instrument selection. Coverage stays **partial**, event risk **UNKNOWN**,
and both permission flags **false**. No calendar is supplied to the financial event guard.
Public FeedCache/headlines signatures and existing serialized evidence are preserved;
MES now excludes unrelated crypto headlines consistently with MNQ.

Verified: **2682 full-suite tests, zero failures/skips, 562 warnings**;
**84.216357%** coverage, unchanged **70%** gate. **267 focused** tests overlap
the full suite; counts are not added. Frontend **12 context / 10 observation / 30 cap /
26 personal-risk** tests pass. Ruff, Black, isort, strict MyPy (124 files), architecture,
TypeScript and build pass. isort keeps 13 configured file exclusions. Full warnings are
DeprecationWarning/FutureWarning; the build retains outdated Browserslist-data warning.
**17 browser checks** pass with intercepted synthetic context and a separate local
API/database; Google-font requests were blocked. Fixtures prove mechanics only.

Fresh run/edge/walk public replay repeats strict whole-file source checks and exact
comparison. Legacy TCP25 examples replay separately as **PASS / FAIL / CENSORED**.
Nothing was rehashed or rewritten to mask mismatch. Five byte archives match the
original baseline. Details, commands and all 29 paths are in this stage's manifest and
verification receipt under `artifacts/earn2trade-50k-readiness/news-events-v1/`.

Sources: FOMC and BEA direct captures parsed 16 and 13 entries. FOMC dates do not
provide exact meeting hours; BEA printed wall times retain an unknown timezone.
BLS direct feed/calendar availability varies between timeout and HTTP403; the
independent calendar capture returned403. No refusal was bypassed. These schedules
are always partial, not a complete economic-calendar or an entry-clearance signal.

The execution environment restarted and removed earlier /tmp receipts. They were
reproduced; earlier observed results are not presented as surviving archived reports.
Two SQLite auxiliaries included in the old baseline (`artifacts/advisory/research.sqlite3-wal`
and `.sqlite3-shm`) are now absent. Their disappearance cannot be timed/attributed from
available evidence and byte preservation of them is **UNKNOWN**. They are runtime
sidecars, not research envelopes. The separately requested assistant startup backs up
the current main journal to a private /tmp copy; this cannot reconstruct absent prior
sidecars or certify journal history. No other public baseline path is missing/changed
outside scope. Prior htmlcov/.coverage bytes are preserved for this increment; the
historical htmlcov exception remains uncertifiable because earlier bytes were not hashed.

Test containers are stopped and isolated ports closed. Docker daemon restoration to
its prior inactive state is **BLOCKED pending local interactive authentication**;
socket was and remains active. User was asked to stop only docker.service.
Following the user's separate “run my project” request, the advisory API8011 and
UI5173 remain available without Docker/Kafka/broker or trading agents. Runtime key,
launchers/caches and current-journal backup are private /tmp files; no .env change.
Temporary test API18112/UI15174 will be stopped independently.

Stop for human review before analysis/recommendation work. Personal **20 Micro**
policy and closed official TCP50 gate are unchanged. Price data, complete calendar,
historical decision-context storage, qualified trading evidence and forward paper
outcomes remain unresolved. **Passing probability UNKNOWN; no trading-edge claim.**
Goal lookup returned null; no Goal was resumed or completed. Heartbeat not reactivated.

---

# News/events stage — authorized 29 paths, IN_PROGRESS

Recovery checkpoint 2026-10-12: temporary receipts disappeared after execution-environment restart. Repository archives and the original 2869-file baseline remain. Earlier observed 2682-pass full suite/84.22% is not a saved final receipt; re-create focused/full/static/browser receipts before completion. User subsequently requested running the project: only advisory API 8011 and dashboard 5173 are started, no agent fabric. Runtime launcher/cache/key/backups live in /tmp; key never published.

Work directory: `/tmp/alghrest-news-events-work-o3vtw4kh`. Before identities and five byte-for-byte archives captured. No tests claimed yet. Goal lookup returned null; no lifecycle change. Heartbeat not reactivated. Resume this exact stage; preserve all prior work.

# نطاق مرحلة الأخبار والأحداث — للموافقة قبل التنفيذ

الجذر: `/home/xsabo/Projects/MY project/alghrest-main`.
**29 ملفًا: 5 ملفات قائمة + 24 ملفًا جديدًا**. منها 12 ملف مصدر/اختبار/توثيق و17 ملف أرشفة/أدلة. فُحصت الوجهات؛ الجديدة غير موجودة حاليًا. لا تعديل للمستودع خلال إعداد هذا المقترح. موافقة المرحلة السابقة لا تمتد تلقائيًا إلى هذه القائمة.

## الناتج المقترح

لوحة أخبار وأحداث مستقلة داخل المساعد تعمل حتى دون أسعار: أخبار ذات صلة بـMES/MNQ، سبب تصنيف الصلة، مصدر ووقت نشر/جلب منفصلان، قائمة أحداث رسمية مع تواريخها/أوقاتها عند معرفتها، وحالة كل مصدر وتغطية جزئية واضحة. لا تنبؤات أسعار ولا توصيات شراء/بيع في هذه المرحلة.

## المسارات الدقيقة


| # | المسار | الحالة والغرض |
|---|---|---|
| 1 | `src/connectors/advisory/news.py` | existing: Extend existing feed cache with actual fetch status/times and content identity; preserve get/headlines signatures; make MES relevance consistent with MNQ. |
| 2 | `src/api/advisor.py` | existing: Wire authenticated context router and per-process calendar cache; no Kafka/calendar guard policy changes. |
| 3 | `dashboard/src/pages/ManualAssistant.tsx` | existing: Mount the independent news/events panel next to the observation panel. |
| 4 | `docs/maintenance/advisory-completion-plan.md` | existing: Stage checkpoint, verified progress and remaining work. |
| 5 | `docs/maintenance/earn2trade-50k-readiness.md` | existing: Evidence, limits, source outages and unresolved readiness gaps. |
| 6 | `src/core/advisory/news_context.py` | new: Pure strict context models, clocks, deterministic relevance explanations and partial coverage; reuse News/EconomicEvent where applicable. |
| 7 | `src/connectors/advisory/economic_calendar.py` | new: Bounded allowlisted official schedule fetching/parsing and memory cache, per-source failure status; unknown time retained. |
| 8 | `src/api/routes/advisory_context.py` | new: Authenticated MES/MNQ context endpoint; reuse existing client/feed cache, injected clocks, no arbitrary URL fetching. |
| 9 | `dashboard/src/components/advisory/NewsEventsPanel.tsx` | new: Arabic headlines/events/source-state display, explicit refresh and optional 5/15-minute visible-page refresh. |
| 10 | `dashboard/src/lib/newsEvents.ts` | new: Strict response validation, source age and late-response protection. |
| 11 | `tests/unit/test_advisory_context.py` | new: Meaningful feed, calendar, clock, error, API, isolation and compatibility regressions. |
| 12 | `dashboard/tests/news-events.test.ts` | new: Context shape, timestamps, late responses, failures and no readiness uplift. |
| 13 | `artifacts/earn2trade-50k-readiness/news-events-v1/before/news.py` | new: Byte-for-byte archive of src/connectors/advisory/news.py |
| 14 | `artifacts/earn2trade-50k-readiness/news-events-v1/before/advisor.py` | new: Byte-for-byte archive of src/api/advisor.py |
| 15 | `artifacts/earn2trade-50k-readiness/news-events-v1/before/ManualAssistant.tsx` | new: Byte-for-byte archive of dashboard/src/pages/ManualAssistant.tsx |
| 16 | `artifacts/earn2trade-50k-readiness/news-events-v1/before/completion-plan.md` | new: Byte-for-byte archive of docs/maintenance/advisory-completion-plan.md |
| 17 | `artifacts/earn2trade-50k-readiness/news-events-v1/before/readiness.md` | new: Byte-for-byte archive of docs/maintenance/earn2trade-50k-readiness.md |
| 18 | `artifacts/earn2trade-50k-readiness/news-events-v1/source-manifest.json` | new: Before/after public identities, preservation, containment. |
| 19 | `artifacts/earn2trade-50k-readiness/news-events-v1/verification.json` | new: Commands, outcomes, earlier failures, limitations and service restoration. |
| 20 | `artifacts/earn2trade-50k-readiness/news-events-v1/focused-tests.xml` | new: Focused test result. |
| 21 | `artifacts/earn2trade-50k-readiness/news-events-v1/focused-tests.log` | new: Focused test log. |
| 22 | `artifacts/earn2trade-50k-readiness/news-events-v1/full-tests.xml` | new: Full-suite result. |
| 23 | `artifacts/earn2trade-50k-readiness/news-events-v1/full-tests.log` | new: Full-suite log or explicit blocker. |
| 24 | `artifacts/earn2trade-50k-readiness/news-events-v1/coverage.json` | new: Actual measured coverage; unchanged 70% gate. |
| 25 | `artifacts/earn2trade-50k-readiness/news-events-v1/checks.log` | new: Ruff/Black/isort/strict MyPy/architecture, TypeScript/build. |
| 26 | `artifacts/earn2trade-50k-readiness/news-events-v1/frontend-tests.log` | new: Frontend test results. |
| 27 | `artifacts/earn2trade-50k-readiness/news-events-v1/browser-checks.json` | new: Actual browser workflow checks or explicit blocker. |
| 28 | `artifacts/earn2trade-50k-readiness/news-events-v1/source-probe.json` | new: Public-source HTTP status/hash/time and limitations; no credentials. |
| 29 | `artifacts/earn2trade-50k-readiness/news-events-v1/calendar-fixtures.json` | new: Bounded official calendar fixture data actually retrieved, with identities; synthetic parser fixtures separately labeled. |

## سلوك مقترح محدد

- أداة واحدة صغيرة للسياق تجمع الأخبار والجداول وحالات مصادرها؛ تستعمل HTTP client وFeedCache القائمين. تبقى signatures وحقول Report/News/EconomicCalendar القديمة كما هي، مع استجابة مستقلة جديدة. لا تعديل models.py أو events.py أو analysis.py أو قواعد المخاطر.
- تحافظ headlines/get على شكلها العام؛ تصحيح استبعاد الكريبتو غير المرتبط لـMES فقط هو التغير المقصود في النتائج القديمة. الترتيب الجديد وأسباب الصلة تظهر في الاستجابة الجديدة؛ لا تغيير سلوك الأدوات الأخرى أو تقليد التحليل السببي.
- جمع عناوين وروابط فقط من المصادر الخمسة الحالية، مع فحص التاريخ والتكرار/HTML والـURL. لا جلب محتوى مقال أو تنفيذ تعليمات داخله، ولا LLM مدفوع أو رابط يرسله المستخدم.
- يُسجل وقت نجاح الجلب الحقيقي ووقت محاولة التحديث، وحالة HTTP/التحليل وعدد العناصر الصالحة وهوية المحتوى. إعادة القراءة من cache لا تجدد المصدر. وقت نشر الخبر ووقت جلبه ووقت التقييم مستقلة.
- تقاويم BLS/FOMC/BEA من روابط رسمية محددة فقط، بجلب محدود الحجم والوقت وإعادة التوجيه المسموح بها. عند 403/فشل parser/تغير الصفحة يظهر المصدر غير متاح. لا محاولة تجاوز رفض BLS. لا ادعاء اكتمال تقويم BLS إن استمر الرفض.
- لا تخمين وقت اجتماع FOMC من تاريخ فقط، ولا تحويل وقت BEA دون معرفة المنطقة الزمنية. تواريخ متعددة الأيام أو TBA تبقى كذلك. تحويل Eastern المصرّح به باستخدام America/New_York واختبار DST. لا ادعاء حدث أُلغي لمجرد اختفائه من الاستجابة.
- كل الجداول تغطيتها جزئية؛ لا complete=True، لا CLEAR تلقائي، لا تعديل سياسة event guard أو اختيار فترات منع دخول نيابة عن المستخدم. وصف المصدر يختلف عن تصنيف خطورة داخلي؛ لا الادعاء بأن الجهة الرسمية تمنح تقييم high/low حين لا تفعل.
- ذاكرة HTTP مؤقتة محدودة لكل خدمة، نجاح 5 دقائق وفشل 30 ثانية، single-flight. هذه ليست verification cache؛ التحقق العددي/الزمني يعاد لكل طلب. لا حفظ قاعدة تقويم دائمة في هذا النطاق؛ حفظ سياق القرار التاريخي مرحلة لاحقة. الأدلة التجريبية تحفظ في الملفات المعتمدة فقط.
- تحديث يدوي، واختيار المستخدم 5 أو15 دقيقة مع إيقاف التحديث التلقائي افتراضيًا، وتوقفه عند إخفاء الصفحة/الخروج. رد متأخر لا يستبدل اختيار أداة أحدث. عداد عمر الأخبار لا يحدّث عمر الأسعار/الملاحظة.
- بيانات قديمة وفشل مصدر وفراغ صحيح وفشل parsing حالات منفصلة. لا مساواة غياب خبر بغياب خطر. يعرض نطاق التاريخ الذي أعاده كل مصدر دون ادعاء تغطية أكبر.
- استجابة جديدة محمية بالمصادقة الحالية ومحدودة لـMES/MNQ، مع trade_permitted=false وexecution_enabled=false. لا قاعدة تنفيذ أو Kafka أو وسيط أو تعديل حساب المستخدم.

## اختبارات القبول والتسليم

1. اختبارات عامة للنواة/HTTP fixtures: صلة MES/MNQ، فشل جزئي/كامل، 403، RSS/HTML غير صالح، حجم زائد، تواريخ ناقصة/مستقبلية/قديمة، timezone/DST، تكرار/تعديل مصدر، نص خبيث وروابط غير مسموحة، cache/تزامن/إلغاء، عدم إعادة وسم المصدر القديم كجديد.
2. API: بلا مصادقة/أداة غير مسموحة، خسارة المصدر، بيانات فارغة، عدم الوصول لأسعار أو تنفيذ أو إعادة تأهيل المخاطر. توافق الواجهات القديمة مع اختبارات الأخبار/الأحداث القائمة.
3. واجهة ومتصفح: عرض المصادر والأخبار/الأحداث منفصلة، فشل الاتصال، إعادة المحاولة، اختيار MES/MNQ، رد متأخر، تحديث 5/15دقيقة بساعة اختبار، إخفاء الصفحة، عمر المصدر دون تحديث السعر، شاشة ضيقة وعدم تنفيذ النص المستورد.
4. اختبارات مركزة ثم المجموعة الكاملة ببوابة70% كما هي؛ Ruff وBlack check وisort check وMyPy الصارم بما يشمل المسار الجديد، وفحص العمارة وTypeScript والبناء. لا جمع الأعداد المتداخلة. أي تعذر يسجل BLOCKED، لا اختلاق نتيجة.
5. خدمات اختبار محلية معزولة فقط وخادمان مؤقتان بقاعدة صناعية عند الحاجة، بعد التقاط الحالة؛ استعادتها لاحقًا. لا تشغيل أثناء مراجعة النطاق الحالية. كل caches وcoverage وpytest وbuild وbrowser profile في /tmp؛ override صريح لمسار HTML. لا تغيير pyproject أوpackage أو.env.
6. baseline قبل التعديل والتجارب يشمل الملفات العامة وhtmlcov/.coverage؛ أرشفة الملفات الخمسة byte-for-byte. حفظ كل الأدلة القديمة، strict source hashes، وfresh public replay لأدلة futures الحالية. إذا ظهر احتياج خارج29مسارًا يوقف التوسع ويعرض النطاق الجديد.
7. حفظ fixtures فعلية محدودة عندما يمكن جلبها، مع المصدر/الوقت/hash؛ fixtures الصناعية معنونة بصورة منفصلة ولا تمثل نجاح جلب حي. تبقى 403 والحدود المعروفة ظاهرة.
8. تقرير الملفات والتجارب والتحذيرات/التخطي والاستعادة وفحص النطاق، ثم توقف للمراجعة. احتمال الاجتياز UNKNOWN. لا شراء، رسائل خارجية، تداول، تغيير سياسات TCP50/20Micro، holdout أو failed soak أو إنشاء مشروعChatGPT. لا إعادة تفعيل heartbeat ضمن هذه الموافقة.

## حدود عملية مهمة

مرحلة سياق معلومات، وليست تقويمًا شاملاً أو مصدر أسعار. BLS المباشر محجوب حاليًا برمز403؛ يمكن عرض رابطه وحالة تعذره دون تعطيل بقية اللوحة. لا ندّعي حل هذا الحجب هندسيًا. أول نجاح مطلوب هو عرض صادق وقابل للفحص لما توفر وما لم يتوفر، قبل مرحلة التحليل المشروط.


---

# Implementation review checkpoint — 2026-10-12

Status: **VERIFIED_STOPPED_FOR_REVIEW**. The authorized 24-path
observation workflow is implemented and tested. Stop for human review; do not
start the next phase. The original checkpoint recorded the broader Goal as **PAUSED**.
The cleanup follow-up returned no Goal from get_goal; no Goal was created, resumed
or marked complete during cleanup.
Heartbeat `alghrest` is paused at this checkpoint to avoid repeated work.

- Full suite: 2645 passed, 0 failures/skips, 562 warnings, 83.926775% coverage;
  unchanged 70% gate. Focused 42 overlap; do not sum them.
- Frontend: 10 observation, 30 cap and 26 risk tests pass; TypeScript/build pass.
- Ruff/Black/isort/strict MyPy/architecture pass; 13 browser checks pass.
- Fresh public futures run/edge/walk and legacy TCP25 PASS/FAIL/CENSORED replays
  pass. All are synthetic mechanics evidence, not trading edge.
- 1493 prior public artifacts, 136 htmlcov files and .coverage preserved;
  three before-file archives match. Final source/containment identities live in
  `artifacts/earn2trade-50k-readiness/observation-workflow-v1/source-manifest.json`.
- Temporary API 18112/UI 15174 and isolated test containers stopped; test ports
  closed. **Restoration verified at 2026-10-12T10:32:35.887437+00:00:** Docker service inactive/socket
  active matches the pre-test state. The user ran the requested stop command;
  independent systemctl/socket checks confirmed it without contacting Docker API.
  The earlier interactive-authentication blocker remains in the receipt history.
- Passing probability UNKNOWN. Existing personal 20 Micro and official TCP50
  BLOCKED gate unchanged. No purchases, external messages, broker mutations,
  trading agents, failed soak, new holdout or deferred ChatGPT project.

Temporary work: `/tmp/alghrest-observation-workflow-wbushkxy`. Exact commands,
harnesses, test results, warning/skip history and limitations are in the approved
`verification.json`. Before editing/testing again, inspect these and preserve the
24-path scope. Any next phase needs a separate exact scope and human review.

The following is the original approved scope and later-stage roadmap, retained
for audit. Its proposal-era wording describes the pre-implementation document;
the checkpoint above is the current status.

# ALGHREST أولًا — مرحلة إدخال المعلومات ومراجعتها وحفظها

2026-10-12. مقترح جاهز للمراجعة؛ لا تعديل للمستودع تم ضمن إعداده.
الجذر: `/home/xsabo/Projects/MY project/alghrest-main`.

هذا المقترح يحل محل مقترح المرحلة الأولى ذي15 ملفًا للمراجعة فقط، ولا يدّعي اعتماد أي منهما. تجهيز مشروع ChatGPT وحزمته المستقلة مؤجل. البيانات يمكن أن تأتي من إدخال المستخدم أو نص من أي مساعد؛ لا اعتماد على مزود ذكاء اصطناعي بعينه.

## ما سيعمل في نهاية هذه المرحلة

في صفحة المساعد القائمة: لصق JSON موحد أو إدخال ملاحظة يدويًا → عرض العقد والفريمات والقيم وأوقات مصادرها → كشف الأخطاء والنواقص → تعديل وحفظ نسخة → مراجعة صريحة لتلك النسخة → إعادة فتحها من السجل. الاختبار يغطي الواجهة وAPI والحفظ وإعادة التشغيل باستخدام بيانات صناعية فقط.

لا تعطي هذه المرحلة توصيات تداول جديدة. إنها أول جزء وظيفي من مسار كامل؛ الأخبار والأحداث والتحليل والحساب تضاف في المراحل التالية.

## النطاق الدقيق — 24 ملفًا

المسارات نسبية إلى الجذر. الفحص الأولي وجد فقط الملفات4 و7 و11 موجودة؛ جميع الوجهات الأخرى جديدة. قبل التنفيذ تعاد مطابقة الحالة. وجود وجهة جديدة مسبقًا يوقف الكتابة عليها لحين تعديل الوجهة.

| # | المسار | الغرض |
|---|---|---|
| 1 | `src/core/advisory/observations.py` | نموذج محدود للمعلومات المعلنة والمراجعة والتحقق الزمني والعددي |
| 2 | `src/connectors/advisory/observation_store.py` | حفظ نسخ append-only في جداول جديدة داخل قاعدة المساعد، باستخدام اتصال التخزين القائم |
| 3 | `src/api/routes/advisory_observations.py` | مسارات تحقق/حفظ/استرجاع/مراجعة محمية بالمصادقة القائمة |
| 4 | `src/api/advisor.py` | توصيل المسارات الجديدة فقط، مع حفظ التغييرات المحلية القائمة |
| 5 | `dashboard/src/components/advisory/ObservationPanel.tsx` | شاشة اللصق والإدخال والمراجعة والتصحيح والتاريخ |
| 6 | `dashboard/src/lib/observations.ts` | أنواع الواجهة، التحقق من استجابات الخادم، وحماية النسخة المعروضة |
| 7 | `dashboard/src/pages/ManualAssistant.tsx` | توصيل الشاشة داخل المساعد الحالي فقط |
| 8 | `tests/unit/test_advisory_observations.py` | اختبارات النموذج، العزل، الحفظ وإعادة الفتح ومسارات API |
| 9 | `dashboard/tests/observations.test.ts` | اختبارات تعارض النسخ والردود المتأخرة والحقول والقدم |
| 10 | `docs/maintenance/advisory-completion-plan.md` | خارطة المراحل ومعايير اكتمالها وسجل الاستئناف |
| 11 | `docs/maintenance/earn2trade-50k-readiness.md` | تسجيل المنجز وحدوده والفجوات المتبقية |
| 12 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/before/advisor.py` | نسخة بايتية قبل التعديل |
| 13 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/before/ManualAssistant.tsx` | نسخة بايتية قبل التعديل |
| 14 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/before/readiness.md` | نسخة بايتية قبل التعديل |
| 15 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/source-manifest.json` | هويات الملفات قبل/بعد وفحص الحفظ |
| 16 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/verification.json` | النتائج والأوامر وحدود التحقق وخطوة الاستئناف |
| 17 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/focused-tests.xml` | نتيجة الاختبارات المركزة |
| 18 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/focused-tests.log` | سجل الاختبارات المركزة |
| 19 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/full-tests.xml` | نتيجة المجموعة الكاملة إن أمكن تشغيلها |
| 20 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/full-tests.log` | السجل الكامل أو سبب التعذر |
| 21 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/coverage.json` | التغطية المقاسة فعلًا؛ لا تختلق إن تعذر التشغيل |
| 22 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/checks.log` | Ruff/Black/isort/MyPy/architecture وبناء الواجهة |
| 23 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/frontend-tests.log` | نتائج اختبارات الواجهة |
| 24 | `artifacts/earn2trade-50k-readiness/observation-workflow-v1/browser-checks.json` | خطوات المتصفح ونتائجها أو BLOCKED مع السبب |

## تفاصيل السلوك

- يدعم MES/MNQ بعقد مؤرخ واحد في الملاحظة؛ عدة فريمات اختيارية5m/15m/1h. المجهول محفوظ كـnull، وليس صفرًا.
- يفصل المصدر المعلن، وقت التقاطه، وقت سعره، وقت الاستيراد، وقت المراجعة. لا تغيير وقت الملاحظة القديمة عند إعادة فتحها أو تحديث الأخبار.
- يفصل الأسعار المنقولة/المؤشرات المطبوعة عن التفسيرات والفرضيات. لا اختراع OHLCV أو ربطها كبديل MarketSnapshot.
- يرفض JSON المكرر، boolean بدل الأعداد، NaN/Infinity، تجاوز الحجم أو الحقول، تعارض العقد والفريم، الأزمنة غير المحددة/غير السليمة أو المستقبلية عند التصريح بها، والأسعار التي تخالف tick. يعرض النواقص وقدم البيانات بوضوح.
- مصدر الصور أو الإدخال اليدوي يبقى user-reported حتى بعد المراجعة. المراجعة تثبت أن مستخدم الواجهة صرح بمراجعة نسخة محددة، لا أنه تحقق مستقلًا من السوق. ادعاء AI أن confirmed=true لا ينشئ مراجعة.
- يُحفظ الأصل والنسخ المعدلة منفصلة، دون تعديل النسخ السابقة. كل مراجعة مرتبطة بهوية النسخة؛ التصحيح يبطل المراجعة السابقة للنسخة الجديدة. تعارض الكتابة من تبويبين يظهر خطأ بدل فقد العمل.
- وقت التقييم يحقن في واجهة النواة لإعادة الاختبار؛ يعاد فحص القدم عند القراءة، وليس cache دائمًا. صلاحية المراجعة لا تجدد صلاحية بيانات السوق.
- النصوص تعرض كنص ولا تنفذ كأوامر أو HTML؛ لا تحميل روابط/ملفات يطلبها النص المستورد. لا مفاتيح أو بيانات حساب مطلوبة.
- لا كتابة تلقائية إلى بيانات حساب المستخدم ولا تحويل الرأي إلى مؤشرات محسوبة أو إذن تداول. تبقى المسارات المالية الحالية كما هي.
- API الجديد يرث المصادقة والقيود المحلية، يستخدم قاعدة المساعد فقط، ولا يصل إلى قاعدة التنفيذ أو وسيط أو Kafka.

## الاختبارات والقبول

1. تجربة كاملة من الواجهة: إدخال، أخطاء واضحة، تصحيح، حفظ، مراجعة، تعديل يبطل المراجعة، إعادة فتح النسخة نفسها وسجلها.
2. اختبار فقد الاتصال، رد متأخر بعد تغيير المدخل، تبويبين يكتبان من نسخة قديمة، السجل بعد إعادة فتح قاعدة البيانات، قاعدة قديمة دون الجداول الجديدة، وعدم لمس سجلاتها السابقة.
3. اختبار الادعاءات المزورة بالجاهزية/المراجعة، أرقام غير سليمة، المصدر/الوقت الناقص، مستقبل/قدم، نص تعليمات خبيث، وطلبات بلا مصادقة.
4. تأكيد عدم تغير واجهات الاستيراد القديمة وقواعد20Micro/حساباتها وسياسةTCP50 وحقول أدلتها. لا تعديل لحساب المخاطر في هذا النطاق.
5. فحوص Ruff/Black check/isort check/MyPy الصارم والعمارة، اختبارات الواجهة وبناؤها، ثم المجموعة الكاملة ببوابة70% كما هي. أعداد المركزة والكاملة لا تجمع، وتذكر التحذيرات والتخطي والفشل.
6. خدمات الاختبار المحلية المعزولة فقط عند الحاجة، وخادما API/واجهة مؤقتان مع قاعدة صناعية ومنافذ منفصلة لا تستبدل خدمات المستخدم. حفظ الحالة السابقة وإعادتها. لا وكلاء أو soak أو نشر.
7. كل coverage/cache/tmp/build تحت دليل /tmp جديد. override صريح للـHTML؛ لا الاعتماد على تعطيله بقيمة فارغة. لا تعديل pyproject.toml أو package.json أو .env. إذا لزم اعتماد ملف آخر يعرض السبب أولًا.
8. baseline للملفات العامة ذات الصلة وhtmlcov/.coverage قبل الاختبارات، وحفظ الأدلة القديمة، ثم مقارنة ما بعد التنفيذ. لا تعرض بيانات خاصة في manifest. تبقى مشكلة htmlcov التاريخية غير قابلة للتصديق بأثر رجعي.
9. whole-file hashes تبقى صارمة، والمصدر المختلف يرفض الأدلة القديمة عند وجوب المطابقة. هذا النطاق لا يعدّل محركات تقييم/مخاطر/futures؛ إذا كشف الفحص أثرًا يتطلب إعادة توليد خارج القائمة يعرض نطاقه قبل الكتابة.
10. أي فحص مطلوب يتعذر يبقى BLOCKED؛ لا تُعلن المرحلة مكتملة التحقق حينها. الأدلة صناعية لا تثبت ميزة تداول. توقف للمراجعة بعد تسليم النتيجة.

## خارطة إكمال ALGHREST بعد هذه المرحلة

1. إدخال ومراجعة وحفظ: هذا النطاق.
2. أخبار وأحداث: وصل المصادر الحالية وتحسين صلتها بـMES/MNQ، وفصل الخبر المنشور عن الحدث المجدول وتحديد تغطية الأخير. لا تحويل نقص التغطية إلى CLEAR.
3. تحليل وخطة: استهلاك المعلومات المراجعة حسب ما تدعمه فعلًا، ودمج الفريمات، وبيان اتفاق/اختلاف الأدلة، وإخراج سيناريوهات مشروطة بأسعار قابلة للتتبع. الخوارزميات المحتاجة لسلسلة شموع لا تُشغّل على بيانات مخترعة.
4. حساب ومخاطر: ربط السيناريو بآخر ملاحظة حساب وتكاليف، وحسم1100/1200 و20Micro/2Mini ونوع drawdown قبل تغيير السياسة. فحص مخاطر المراكز المفتوحة يتطلب بيانات وقفها؛ لا تُفترض.
5. تقرير وتشغيل: تقرير عربي موحد، عمر المصادر، تحديث أخبار5/15دقيقة أثناء الاستخدام، سجل قرارات وتنبيهات واضحة. تحديث الخبر لا يحدّث سعرًا قديمًا.
6. تجربة DEMO مستقبلية: سيناريوهات محفوظة قبل النتائج، بيانات فعلية من المستخدم، قياس الأخطاء والنتائج والتكاليف وعدم اليقين. لا شراء أو وعود اجتياز.

تُحدد ملفات كل مرحلة لاحقة بعد مراجعة نتيجة سابقتها. هذا تقسيم للعمل وليس ادعاء بإمكانية إتمام كل المدخلات الخارجية هندسيًا. إنشاء مشروعChatGPT خارج النطاق ومؤجل.

Goal الحالي PAUSED، ولم تتوفر أداة استئناف؛ لا ادعاء استئناف أو اكتمال. لا ميزانية توكن محددة. سجل كل مرحلة يحفظ المنجز والمتبقي وأمر الاستئناف، ولا يَعِد بتجاوز حدود الاستخدام.
