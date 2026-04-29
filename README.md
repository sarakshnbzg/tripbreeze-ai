# TripBreeze AI ✈️

TripBreeze AI is an agentic travel planner that turns a free-text trip request into a fully researched, budgeted, and weather-enriched itinerary. It orchestrates a multi-step AI pipeline for live flight and hotel search, grounded entry-requirement research, budget validation, and day-by-day itinerary generation, with a human-in-the-loop review step before anything gets locked in.

Built on LangGraph with a FastAPI backend and Next.js frontend, it supports single-city and multi-city trips, remembers preferences across sessions, and streams results in real time.

**Live:** [tripbreeze-ai.vercel.app](https://tripbreeze-ai.vercel.app) · **API:** [tripbreeze-ai.onrender.com](https://tripbreeze-ai.onrender.com)

---

## 🖼️ Screenshots

<p align="center">
  <img src="docs/images/auth-screen.png" alt="TripBreeze AI authentication screen" width="48%" />
  <img src="docs/images/planner-workspace.png" alt="TripBreeze AI planning workspace" width="48%" />
</p>
<p align="center"><em>Left: login. Right: planning workspace with preferences, trip history, and guided search.</em></p>

---

## ✨ What It Does

- 🎙️ Accepts trip requests by text or voice (Whisper transcription)
- 🗣️ Parses free-text input — single-city or multi-city
- 🔎 Searches live flights and hotels via SerpAPI
- 🛂 Retrieves grounded entry guidance from a local RAG knowledge base
- 💸 Checks the budget before committing to a plan
- 🧑‍⚖️ Pauses for **human review** before finalising
- 🌤️ Generates a day-by-day itinerary enriched with live weather
- 🗂️ Saves user preferences and trip history in Postgres
- 🔐 Uses session cookies, CSRF protection, and per-route rate limiting for authenticated API access

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

## 🛠️ Tech Stack

| Layer | Tools |
|---|---|
| Backend | Python 3.13, FastAPI, LangGraph, LangChain |
| LLMs | OpenAI or Gemini for chat, OpenAI embeddings/moderation, Whisper |
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
OPENAI_API_KEY=...
SERPAPI_API_KEY=...
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
```

`DATABASE_URL` is required for auth, profiles, long-term memory, and restart-safe HITL review. Set `SESSION_SECRET` as well before deploying anywhere shared or public.

Optional for Gemini chat:

```env
GOOGLE_API_KEY=...
```

OpenAI is still required for embeddings, moderation, and transcription even if you use Gemini for chat.

All settings are typed and documented in [settings.py](settings.py).

### 2. Backend

```bash
uv sync
uv run python scripts/rebuild_rag.py   # build RAG index
uv run python app.py                   # starts on :8100
```

Key endpoints: `GET /healthz` · `GET /docs` · `POST /api/auth/login` · `POST /api/search` · `POST /api/transcribe` · `POST /api/itinerary/pdf`

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

## 🗺️ Example Prompts

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

- Restart-safe HITL review requires Postgres-backed checkpointing, and staging/production now fail fast if `DATABASE_URL` is missing
- Live search quality depends on SerpAPI quotas, source coverage, and usage costs that can rise with repeated searches
- The end-to-end planning flow depends on several external services such as OpenAI, SerpAPI, Postgres, and optional SMTP, so upstream outages or rate limits can degrade the user experience even when the application itself is healthy
- The app currently runs as a single-region deployment, so distant users and regional outages can still affect latency and availability
- End-to-end latency can vary noticeably because research, retrieval, and itinerary generation combine multiple network-bound steps
- LLM research and finalisation can still be imperfect when source data is sparse or ambiguous
- Auth is suitable for demos and small deployments, but broader production hardening is still needed
- Golden-prompt replay tests cover intake, research, and finaliser flows, but offline evaluation breadth is still limited compared with a larger curated dataset or live judge pipeline

---

## 🔭 Future Work

- Expand visa and entry coverage with fresher, passport-specific data
- Broaden offline evaluation with more golden cases, regression thresholds, and scheduled judge runs
- Add deeper robustness testing for messy prompts, conflicting constraints, and longer revision loops
- Add graceful fallback and partial-result handling when external providers are slow, unavailable, or rate-limited
- Improve revision flows so users can adjust specific choices without restarting the full plan
- Add user-facing profile management with stronger linking to past trips
- Strengthen auth to production-grade standards
