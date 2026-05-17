# ALGHREST Kill Switch Testing Guide  
# دليل اختبار نظام الإيقاف الطارئ

## 🎯 الهدف من الاختبارات

هذا الدليل يقدم سيناريوهات شاملة لاختبار نظام Kill Switch في ALGHREST تحت أقسى ظروف السوق المحتملة. الهدف هو ضمان:

- **سرعة الاستجابة** تحت الضغط الشديد
- **موثوقية إلغاء الأوامر** عبر جميع البورصات
- **التصعيد التدريجي** حسب مستوى الخطر
- **الامتثال الشامل** عبر جميع وكلاء النظام
- **التعافي السليم** بعد انتهاء الأزمة

## 📋 السيناريوهات المتاحة

### 1. Flash Crash (الانهيار السريع) 🌪️
**الوصف:** محاكاة انهيار سريع بنسبة 15% خلال 5 دقائق  
**الهدف:** قياس سرعة تفعيل Kill Switch في الحالات الطارئة  
**المعيار:** يجب التفعيل خلال أقل من 30 ثانية

```bash
python scripts/run_kill_switch_stress_test.py --scenario flash_crash
```

**متطلبات النجاح:**
- ✅ تفعيل Kill Switch عند الوصول لحد 5% انخفاض يومي
- ✅ إلغاء جميع الأوامر المفتوحة خلال 30 ثانية
- ✅ إيقاف جميع الاستراتيجيات فوراً

### 2. Black Swan (الحدث الأسود) 🦢
**الوصف:** انهيار شديد بنسبة 25% خلال 30 دقيقة  
**الهدف:** اختبار نظام التصعيد التدريجي  
**المعيار:** تفعيل جميع مستويات التنبيه

```bash
python scripts/run_kill_switch_stress_test.py --scenario black_swan
```

**التدرج المتوقع:**
1. **3% انخفاض:** تنبيه للـ CIO
2. **5% انخفاض:** إيقاف الاستراتيجيات الخاسرة
3. **7% انخفاض:** إيقاف جميع الاستراتيجيات
4. **12% انخفاض:** Kill Switch كامل

### 3. Systematic Failure (الفشل النظامي) ⚠️
**الوصف:** انهيار شامل بنسبة 35% خلال ساعة  
**الهدف:** اختبار الأداء تحت الضغط المستمر  
**المعيار:** حماية 65% من رأس المال على الأقل

```bash
python scripts/run_kill_switch_stress_test.py --scenario systematic_failure
```

### 4. Order Cancellation (إلغاء الأوامر) 📊
**الوصف:** اختبار إلغاء 1000+ أمر عبر بورصات متعددة  
**الهدف:** قياس كفاءة الإلغاء تحت الضغط  
**المعيار:** أكثر من 100 أمر/ثانية

```bash
python scripts/run_kill_switch_stress_test.py --scenario order_cancellation
```

### 5. Escalation Levels (مستويات التصعيد) 📈
**الوصف:** التحقق من عمل جميع مستويات التصعيد  
**الهدف:** ضمان التدرج السليم في الاستجابة  

```bash
python scripts/run_kill_switch_stress_test.py --scenario escalation_levels
```

### 6. System Compliance (امتثال النظام) 🔒
**الوصف:** التأكد من احترام جميع الوكلاء لحالة Kill Switch  
**الهدف:** ضمان الإيقاف الشامل  

```bash
python scripts/run_kill_switch_stress_test.py --scenario system_compliance
```

### 7. Recovery Procedures (إجراءات التعافي) 🔄
**الوصف:** اختبار إعادة تشغيل النظام بعد الأزمة  
**الهدف:** ضمان العودة السليمة للعمل  

```bash
python scripts/run_kill_switch_stress_test.py --scenario recovery_procedures
```

### 8. Performance Benchmark (قياس الأداء) ⚡
**الوصف:** قياس سرعة الاستجابة تحت حمل عالي  
**الهدف:** تحديد حدود الأداء  

```bash
python scripts/run_kill_switch_stress_test.py --scenario performance_benchmark
```

## 🚀 تشغيل جميع الاختبارات

```bash
# تشغيل جميع السيناريوهات
python scripts/run_kill_switch_stress_test.py --scenario all

# تشغيل مع حفظ التقرير
python scripts/run_kill_switch_stress_test.py --scenario all --output kill_switch_report.json

# تشغيل مع تفاصيل أكثر
python scripts/run_kill_switch_stress_test.py --scenario all --verbose
```

## 📊 تفسير النتائج

### مؤشرات النجاح الأساسية:

| المؤشر | الهدف | الحد الأدنى المقبول |
|--------|-------|------------------|
| سرعة التفعيل | < 30 ثانية | < 60 ثانية |
| معدل إلغاء الأوامر | > 100 أمر/ثانية | > 50 أمر/ثانية |
| دقة التصعيد | 100% | 90% |
| امتثال الوكلاء | 100% | 95% |
| وقت التعافي | < 10 ثوانِ | < 30 ثانية |

### نموذج تقرير ناجح:

```json
{
  "scenario": "flash_crash",
  "status": "PASSED",
  "response_time_seconds": 12.5,
  "trigger_drawdown": 0.05,
  "positions_closed": 15,
  "orders_cancelled": 247,
  "cancellation_rate_per_second": 156.2
}
```

## ⚙️ إعداد البيئة للاختبار

### 1. متطلبات التشغيل

```bash
# تفعيل البيئة الافتراضية
poetry shell

# تثبيت التبعيات المطلوبة
poetry install --with testing

# تشغيل البنية التحتية (Docker)
docker compose up -d kafka redis timescaledb
```

### 2. إعداد متغيرات البيئة

```bash
export ENVIRONMENT=development
export ANTHROPIC_API_KEY=your_test_key
export REDIS_URL=redis://localhost:6379
export KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

### 3. التحقق من الخدمات

```bash
# التأكد من تشغيل Kafka
docker compose logs kafka | grep "started"

# التأكد من Redis
redis-cli ping

# التأكد من TimescaleDB  
psql -h localhost -U alghrest_user -d alghrest_test -c "SELECT 1;"
```

## 🔍 استكشاف الأخطاء

### مشاكل شائعة وحلولها:

#### 1. فشل الاتصال بـ Kafka
```bash
# التحقق من حالة Kafka
docker compose ps kafka

# إعادة تشغيل Kafka
docker compose restart kafka
```

#### 2. بطء في إلغاء الأوامر
```bash
# التحقق من اتصال شبكة البورصات
ping api.binance.com
ping api.coinbase.com
ping api.kraken.com
```

#### 3. فشل تفعيل Kill Switch
```bash
# التحقق من Redis
redis-cli get "alghrest:kill_switch:active"

# مسح الحالة السابقة إذا لزم الأمر
redis-cli del "alghrest:kill_switch:active"
```

## 🎯 أفضل الممارسات

### قبل الاختبار:
1. ✅ تأكد من تشغيل جميع الخدمات
2. ✅ احفظ نسخة احتياطية من البيانات المهمة
3. ✅ أعلم الفريق بوقت الاختبار
4. ✅ راجع حدود الـ API للبورصات

### أثناء الاختبار:
1. 📊 راقب استهلاك الموارد
2. 📝 سجل أي سلوك غير متوقع
3. ⏱️ اقيس الأوقات بدقة
4. 🔍 تحقق من السجلات (logs)

### بعد الاختبار:
1. 📋 راجع التقرير الكامل
2. 🔄 اختبر إعادة التشغيل
3. 📈 وثق أي تحسينات مطلوبة
4. 🏆 احتفل بالنجاح!

## 🚨 تحذيرات مهمة

⚠️ **لا تشغل هذه الاختبارات في بيئة الإنتاج!**

⚠️ **تأكد من إعداد `ENVIRONMENT=development` أو `paper_trading`**

⚠️ **لا تستخدم مفاتيح API حقيقية أثناء الاختبار**

⚠️ **راجع حدود استهلاك API للبورصات**

## 📞 الدعم والمساعدة

في حالة مواجهة مشاكل:

1. **راجع السجلات:** `docker compose logs -f`
2. **تحقق من الموارد:** `docker stats`
3. **أعد تشغيل الخدمات:** `docker compose restart`
4. **اتصل بالفريق الفني** للحصول على مساعدة

---

**📝 ملاحظة:** هذا الدليل مخصص لاختبار نظام Kill Switch في بيئة آمنة. الهدف هو ضمان عمل النظام بشكل مثالي عند الحاجة إليه في ظروف السوق الحقيقية.