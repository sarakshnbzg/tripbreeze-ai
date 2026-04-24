# TripBreeze AI ✈️

> Turn a trip idea into a researched, budgeted, day-by-day itinerary — with a human in the loop.

**Live:** [tripbreeze-ai.vercel.app](https://tripbreeze-ai.vercel.app) · **API:** [tripbreeze-ai.onrender.com](https://tripbreeze-ai.onrender.com)

---

## 📸 Screenshots

<p align="center">
  <img src="docs/images/auth-screen.png" alt="TripBreeze AI authentication screen" width="48%" />
  <img src="docs/images/planner-workspace.png" alt="TripBreeze AI planning workspace" width="48%" />
</p>
<p align="center"><em>Left: login. Right: planning workspace with preferences, trip history, and guided search.</em></p>

---

## ✨ What It Does

- 🗺️ Parses free-text trip requests — single-city or multi-city
- 🔍 Searches live flights and hotels via SerpAPI
- 🛂 Retrieves visa and entry guidance from a local RAG knowledge base
- 💰 Checks the budget before committing to a plan
- 🧑‍✈️ Pauses for **human review** before finalising
- 🌤️ Generates a day-by-day itinerary enriched with live weather
- 💾 Saves user preferences and trip history in Postgres

---

## 🏗️ Architecture

```text
Next.js frontend  ──(HTTP + SSE)──▶  FastAPI backend
                                            │
                                      LangGraph workflow
                                      load_profile → trip_intake → research
                                      → aggregate_budget → review
                                      → feedback_router
                                         ├─ approve → attractions → finalise → update_memory
                                         ├─ revise  → trip_intake
                                         └─ cancel
                                            │
                                      External services
                                      OpenAI · Gemini · SerpAPI · Open-Meteo · SMTP
```

Key files: [application/graph.py](application/graph.py) · [application/state.py](application/state.py) · [presentation/api.py](presentation/api.py) · [AGENTS.md](AGENTS.md)

---

## 🧰 Tech Stack

| Layer | Tools |
|---|---|
| Backend | Python 3.13, FastAPI, LangGraph, LangChain |
| LLMs | OpenAI, Google Gemini, Whisper |
| Search & Weather | SerpAPI, Open-Meteo |
| Retrieval | ChromaDB + BM25 hybrid RAG |
| Database | Postgres |
| Frontend | Next.js 15, React 19, Tailwind CSS |
| Infra | Docker |

---

## 🚀 Quick Start

### 1. Environment

```bash
cp .env.example .env
```

Minimum required:

```env
OPENAI_API_KEY=...        # or GOOGLE_API_KEY
SERPAPI_API_KEY=...
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
```

All settings are typed and documented in [settings.py](settings.py).

### 2. Backend

```bash
uv sync
uv run python scripts/rebuild_rag.py   # build RAG index
uv run python app.py                   # starts on :8100
```

Key endpoints: `GET /healthz` · `GET /docs` · `POST /api/search` · `GET /api/search/{id}/state`

### 3. Full Stack

```bash
cp frontend/.env.local.example frontend/.env.local
npm install --prefix frontend
uv run python scripts/dev.py
```

Frontend → `http://127.0.0.1:3000` · Backend → `http://127.0.0.1:8100`

Set `NEXT_PUBLIC_API_BASE_URL` if targeting a different backend.

### 4. Docker 🐳

```bash
docker compose up --build
```

---

## 🧪 Testing

```bash
# Backend
uv run pytest -q

# Frontend
npm run test --prefix frontend
npm run test:e2e --prefix frontend

# RAG evaluation
uv sync --group eval
uv run python scripts/evaluate_rag.py --provider openai
```

RAG eval results write to `evals/results/`. Add `--retrieval-only` or `--llm-judge` for targeted runs.

---

## 💬 Example Prompts

```
I want to fly from London to Tokyo from 2026-06-10 to 2026-06-17 for 2 travelers with a budget of 3000 EUR.
```
```
Paris for 3 days, then Barcelona for 4 days, then fly home.
```
```
Business class, exclude Ryanair, keep the flight under 10 hours.
```

---

## 🛡️ Ethics & Privacy

TripBreeze assists with planning — it does not replace official airline, border-control, or government sources. Entry requirements change; always verify before booking.

Hallucination risk is reduced by grounding guidance in a local knowledge base, checking budgets before finalisation, and requiring human sign-off. Full write-up: [docs/ethics.md](docs/ethics.md).

---

## ⚠️ Limitations

- Restart-safe HITL review requires Postgres-backed checkpointing
- Live search quality depends on SerpAPI quotas and source coverage
- LLM research and finalisation can still be imperfect when source data is sparse or ambiguous
- Auth is intentionally lightweight, not production-grade

---

## 🔭 Future Work

- Expand visa and entry coverage with fresher, passport-specific data
- Improve revision flows so users can adjust specific choices without restarting the full plan
- Add user-facing profile management with stronger linking to past trips
- Strengthen auth to production-grade standards
