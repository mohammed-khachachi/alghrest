FROM python:3.12-slim

# Install system dependencies required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies (no dev deps, no venv in container)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --without dev,backtesting 2>/dev/null || true

# Copy source code
COPY . .

# Create log directories
RUN mkdir -p logs/compliance ml/checkpoints

# Non-root user for security
RUN useradd -m -u 1000 alghrest && chown -R alghrest:alghrest /app
USER alghrest

# Default: run the API server
CMD ["python", "-m", "api.main"]
