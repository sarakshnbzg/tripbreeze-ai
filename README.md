# TripBreeze AI

TripBreeze AI is an AI-powered travel planning assistant that combines trip intake, live travel research, budget checks, entry guidance, and itinerary generation in one workflow.

It uses a `FastAPI` backend for the LangGraph workflow and a standalone `Next.js` frontend for the browser experience.

## Highlights ✨

TripBreeze can:

- parse free-text trip requests
- support single-city and multi-city planning
- accept voice input via Whisper transcription
- search live flights and hotels with SerpAPI
- retrieve grounded visa and entry information from a local RAG knowledge base
- estimate budget fit before itinerary generation
- pause for human review, revision, or cancellation
- generate day-by-day itineraries with weather enrichment
- export itineraries as PDF and optionally email them
- remember user preferences and trip history in Postgres

## Architecture 🏗️

```text
Next.js frontend (frontend/, port 3000)
    |
    | HTTP + SSE
    v
FastAPI backend (port 8100)
    |
    +-- LangGraph workflow
    |     load_profile
    |     -> trip_intake
    |     -> research
    |     -> aggregate_budget
    |     -> review
    |     -> feedback_router
    |        -> attractions
    |        -> finalise
    |        -> update_memory
    |
    +-- Services
    |     OpenAI / Gemini
    |     SerpAPI
    |     Open-Meteo
    |     SMTP
    |
    +-- Data
          ChromaDB indexes
          Postgres memory + checkpoints
```

Core entry points:

- Backend API: [`presentation/api.py`](presentation/api.py)
- Graph: [`application/graph.py`](application/graph.py)
- State schema: [`application/state.py`](application/state.py)
- Detailed workflow docs: [`AGENTS.md`](AGENTS.md)

## Workflow 🔄

```text
Profile Loader
  -> Trip Intake
  -> Research Orchestrator
     -> flights
     -> hotels
     -> RAG entry requirements
  -> Budget Aggregator
  -> HITL Review
  -> Feedback Router
     -> approve: Attractions -> Finaliser -> Memory Updater
     -> revise_plan: back to Trip Intake
     -> cancel: end
```

Review actions:

- `rewrite_itinerary`: keep the approved trip, rewrite the final itinerary
- `revise_plan`: patch the trip request and rerun planning
- `cancel`: stop the workflow

## Tech Stack 🧰

- `Python 3.13`
- `FastAPI`, `uvicorn`, `sse-starlette`
- `LangGraph`, `LangChain`
- `OpenAI`, `Google Gemini`, `Whisper`
- `SerpAPI`
- `ChromaDB`, `BM25`
- `Open-Meteo`
- `Postgres`, `psycopg`, `langgraph-checkpoint-postgres`
- `Next.js 15`, `React 19`, `Tailwind CSS`
- `ReportLab`
- `Docker`
- `LangSmith`

## Quick Start 🚀

Choose one:

- Backend only
- Full stack
- Docker

### Prerequisites ✅

Required:

- `Python 3.13`
- `uv`
- `SERPAPI_API_KEY`
- `DATABASE_URL`
- at least one LLM key: `OPENAI_API_KEY` or `GOOGLE_API_KEY`

Optional:

- `CSC_API_KEY` for country/city sync
- SMTP credentials for email delivery
- LangSmith credentials for tracing
- `Node.js` and `npm` for the frontend

### Environment Setup ⚙️

```bash
cp .env.example .env
```

Minimum recommended `.env` values:

```env
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
SERPAPI_API_KEY=...
DATABASE_URL=postgresql://username:password@host/database?sslmode=require
```

TripBreeze reads runtime settings centrally from [`settings.py`](settings.py), with
[`config.py`](config.py) kept as a compatibility shim for older imports.

Useful optional tuning values in `.env` include `RAG_CHUNK_SIZE`, `RAG_CHUNK_OVERLAP`, `RAG_TOP_K`,
`MAX_FLIGHT_RESULTS`, `RAW_FLIGHT_CANDIDATES`, `MAX_HOTEL_RESULTS`, `DEFAULT_CURRENCY`, and
`DEFAULT_STAY_NIGHTS`.

## Local Development 💻

### Backend

Install dependencies:

```bash
pip install uv
uv sync
```

Optional reference data sync:

```bash
uv run python scripts/sync_reference_data.py
```

Build or refresh the RAG index:

```bash
uv run python scripts/rebuild_rag.py
```

Provider-specific rebuilds:

```bash
uv run python scripts/rebuild_rag.py openai
uv run python scripts/rebuild_rag.py google
```

Start the API:

```bash
uv run python app.py
```

Default backend URL: `http://127.0.0.1:8100`

Useful endpoints:

- `GET /healthz`
- `GET /docs`
- `POST /api/transcribe`
- `POST /api/search`
- `GET /api/search/{thread_id}/state`
- `POST /api/search/{thread_id}/clarify`
- `POST /api/search/{thread_id}/approve`
- `POST /api/search/{thread_id}/return-flights`

### Full Stack

```bash
cp frontend/.env.local.example frontend/.env.local
npm install --prefix frontend
uv run python scripts/dev.py
```

Defaults:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8100`

Override the frontend API target with `NEXT_PUBLIC_API_BASE_URL`.

## Testing 🧪

Run all backend tests:

```bash
uv run pytest -q
```

Run one file:

```bash
uv run pytest -q tests/test_trip_intake.py
```

Frontend tests:

```bash
npm run test --prefix frontend
npm run test:e2e --prefix frontend
```

## RAG Evaluation 📚

Install optional evaluation dependencies:

```bash
uv sync --group eval
```

Run the evaluator:

```bash
uv run python scripts/evaluate_rag.py --provider openai
```

Useful variants:

```bash
uv run python scripts/evaluate_rag.py --provider openai --retrieval-only
uv run python scripts/evaluate_rag.py --provider openai --llm-judge
```

Results are written to `evals/results/`.

Golden itinerary judging:

```bash
RUN_LLM_JUDGE_GOLDENS=1 uv run pytest tests/test_golden_prompts.py -k finaliser
```

## Ethics & Privacy 🛡️

TripBreeze is designed to support travel planning, not to replace official government,
airline, or border-control guidance. Entry requirements can change, so the app keeps
visa and entry notes grounded in the local knowledge base and surfaces them during
review, but travelers should still confirm critical details with official sources before
booking or departure.

The workflow includes several safeguards to reduce unreliable output:

- entry guidance is retrieved from a local RAG knowledge base instead of generated from memory alone
- LLM prompts treat trip fields and profile data as untrusted input to reduce prompt-injection risk
- budget checks, review summaries, and human approval happen before the final itinerary is generated
- when grounded information is limited, the system is expected to say so instead of inventing facts

TripBreeze also stores profile preferences and recent trip history to improve future planning.
In production, this should be paired with clear user consent, secure credential management,
database protection, and a retention policy that keeps only the minimum data needed for the
experience.

## Docker 🐳

Build:

```bash
docker build -t tripbreeze-ai .
```

Run full stack:

```bash
docker compose up --build
```

Run backend only:

```bash
docker run --rm -p 8100:8100 --env-file .env tripbreeze-ai
```

Persist RAG indexes:

```bash
docker run --rm -p 8100:8100 --env-file .env \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

## Operations 🔎

TripBreeze emits structured JSON logs via [`infrastructure/logging_utils.py`](infrastructure/logging_utils.py).

High-signal workflow events:

- `workflow.graph_build_started`
- `workflow.graph_build_completed`
- `workflow.profile_loaded`
- `workflow.intake_completed`
- `workflow.intake_clarification_requested`
- `workflow.intake_blocked_out_of_domain`
- `workflow.intake_failed`
- `workflow.research_completed`
- `workflow.review_ready`
- `workflow.review_decision_received`
- `workflow.route_after_review`
- `workflow.finaliser_completed`
- `workflow.finaliser_fallback_used`
- `workflow.memory_updated`

Useful production checks:

- rising `workflow.intake_failed`
- rising `workflow.finaliser_fallback_used`
- searches reaching review but not memory update
- frequent partial flight or hotel results

## Example Prompts 💬

```text
I want to fly from London to Tokyo from 2026-06-10 to 2026-06-17 for 2 travelers with a budget of 3000 EUR.
```

```text
Paris for 3 days, then Barcelona for 4 days, then fly home.
```

```text
Business class, exclude Ryanair, and keep the flight under 10 hours.
```

## Project Structure 🗂️

```text
tripbreeze-ai/
├── app.py
├── config.py
├── application/
├── domain/
├── infrastructure/
├── presentation/
├── frontend/
├── knowledge_base/
├── scripts/
├── tests/
├── evals/
├── SMTP_SETUP.md
└── AGENTS.md
```

## Notes 📝

- [`settings.py`](settings.py) is the typed source of truth for runtime settings.
- [`config.py`](config.py) re-exports settings for backward compatibility.
- Postgres persistence is strongly recommended for human-in-the-loop review flows.
- Rebuild retrieval indexes after knowledge-base changes with `uv run python scripts/rebuild_rag.py`.
- SMTP setup details live in [`SMTP_SETUP.md`](SMTP_SETUP.md).

## Limitations ⚠️

- Restart-safe HITL review depends on persistent Postgres-backed checkpointing.
- Live flight and hotel search availability depends on SerpAPI quotas, latency, and cost.
- LLM-based research and finalisation can still be imperfect when source data is sparse or ambiguous.
- Authentication is intentionally lightweight and not production-grade.

## Future Work 🔭

- [ ] Expand RAG visa information with more countries, clearer passport-specific rules, and source freshness checks.
- [ ] Improve the review step so users can revise specific flight, hotel, or itinerary preferences without restarting the whole workflow.
- [ ] Add clearer fallback behavior when live search APIs return incomplete or unavailable results.
- [ ] Add user profile management so travellers can view and update saved preferences directly.
- [ ] Add links from each user profile to previously generated travel plans.
- [ ] Replace remaining bootstrap reference data with managed sources so defaults do not require code changes.
