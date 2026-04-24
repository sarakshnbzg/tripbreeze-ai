#!/usr/bin/env bash
set -euo pipefail

rebuild_provider() {
  local provider="$1"
  echo "Building RAG index for provider: ${provider}"
  uv run python scripts/rebuild_rag.py "${provider}"
}

has_openai_provider=0

if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  has_openai_provider=1
fi

if [[ "${REBUILD_RAG_ON_START:-0}" == "1" ]]; then
  echo "Rebuilding OpenAI RAG index before startup..."
  if [[ "${has_openai_provider}" == "1" ]]; then
    rebuild_provider openai
  fi
elif [[ "${REBUILD_RAG_IF_MISSING:-1}" == "1" ]]; then
  if [[ "${has_openai_provider}" == "1" && ! -d "/app/chroma_db/openai" ]]; then
    rebuild_provider openai
  fi
fi

exec uv run uvicorn app:app \
  --host="${API_HOST}" \
  --port="${API_PORT}"
