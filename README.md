# TripBreeze AI

TripBreeze AI is a single-trip planning assistant that combines live flight and hotel search, local destination knowledge, budget checks, and itinerary generation in one workflow.

## What It Does

- Searches flights with SerpAPI / Google Flights
- Searches hotels with SerpAPI / Google Hotels
- Retrieves destination tips, visa info, and travel guidance from a local RAG knowledge base
- Tracks budget against the trip request
- Lets the user review results before finalising
- Remembers preferences such as home airport, class, and trip history

## Workflow

```text
Profile Loader
  -> Trip Intake
  -> Research Orchestrator
  -> Budget Aggregator
  -> Review
  -> Finaliser
  -> Memory Updater
```

## Stack

- `LangGraph` for workflow orchestration
- `Streamlit` for the UI
- `OpenAI` or `Google Gemini` for intake, research, and final itinerary generation
- `SerpAPI` for live flight and hotel data
- `ChromaDB` for local retrieval
- JSON-based memory for user preferences

## Setup

### Prerequisites

- Python 3.13
- `SERPAPI_API_KEY`
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, or both

### Install

```bash
pip install uv
uv sync
cp .env.example .env
```

Add your keys to `.env`:

```env
OPENAI_API_KEY=...
GOOGLE_API_KEY=...
SERPAPI_API_KEY=...
```

### Build The Knowledge Base

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

### Run

```bash
uv run streamlit run app.py
```

## Deploy To Streamlit Community Cloud

This repo is ready to deploy on Streamlit Community Cloud with `app.py` as the entrypoint.

### Before you deploy

- Push this repository to GitHub.
- Make sure your app secrets are not committed.
- Use Streamlit's app settings to provide secrets instead of relying on a local `.env`.

Community Cloud supports multiple dependency file formats and will automatically detect one from your repo. This project already includes `uv.lock` and `pyproject.toml`, so you do not need to add a separate `requirements.txt`.

### Secrets

Copy `.streamlit/secrets.toml.example` into your local `.streamlit/secrets.toml` for local testing if you want, but do not commit that file.

When deploying, paste the equivalent values into the app's "Advanced settings" secrets box:

```toml
OPENAI_API_KEY = "..."
GOOGLE_API_KEY = "..."
SERPAPI_API_KEY = "..."
LANGCHAIN_TRACING_V2 = "false"
LANGCHAIN_PROJECT = "tripbreeze-ai"
LANGCHAIN_API_KEY = "..."
```

The app reads config from environment variables locally and falls back to `st.secrets` on Streamlit Community Cloud.

### Deploy steps

1. Open Streamlit Community Cloud.
2. Create a new app from this GitHub repository.
3. Set the main file path to `app.py`.
4. Choose Python `3.13` in Advanced settings to match `pyproject.toml`.
5. Paste your secrets into the secrets box.
6. Deploy the app.

### Important note about persistence

TripBreeze stores user memory in `memory/` and retrieval indexes in `chroma_db/`. Community Cloud storage is not a durable database, so those files may be cleared when the app rebuilds or moves. The app will still run, but saved traveler profiles and cached RAG indexes should be treated as temporary in this hosting environment.

## Typical Flow

1. Select an LLM provider and model in the sidebar.
2. Fill in the structured trip form for origin, destination, dates, travellers, budget, and similar core fields.
3. Add optional free-text preferences for extra constraints such as nonstop flights, airline exclusions, hotel star preferences, or max flight price.
4. Review flight, hotel, destination, and budget results.
5. Approve to generate the final itinerary.

## Free-Text Preference Examples

Use the form for the main trip details. The optional free-text field is best for extra constraints like these:

```text
Nonstop flights only.
```

```text
Business class, exclude Ryanair, and keep the flight under 10 hours.
```

```text
4-star hotels and max flight price of 800 EUR per person.
```

## Project Structure

```text
tripbreeze-ai/
├── app.py
├── config.py
├── presentation/
├── application/
├── domain/
├── infrastructure/
├── knowledge_base/
├── memory/
├── scripts/
├── tests/
└── README.md
```

## Notes

- Model names, API keys, paths, and defaults are centralised in `config.py`.
- If retrieval looks stale, rebuild the RAG index with `uv run python scripts/rebuild_rag.py`.
- If commands are missing, run them through `uv run` or make sure the project's virtual environment is active.
