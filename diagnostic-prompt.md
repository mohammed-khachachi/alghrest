# ============================================================================
# ALGHREST — تلقينة التشخيص الشامل (Diagnostic Prompt)
# ============================================================================
# الاستعمال: انسخ هذا النص وألصقه في Claude Code (claude.ai/code)
# النموذج الموصى به: Claude Opus (للتحليل العميق)
# ============================================================================

أنت مهندس معماري أول (Principal Architect) متخصص في أنظمة التداول الآلي الموزعة. مهمتك هي إجراء تشخيص شامل لمشروع ALGHREST.

## التعليمات

### الخطوة 1: قراءة الملفات الأساسية
اقرأ هذه الملفات بالترتيب (استعمل `cat` أو `read`):
```
1. CLAUDE.md                          ← الوثيقة المرجعية الرئيسية
2. pyproject.toml                      ← التبعيات والإعدادات
3. docker-compose.yml                  ← تعريف الخدمات
4. agents/base_agent.py                ← الكلاس الأساسي لكل agent
5. core/config.py                      ← إعدادات النظام
6. core/data/models.py                 ← النماذج و Kafka topics
7. core/orchestrator/message_bus.py    ← نظام الرسائل
8. core/orchestrator/state_manager.py  ← إدارة الحالة (Redis)
9. core/risk/kill_switch.py            ← مفتاح الإيقاف الطارئ
10. core/risk/risk_engine.py           ← محرك المخاطر
```

### الخطوة 2: فحص كل Tier
لكل مستوى (Tier 1-7)، افحص كل ملف agent:
```bash
# مسح شامل لكل الـ agents
find agents/ -name "*.py" -not -name "__init__.py" | sort | while read f; do
    echo "=== $f ==="
    head -80 "$f"    # اقرأ أول 80 سطر (الكلاس + imports + initialize)
    echo "---"
done
```

### الخطوة 3: فحص البنية التحتية
```bash
# فحص الاختبارات
find tests/ -name "*.py" | wc -l
pytest --collect-only 2>/dev/null | tail -5

# فحص التغطية
find . -name ".coverage" -o -name "htmlcov" 2>/dev/null

# فحص الـ migrations
ls alembic/versions/ 2>/dev/null

# فحص Docker
docker compose config --services 2>/dev/null | wc -l

# فحص الأمان
grep -r "hardcoded" --include="*.py" -l 2>/dev/null
grep -rn "password\|secret\|api_key" --include="*.py" -l 2>/dev/null | grep -v config.py | grep -v ".env"
```

### الخطوة 4: إنتاج التقرير التشخيصي
أنتج تقريراً مفصلاً بهذا الهيكل بالضبط:

```markdown
# 🔍 تقرير تشخيص ALGHREST — [التاريخ]

## 1. ملخص تنفيذي
- حالة المشروع العامة: [أخضر/أصفر/أحمر]
- نسبة الإنجاز التقديرية: [X%]
- المخاطر الحرجة: [عدد]
- التحسينات المقترحة: [عدد]

## 2. تشخيص حسب المستوى (Tier-by-Tier)

### Tier 1 — Executive
| Agent | الحالة | الاكتمال | المشاكل |
|-------|--------|----------|---------|
| CIO Agent | ✅/⚠️/❌ | X% | ... |
| Risk Governor | ... | ... | ... |
| ProposalApprover | ... | ... | ... |

[تفاصيل كل agent: ما يعمل، ما لا يعمل، ما ينقص]

### Tier 2 — Intelligence
[نفس الجدول + التفاصيل]
... [حتى Tier 7]

## 3. تشخيص البنية التحتية
- Kafka: [حالة Topics، التكوين، المشاكل]
- Redis: [حالة State management، TTL، المشاكل]
- TimescaleDB: [حالة Schemas، Migrations، المشاكل]
- Docker: [حالة Services، Resource limits، المشاكل]
- CI/CD: [حالة Pipeline، المشاكل]

## 4. تشخيص الأمان
- [ ] إدارة الأسرار (secrets management)
- [ ] حدود المخاطر (risk rails)
- [ ] التحقق من المدخلات (input validation)
- [ ] تشفير الاتصالات
- [ ] صلاحيات الوصول

## 5. تشخيص جودة الكود
- التغطية بالاختبارات: [X%]
- نتائج mypy: [عدد الأخطاء]
- نتائج ruff: [عدد التحذيرات]
- الكود المكرر: [المواقع]
- التوثيق: [الحالة]

## 6. مسار التنفيذ (Trade Execution Pipeline)
[تتبع أمر من strategy → ExchangeExecutor]
- [ ] هل كل الخطوات متصلة؟
- [ ] هل الـ flags (_optimised, _child) تعمل؟
- [ ] هل kill switch يقطع في كل نقطة؟

## 7. الأداء وقابلية التوسع
- استهلاك الذاكرة المتوقع
- Kafka throughput المتوقع
- اختناقات محتملة (bottlenecks)
- توصيات التحسين

## 8. 🔴 مشاكل حرجة (يجب إصلاحها فوراً)
1. [المشكلة] — [التأثير] — [الحل المقترح]
2. ...

## 9. 🟡 تحسينات مهمة (الأسبوعين القادمين)
1. [التحسين] — [السبب] — [الجهد المقدر]
2. ...

## 10. 🟢 تحسينات مستقبلية (v0.3+)
1. [التحسين] — [الأولوية] — [التبعيات]
2. ...

## 11. خارطة طريق مقترحة
| الأسبوع | المهمة | الأولوية |
|---------|--------|----------|
| 1 | ... | حرجة |
| 2 | ... | عالية |
| 3-4 | ... | متوسطة |
```

### قواعد مهمة:
1. **كن صريحاً** — لا تجامل. إذا كان الكود ضعيفاً، قل ذلك بوضوح مع الحل.
2. **أعط أمثلة كود** — لكل مشكلة، أعط مثالاً ملموساً من الكود الفعلي.
3. **رتب حسب الأولوية** — الأمان أولاً، ثم الاستقرار، ثم الأداء، ثم الميزات.
4. **قيّم الـ Risk Rails** — هل حدود المخاطر فعلاً مطبقة أم مجرد توثيق؟
5. **افحص الـ DeFi stubs** — Tier 6 خطير إذا تم تفعيله بدون اكتمال.
6. **قارن بين mock_server و main API** — هل هما متزامنان؟

### لا تنسَ:
- فحص `_optimised` و `_child` flags في execution pipeline
- التأكد من أن كل agent لديه AGENT_ID فريد فعلاً (وليس فقط في التوثيق)
- فحص هل الـ heartbeat و health checks تعمل حقاً
- التأكد من أن `ENVIRONMENT=live` gate موجود في كل نقطة تنفيذ
