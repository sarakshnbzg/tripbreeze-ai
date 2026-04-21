# TripBreeze AI

TripBreeze AI is an AI-powered travel planning assistant that combines trip intake, live travel research, budget checks, entry-requirement guidance, and itinerary generation in a single workflow.

The project is built as a FastAPI backend with a standalone Next.js frontend. The backend owns the LangGraph workflow, tool calls, retrieval, persistence, and streaming responses. The frontend provides the browser-based planning experience.

## Overview

TripBreeze can:

- parse free-text trip requests such as "Paris for 3 days, then Barcelona for 4"
- accept voice input through Whisper transcription
- search flights with SerpAPI-backed Google Flights
- compare optional ground transport alongside flights
- search hotels with SerpAPI-backed Google Hotels
- retrieve grounded visa and entry guidance from a local RAG knowledge base
- support multi-city itineraries with per-leg selections
- estimate budget fit before itinerary generation
- pause for human review, revision, or cancellation
- generate a polished day-by-day itinerary with weather enrichment
- export itineraries as PDF and optionally email them
- remember user preferences and trip history in Postgres

## Architecture

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
    +-- External services
    |     OpenAI / Gemini
    |     SerpAPI
    |     Open-Meteo
    |     SMTP
    |
    +-- Local + persistent data
          ChromaDB knowledge indexes
          Neon Postgres / Postgres memory + checkpoints
```

The backend exposes HTTP and SSE endpoints from [`presentation/api.py`](presentation/api.py), while the graph and state live in [`application/graph.py`](application/graph.py) and [`application/state.py`](application/state.py).

## Workflow

```text
Profile Loader
  -> Trip Intake
  -> Research Orchestrator
     -> flights
     -> ground transport
     -> hotels
     -> RAG entry requirements
  -> Budget Aggregator
  -> HITL Review
  -> Feedback Router
     -> approve: Attractions Research -> Trip Finaliser -> Memory Updater
     -> revise_plan: back to Trip Intake
     -> cancel: end
```

Review actions behave like this:

- `rewrite_itinerary`: keep the approved trip and options, but change the final itinerary wording
- `revise_plan`: patch the current trip request and rerun intake, research, budget, and review
- `cancel`: stop the workflow

More implementation detail for every node and agent is documented in [`AGENTS.md`](AGENTS.md).

## Tech Stack

- `Python 3.13`
- `FastAPI`, `uvicorn`, `sse-starlette`
- `LangGraph`, `LangChain`
- `OpenAI`, `Google Gemini`
- `OpenAI Whisper`
- `SerpAPI`
- `ChromaDB`, `BM25`
- `Open-Meteo`
- `Postgres`, `psycopg`, `langgraph-checkpoint-postgres`
- `Next.js 15`, `React 19`, `Tailwind CSS`
- `ReportLab`
- `bcrypt`
- `Docker`
- `LangSmith`

## Quick Start

Choose the path that matches how you want to work:

- Backend only: run the FastAPI API directly with `uv`
- Full stack: run the FastAPI backend and Next.js frontend together
- Docker: run the backend in a container

## Prerequisites

Backend:

- Python 3.13
- `uv`
- at least one LLM provider key: `OPENAI_API_KEY` or `GOOGLE_API_KEY`
- `SERPAPI_API_KEY`
- a Postgres connection string in `DATABASE_URL` for persistent memory and checkpoints

Frontend:

- Node.js and `npm`

Optional:

- `CSC_API_KEY` for syncing country and city reference data
- SMTP credentials for email delivery
- LangSmith credentials for tracing

## Environment Setup

Copy the example environment file and fill in the required values:

```bash
cp .env.example .env
```

Minimum recommended `.env` values:

```env
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
SERPAPI_API_KEY=...
DATABASE_URL=postgresql://username:password@your-neon-host/database?sslmode=require
```

Optional settings:

```env
CSC_API_KEY=...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tripbreeze-ai
LANGCHAIN_API_KEY=...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=your-email@gmail.com
SMTP_SENDER_PASSWORD=your-app-password
SMTP_USE_TLS=true
REQUIRE_PERSISTENT_CHECKPOINTER=true
```

TripBreeze reads configuration centrally from [`config.py`](config.py), not directly throughout the codebase.

## Backend Local Setup

### 1. Install dependencies

```bash
pip install uv
uv sync
```

### 2. Sync reference data

Populate database-backed `countries` and `cities` from the Country State City API:

```bash
uv run python scripts/sync_reference_data.py
```

This step is only needed if you want the external reference dataset populated.

### 3. Build the RAG index

Run this once on first setup, and again after changing files in [`knowledge_base/`](knowledge_base/):

```bash
uv run python scripts/rebuild_rag.py
```

If you want provider-specific indexes for both supported providers:

```bash
uv run python scripts/rebuild_rag.py openai
uv run python scripts/rebuild_rag.py google
```

Indexes are stored under `chroma_db/openai` and `chroma_db/google`.

### 4. Start the API

```bash
uv run python app.py
```

The backend starts on `http://127.0.0.1:8100` by default.

Useful endpoints:

- `GET /healthz`
- `GET /docs`
- `POST /api/transcribe`
- `POST /api/search`
- `GET /api/search/{thread_id}/state`
- `POST /api/search/{thread_id}/clarify`
- `POST /api/search/{thread_id}/approve`
- `POST /api/search/{thread_id}/return-flights`

## Full-Stack Local Setup

If you want the browser UI as well:

```bash
cp frontend/.env.local.example frontend/.env.local
npm install --prefix frontend
uv run python scripts/dev.py
```

That starts:

- frontend at `http://127.0.0.1:3000`
- API at `http://127.0.0.1:8100`

The frontend expects the backend at `http://127.0.0.1:8100` by default. You can override that with `NEXT_PUBLIC_API_BASE_URL`.

The backend allows local browser access from:

- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://localhost:3001`
- `http://127.0.0.1:3001`

To customize this list, set `FRONTEND_ORIGINS` in `.env` as a comma-separated list.

## Testing

Run the full test suite:

```bash
uv run pytest -q
```

Run a single file:

```bash
uv run pytest -q tests/test_trip_intake.py
```

GitHub Actions also runs the test suite on pushes and pull requests.

## RAG Evaluation

Install the optional evaluation dependencies:

```bash
uv sync --group eval
```

Run the offline evaluator against [`evals/rag_eval_dataset.jsonl`](evals/rag_eval_dataset.jsonl):

```bash
uv run python scripts/evaluate_rag.py --provider openai
```

Useful variants:

```bash
uv run python scripts/evaluate_rag.py --provider openai --retrieval-only
uv run python scripts/evaluate_rag.py --provider openai --llm-judge
uv run python scripts/evaluate_rag.py --provider openai --llm-judge --judge-provider openai --judge-model gpt-4.1-mini
```

Results are written to `evals/results/`.

### Golden itinerary judging

Replay-based golden tests stay deterministic by default, but you can opt into LLM-as-a-judge scoring for the final itinerary cases:

```bash
RUN_LLM_JUDGE_GOLDENS=1 uv run pytest tests/test_golden_prompts.py -k finaliser
```

Optional overrides:

```bash
RUN_LLM_JUDGE_GOLDENS=1 \
GOLDEN_JUDGE_PROVIDER=openai \
GOLDEN_JUDGE_MODEL=gpt-4.1-mini \
uv run pytest tests/test_golden_prompts.py -k finaliser
```

## Docker Setup

Build the image:

```bash
docker build -t tripbreeze-ai .
```

Or start with Docker Compose:

```bash
docker compose up --build
```

Run the container with your local `.env`:

```bash
docker run --rm -p 8100:8100 --env-file .env tripbreeze-ai
```

To persist RAG indexes between container restarts:

```bash
docker run --rm -p 8100:8100 --env-file .env \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

To force a rebuild on every container start:

```bash
docker run --rm -p 8100:8100 --env-file .env \
  -e REBUILD_RAG_ON_START=1 \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

The API docs remain available at `http://localhost:8100/docs`.

## Example Prompts

Free-text trip requests:

```text
I want to fly from London to Tokyo from 2026-06-10 to 2026-06-17 for 2 travelers with a budget of 3000 EUR.
```

```text
Paris for 3 days, then Barcelona for 4 days, then fly home.
```

```text
Visit Tokyo for a week then Kyoto for 5 days. 2 travelers, budget 5000 USD.
```

Preference-only follow-ups:

```text
Nonstop flights only.
```

```text
Business class, exclude Ryanair, and keep the flight under 10 hours.
```

```text
4-star hotels and max flight price of 800 EUR per person.
```

Multi-city trips can be round-trip by default or open-jaw / one-way when `return_to_origin=false`. In the form UI, this is exposed through the multi-city and one-way controls.

## Project Structure

```text
tripbreeze-ai/
├── app.py
├── config.py
├── application/
│   ├── graph.py
│   └── state.py
├── domain/
│   ├── agents/
│   └── nodes/
├── infrastructure/
│   ├── apis/
│   ├── llms/
│   ├── persistence/
│   ├── rag/
│   ├── email_sender.py
│   └── pdf_generator.py
├── presentation/
│   └── api.py
├── frontend/
├── knowledge_base/
├── scripts/
├── tests/
├── evals/
├── SMTP_SETUP.md
└── AGENTS.md
```

## Notes

- `config.py` is the single source of truth for runtime settings, defaults, and model names.
- Postgres persistence is strongly recommended for any workflow that uses human-in-the-loop review.
- The ground transport provider is currently a stub in [`infrastructure/apis/ground_transport_client.py`](infrastructure/apis/ground_transport_client.py). It returns realistic mock data behind a stable contract, so it can later be replaced by a real provider.
- If retrieval looks stale, rebuild the index with `uv run python scripts/rebuild_rag.py`.
- SMTP setup details live in [`SMTP_SETUP.md`](SMTP_SETUP.md).

## Limitations

- HITL review state is only restart-safe when `DATABASE_URL` or `NEON_DATABASE_URL` is configured. In deployed environments, `REQUIRE_PERSISTENT_CHECKPOINTER=true` should be enabled so the app fails fast instead of silently falling back to in-memory checkpoints.
- Live search depends on SerpAPI-backed Google Flights and Google Hotels, so quotas, latency, and API costs affect availability.
- Authentication is intentionally lightweight and suitable for a course project, not a full production identity stack.
- The research and finalisation steps rely on LLM tool calling. Even with structured outputs and retrieval grounding, results can still be imperfect when source data is sparse or ambiguous.
- Evaluation coverage is solid but not exhaustive. Real-world travel planning still benefits from monitoring and human review.

## Future Work

- [ ] Replace remaining bootstrap reference data with managed sources so defaults such as `AIRLINES`, `CITY_TO_AIRPORT`, and daily-expense mappings do not require code changes.
