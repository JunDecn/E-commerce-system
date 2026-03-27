# ── 建置階段 ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# 安裝系統依賴（psycopg2-binary 需要 libpq）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── 執行階段 ──────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# 複製已安裝的套件
COPY --from=builder /install /usr/local

# 複製應用程式原始碼
COPY . .

# 不使用 root 執行（最小權限原則）
RUN adduser --disabled-password --gecos "" appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
