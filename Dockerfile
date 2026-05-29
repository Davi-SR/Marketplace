# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY main.py agent.py ./
COPY prompts ./prompts
RUN uv sync --locked --no-dev --no-install-project \
    && mkdir -p /app/data /app/runtime /database \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /opt/venv /database

USER appuser

ENV DB_URL=duckdb:////database/ANS.db \
    AIBI_STORAGE_PATH=/app/runtime/aibi_storage.db \
    PROMPTS_DIR=/app/prompts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM nginx:alpine AS frontend

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY Front /usr/share/nginx/html/Front
COPY Assets /usr/share/nginx/html/Assets

EXPOSE 80
