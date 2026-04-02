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
- If retrieval looks stale, rebuild the RAG index with `python scripts/rebuild_rag.py`.
- If imports fail, make sure the Conda environment is active before running the app.
