# ✈️ TripBreeze AI

An intelligent, single-trip planning agent that researches flights, hotels, and destinations in one coherent workflow — powered by LangGraph, RAG, and real API integrations.

## Agent Purpose

This agent helps travelers plan trips by automatically searching for flights and hotels, retrieving destination guides and visa requirements, aggregating budget information, and presenting everything in a clear itinerary — all through a conversational interface.

**Target users:** Anyone planning international or domestic travel who wants AI-assisted research and itinerary generation.

**Why this agent is useful:**
- Eliminates the need to manually search multiple travel sites
- Provides destination-specific advice (visa requirements, local tips, safety info)
- Remembers user preferences across sessions (home airport, travel class, past trips)
- Confirms key decisions before finalizing (human-in-the-loop)

## Architecture

```
[Start] → [Profile Loader] → [Trip Intake]
                              ↓
                 [Research Orchestrator (LLM Tool Calling)]
                              ↓
                      [Budget Aggregator]
                                                      ↓
                                              [HITL Review] ← user confirms/edits
                                                      ↓
                                             [Trip Finaliser]
                                                      ↓
                                          [Memory Updater] → [End]
```

### Node Descriptions

| Node | Description |
|------|-------------|
| **Profile Loader** | Loads user preferences from long-term JSON-based memory |
| **Trip Intake** | Builds trip request from structured form fields; uses LLM tool calling only to parse free-text special requests into filters (stops, max price, airlines, etc.) |
| **Research Orchestrator** | Uses the user-selected OpenAI or Google Gemini model with tool calling to dynamically choose research tools |
| **Flight Agent** | Searches real flights via SerpAPI (Google Flights) when selected by the orchestrator |
| **Hotel Agent** | Searches real hotels via SerpAPI (Google Hotels) when selected by the orchestrator |
| **RAG Tool** | Exposes knowledge-base retrieval as an optional tool inside the orchestrator's ReAct loop |
| **Budget Aggregator** | Combines costs and checks against user's budget limit |
| **HITL Review** | Presents options to the user for approval or feedback |
| **Trip Finaliser** | Generates a polished itinerary document using the user-selected OpenAI or Google Gemini model |
| **Memory Updater** | Persists learned preferences (home airport, travel class, past trips) |

## Setup

### 1. Prerequisites

- Conda or Miniconda
- Python 3.13 recommended
- OpenAI API key or Google AI Studio API key
- SerpAPI key (free tier at [serpapi.com](https://serpapi.com) — 100 searches/month)

### 2. Create and Activate a Conda Environment

```bash
cd tripbreeze-ai
conda create -n tripbreeze-ai python=3.13 -y
conda activate tripbreeze-ai
```

Verify that your shell is using the Conda environment:

```bash
which python
python --version
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=your-google-ai-studio-key
SERPAPI_API_KEY=your-serpapi-key
```

Set `OPENAI_API_KEY` for OpenAI models, `GOOGLE_API_KEY` for Google Gemini models, or both if you want the full picker available in the UI.

### 5. Build or Rebuild the RAG Knowledge Base

The RAG source documents live in `knowledge_base/`, and the persisted Chroma index lives in `chroma_db/`.

If this is your first run, or if you changed any markdown files in `knowledge_base/`, rebuild the index:

```bash
python scripts/rebuild_rag.py
```

### 6. Choose Your LLM in the UI

Use the sidebar to pick:
- `OpenAI` or `Google` as the provider
- a supported model for that provider

The selected provider/model is then used for trip intake, research orchestration, and final itinerary generation.

### 7. Run the App

```bash
streamlit run app.py
```

### 8. Recommended Startup Flow

```bash
cd tripbreeze-ai
conda activate tripbreeze-ai
pip install -r requirements.txt
python scripts/rebuild_rag.py
streamlit run app.py
```

### Troubleshooting

- If you see `ModuleNotFoundError`, your Conda environment is probably not active.
- If retrieval results seem stale after editing docs in `knowledge_base/`, run `python scripts/rebuild_rag.py` again.
- If `which python` points outside your Conda env, reactivate it before running the app.

## Usage Examples

### Example 1: Basic Trip Planning
```
"I want to fly from New York to Paris, June 15 to June 22, budget $3000"
```

### Example 2: With Preferences
```
"Plan a business class trip from London to Tokyo for 2 people, September 1-10, 4-star hotels"
```

### Example 3: Budget Trip
```
"Cheapest trip from LAX to Bangkok, December 20 to January 3, max $1500"
```

### User Profile
Set up your profile in the sidebar:
- **Home Airport** — auto-fills your departure city
- **Passport Country** — gets relevant visa info via RAG
- **Preferred Class** — defaults for future searches
- **Budget Style** — influences recommendations

Your preferences are remembered across sessions.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **LangGraph** | Provides structured workflow with LLM-directed research orchestration and built-in state management |
| **SerpAPI** | Google Flights + Google Hotels via single API key; free tier with 100 searches/month |
| **ChromaDB** | Lightweight vector store that runs locally — no external database needed |
| **OpenAI or Google Gemini** | The user can choose the provider/model in the sidebar for parsing, research orchestration, and itinerary generation |
| **JSON file memory** | Simple, inspectable persistence for user profiles; no database overhead |
| **Streamlit** | Rapid UI development with built-in chat components and session state |

## Project Structure

The project follows a **layered architecture** with strict dependency rules:
each layer only imports from the layer directly below it.

```
┌──────────────────────────────────────────────┐
│  Presentation    (Streamlit UI)              │  ← user-facing
├──────────────────────────────────────────────┤
│  Application     (LangGraph, state schema)   │  ← orchestration
├──────────────────────────────────────────────┤
│  Domain          (agents, nodes, logic)      │  ← business rules
├──────────────────────────────────────────────┤
│  Infrastructure  (APIs, RAG, persistence)    │  ← external I/O
└──────────────────────────────────────────────┘
```

```
tripbreeze-ai/
├── app.py                                  # Entry point (thin bootstrap)
├── config.py                               # Centralised settings
├── presentation/                           # ── UI Layer ──
│   └── streamlit_app.py                    #    Chat interface & sidebar
├── application/                            # ── Orchestration Layer ──
│   ├── state.py                            #    Graph state schema (TypedDict)
│   └── graph.py                            #    LangGraph workflow + HITL
├── domain/                                 # ── Business Logic Layer ──
│   ├── agents/
│   │   ├── flight_agent.py                 #    Flight search node
│   │   └── hotel_agent.py                  #    Hotel search node
│   └── nodes/
│       ├── profile_loader.py               #    Load user profile
│       ├── trip_intake.py                  #    Combine form fields with LLM-parsed preferences
│       ├── budget_aggregator.py            #    Aggregate & check budget
│       ├── trip_finaliser.py               #    Generate final itinerary
│       └── memory_updater.py               #    Persist preferences
├── infrastructure/                         # ── External Services Layer ──
│   ├── apis/
│   │   └── serpapi_client.py               #    SerpAPI wrapper (flights + hotels)
│   ├── rag/
│   │   └── vectorstore.py                  #    ChromaDB build & retrieval
│   └── persistence/
│       └── memory_store.py                 #    JSON-file user profiles
├── scripts/
│   └── rebuild_rag.py                      #    Rebuild the persisted Chroma index
├── knowledge_base/                         # RAG source documents
│   ├── destinations.md                     #    City guides (10 destinations)
│   ├── visa_requirements.md                #    Visa/entry requirements
│   └── travel_tips.md                      #    General travel advice
├── memory/                                 # User profile JSON files
├── requirements.txt
├── .env.example
└── README.md
```

## Key Features

- **Real API Integration** — Live flight and hotel search via SerpAPI (Google Flights & Hotels)
- **Agentic RAG** — Retrieval is an optional tool inside the main ReAct-style research loop
- **Long-Term Memory** — User preferences persist across sessions
- **Human-in-the-Loop** — Review and approve/adjust before finalizing
- **Dynamic Tool Calling** — The LLM chooses which research tools to call based on the trip request
- **LLM Picker** — Choose between OpenAI and Google Gemini models in the sidebar
- **Structured Form + Smart Preferences** — Trip details come from form fields; free-text special requests are parsed by the LLM into filters (stops, airlines, max price, duration, etc.)
- **Budget Tracking** — Automatic cost aggregation with budget alerts
