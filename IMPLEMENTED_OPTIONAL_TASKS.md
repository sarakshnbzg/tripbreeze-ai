# Implemented Optional Tasks

This document summarises the optional upgrade tasks that are implemented in
TripBreeze AI, based on the current codebase.

## Implemented

### User-selectable LLMs

The app lets users choose between OpenAI and Google Gemini models from the
Streamlit sidebar.

Evidence:

- `presentation/streamlit_app.py` implements the provider toggle and model selector.
- `infrastructure/llms/model_factory.py` defines supported OpenAI and Google Gemini models and creates the selected chat model.
- `application/state.py` carries `llm_provider` and `llm_model` through the graph state.

Optional task covered:

- Provide the user with the ability to choose from a list of LLMs (Gemini, OpenAI, etc.) for this project.
- Implement multi-model support (OpenAI, Anthropic, etc.) partially, with OpenAI and Google Gemini support.

### Token Usage and Cost Display

The app tracks token usage from LLM calls and displays estimated cost in the
sidebar.

Evidence:

- `infrastructure/llms/model_factory.py` includes `extract_token_usage`.
- `presentation/streamlit_app.py` includes `_render_token_usage`.
- `application/state.py` includes append-only `token_usage` state.
- `config.py` centralises model cost settings.

Optional task covered:

- Calculate and display token usage and costs.

### Retry Logic for LLM Calls

LLM calls are wrapped with retry logic for transient failures such as timeouts,
rate limits, connection failures, and server errors.

Evidence:

- `infrastructure/llms/model_factory.py` includes `invoke_with_retry`, using Tenacity with exponential backoff.
- `domain/nodes/trip_intake.py`, `domain/nodes/research_orchestrator.py`, and `domain/nodes/trip_finaliser.py` call LLMs via `invoke_with_retry`.

Optional task covered:

- Add retry logic for agents.

### Long-term Memory

The app persists user preferences and trip history in a Neon/Postgres database and
loads them at the beginning of the graph.

Evidence:

- `infrastructure/persistence/memory_store.py` handles Postgres-backed profile loading, saving, listing, and updating.
- `domain/nodes/profile_loader.py` loads the user profile.
- `domain/nodes/memory_updater.py` updates learned preferences after finalisation.
- `application/graph.py` wires `load_profile` and `update_memory` into the LangGraph workflow.

Optional task covered:

- Implement long-term or short-term memory in LangChain/LangGraph.

### External API Function Tools

The research workflow includes external API-backed tools for live flight and
hotel search.

Evidence:

- `domain/agents/flight_agent.py` exposes flight search logic.
- `domain/agents/hotel_agent.py` exposes hotel search logic.
- `infrastructure/apis/serpapi_client.py` calls SerpAPI Google Flights and Google Hotels.
- `domain/nodes/research_orchestrator.py` registers `search_flights` and `search_hotels` as LLM-callable tools.

Optional task covered:

- Implement one more function tool that would call an external API.
- Implement an agent that can integrate with external data sources to enrich its knowledge.

### Caching Mechanism

The RAG layer caches loaded chunks, Chroma vectorstores, and the BM25 retriever
in memory. Chroma indexes are also persisted on disk.

Evidence:

- `infrastructure/rag/vectorstore.py` defines `_cached_chunks`, `_cached_vectorstores`, and `_cached_bm25`.
- `infrastructure/rag/vectorstore.py` loads existing Chroma indexes from `chroma_db` when available.
- `scripts/rebuild_rag.py` supports rebuilding the persisted RAG index.

Optional task covered:

- Implement a caching mechanism to store and retrieve frequently used responses.

Note: this is implemented specifically for RAG retrieval/indexing rather than
as a general cache for every chatbot response.

### Agentic RAG

The research orchestrator gives the LLM an optional RAG retrieval tool and lets
the model decide when to call it.

Evidence:

- `domain/nodes/research_orchestrator.py` defines the ReAct-style research prompt.
- `domain/nodes/research_orchestrator.py` registers `retrieve_knowledge` as a tool.
- `infrastructure/rag/vectorstore.py` implements hybrid retrieval using Chroma vector search and BM25.
- `knowledge_base/destinations.md`, `knowledge_base/visa_requirements.md`, and `knowledge_base/travel_tips.md` provide the local knowledge base.

Optional task covered:

- Agentic RAG: add RAG functionality to the LangChain/LangGraph application and implement it.

### LangSmith Observability

The project includes LangSmith tracing configuration through environment or
Streamlit secrets, and a LangSmith project dashboard is available for viewing
traces.

Evidence:

- `config.py` reads `LANGCHAIN_TRACING_V2`, `LANGCHAIN_PROJECT`, and `LANGCHAIN_API_KEY`.
- `config.py` sets the relevant LangChain environment variables when tracing is enabled.
- LangSmith dashboard: <https://smith.langchain.com/o/877c675a-ba6b-46dd-8d36-826feba406a5/dashboards/projects/26b438d7-28b2-4404-bb1f-74410a14ed91>

Optional task covered:

- Add one of these LLM observability tools: Arize Phoenix, LangSmith, Lunary, or others.

## Partially Implemented

### Feedback Handling

The user can provide special requests or adjustments before generating the final
itinerary. This feedback is passed into the finaliser prompt.

Evidence:

- `presentation/streamlit_app.py` captures optional user feedback in the review screen.
- `domain/nodes/trip_finaliser.py` includes `user_feedback` in the final itinerary prompt.
- `application/state.py` includes `user_feedback`.

Optional task partially covered:

- Implement a feedback loop where users can rate the responses, and use this feedback to improve the agent's performance.
- Create an agent that can learn from user feedback.

Note: this is not a full learning or rating loop. The feedback affects the
current final itinerary only.

## Not Found in the Current Codebase

The following optional tasks do not appear to be implemented yet:

- Ask ChatGPT to critique the solution from usability, security, and prompt-engineering sides.
- Give the agent a user-selectable personality.
- Add OpenAI temperature and top-p sliders or fields.
- Add an interactive help feature or chatbot guide.
- Add user authentication and personalisation beyond local profile IDs.
- Add a response rating system that improves future performance.
- Add a plugin system or UI to enable and disable tools dynamically.
- Add Anthropic support.
- Fine-tune the model for the travel domain.
- Build a feedback-learning agent that changes future behavior from ratings.
- Implement distributed multi-agent collaboration.
- Deploy the app to the cloud with proper scaling.
