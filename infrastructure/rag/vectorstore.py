"""ChromaDB vector store — builds and queries the RAG knowledge base.

Uses hybrid search (vector similarity + BM25 keyword matching) via
LangChain's EnsembleRetriever for better retrieval quality.
"""

from __future__ import annotations

import re
import shutil
import time
from functools import lru_cache

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHROMA_ROOT_DIR,
    DEFAULT_LLM_PROVIDER,
    KNOWLEDGE_BASE_DIR,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_VECTOR_WEIGHT,
    RAG_BM25_WEIGHT,
    RAG_EMBEDDING_BATCH_SIZE,
    RAG_EMBEDDING_MAX_RETRIES,
    RAG_GOOGLE_EMBEDDING_BATCH_DELAY_SECONDS,
)
from infrastructure.llms.model_factory import create_embeddings, normalise_llm_selection
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

# Module-level caches
_cached_chunks: list | None = None
_cached_vectorstores: dict[str, Chroma] = {}
_cached_bm25: BM25Retriever | None = None


def _normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _extract_heading(page_content: str) -> str:
    match = re.search(r"^##\s+(.+)$", page_content or "", flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _detect_topics(page_content: str, source_type: str) -> list[str]:
    lowered = (page_content or "").lower()
    topics: set[str] = set()

    keyword_map = {
        "entry_requirements": ["visa-free", "visa required", "documents needed", "passport", "entry requirements"],
        "transport": ["local transport", "metro", "tram", "subway", "bus", "ferry", "cycling", "bike"],
        "budget": ["budget tip", "average daily budget", "daily budget", "cheap", "value destination"],
        "safety": ["## safety", "- **safety:", "pickpocket", "scam", "situational awareness"],
        "packing": ["packing", "carry-on", "packing cubes", "essential documents"],
        "health": ["vaccinations", "water safety", "altitude sickness", "travel pharmacy", "jet lag"],
        "flight_booking": ["book early", "nearby airports", "layovers", "budget airlines", "red-eye"],
        "hotel_booking": ["check cancellation policy", "book directly", "location matters", "recent reviews"],
        "etiquette": ["dress codes", "photography", "haggling", "religious sensitivity", "left hand"],
    }

    for topic, keywords in keyword_map.items():
        if any(keyword in lowered for keyword in keywords):
            topics.add(topic)

    if source_type == "destinations":
        topics.add("destination_overview")
    if source_type == "visa_requirements":
        topics.add("entry_requirements")

    return sorted(topics)


def _extract_doc_metadata(source_path: str, page_content: str) -> dict[str, str | list[str]]:
    heading = _extract_heading(page_content)
    source_stem = _normalise_text(source_path.split("/")[-1].replace(".md", ""))
    source_type = source_stem.replace(" ", "_")
    city = ""
    country = ""

    if source_type == "destinations" and heading:
        if "," in heading:
            city, country = [part.strip() for part in heading.split(",", 1)]
        else:
            city = heading.strip()
    elif source_type == "visa_requirements" and heading:
        country = heading.split("(", 1)[0].strip()
    elif source_type == "travel_tips" and heading:
        country = ""

    topics = _detect_topics(page_content, source_type)

    metadata: dict[str, str | list[str]] = {
        "source_type": source_type,
        "heading": heading,
        "city": city,
        "country": country,
    }
    if topics:
        metadata["topics"] = topics
    return metadata


@lru_cache(maxsize=1)
def _known_places() -> list[tuple[str, str, str]]:
    places: list[tuple[str, str, str]] = []
    for path in (KNOWLEDGE_BASE_DIR / "destinations.md", KNOWLEDGE_BASE_DIR / "visa_requirements.md"):
        text = path.read_text(encoding="utf-8")
        source_type = path.stem
        for match in re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE):
            heading = match.group(1).strip()
            if source_type == "destinations":
                city, _, country = heading.partition(",")
                city = city.strip()
                country = country.strip()
                if city:
                    places.append((_normalise_text(city), "city", city))
                if country:
                    places.append((_normalise_text(country.split("(", 1)[0].strip()), "country", country.split("(", 1)[0].strip()))
            else:
                country = heading.split("(", 1)[0].strip()
                if country:
                    places.append((_normalise_text(country), "country", country))
    return places


def _infer_query_metadata(query: str) -> dict[str, str | list[str]]:
    lowered = _normalise_text(query)
    city = ""
    country = ""
    for alias, kind, canonical in _known_places():
        if alias and re.search(rf"\b{re.escape(alias)}\b", lowered):
            if kind == "city" and not city:
                city = canonical
            if kind == "country" and not country:
                country = canonical

    intents: list[str] = []
    intent_patterns = {
        "entry_requirements": ["visa", "entry requirement", "passport", "etias"],
        "transport": ["transport", "get around", "metro", "tram", "subway", "bus", "bike"],
        "budget": ["budget", "cheap", "money-saving", "expensive", "value"],
        "safety": ["safety", "safe", "scam", "street smarts"],
        "packing": ["packing", "pack"],
        "health": ["health", "vaccination", "altitude", "water safety"],
        "flight_booking": ["flight-booking", "book flights", "flight strategy", "layover"],
        "hotel_booking": ["hotel-booking", "hotel booking", "book hotels"],
        "etiquette": ["etiquette", "cultural", "dress code", "haggling"],
    }
    for intent, keywords in intent_patterns.items():
        if any(keyword in lowered for keyword in keywords):
            intents.append(intent)

    return {"city": city, "country": country, "intents": intents, "query": lowered}


def _score_doc_for_query(doc, query_meta: dict[str, str | list[str]], rank_index: int) -> float:
    score = max(0.0, 20.0 - rank_index)
    metadata = getattr(doc, "metadata", {}) or {}
    doc_city = _normalise_text(str(metadata.get("city", "")))
    doc_country = _normalise_text(str(metadata.get("country", "")))
    doc_source_type = str(metadata.get("source_type", ""))
    doc_topics = set(metadata.get("topics", []) or [])
    query_city = _normalise_text(str(query_meta.get("city", "")))
    query_country = _normalise_text(str(query_meta.get("country", "")))
    query_intents = set(query_meta.get("intents", []) or [])

    if query_city and doc_city:
        score += 8 if doc_city == query_city else -4
    if query_country and doc_country:
        score += 6 if doc_country == query_country else -3

    if "entry_requirements" in query_intents:
        score += 10 if doc_source_type == "visa_requirements" else -2
        if "entry_requirements" in doc_topics:
            score += 4
    if "transport" in query_intents and "transport" in doc_topics:
        score += 5
    if "budget" in query_intents and "budget" in doc_topics:
        score += 5
    if "safety" in query_intents and "safety" in doc_topics:
        score += 5
    if "packing" in query_intents and "packing" in doc_topics:
        score += 5
    if "health" in query_intents and "health" in doc_topics:
        score += 5
    if "flight_booking" in query_intents and "flight_booking" in doc_topics:
        score += 5
    if "hotel_booking" in query_intents and "hotel_booking" in doc_topics:
        score += 5
    if "etiquette" in query_intents and "etiquette" in doc_topics:
        score += 5

    if not query_intents and doc_source_type == "destinations":
        score += 2

    return score


def _rerank_docs_for_query(docs: list, query: str, k: int) -> list:
    query_meta = _infer_query_metadata(query)
    base_scores = [
        (_score_doc_for_query(doc, query_meta, idx), idx, doc)
        for idx, doc in enumerate(docs)
    ]
    rescored = sorted(base_scores, key=lambda item: item[0], reverse=True)

    seen: set[tuple[str, str]] = set()
    deduped = []
    selected_source_types: list[str] = []
    selected_headings: list[str] = []

    while rescored and len(deduped) < k:
        best_choice = None
        best_adjusted_score = None

        for base_score, original_index, doc in rescored:
            metadata = getattr(doc, "metadata", {}) or {}
            key = (
                str(metadata.get("source", "")),
                (getattr(doc, "page_content", "") or "")[:120],
            )
            if key in seen:
                continue

            source_type = str(metadata.get("source_type", ""))
            heading = str(metadata.get("heading", ""))
            adjusted_score = base_score

            adjusted_score -= 1.25 * selected_source_types.count(source_type)
            if heading:
                adjusted_score -= 0.75 * selected_headings.count(heading)
            if source_type and source_type not in selected_source_types:
                adjusted_score += 1.5

            if best_adjusted_score is None or adjusted_score > best_adjusted_score:
                best_adjusted_score = adjusted_score
                best_choice = (base_score, original_index, doc)

        if best_choice is None:
            break

        rescored.remove(best_choice)
        _, _, chosen_doc = best_choice
        chosen_metadata = getattr(chosen_doc, "metadata", {}) or {}
        chosen_key = (
            str(chosen_metadata.get("source", "")),
            (getattr(chosen_doc, "page_content", "") or "")[:120],
        )
        seen.add(chosen_key)
        deduped.append(chosen_doc)
        selected_source_types.append(str(chosen_metadata.get("source_type", "")))
        selected_headings.append(str(chosen_metadata.get("heading", "")))

    return deduped


def _batched(items: list, batch_size: int):
    """Yield non-empty batches from a list."""
    safe_batch_size = max(1, batch_size)
    for index in range(0, len(items), safe_batch_size):
        yield items[index : index + safe_batch_size]


def _retry_delay_from_error(exc: Exception) -> float | None:
    """Extract a provider-suggested retry delay from quota errors when present."""
    message = str(exc)
    patterns = [
        r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry in (\d+(?:\.\d+)?)s",
        r"Please retry in (\d+(?:\.\d+)?)s",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _add_documents_with_quota_backoff(
    *,
    vectorstore: Chroma,
    chunks: list,
    provider: str,
) -> None:
    """Add chunks in batches, slowing down for providers with strict embedding quotas."""
    is_google = provider == "google"
    batch_delay = RAG_GOOGLE_EMBEDDING_BATCH_DELAY_SECONDS if is_google else 0
    batches = list(_batched(chunks, RAG_EMBEDDING_BATCH_SIZE))

    for batch_number, batch in enumerate(batches, start=1):
        for attempt in range(1, RAG_EMBEDDING_MAX_RETRIES + 1):
            try:
                logger.info(
                    "Adding RAG embedding batch provider=%s batch=%s/%s size=%s attempt=%s",
                    provider,
                    batch_number,
                    len(batches),
                    len(batch),
                    attempt,
                )
                vectorstore.add_documents(batch)
                break
            except Exception as exc:
                if attempt >= RAG_EMBEDDING_MAX_RETRIES:
                    raise
                retry_delay = _retry_delay_from_error(exc)
                fallback_delay = min(60, 2 ** attempt)
                sleep_seconds = retry_delay if retry_delay is not None else fallback_delay
                logger.warning(
                    "Embedding batch failed; retrying provider=%s batch=%s/%s attempt=%s sleep_seconds=%s error=%s",
                    provider,
                    batch_number,
                    len(batches),
                    attempt,
                    sleep_seconds,
                    exc,
                )
                time.sleep(sleep_seconds)

        if batch_delay and batch_number < len(batches):
            logger.info(
                "Sleeping between Google embedding batches seconds=%s",
                batch_delay,
            )
            time.sleep(batch_delay)


def _load_and_split_docs() -> list:
    """Load knowledge-base documents and split into chunks."""
    global _cached_chunks
    if _cached_chunks is not None:
        logger.info("Using cached RAG chunks count=%s", len(_cached_chunks))
        return _cached_chunks

    loader = DirectoryLoader(
        str(KNOWLEDGE_BASE_DIR),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
    )
    docs = loader.load()
    logger.info("Loaded %s knowledge base documents", len(docs))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=RAG_CHUNK_SIZE,
        chunk_overlap=RAG_CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(docs)
    for chunk in chunks:
        source_path = str(chunk.metadata.get("source", ""))
        chunk.metadata.update(_extract_doc_metadata(source_path, chunk.page_content))
    _cached_chunks = chunks
    logger.info("Split knowledge base into %s chunks", len(_cached_chunks))
    return _cached_chunks


def _chroma_dir_for_provider(provider: str | None):
    chosen_provider, _ = normalise_llm_selection(provider, None)
    return CHROMA_ROOT_DIR / chosen_provider


def _build_vectorstore(
    provider: str | None = DEFAULT_LLM_PROVIDER,
    force_rebuild: bool = False,
) -> Chroma:
    """Build or load the ChromaDB vector store from knowledge-base documents."""
    global _cached_vectorstores
    chosen_provider, _ = normalise_llm_selection(provider, None)

    if not force_rebuild and chosen_provider in _cached_vectorstores:
        logger.info("Using cached vectorstore for provider=%s", chosen_provider)
        return _cached_vectorstores[chosen_provider]

    chroma_dir = _chroma_dir_for_provider(chosen_provider)
    chroma_exists = chroma_dir.exists() and any(chroma_dir.iterdir())
    logger.info(
        "Preparing vectorstore provider=%s force_rebuild=%s chroma_exists=%s",
        chosen_provider,
        force_rebuild,
        chroma_exists,
    )
    embeddings = create_embeddings(chosen_provider)

    if chroma_exists and not force_rebuild:
        logger.info("Loading existing Chroma vectorstore from %s", chroma_dir)
        vs = Chroma(persist_directory=str(chroma_dir), embedding_function=embeddings)
    else:
        chunks = _load_and_split_docs()
        if force_rebuild and chroma_dir.exists():
            logger.info("Removing existing Chroma vectorstore at %s", chroma_dir)
            shutil.rmtree(chroma_dir)
        chroma_dir.parent.mkdir(parents=True, exist_ok=True)
        vs = Chroma(
            persist_directory=str(chroma_dir),
            embedding_function=embeddings,
        )
        _add_documents_with_quota_backoff(
            vectorstore=vs,
            chunks=chunks,
            provider=chosen_provider,
        )

    _cached_vectorstores[chosen_provider] = vs
    return vs


def _source_label(source_path: str) -> str:
    """Turn a file path like 'knowledge_base/visa_requirements.md' into 'Visa Requirements'."""
    from pathlib import Path

    stem = Path(source_path).stem  # e.g. "visa_requirements"
    return stem.replace("_", " ").title()


def retrieve(
    query: str, k: int = RAG_TOP_K, provider: str | None = DEFAULT_LLM_PROVIDER
) -> list[dict[str, str]]:
    """Return the top-k relevant text chunks with source metadata using hybrid search.

    Combines vector similarity (ChromaDB) with keyword matching (BM25)
    using reciprocal rank fusion via EnsembleRetriever.

    Each result is a dict with keys ``content`` and ``source``.
    """
    global _cached_bm25
    logger.info("Running RAG retrieval query=%s k=%s provider=%s", query, k, provider)
    # Vector retriever
    vs = _build_vectorstore(provider=provider)
    candidate_k = max(k * 3, 8)
    vector_retriever = vs.as_retriever(search_kwargs={"k": candidate_k})

    # BM25 keyword retriever (cached; k is set per-query)
    if _cached_bm25 is None:
        chunks = _load_and_split_docs()
        _cached_bm25 = BM25Retriever.from_documents(chunks, k=candidate_k)
    _cached_bm25.k = candidate_k
    bm25_retriever = _cached_bm25

    # Hybrid: ensemble with reciprocal rank fusion
    ensemble_retriever = EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[RAG_VECTOR_WEIGHT, RAG_BM25_WEIGHT],
    )

    docs = ensemble_retriever.invoke(query)
    docs = _rerank_docs_for_query(docs, query, k)
    logger.info("RAG retrieval returned %s documents after reranking", len(docs))
    return [
        {
            "content": doc.page_content,
            "source": _source_label(doc.metadata.get("source", "Unknown")),
        }
        for doc in docs[:k]
    ]
