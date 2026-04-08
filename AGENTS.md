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
Research Orchestrator         ← LLM decides which research tools to call
  │
  ├──────────┬──────────┐
  ▼          ▼          ▼
Flight    Hotel      RAG
Tool      Tool       Tool
  │          │          │
  └──────────┴──────────┘
             │
             ▼
      Budget Aggregator       ← sums costs, checks budget limit
             │
             ▼
        HITL Review           ← presents options, waits for user
             │
        ┌────┴────┐
        ▼         ▼
    Finaliser   [END]         ← approve → finalise; feedback → stop
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
| **Purpose** | Let the LLM dynamically choose which research tools to call for the current trip |
| **LLM** | User-selected OpenAI or Google Gemini chat model with tool calling |
| **Reads from state** | `trip_request`, `user_profile`, `llm_provider`, `llm_model` |
| **Writes to state** | `flight_options`, `hotel_options`, `destination_info`, research summary message |
| **Tool choices** | `search_flights`, `search_hotels`, `retrieve_knowledge`, `SubmitResearchResult` |
| **Routing behavior** | May call any subset of tools, including skipping retrieval entirely or calling it multiple times, and finishes by calling `SubmitResearchResult` |

### Flight Tool

| Field | Detail |
|-------|--------|
| **File** | `domain/agents/flight_agent.py` |
| **Callable name** | `search_flights` |
| **Purpose** | Search real flights for the requested route and dates |
| **Infrastructure** | `infrastructure/apis/serpapi_client.search_flights` (Google Flights) |
| **Reads from state** | `trip_request` (origin, destination, dates, class, travellers, currency) |
| **Writes to state** | `flight_options` — list of dicts with airline, times, duration, stops, price |
| **Error handling** | Returns empty list + status message on missing inputs or API failure |

### Hotel Tool

| Field | Detail |
|-------|--------|
| **File** | `domain/agents/hotel_agent.py` |
| **Callable name** | `search_hotels` |
| **Purpose** | Search real hotels in the destination city |
| **Infrastructure** | `infrastructure/apis/serpapi_client.search_hotels` (Google Hotels) |
| **Reads from state** | `trip_request` (destination, check-in/out, star rating, travellers, currency) |
| **Writes to state** | `hotel_options` — list of dicts with name, address, rating, price, amenities |
| **Error handling** | Returns empty list + status message on missing inputs or API failure |

### Knowledge Retrieval Tool

| Field | Detail |
|-------|--------|
| **Active location** | `domain/nodes/research_orchestrator.py` |
| **Callable name** | `retrieve_knowledge` |
| **Purpose** | Search the local knowledge base for destination guides, visa requirements, travel tips, transport, safety, and budget information |
| **Infrastructure** | `infrastructure/rag/vectorstore.retrieve` (ChromaDB) |
| **Used by** | The main `research` node, which decides whether retrieval is useful |
| **Behavior** | Optional tool inside the orchestrator's ReAct loop; may be skipped or called multiple times |
| **Output** | Retrieved knowledge-base chunks that the orchestrator uses to write `destination_info` |
| **Knowledge base** | `knowledge_base/destinations.md`, `visa_requirements.md`, `travel_tips.md` |

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
| **Tool schema** | `EvaluateDomain`, `ExtractTripDetails`, `ExtractPreferences` |
| **Reads from state** | `structured_fields` (form inputs), `user_profile` (for defaults), `llm_provider`, `llm_model` |
| **Writes to state** | `trip_request` — dict with origin, destination, dates, class, budget, stops, max_flight_price, airlines, etc. |
| **Behavior notes** | Free text can provide the whole trip request, structured fields take precedence when both are present, and one-way trips default to a 7-night stay if no check-out date is given |

### Budget Aggregator

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/budget_aggregator.py` |
| **Node name** | `aggregate_budget` |
| **Purpose** | Sum cheapest flight + hotel + estimated daily expenses; check vs budget limit |
| **Pure logic** | No LLM, no API — arithmetic only |
| **Reads from state** | `trip_request`, `flight_options`, `hotel_options` |
| **Writes to state** | `budget` — dict with cost breakdown, total, within_budget flag, notes |
| **Daily estimate** | Configurable via `config.DEFAULT_DAILY_EXPENSE` (default $80/day) |

### HITL Review

| Field | Detail |
|-------|--------|
| **File** | `application/graph.py` (inline) |
| **Node name** | `review` |
| **Purpose** | Format research results for human review; pause for approval |
| **Pure logic** | String formatting only |
| **Reads from state** | `flight_options`, `hotel_options`, `budget`, `destination_info` |
| **Writes to state** | Formatted review message |
| **Routing** | If `user_approved` → `finalise`; otherwise → `END` (UI waits for input) |

### Trip Finaliser

| Field | Detail |
|-------|--------|
| **File** | `domain/nodes/trip_finaliser.py` |
| **Node name** | `finalise` |
| **Purpose** | Generate a polished, professional itinerary document |
| **LLM** | User-selected OpenAI or Google Gemini chat model (temperature 0.5) |
| **Reads from state** | `trip_request`, `flight_options`, `hotel_options`, `destination_info`, `budget`, `user_feedback`, `llm_provider`, `llm_model` |
| **Writes to state** | `final_itinerary` — complete markdown itinerary |

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

## Configuration

All model names, API keys, search limits, and file paths are centralised in `config.py`.
Agents and nodes import settings from there — never from environment variables directly.
