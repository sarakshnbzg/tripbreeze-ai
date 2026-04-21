# Agents

This document describes every agent and node in the travel planning workflow,
their responsibilities, inputs, outputs, and how they connect.

## Workflow Overview

```
[START]
  │
  ▼
Profile Loader                ← loads user prefs from long-term memory
  │
  ▼
Trip Intake                   ← merges structured fields with free text; validates dates and defaults
  │
  ▼
Research Orchestrator         ← ReAct agent: decides which research tools to call
  │
  ├──────────┬──────────┬──────────┐
  ▼          ▼          ▼          ▼
Flight    Ground      Hotel      RAG
Tool      Transport   Tool       Tool
          Tool
  │          │          │          │
  └──────────┴──────────┴──────────┘
             │
             ▼
      Budget Aggregator       ← sums costs, checks budget limit
             │
             ▼
        HITL Review           ← presents options (overview + entry requirements), waits for user
             │
             ▼
      Feedback Router         ← pauses for approve / revise / cancel
        ┌────┼────┐
        ▼    ▼    ▼
  Attractions Trip Intake [END]
        │
        ▼
    Finaliser                ← approve path; revise loops back through intake
        │
        ├── RAG Tool          ← uses grounded entry requirements prepared earlier
        │
        ▼
   Memory Updater             ← persists learned preferences
        │
        ▼
      [END]
```

---

## Research Layer

### Research Orchestrator

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/research_orchestrator.py` |
| **Node name** | `research` |
| **Implementation** | `research_orchestrator(...)` |
| **Purpose** | ReAct agent that dynamically chooses which research tools to call for the current trip |
| **LLM** | User-selected OpenAI or Google Gemini chat model with tool calling |
| **Reads from state** | `trip_request`, `trip_legs` (for multi-city), `user_profile`, `llm_provider`, `llm_model` |
| **Writes to state** | `flight_options`, `hotel_options`, `destination_info` (entry requirements only), `rag_sources`, research summary message; for multi-city: `flight_options_by_leg`, `hotel_options_by_leg` |
| **Tool choices** | `search_flights`, `search_hotels`, `retrieve_knowledge`, `SubmitResearchResult` |
| **Routing behavior** | May call any subset of tools, including skipping retrieval entirely or calling it multiple times, and finishes by calling `SubmitResearchResult` |
| **Multi-city** | When `trip_legs` is present, searches flights and hotels per leg (one-way flights) and aggregates results into `*_by_leg` fields |
| **RAG output** | Only extracts grounded `entry_requirements` from the local knowledge base |

### Flight Tool

| Field | Detail |
|-------|--------|
| **File** | `domain/agents/flight_agent.py` |
| **Callable name** | `search_flights` (single-destination), `search_leg_flights` (per-leg for multi-city) |
| **Purpose** | Search real flights for the requested route and dates |
| **Infrastructure** | `infrastructure/apis/serpapi_client.search_flights` (Google Flights) |
| **Reads from state** | `trip_request` (origin, destination, dates, class, travellers, currency) |
| **Writes to state** | `flight_options` — list of dicts with airline, times, duration, stops, price |
| **Multi-city** | `search_leg_flights` searches one-way flights for a single leg, used when iterating over `trip_legs` |
| **Error handling** | Returns empty list + status message on missing inputs or API failure |

### Hotel Tool

| Field | Detail |
|-------|--------|
| **File** | `domain/agents/hotel_agent.py` |
| **Callable name** | `search_hotels` (single-destination), `search_leg_hotels` (per-leg for multi-city) |
| **Purpose** | Search real hotels in the destination city |
| **Infrastructure** | `infrastructure/apis/serpapi_client.search_hotels` (Google Hotels) |
| **Reads from state** | `trip_request` (destination, check-in/out, star rating, travellers, currency) |
| **Writes to state** | `hotel_options` — list of dicts with name, description, rating, price, amenities |
| **Multi-city** | `search_leg_hotels` searches hotels for a single leg's destination and dates |
| **Error handling** | Returns empty list + status message on missing inputs or API failure |

### Knowledge Retrieval Tool

| Field | Detail |
|-------|--------|
| **Callable name** | `retrieve_knowledge` |
| **Purpose** | Search the local knowledge base for visa and entry requirement information |
| **Infrastructure** | `infrastructure/rag/vectorstore.retrieve` (ChromaDB) |
| **Used by** | Research orchestrator for entry requirements; Trip Finaliser consumes the grounded result already prepared earlier |
| **Behavior** | Optional tool inside both ReAct loops; may be skipped or called multiple times |
| **Output** | Retrieved knowledge-base chunks that agents use to write grounded destination information |
| **Knowledge base** | `knowledge_base/visa_requirements.md` |

#### RAG Retrieval Sketch

```
User/tool query
  │
  ▼
Enrich query with trip context where helpful
  │
  ▼
Load local visa knowledge base
  │
  ▼
Split docs into chunks
  │
  ▼
Attach chunk metadata
  └─ source_type, heading, city, country, topics
  │
  ▼
Infer query metadata
  └─ e.g. city, country, visa / transport / budget / safety intent
  │
  ▼
Run metadata-aware retrieval
  ├─ Chroma vector similarity with source/place filters when possible
  └─ BM25 keyword search over filtered chunks
  │
  ▼
Merge and dedupe candidates
  │
  ▼
Return top chunks + source labels
  │
  ▼
Research Orchestrator / Trip Finaliser uses them to write grounded output
```

Notes:
- Retrieval itself now uses metadata-aware narrowing before results are merged.
- The retriever returns chunk text plus source labels; the calling nodes decide how to summarise and cite it.

---

## Nodes (sequential pipeline)

### Profile Loader

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/profile_loader.py` |
| **Node name** | `load_profile` |
| **Purpose** | Load the user's saved preferences from long-term memory |
| **Infrastructure** | `infrastructure/persistence/memory_store.load_profile` |
| **Reads from state** | `user_id` |
| **Writes to state** | `user_profile` (home airport, travel class, budget style, passport, past trips) |

### Trip Intake

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/trip_intake.py` |
| **Node name** | `trip_intake` |
| **Purpose** | Build trip request from structured form fields and/or free text, classify out-of-domain requests, and validate trip details |
| **LLM** | User-selected OpenAI or Google Gemini chat model with tool calling |
| **Tool schema** | `EvaluateDomain`, `ExtractTripDetails` (single-destination), `ExtractMultiCityTrip` (multi-city), `ExtractPreferences` |
| **Reads from state** | `structured_fields` (form inputs), `user_profile` (for defaults), `llm_provider`, `llm_model` |
| **Writes to state** | `trip_request` — dict with origin, destination, dates, class, budget, stops, max_flight_price, airlines, etc.; `trip_legs` — list of leg dicts for multi-city trips |
| **Multi-city detection** | LLM chooses `ExtractMultiCityTrip` for queries like "Paris for 3 days, then Barcelona for 4 days"; builds `trip_legs` with origin, destination, departure_date, nights, needs_hotel per leg. The final return-to-origin leg is appended only when `return_to_origin=true` (default); open-jaw / one-way multi-city trips skip it. The form UI exposes this via the "One-way" checkbox when multi-city is enabled |
| **Behavior notes** | Free text can provide the whole trip request, structured fields take precedence when both are present, and one-way trips default to a 7-night stay if no check-out date is given |

### Budget Aggregator

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/budget_aggregator.py` |
| **Node name** | `aggregate_budget` |
| **Purpose** | Sum cheapest flight + hotel + estimated daily expenses; check vs budget limit |
| **Pure logic** | No LLM, no API — arithmetic only |
| **Reads from state** | `trip_request`, `trip_legs`, `flight_options`, `hotel_options`, `flight_options_by_leg`, `hotel_options_by_leg` |
| **Writes to state** | `budget` — dict with cost breakdown, total, within_budget flag, notes; for multi-city includes `per_leg_breakdown` |
| **Multi-city** | Aggregates costs per leg (flight + hotel + daily expenses per destination) and calculates grand total |
| **Daily estimate** | Configurable via `config.DEFAULT_DAILY_EXPENSE` (default $80/day) |

### HITL Review

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/hitl_review.py` |
| **Node name** | `review` |
| **Purpose** | Format research results for human review before the graph asks for the next action |
| **Pure logic** | String formatting only |
| **Reads from state** | `flight_options`, `hotel_options`, `trip_legs`, `flight_options_by_leg`, `hotel_options_by_leg`, `budget`, `destination_info`, `rag_sources`, `trip_request` |
| **Writes to state** | Formatted review message |
| **What's shown** | Entry requirements, trip summary, budget notes |
| **Multi-city** | Shows leg-by-leg summary table with route, dates, and nights per destination |
| **Routing** | Always hands off to `feedback_router`, which pauses for `approve`, `revise_plan`, or `cancel` |

### Feedback Router

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/review_router.py` |
| **Node name** | `feedback_router` |
| **Purpose** | Pause the graph after review and route based on the user's decision |
| **Implementation** | Uses LangGraph `interrupt(...)` to wait for a structured review decision |
| **Reads from state** | `user_feedback`, `feedback_type`, `trip_request`, `trip_legs`, selected options |
| **Writes to state** | For `approve`: keeps selections and continues to itinerary generation. For `revise_plan`: builds a `revision_baseline`, clears prior options, writes revision feedback back into `free_text_query`, and loops to `trip_intake`. For `cancel`: routes to `END` |
| **Revision behavior** | Simple duration changes like "make it 5 nights" patch the existing trip deterministically before intake reruns, so old dates do not override the revised stay length |

### Attractions Research

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/attractions_research.py` |
| **Node name** | `attractions` |
| **Purpose** | Fetch attraction candidates after approval so the final itinerary uses the final interests and destinations |
| **Reads from state** | `trip_request`, `trip_legs` |
| **Writes to state** | `attraction_candidates` |

### Trip Finaliser

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/trip_finaliser.py` |
| **Node name** | `finalise` |
| **Purpose** | ReAct agent that generates a polished, professional itinerary document with grounded destination tips |
| **LLM** | User-selected OpenAI or Google Gemini chat model with tool calling (temperature 0.5) |
| **Tool choices** | `Itinerary` (single-destination), `MultiCityItinerary` (multi-city) |
| **Reads from state** | `trip_request`, `trip_legs`, `selected_flight`, `selected_hotel`, `selected_flights`, `selected_hotels`, `destination_info`, `budget`, `user_feedback`, `attraction_candidates`, `rag_sources`, `llm_provider`, `llm_model` |
| **Writes to state** | `final_itinerary` — complete markdown itinerary, `itinerary_data` — structured data, `rag_sources` — updated with any new sources |
| **Behavior** | Uses grounded entry requirements already prepared earlier in the flow; submits via `Itinerary` or `MultiCityItinerary` tool call |
| **Multi-city** | Uses `_finalise_multi_city()` when `trip_legs` present; generates per-leg flight/hotel details and combined itinerary |
| **Weather** | After LLM generates the itinerary, enriches each daily plan with weather forecasts from Open-Meteo (forecasts up to 16 days, historical data for dates beyond) |

### Memory Updater

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/memory_updater.py` |
| **Node name** | `update_memory` |
| **Purpose** | Persist preferences learned during this session to long-term memory |
| **Infrastructure** | `infrastructure/persistence/memory_store.update_profile_from_trip` |
| **Reads from state** | `user_id`, `trip_request`, `user_profile` |
| **Writes to state** | Updated `user_profile` |
| **What it saves** | Home airport (first time only), travel class, passport country, trip to history (last 10) |

---

## State Schema

Defined in `application/state.py` as `TravelState` (TypedDict).
The state includes `structured_fields` (form inputs passed directly from the UI), `llm_provider` and `llm_model` so the user-selected OpenAI or Google Gemini model flows through the graph.
The `messages` field uses `operator.add` for append-only accumulation across nodes.

### Multi-City State Fields

For multi-city trips, additional fields are populated:

| Field | Type | Description |
|-------|------|-------------|
| `trip_legs` | `list[dict]` | List of leg dicts with `origin`, `destination`, `departure_date`, `nights`, `needs_hotel`, `check_out_date` |
| `flight_options_by_leg` | `list[list[dict]]` | Flight options indexed by leg number |
| `hotel_options_by_leg` | `list[list[dict]]` | Hotel options indexed by leg number |
| `selected_flights` | `list[dict]` | User-selected flight per leg |
| `selected_hotels` | `list[dict]` | User-selected hotel per leg (empty dict if no hotel needed) |
| `feedback_type` | `str` | Review decision type such as `rewrite_itinerary`, `revise_plan`, or `cancel` |
| `revision_baseline` | `dict` | Working copy of the current trip request used when a revise action should override existing values instead of only filling empty fields |

The trip intake's `structured_fields` payload may also carry `return_to_origin: bool` (defaults to `true`). When `false`, the intake skips the synthetic return leg, producing an open-jaw / one-way multi-city itinerary.

## Configuration

All model names, API keys, search limits, and file paths are centralised in `config.py`.
Agents and nodes import settings from there — never from environment variables directly.
