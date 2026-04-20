# TripBreeze AI

TripBreeze AI is an AI-powered travel planning assistant that combines live flight and hotel search, entry-requirement guidance, budget checks, and itinerary generation in one streamlined workflow.

## 🌐 Live Deployment

TripBreeze is deployed on Streamlit Community Cloud:
<https://tripbreeze-ai.streamlit.app/>

## ✨ What It Does

- Uses a ReAct-style research orchestrator to decide when to search flights, search hotels, and query the local knowledge base
- 🎙️ Accepts voice input — describe your trip by speaking and it's transcribed via OpenAI Whisper
- ✈️ Searches flights with SerpAPI / Google Flights
- 🚆 Shows ground transport options (trains, buses, ferries) side-by-side with flights so users can compare modes. Currently backed by a stub; swap `infrastructure/apis/ground_transport_client.py` for a real provider when one becomes available.
- 🏨 Searches hotels with SerpAPI / Google Hotels
- 🌍 Supports **multi-city itineraries** — plan trips like "Paris for 3 days, then Barcelona for 4 days" with per-leg flight and hotel selection
- 📚 Retrieves visa and entry requirement guidance from a local RAG knowledge base
- 🌤️ Shows weather forecasts for each day of the trip (via Open-Meteo, no API key needed)
- 💸 Tracks budget against the trip request
- ✅ Lets the user review results, revise the plan, or continue to final itinerary generation
- 🔐 Supports user accounts with securely hashed passwords (`bcrypt`)
- 🧠 Remembers preferences such as home airport, class, and trip history (with PDF download for past trips)
- 📄 Exports final itinerary as a downloadable PDF
- 📧 Sends itinerary via email with PDF attachment (requires SMTP configuration)

## 🧭 Workflow

```text
Profile Loader
  -> Trip Intake
  -> Research Orchestrator (ReAct agent: flights, ground transport, hotels, RAG for entry requirements)
  -> Budget Aggregator
  -> Review (HITL pause)
  -> Feedback Router (approve / revise plan / cancel)
     -> approve: Attractions Research -> Trip Finaliser -> Memory Updater
     -> revise plan: back to Trip Intake, then through research/budget/review again
     -> cancel: end
```

## 🏗️ Architecture

TripBreeze uses a two-layer architecture running in a single process:

```text
Streamlit (UI client, port 8501)
    │ httpx
FastAPI (backend API, port 8100 — background thread)
    ├── POST /api/transcribe           → OpenAI Whisper → text
    ├── POST /api/search               → LangGraph pipeline → SSE stream
    ├── GET  /api/search/{thread}/state → current graph state for HITL review
    ├── POST /api/search/{thread}/return-flights → return flight lookup
    ├── POST /api/search/{thread}/clarify → resume after missing-field clarification
    └── POST /api/search/{thread}/approve → resume after review; supports approve or revise-plan SSE flows
```

Review actions currently work like this:

- `rewrite_itinerary`: keep the approved trip and selected options, then use feedback only in the final itinerary wording
- `revise_plan`: patch the current trip request and rerun intake/research/budget/review
- `cancel`: stop the workflow

Streamlit is a thin UI client. All LangGraph orchestration, LLM calls, and API interactions run behind FastAPI, which streams progress and results back via Server-Sent Events (SSE). This separation allows the backend to be deployed independently for multi-user scaling.

## 🛠️ Stack

- `Python 3.13`
- `FastAPI`, `uvicorn`, `sse-starlette`: backend API and SSE streaming
- `Streamlit`: frontend UI
- `LangGraph`, `LangChain`: workflow orchestration, tool calling, and structured LLM interactions
- `OpenAI`, `Google Gemini`: trip intake, research, and itinerary generation
- `OpenAI Whisper`: voice-to-text transcription
- `SerpAPI`, `Google Flights`, `Google Hotels`, `Google Maps`: live flight, hotel, and attraction data
- `ChromaDB`, `BM25`: hybrid retrieval for the local RAG knowledge base
- `Open-Meteo`: trip weather forecasts and historical fallback weather data
- `Neon Postgres`, `psycopg`, `psycopg_pool`: long-term memory and LangGraph checkpoint persistence
- `bcrypt`: secure password hashing for user authentication
- `httpx`: Streamlit-to-FastAPI communication
- `ReportLab`: PDF itinerary export
- `SMTP`: itinerary email delivery
- `Docker`: containerized deployment
- `LangSmith`: observability and trace dashboards

## 🚀 Quick Start

Choose one of these paths:

- `Local Python setup` if you want to run the app directly with `uv`
- `Docker setup` if you want to run everything in a container

## 💻 Local Setup

### 1. Prerequisites

- Python 3.13
- `SERPAPI_API_KEY`
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, or both

### 2. Install dependencies

```bash
pip install uv
uv sync
cp .env.example .env
```

Add your API keys and Neon Postgres connection string to `.env`:

```env
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
SERPAPI_API_KEY=...
CSC_API_KEY=...
DATABASE_URL=postgresql://username:password@your-neon-host/database?sslmode=require
```

TripBreeze uses Neon Postgres for long-term profile memory.

Optional LangSmith tracing:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tripbreeze-ai
LANGCHAIN_API_KEY=...
```

You can view traces in your LangSmith project dashboard after enabling these settings.

### 3. Sync external reference data

Populate DB-backed `countries` and `cities` from Country State City API:

```bash
uv run python scripts/sync_reference_data.py
```

Optional SMTP configuration for email delivery (see [SMTP_SETUP.md](SMTP_SETUP.md) for details):

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SENDER_EMAIL=your-email@gmail.com
SMTP_SENDER_PASSWORD=your-app-password
SMTP_USE_TLS=true
```

### 4. Build the knowledge base

Run this once on first setup, and again after editing files in `knowledge_base/`:

```bash
uv run python scripts/rebuild_rag.py
```

If you want retrieval to work with both supported providers, rebuild a provider-specific index for each one:

```bash
uv run python scripts/rebuild_rag.py openai
uv run python scripts/rebuild_rag.py google
```

TripBreeze stores these separately under `chroma_db/openai` and `chroma_db/google`, and automatically uses the matching index for the provider selected in the app.

### 5. Run the app

```bash
uv run streamlit run app.py
```

This starts both the Streamlit UI on `http://localhost:8501` and the FastAPI backend on `http://localhost:8100` (background thread). The FastAPI interactive docs are available at `http://localhost:8100/docs`.

### 6. Run tests

```bash
uv run pytest -q
```

GitHub Actions also runs the test suite automatically on every push and pull request.

### 7. Evaluate RAG

Install the optional evaluation dependencies:

```bash
uv sync --group eval
```

Then run the offline evaluator against the sample dataset in [`evals/rag_eval_dataset.jsonl`](evals/rag_eval_dataset.jsonl):

```bash
uv run python scripts/evaluate_rag.py --provider openai
```

Use retrieval-only mode if you just want to inspect fetched chunks without generating answers or scoring:

```bash
uv run python scripts/evaluate_rag.py --provider openai --retrieval-only
```

You can also add an LLM-as-a-judge pass over the generated answers:

```bash
uv run python scripts/evaluate_rag.py --provider openai --llm-judge
```

To use a different judge provider or model:

```bash
uv run python scripts/evaluate_rag.py --provider openai --llm-judge \
  --judge-provider openai --judge-model gpt-4.1-mini
```

The judge writes row-level scores plus aggregate averages for faithfulness, correctness,
completeness, groundedness, pass rate, and overall score to `evals/results/`.
The script also continues to write retrieval snapshots and RAGAs score summaries there.

### 8. Judge golden itineraries

The replay-based golden tests stay deterministic by default, but you can opt into
LLM-as-a-judge scoring for the final itinerary golden cases:

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

When enabled, the tests still perform the normal structural assertions, then ask a
judge model to score each golden itinerary on constraint following, trip relevance,
structure quality, personalization, groundedness, and overall quality against the
minimum thresholds stored in `tests/golden_prompts/finaliser.json`.

## 🐳 Docker Setup

### 1. Build the image

```bash
docker build -t tripbreeze-ai .
```

Or start it with Docker Compose:

```bash
docker compose up --build
```

### 2. Run the container

Use your local `.env` file:

```bash
docker run --rm -p 8501:8501 -p 8100:8100 --env-file .env tripbreeze-ai
```

If you want cached RAG indexes to persist across container restarts, mount the Chroma directory too:

```bash
docker run --rm -p 8501:8501 -p 8100:8100 --env-file .env \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

Then open `http://localhost:8501`.
TripBreeze stores long-term profile memory in Neon Postgres using `DATABASE_URL` or `NEON_DATABASE_URL`.

If you want to use the same hosted database in Docker, keep `DATABASE_URL` in `.env` and pass that file with `--env-file`.

On first container startup, TripBreeze will rebuild the RAG indexes automatically for any configured provider whose persisted directory is missing. Mounting `./chroma_db:/app/chroma_db` keeps those indexes between restarts and avoids rebuilding each time.

You can also force a rebuild on every start:

```bash
docker run --rm -p 8501:8501 -p 8100:8100 --env-file .env \
  -e REBUILD_RAG_ON_START=1 \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

With the default Docker settings, the FastAPI docs are also reachable at `http://localhost:8100/docs`.

## 🧳 Typical Flow

1. Select an LLM provider and model in the sidebar.
2. Describe the trip in free text or by voice, optionally refining it with structured form fields for dates, destination, travellers, budget, and similar core details.
3. The intake step merges structured fields with free text, validates dates, and extracts travel filters such as nonstop flights, airline exclusions, hotel stars, or max flight price.
4. The ReAct-style research orchestrator decides which tools to call for this request: flights, hotels, knowledge retrieval, or any combination of them.
5. Review flight, ground transport, hotel, destination, and budget results. Ground transport is optional — pick a train/bus/ferry alongside (or instead of) your flight.
6. Approve to generate the final itinerary. After approval, the app fetches attraction candidates for the destination and uses them to ground the day-by-day plan.
7. Download the itinerary as a PDF or email it directly to yourself.

## 💬 Free-Text Examples

The free-text field can describe the whole trip or just extra constraints. For example:

```text
I want to fly from London to Tokyo from 2026-06-10 to 2026-06-17 for 2 travelers with a budget of 3000 EUR.
```

```text
Nonstop flights only.
```

```text
Business class, exclude Ryanair, and keep the flight under 10 hours.
```

```text
4-star hotels and max flight price of 800 EUR per person.
```

### Multi-City Trips

TripBreeze automatically detects multi-city itineraries:

```text
Paris for 3 days, then Barcelona for 4 days, then fly home.
```

```text
Rome → Florence → Venice, 2 nights each, starting June 10.
```

```text
Visit Tokyo for a week then Kyoto for 5 days. 2 travelers, budget 5000 USD.
```

For multi-city trips, the app searches flights and hotels for each leg separately, letting you select options per destination before generating the combined itinerary.

Multi-city trips can be **round-trip** (return to origin, the default) or **open-jaw / one-way** (no return leg). In the form, tick both "Multi-city" and "One-way" to skip the return. In free text, phrases like "not coming back" or "ending in Rome" trigger the same behaviour via `return_to_origin=false`.

## 📁 Project Structure

```text
tripbreeze-ai/
├── app.py                        # Entry point — starts FastAPI + Streamlit
├── config.py                     # Centralised settings
├── presentation/
│   ├── api.py                    # FastAPI backend (SSE endpoints)
│   ├── api_client.py             # httpx client for Streamlit → FastAPI
│   └── streamlit_app.py          # Streamlit UI (thin client)
├── application/
│   ├── graph.py                  # LangGraph workflow
│   └── state.py                  # Graph state schema
├── domain/                       # Agents and nodes
├── infrastructure/
│   ├── pdf_generator.py          # PDF export using reportlab
│   ├── email_sender.py           # SMTP email delivery
│   └── ...                       # APIs, LLMs, persistence, RAG
├── knowledge_base/
├── scripts/
├── tests/
├── SMTP_SETUP.md                 # Email configuration guide
└── README.md
```

## 📝 Notes

- Model names, API keys, paths, and defaults are centralised in `config.py`.
- Long-term profile memory requires `DATABASE_URL` or `NEON_DATABASE_URL`.
- Authentication uses `bcrypt` for password hashing. If you previously created local accounts before this change, recreate them after clearing old credentials.
- Neon Postgres is the app's long-term memory store.
- If retrieval looks stale, rebuild the RAG index with `uv run python scripts/rebuild_rag.py`.
- If commands are missing, run them through `uv run` or make sure the project's virtual environment is active.

## 🔮 Future Work

- [ ] **Replace remaining seeded collections with a scalable data source** — Move seed datasets such as `CITIES`, `COUNTRIES`, `AIRLINES`, `CITY_TO_AIRPORT`, `DAILY_EXPENSE_BY_DESTINATION`, and similar bootstrap lists into fully managed database content or an external API (e.g., Airtable, Amadeus, or a custom backend) to enable updates without code changes.
