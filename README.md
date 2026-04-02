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
- Conda or Miniconda
- `SERPAPI_API_KEY`
- `OPENAI_API_KEY`, `GOOGLE_API_KEY`, or both

### Install

```bash
conda create -n tripbreeze-ai python=3.13 -y
conda activate tripbreeze-ai
pip install -r requirements.txt
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
python scripts/rebuild_rag.py
```

### Run

```bash
streamlit run app.py
```

## Typical Flow

1. Select an LLM provider and model in the sidebar.
2. Enter trip details and optional preferences.
3. Review flight, hotel, destination, and budget results.
4. Approve to generate the final itinerary.

## Example Prompts

```text
I want to fly from New York to Paris, June 15 to June 22, budget $3000.
```

```text
Plan a business class trip from London to Tokyo for 2 people, September 1 to September 10, with 4-star hotels.
```

```text
Cheapest trip from LAX to Bangkok, December 20 to January 3, max $1500.
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
- If retrieval looks stale, rebuild the RAG index with `python scripts/rebuild_rag.py`.
- If imports fail, make sure the Conda environment is active before running the app.
