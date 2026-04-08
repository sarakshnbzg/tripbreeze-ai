# TripBreeze AI

TripBreeze AI is an AI-powered travel planning assistant that combines live flight and hotel search, destination guidance, budget checks, and itinerary generation in one streamlined workflow.

## 🌐 Live Deployment

TripBreeze is deployed on Streamlit Community Cloud:
<https://tripbreeze-ai.streamlit.app/>

## ✨ What It Does

- Uses a ReAct-style research orchestrator to decide when to search flights, search hotels, and query the local knowledge base
- ✈️ Searches flights with SerpAPI / Google Flights
- 🏨 Searches hotels with SerpAPI / Google Hotels
- 📚 Retrieves destination tips, visa info, and travel guidance from a local RAG knowledge base
- 💸 Tracks budget against the trip request
- ✅ Lets the user review results before finalising
- 🧠 Remembers preferences such as home airport, class, and trip history
- 📈 Supports LangSmith tracing for LLM observability

## 🧭 Workflow

```text
Profile Loader
  -> Trip Intake
  -> Research Orchestrator (dynamic tool calling for flights, hotels, and RAG)
  -> Budget Aggregator
  -> Review
  -> Finaliser
  -> Memory Updater
```

## 🛠️ Stack

- `LangGraph` for workflow orchestration
- `Streamlit` for the UI
- `OpenAI` or `Google Gemini` for intake, research, and final itinerary generation
- `SerpAPI` for live flight and hotel data
- `ChromaDB` for local retrieval
- Neon Postgres-backed long-term memory for user preferences
- `LangSmith` for observability and trace dashboards

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
DATABASE_URL=postgresql://username:password@your-neon-host/database?sslmode=require
```

TripBreeze uses Neon Postgres for long-term profile memory. You can manage the project database from the Neon console:
<https://console.neon.tech/app/projects/autumn-cherry-20180503/branches/br-green-morning-alh1r6cy/tables>

Optional LangSmith tracing:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=tripbreeze-ai
LANGCHAIN_API_KEY=...
```

LangSmith dashboard:
<https://smith.langchain.com/o/877c675a-ba6b-46dd-8d36-826feba406a5/dashboards/projects/ba117436-e649-43df-bd87-4ebf4e8c22c8>

### 3. Build the knowledge base

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

### 4. Run the app

```bash
uv run streamlit run app.py
```

Then open `http://localhost:8501`.

## 🐳 Docker Setup

### 1. Build the image

```bash
docker build -t tripbreeze-ai .
```

### 2. Run the container

Use your local `.env` file:

```bash
docker run --rm -p 8501:8501 --env-file .env tripbreeze-ai
```

If you want cached RAG indexes to persist across container restarts, mount the Chroma directory too:

```bash
docker run --rm -p 8501:8501 --env-file .env \
  -v "$(pwd)/chroma_db:/app/chroma_db" \
  tripbreeze-ai
```

Then open `http://localhost:8501`.
TripBreeze stores long-term profile memory in Neon Postgres using `DATABASE_URL` or `NEON_DATABASE_URL`.

If you want to use the same hosted database in Docker, keep `DATABASE_URL` in `.env` and pass that file with `--env-file`.

## 🧳 Typical Flow

1. Select an LLM provider and model in the sidebar.
2. Describe the trip in free text, optionally refining it with structured form fields for dates, destination, travellers, budget, and similar core details.
3. The intake step merges structured fields with free text, validates dates, and extracts travel filters such as nonstop flights, airline exclusions, hotel stars, or max flight price.
4. The ReAct-style research orchestrator decides which tools to call for this request: flights, hotels, knowledge retrieval, or any combination of them.
5. Review flight, hotel, destination, and budget results.
6. Approve to generate the final itinerary.

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

## 📁 Project Structure

```text
tripbreeze-ai/
├── app.py
├── config.py
├── presentation/
├── application/
├── domain/
├── infrastructure/
├── knowledge_base/
├── scripts/
├── tests/
└── README.md
```

## 📝 Notes

- Model names, API keys, paths, and defaults are centralised in `config.py`.
- Long-term profile memory requires `DATABASE_URL` or `NEON_DATABASE_URL`.
- Neon Postgres is the app's long-term memory store; the current project database is managed in the Neon console:
  <https://console.neon.tech/app/projects/autumn-cherry-20180503/branches/br-green-morning-alh1r6cy/tables>
- If retrieval looks stale, rebuild the RAG index with `uv run python scripts/rebuild_rag.py`.
- If commands are missing, run them through `uv run` or make sure the project's virtual environment is active.
