FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    STREAMLIT_HOST=0.0.0.0 \
    STREAMLIT_PORT=8501 \
    API_HOST=0.0.0.0 \
    API_PORT=8100

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/chroma_db \
    && chown -R appuser:appuser /app \
    && chmod +x /app/docker-entrypoint.sh

USER appuser

VOLUME ["/app/chroma_db"]

EXPOSE 8501 8100

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD sh -c 'curl --fail "http://127.0.0.1:${STREAMLIT_PORT}/_stcore/health" || exit 1'

ENTRYPOINT ["/app/docker-entrypoint.sh"]
