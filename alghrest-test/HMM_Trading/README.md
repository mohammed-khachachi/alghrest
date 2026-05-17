# HMM Market Regime Detection
## نماذج ماركوف المخفية لاكتشاف أنظمة السوق

> **مشروع بحثي** في التداول الكمي باستخدام Hidden Markov Models  
> المصدر النظري: Stanford HMM Framework (CS229 / CS228)  
> ⚠ لأغراض تعليمية وبحثية فقط — ليس نصيحة مالية

---

## الهدف

اكتشاف **الأنظمة السوقية المخفية** (Market Regimes) تلقائياً من بيانات الأسعار والأحجام، باستخدام نماذج ماركوف المخفية (HMM)، وبناء استراتيجية تداول تعليمية مبنية على هذه الأنظمة.

## الفكرة

الأسواق تعيش حالات مخفية لا تُرى مباشرةً: صعود هادئ، هبوط متسارع، تذبذب جانبي، أزمة حادة.  
HMM يكتشف هذه الحالات تلقائياً (Baum-Welch)، ثم يُرمّزها تاريخياً (Viterbi).

## المرجع النظري Stanford

| الملف | المسار | الملاحظة |
|:---|:---|:---|
| Stanford HMM Framework | CS229/CS228 (مُدمج في المشروع) | مواد ستانفورد لم تُحمَّل كـ PDF — المشروع يعتمد على المعرفة المُضمَّنة |
| الملخص المُستخرج | `outputs/extracted_text/stanford_hmm_extracted.txt` | يُنشأ تلقائياً عند التشغيل |

> إذا كان لديك ملف Stanford HMM PDF، ضعه في `references/` وسيتعرف عليه النموذج تلقائياً.

---

## بنية المشروع

```
project/
├── main.py                          ← نقطة التشغيل الرئيسية
├── requirements.txt                 ← المكتبات المطلوبة
├── README.md                        ← هذا الملف
│
├── references/
│   └── README.md                    ← معلومات المراجع
│
├── src/
│   ├── __init__.py
│   ├── file_finder.py               ← البحث عن Stanford PDF
│   ├── pdf_reader.py                ← استخراج النص من PDF
│   ├── data_loader.py               ← تحميل بيانات السوق (yfinance)
│   ├── features.py                  ← بناء مصفوفة الخصائص (Observations)
│   ├── hmm_model.py                 ← تدريب GaussianHMM (Baum-Welch)
│   ├── regime_interpreter.py        ← تفسير الأنظمة المكتشفة
│   ├── backtest.py                  ← باكتيست تعليمي
│   ├── visualization.py             ← رسم المخرجات
│   └── utils.py                     ← أدوات مشتركة
│
├── reports/
│   └── HMM_Trading_Report.md        ← التقرير الأكاديمي العربي
│
├── notebooks/
│   └── hmm_market_regime_detection.ipynb  ← Jupyter Notebook تفاعلي
│
├── outputs/
│   ├── figures/                     ← الرسوم البيانية
│   ├── results/                     ← CSV وJSON
│   └── extracted_text/              ← النص المستخرج من PDF
│
└── tests/
    ├── test_features.py
    ├── test_hmm_model.py
    └── test_backtest.py
```

---

## التثبيت

```bash
# 1. إنشاء بيئة افتراضية (اختياري لكن مُوصى به)
python -m venv .venv
source .venv/bin/activate       # Linux / Mac
.venv\Scripts\activate          # Windows

# 2. تثبيت المكتبات
pip install -r requirements.txt
```

## التشغيل

```bash
# تشغيل المشروع كاملاً
cd project/
python main.py

# البحث عن ملف Stanford PDF فقط
python src/file_finder.py

# استخراج النص من PDF
python src/pdf_reader.py
```

## استخراج النص من PDF

إذا كان لديك ملف Stanford HMM PDF:
```bash
# ضع الملف في references/
cp Stanford_HMM.pdf references/

# ثم شغّل
python main.py  # سيجده تلقائياً
# أو
python src/pdf_reader.py
```

## تشغيل الاختبارات

```bash
pip install pytest
cd project/
pytest tests/ -v
```

---

## مخرجات المشروع

| الملف | الوصف |
|:---|:---|
| `outputs/figures/01_price_regimes.png` | السعر مع تلوين الأنظمة |
| `outputs/figures/02_equity_curves.png` | أداء الاستراتيجية مقابل Buy&Hold |
| `outputs/figures/03_regime_distribution.png` | توزيع الوقت بين الأنظمة |
| `outputs/figures/04_transition_matrix.png` | مصفوفة انتقال الأنظمة |
| `outputs/results/hmm_regimes.csv` | الأنظمة اليومية |
| `outputs/results/state_summary.csv` | إحصاءات كل نظام |
| `outputs/results/backtest_metrics.csv` | مقاييس الأداء |
| `outputs/results/transition_matrix.csv` | مصفوفة الانتقال |
| `outputs/extracted_text/stanford_hmm_extracted.txt` | ملخص نظري Stanford |
| `reports/HMM_Trading_Report.md` | التقرير الأكاديمي العربي الكامل |

---

## حدود النموذج

- ✗ الباكتيست داخل العيّنة (In-Sample) — نتائج متحيزة نحو التفاؤل
- ✗ لا Walk-Forward Analysis
- ✗ لا تكاليف واقعية (Spread / Slippage)
- ✗ N=3 تحكمي — يمكن تحسينه بـ BIC/AIC
- ✗ لا Short بيع في النسخة الأولى

---

## ⚠ تحذير

هذا المشروع **لأغراض تعليمية وبحثية فقط**.  
لا يُمثّل نصيحة مالية أو استثمارية.  
التداول في الأسواق المالية ينطوي على مخاطر خسارة كبيرة.

---

## أفكار التطوير

- Walk-Forward Validation (Out-of-Sample)
- اختيار N بـ BIC/AIC
- Regime-Aware Portfolio Optimization
- دمج أصول متعددة (Multi-Asset)
- Online Baum-Welch (تحديث تدريجي)
- Regime Switching GARCH
