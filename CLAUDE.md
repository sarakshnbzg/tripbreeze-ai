# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Commands

### Backend (Python 3.13 + uv)

```bash
uv sync                                          # install dependencies
uv run pytest -q                                 # all tests
uv run pytest tests/test_trip_intake.py -q       # single test file
uv run python scripts/rebuild_rag.py             # rebuild ChromaDB after knowledge_base/ changes
uv run python scripts/evaluate_rag.py --provider openai  # RAG eval
uv run python scripts/sync_reference_data.py     # sync Postgres reference data
RUN_LLM_JUDGE_GOLDENS=1 uv run pytest tests/test_golden_prompts.py -k finaliser  # LLM-judged golden tests
```

### Frontend (Next.js 15 + Node)

```bash
npm run dev --prefix frontend          # dev server on :3000
npm run test --prefix frontend         # typecheck + vitest
npm run test:e2e --prefix frontend     # Playwright e2e
npm run lint --prefix frontend
```

### Full stack

```bash
docker compose up --build
```

## Architecture

Dependency direction: `application` → `domain` → `infrastructure`. `presentation` depends on `application` only.

- **`application/`** — LangGraph wiring (`graph.py`) + `TravelState` schema (`state.py`). Only layer touching LangGraph internals.
- **`domain/nodes/`** — pipeline nodes (intake, research, budget, review, finaliser, memory). Each reads/writes `TravelState` fields per `AGENTS.md`.
- **`domain/agents/`** — tool-callable flight/hotel search wrappers for research orchestrator ReAct loop.
- **`infrastructure/`** — all external I/O: LLM factory, SerpAPI/weather/geocoding clients, ChromaDB+BM25 hybrid RAG, Postgres, SSE streaming.
- **`presentation/`** — FastAPI split into route modules (`api_routes_auth`, `api_routes_planning`, `api_routes_itinerary`, `api_routes_system`) + SSE via `api_sse.py`.
- **`knowledge_base/`** — Markdown source for RAG. Rebuild index after changes.

## Key Patterns

**Settings** — Config comes from `settings.py` (pydantic-settings, typed). Nodes and agents should read settings from there rather than from environment variables directly.

**LLM calls** — Always use `invoke_with_retry` / `stream_with_retry` from `infrastructure/llms/model_factory.py`. Handle backoff retry, emit `llm.call_completed` / `llm.stream_completed` structured logs with token counts + cost.

**Logging** — Use `log_event(logger, "event.name", **fields)` for high-signal events. Emits structured JSON. Names follow `layer.action_verb` (e.g. `workflow.intake_completed`, `llm.call_failed`).

**HITL pause** — `feedback_router` calls LangGraph `interrupt()`. State persists in Postgres (falls back to MemorySaver when `DATABASE_URL` absent). Restart-safe review needs Postgres checkpointer.

**Multi-city** — When `trip_legs` set, all nodes operate on `*_by_leg` variants. Single-city/multi-city paths diverge per node; `AGENTS.md` documents both.

**RAG retrieval** — Hybrid: Chroma vector + BM25, merged + deduplicated. Metadata-aware narrowing (source type, destination) before merge. Entry requirements retrieved once in `research_orchestrator`; `trip_finaliser` reuses, no re-query.

**Prompt injection** — Free-text from users stripped of injection patterns in `trip_intake` before prompt insertion. Treat `structured_fields` as untrusted.

## Testing

LLM calls mocked via `mock_llm_responses` fixture (`tests/conftest.py`) — patches `create_chat_model`, `invoke_with_retry`, `extract_token_usage`. Recorded responses in `tests/golden_prompts/*.json`.

Integration tests (`test_integration.py`, `test_api_integration.py`) hit real infra, need env vars.
