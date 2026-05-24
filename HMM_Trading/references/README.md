# References — المراجع

## Stanford Hidden Markov Models PDF

Drop the Stanford HMM PDF into this folder and `src/references/finder.py` will discover it automatically the next time `python main.py` runs.

ضع ملف Stanford HMM PDF هنا وسيُكتشف تلقائياً عند تشغيل المشروع.

**Recognised filenames / الأسماء المتوقعة للملف:**

- `Stanford_Hidden_Markov_Models.pdf`
- `cs229-hmm.pdf`
- `cs228-hmm.pdf`
- Any PDF whose name contains: `stanford`, `hidden`, `markov`, `hmm`, `cs228`, `cs229`, `cs221`

The finder ranks every PDF under the repo (skipping `.venv`, `node_modules`, `outputs`, `__pycache__`, etc.) and selects the highest-scoring candidate. Files inside a folder named `references` receive a small bonus; generated artefacts such as `*trading_report*` or `*backtest*` are penalised.

**Official sources / المصادر الرسمية:**

- Stanford CS229: https://cs229.stanford.edu/
- Stanford CS228: https://cs228.stanford.edu/
- Direct: https://cs229.stanford.edu/section/cs229-hmm.pdf

## Fallback / الاحتياط

If no matching PDF is found, the pipeline keeps running and falls back to the embedded summary at:

`outputs/extracted_text/stanford_hmm_extracted.txt`

إذا لم يكن الملف موجوداً، سيستخدم المشروع الملخص النظري المُدمج الموجود في:
`outputs/extracted_text/stanford_hmm_extracted.txt`

## How extraction works

`src/references/extractor.py::extract_pdf_text` reads the located PDF, normalises its text, and caches the extracted content under `outputs/extracted_text/` so subsequent runs do not re-parse the PDF.
