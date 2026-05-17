# Dockerfile - نهج pip مباشر
FROM python:3.12-slim

WORKDIR /app

# 1. نسخ المتطلبات الأساسية
COPY requirements.txt ./

# 2. تثبيت المتطلبات بـ pip مباشرة
RUN pip install --no-cache-dir -r requirements.txt

# 3. نسخ الكود
COPY . .

# 4. الأمر الافتراضي
CMD ["python", "run_agent.py"]
