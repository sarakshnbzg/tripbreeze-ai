FROM python:3.13-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Create non-root user and ensure writable dirs for runtime data
RUN useradd --create-home appuser \
    && mkdir -p /app/memory /app/chroma_db \
    && chown -R appuser:appuser /app
USER appuser

VOLUME ["/app/memory", "/app/chroma_db"]

EXPOSE 8501

HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"]

ENTRYPOINT ["uv", "run", "streamlit", "run", "app.py", \
    "--server.port=8501", "--server.address=0.0.0.0"]
