# TripBreeze AI

TripBreeze AI is an AI travel planner that turns a trip request into researched options, budget checks, entry guidance, and a polished itinerary.

It uses a `FastAPI` backend with a LangGraph workflow and a `Next.js` frontend.

## Product Screenshots

<p align="center">
  <img src="docs/images/auth-screen.png" alt="TripBreeze AI authentication screen" width="48%" />
  <img src="docs/images/planner-workspace.png" alt="TripBreeze AI planning workspace" width="48%" />
</p>

<p align="center">
  <em>Left: streamlined login experience. Right: planning workspace with preferences, trip history, and guided trip search.</em>
</p>

## What It Does ✨

- parses free-text and structured trip requests
- supports single-city and multi-city planning
- searches live flights and hotels with SerpAPI
- retrieves grounded visa and entry information from a local RAG knowledge base
- estimates whether a trip fits the user's budget
- pauses for human review before finalising
- generates day-by-day itineraries with weather enrichment
- stores user preferences and recent trip history in Postgres

## Architecture 🏗️

```text
Next.js frontend
    |
    | HTTP + SSE
    v
FastAPI backend
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
          OpenAI / Gemini / SerpAPI / Open-Meteo / SMTP
```

Core files:

- Backend API: [presentation/api.py](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/presentation/api.py)
- Graph: [application/graph.py](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/application/graph.py)
- State schema: [application/state.py](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/application/state.py)
- Workflow documentation: [AGENTS.md](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/AGENTS.md)

## Workflow 🔄

Trip flow: `load_profile -> trip_intake -> research -> aggregate_budget -> review -> feedback_router`, then either `approve -> attractions -> finalise -> update_memory`, `revise_plan -> trip_intake`, or `cancel`.

For the full agent and node breakdown, see [AGENTS.md](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/AGENTS.md).

## Tech Stack 🧰

- `Python 3.13`
- `FastAPI`, `LangGraph`, `LangChain`
- `OpenAI`, `Google Gemini`, `Whisper`
- `SerpAPI`, `Open-Meteo`
- `ChromaDB`, `BM25`
- `Postgres`
- `Next.js 15`, `React 19`, `Tailwind CSS`
- `Docker`

## Quick Start 🚀

### Prerequisites ✅

Required:

- `Python 3.13`
- `uv`
- `SERPAPI_API_KEY`
- `DATABASE_URL`
- at least one LLM key: `OPENAI_API_KEY` or `GOOGLE_API_KEY`

Optional:

- `Node.js` and `npm` for the frontend
- SMTP credentials for email delivery
- LangSmith credentials for tracing

### Environment ⚙️

```bash
cp .env.example .env
```

Minimum recommended values:

```env
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
SERPAPI_API_KEY=...
DATABASE_URL=postgresql://username:password@host/database?sslmode=require
```

Runtime settings are centralised in [settings.py](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/settings.py). [config.py](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/config.py) remains as a compatibility shim for older imports.

## Local Development 💻

### Backend

Install dependencies:

```bash
uv sync
```

Optional reference sync:

```bash
uv run python scripts/sync_reference_data.py
```

Build or refresh the RAG index:

```bash
uv run python scripts/rebuild_rag.py
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

### Full Stack

```bash
cp frontend/.env.local.example frontend/.env.local
npm install --prefix frontend
uv run python scripts/dev.py
```

Defaults:

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8100`

Set `NEXT_PUBLIC_API_BASE_URL` if the frontend should target a different backend URL.

## Deployment ☁️

TripBreeze AI is live at `https://tripbreeze-ai.vercel.app/`, with the API deployed at `https://tripbreeze-ai.onrender.com`.

## Testing 🧪

Backend:

```bash
uv run pytest -q
```

Frontend:

```bash
npm run test --prefix frontend
npm run test:e2e --prefix frontend
```

## RAG Evaluation 📚

Install optional evaluation dependencies with `uv sync --group eval`, then run:

```bash
uv run python scripts/evaluate_rag.py --provider openai
```

Useful variants:

```bash
uv run python scripts/evaluate_rag.py --provider openai --retrieval-only
uv run python scripts/evaluate_rag.py --provider openai --llm-judge
RUN_LLM_JUDGE_GOLDENS=1 uv run pytest tests/test_golden_prompts.py -k finaliser
```

Results are written to `evals/results/`.

## Ethics & Privacy 🛡️

TripBreeze is designed to assist with travel planning, not replace official airline, border-control, health, or government guidance. Entry requirements can change, so travelers should confirm critical details with official sources before booking or departure.

The system reduces unreliable output by grounding entry guidance in a local knowledge base, checking budgets before finalisation, and requiring human review before approval. A fuller write-up lives in [docs/ethics.md](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/docs/ethics.md).

## Docker 🐳

Build:

```bash
docker build -t tripbreeze-ai .
docker compose up --build
```

## Operations 🔎

TripBreeze emits structured JSON logs via `infrastructure/logging_utils.py`. High-signal workflow events include `workflow.intake_completed`, `workflow.research_completed`, `workflow.review_ready`, `workflow.review_decision_received`, `workflow.finaliser_completed`, and `workflow.memory_updated`.

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
├── application/
├── domain/
├── infrastructure/
├── presentation/
├── frontend/
├── knowledge_base/
├── scripts/
├── tests/
├── AGENTS.md
└── settings.py
```

## Notes 📝

- Rebuild retrieval indexes after knowledge-base changes with `uv run python scripts/rebuild_rag.py`.
- SMTP setup details live in [SMTP_SETUP.md](/Users/sarakashanibozorg/Documents/AI Engineering Course/tripbreeze-ai/SMTP_SETUP.md).
- Entry requirements should still be verified against official sources before booking or departure.

## Limitations ⚠️

- Restart-safe HITL review depends on Postgres-backed checkpointing.
- Live flight and hotel search quality depends on SerpAPI quotas, latency, and source coverage.
- LLM-based research and finalisation can still be imperfect when source data is sparse or ambiguous.
- Authentication is intentionally lightweight and not production-grade.

## Future Work 🔭

- Expand visa and entry coverage with fresher, more passport-specific data.
- Improve revision flows so users can adjust specific choices without restarting more of the plan.
- Add user-facing profile management and stronger linking between users and past plans.
