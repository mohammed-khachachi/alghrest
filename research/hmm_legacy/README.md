# HMM Market Regime Detection for Quantitative Trading

مشروع بحثي وتطبيقي يشرح كيف يمكن استعمال نماذج ماركوف المخفية
Hidden Markov Models لاكتشاف أنظمة السوق في التداول الكمي، مع كود Python
منظم وتقرير عربي احترافي.

## الهدف من المشروع

الهدف هو بناء نموذج تعليمي قابل للتشغيل يقوم بما يلي:

- تحميل بيانات مالية يومية من Yahoo Finance عبر `yfinance`.
- حساب خصائص مالية مثل العائد اليومي، التقلب، وميل المتوسطات المتحركة.
- تدريب نموذج `GaussianHMM` من مكتبة `hmmlearn`.
- استخراج الحالات المخفية التي تمثل أنظمة سوقية محتملة.
- تفسير الحالات إحصائيا واقتصاديا.
- بناء Backtest بسيط لاستراتيجية long-only تعتمد على الحالات.
- حفظ النتائج والرسوم داخل `outputs/`.

هذا المشروع تعليمي وبحثي فقط، وليس نصيحة مالية أو توصية تداول.

## فكرة HMM في التداول الكمي

السوق لا يعلن حالته الحقيقية مباشرة. نحن نرى السعر، العائد، الحجم، والتقلب،
لكننا لا نرى بشكل مباشر هل السوق في حالة صعود، هبوط، ضغط، أو استقرار.
نموذج HMM يفصل بين:

- **Hidden States:** حالات السوق غير المرئية مباشرة.
- **Observations:** البيانات التي نلاحظها يوميا.
- **Transition Probabilities:** احتمالات انتقال السوق من حالة إلى أخرى.
- **Emission Probabilities:** احتمال ظهور عائد أو تقلب معين داخل حالة سوقية معينة.

بهذا يصبح HMM أداة مناسبة لاكتشاف Market Regimes بدل الاعتماد على قواعد يدوية فقط.

## بنية المشروع

```text
project/
├── README.md
├── requirements.txt
├── main.py
├── references/
│   └── README.md
├── src/
│   ├── file_finder.py
│   ├── data_loader.py
│   ├── features.py
│   ├── hmm_model.py
│   ├── visualization.py
│   └── backtest.py
├── notebooks/
│   └── hmm_market_regime_detection.ipynb
├── reports/
│   └── HMM_Trading_Report.md
└── outputs/
    ├── figures/
    └── results/
```

## طريقة التثبيت

من داخل مجلد `project/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## طريقة التشغيل

```powershell
Set-Location project
python main.py
```

السكربت سيقوم تلقائيا بالخطوات التالية:

1. التحقق اختياريا من وجود ملف Stanford Hidden Markov Models PDF داخل `references/` دون افتراض وجوده.
2. تحميل بيانات `^GSPC` من Yahoo Finance.
3. حساب الخصائص المالية.
4. تدريب نموذج HMM بثلاث حالات.
5. تفسير الحالات.
6. تشغيل backtest تعليمي.
7. حفظ النتائج داخل `outputs/results/` والرسوم داخل `outputs/figures/`.

إذا لم يجد السكربت ملف Stanford PDF، سيطبع تحذيرا واضحا ثم يكمل المشروع
بالاعتماد على المفاهيم القياسية العامة لنماذج HMM.

## ملاحظة حول ملف Stanford

لم يتم العثور حالياً على ملف Stanford Hidden Markov Models PDF داخل المشروع.
لذلك يعتمد التقرير الحالي على المفاهيم النظرية القياسية لنماذج HMM. إذا أضيف
الملف لاحقاً داخل project/references/، يمكن إعادة تشغيل البحث وتحديث التقرير
بناءً عليه.

لا يحتوي التقرير الحالي على أي قسم يحلل مصدراً غير موجود، ولا يدعي أنه
مستخرج من مصدر خارجي غير متوفر داخل المشروع.

## طريقة وضع ملف Stanford إذا توفر لاحقا

ضع الملف داخل `project/references/`، مثلا:

```text
project/references/Stanford_Hidden_Markov_Models.pdf
```

الامتدادات التي يبحث عنها السكربت:

```text
.pdf, .ppt, .pptx, .doc, .docx, .md, .txt, .ipynb
```

## طريقة البحث عن الملف

يمكن تشغيل البحث فقط:

```powershell
Set-Location project
python src\file_finder.py
```

يقوم `file_finder.py` بالبحث داخل المسار الاختياري `project/references/`.
يفحص أسماء الملفات، ويبحث داخل محتوى الملفات النصية والـ notebooks إن أمكن،
ثم يرتب النتائج حسب درجة التشابه مع كلمات مثل:

```text
Stanford, Hidden Markov Models, HMM, Markov, CS228, CS229, CS221, lecture, notes, slides
```

## ماذا يحدث إذا وجد الملف لاحقا؟

إذا وجد السكربت ملفا يحتوي على Stanford وHMM، يطبعه كأفضل مصدر مرشح.
في النسخة البحثية يمكن استعمال هذا الملف لتحديث مقدمة التقرير وإضافة ملخص
لأهم المفاهيم النظرية الموجودة فيه، مع إعادة الصياغة وعدم النسخ الحرفي.
لا يقوم `file_finder.py` بتعديل التقرير تلقائيا.

## ماذا يحدث إذا لم يوجد الملف؟

إذا لم يوجد ملف Stanford، يستمر المشروع بشكل طبيعي. التقرير الحالي يتضمن
تنبيها واضحا بأنه يعتمد على المفاهيم النظرية القياسية لنماذج HMM كما تدرس
في المقررات الجامعية، مع ربطها بتطبيقات التداول الكمي.

الرسالة المتوقعة عند غياب الملف:

```text
No Stanford Hidden Markov Models PDF was found. The project will continue using standard HMM theory.
```

## مثال على النتائج

بعد التشغيل، تظهر ملفات مثل:

```text
outputs/results/state_summary.csv
outputs/results/hmm_regimes.csv
outputs/results/backtest_metrics.csv
outputs/figures/hmm_market_regimes.png
outputs/figures/hmm_backtest_equity.png
```

جدول الحالات يحتوي على:

- رقم الحالة.
- عدد الأيام داخل الحالة.
- متوسط العائد.
- الانحراف المعياري.
- متوسط التقلب.
- تفسير الحالة.

## حدود النموذج

- HMM لا يتنبأ بالسعر بشكل مضمون.
- اختيار عدد الحالات `n_components` يؤثر بقوة في النتيجة.
- النموذج حساس للخصائص المختارة وللفترة الزمنية.
- الأسواق قد تتغير بطريقة لا تشبه الماضي.
- الباكتيست التعليمي لا يكفي لاعتماد استراتيجية حقيقية.
- يجب إضافة إدارة مخاطر صارمة قبل أي استخدام عملي.

## أفكار مستقبلية للتطوير

- اختبار عدد حالات مختلف واختيار الأفضل عبر AIC/BIC.
- فصل train/test لتقييم Out-of-Sample.
- إضافة خصائص مثل VIX، العوائد القطاعية، أو أسعار الفائدة.
- تجربة Markov-Switching GARCH.
- إضافة walk-forward validation.
- مقارنة HMM مع نماذج مثل KMeans، Gaussian Mixture، وLSTM.
- بناء dashboard تفاعلي لعرض الحالات.

## تحذير مالي

هذا المشروع لأغراض تعليمية وبحثية فقط. لا يمثل توصية استثمارية ولا ينبغي
استعماله وحده لاتخاذ قرارات تداول حقيقية. أي تطبيق عملي يحتاج إلى تحقق
إحصائي صارم، إدارة مخاطر، واختبارات خارج العينة.
