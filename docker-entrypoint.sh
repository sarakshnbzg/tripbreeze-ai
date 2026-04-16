#!/usr/bin/env bash
set -euo pipefail

rebuild_provider() {
  local provider="$1"
  echo "Building RAG index for provider: ${provider}"
  uv run python scripts/rebuild_rag.py "${provider}"
}

has_openai_provider=0
has_google_provider=0

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  has_openai_provider=1
fi

if [[ -n "${GOOGLE_API_KEY:-}" || -n "${GEMINI_API_KEY:-}" ]]; then
  has_google_provider=1
fi

if [[ "${REBUILD_RAG_ON_START:-0}" == "1" ]]; then
  echo "Rebuilding configured RAG indexes before startup..."
  if [[ "${has_openai_provider}" == "1" ]]; then
    rebuild_provider openai
  fi
  if [[ "${has_google_provider}" == "1" ]]; then
    rebuild_provider google
  fi
elif [[ "${REBUILD_RAG_IF_MISSING:-1}" == "1" ]]; then
  if [[ "${has_openai_provider}" == "1" && ! -d "/app/chroma_db/openai" ]]; then
    rebuild_provider openai
  fi
  if [[ "${has_google_provider}" == "1" && ! -d "/app/chroma_db/google" ]]; then
    rebuild_provider google
  fi
fi

exec uv run streamlit run app.py \
  --server.port="${STREAMLIT_PORT}" \
  --server.address="${STREAMLIT_HOST}"
