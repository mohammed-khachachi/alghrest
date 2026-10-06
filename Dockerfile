FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Install only the application packages, not research or local development files.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

COPY run_agent.py ./
COPY scripts/ ./scripts/
COPY infra/migrations/ ./infra/migrations/
COPY infra/init/ ./infra/init/

CMD ["python", "run_agent.py"]
