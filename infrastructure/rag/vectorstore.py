"""ChromaDB vector store for visa-only retrieval."""

from __future__ import annotations

import re
import shutil
import time
from functools import lru_cache

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHROMA_ROOT_DIR,
    DEFAULT_LLM_PROVIDER,
    KNOWLEDGE_BASE_DIR,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_EMBEDDING_BATCH_SIZE,
    RAG_EMBEDDING_MAX_RETRIES,
    RAG_GOOGLE_EMBEDDING_BATCH_DELAY_SECONDS,
)
from infrastructure.llms.model_factory import create_embeddings, normalise_llm_selection
from infrastructure.logging_utils import get_logger
from infrastructure.persistence.memory_store import list_place_aliases

logger = get_logger(__name__)

# Module-level caches
_cached_chunks: list | None = None
_cached_vectorstores: dict[str, Chroma] = {}

def _normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _extract_heading(page_content: str) -> str:
    match = re.search(r"^##\s+(.+)$", page_content or "", flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _detect_topics(page_content: str, source_type: str) -> list[str]:
    lowered = (page_content or "").lower()
    topics: set[str] = set()

    keyword_map = {
        "entry_requirements": ["visa-free", "visa required", "documents needed", "passport", "entry requirements", "esta", "eta", "etias"],
    }

    for topic, keywords in keyword_map.items():
        if any(keyword in lowered for keyword in keywords):
            topics.add(topic)

    if source_type == "visa_requirements":
        topics.add("entry_requirements")

    return sorted(topics)


def _extract_doc_metadata(source_path: str, page_content: str) -> dict[str, str | list[str]]:
    heading = _extract_heading(page_content)
    source_stem = _normalise_text(source_path.split("/")[-1].replace(".md", ""))
    source_type = source_stem.replace(" ", "_")
    city = ""
    country = ""

    if source_type == "visa_requirements" and heading:
        country = heading.split("(", 1)[0].strip()

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
    for path in (KNOWLEDGE_BASE_DIR / "visa_requirements.md",):
        text = path.read_text(encoding="utf-8")
        source_type = path.stem
        for match in re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE):
            heading = match.group(1).strip()
            if source_type == "visa_requirements":
                country = heading.split("(", 1)[0].strip()
                if country:
                    places.append((_normalise_text(country), "country", country))
    try:
        for alias in list_place_aliases():
            normalized_name = _normalise_text(alias.get("normalized_name", ""))
            city_name = str(alias.get("city_name", "")).strip()
            country_name = str(alias.get("country_name", "")).strip()
            if normalized_name and city_name:
                places.append((normalized_name, "city", city_name))
            if normalized_name and country_name and _normalise_text(country_name) == normalized_name:
                places.append((normalized_name, "country", country_name))
    except Exception:
        logger.warning("Falling back to knowledge-base place metadata only")
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

    if city and not country:
        try:
            for alias in list_place_aliases():
                if str(alias.get("city_name", "")).strip() == city:
                    country = str(alias.get("country_name", "")).strip()
                    break
        except Exception:
            logger.warning("Unable to resolve city-to-country mapping from place aliases")

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


def _preferred_source_types(query_meta: dict[str, str | list[str]]) -> list[str]:
    query_intents = set(query_meta.get("intents", []) or [])

    if "entry_requirements" in query_intents:
        return ["visa_requirements"]
    return []


def _doc_matches_filters(
    metadata: dict,
    *,
    query_meta: dict[str, str | list[str]],
    allowed_source_types: list[str] | None,
    require_place_match: bool,
) -> bool:
    source_type = str(metadata.get("source_type", ""))
    if allowed_source_types and source_type not in allowed_source_types:
        return False

    query_city = _normalise_text(str(query_meta.get("city", "")))
    query_country = _normalise_text(str(query_meta.get("country", "")))
    if not require_place_match or (not query_city and not query_country):
        return True

    doc_city = _normalise_text(str(metadata.get("city", "")))
    doc_country = _normalise_text(str(metadata.get("country", "")))

    if query_city and doc_city and doc_city != query_city:
        return False
    if query_country and doc_country and doc_country != query_country:
        return False

    return bool(
        (query_city and doc_city == query_city)
        or (query_country and doc_country == query_country)
    )


def _build_chroma_filter(
    *,
    query_meta: dict[str, str | list[str]],
    allowed_source_types: list[str] | None,
    require_place_match: bool,
) -> dict | None:
    clauses: list[dict] = []
    if allowed_source_types:
        if len(allowed_source_types) == 1:
            clauses.append({"source_type": allowed_source_types[0]})
        else:
            clauses.append({"source_type": {"$in": allowed_source_types}})

    if require_place_match:
        query_city = str(query_meta.get("city", "")).strip()
        query_country = str(query_meta.get("country", "")).strip()
        place_clauses: list[dict] = []
        if query_city:
            place_clauses.append({"city": query_city})
        if query_country:
            place_clauses.append({"country": query_country})
        if place_clauses:
            clauses.append(place_clauses[0] if len(place_clauses) == 1 else {"$or": place_clauses})

    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _iter_retrieval_plans(query_meta: dict[str, str | list[str]]) -> list[dict[str, object]]:
    plans: list[dict[str, object]] = []
    seen: set[tuple[tuple[str, ...], bool]] = set()
    preferred_source_types = _preferred_source_types(query_meta)
    has_place = bool(query_meta.get("city") or query_meta.get("country"))

    candidates = [
        (preferred_source_types or None, has_place),
        (preferred_source_types or None, False),
        (None, has_place),
        (None, False),
    ]

    for allowed_source_types, require_place_match in candidates:
        key = (tuple(allowed_source_types or ()), bool(require_place_match))
        if key in seen:
            continue
        seen.add(key)
        plans.append(
            {
                "allowed_source_types": allowed_source_types,
                "require_place_match": require_place_match,
            }
        )

    return plans


def _run_vector_retrieval(
    *,
    vectorstore: Chroma,
    query: str,
    k: int,
    query_meta: dict[str, str | list[str]],
    allowed_source_types: list[str] | None,
    require_place_match: bool,
) -> list:
    search_filter = _build_chroma_filter(
        query_meta=query_meta,
        allowed_source_types=allowed_source_types,
        require_place_match=require_place_match,
    )
    try:
        docs = vectorstore.similarity_search(query, k=k, filter=search_filter)
    except Exception:
        logger.warning("Filtered vector retrieval failed; retrying without metadata filter", exc_info=True)
        docs = vectorstore.similarity_search(query, k=k)

    if search_filter is None:
        return docs

    return [
        doc
        for doc in docs
        if _doc_matches_filters(
            getattr(doc, "metadata", {}) or {},
            query_meta=query_meta,
            allowed_source_types=allowed_source_types,
            require_place_match=require_place_match,
        )
    ]


def _run_bm25_retrieval(
    *,
    chunks: list,
    query: str,
    k: int,
    query_meta: dict[str, str | list[str]],
    allowed_source_types: list[str] | None,
    require_place_match: bool,
) -> list:
    filtered_chunks = [
        chunk
        for chunk in chunks
        if _doc_matches_filters(
            getattr(chunk, "metadata", {}) or {},
            query_meta=query_meta,
            allowed_source_types=allowed_source_types,
            require_place_match=require_place_match,
        )
    ]
    if not filtered_chunks:
        return []

    retriever = BM25Retriever.from_documents(filtered_chunks, k=k)
    return retriever.invoke(query)


def _dedupe_docs(docs: list, k: int) -> list:
    seen: set[tuple[str, str]] = set()
    deduped = []
    for doc in docs:
        metadata = getattr(doc, "metadata", {}) or {}
        key = (
            str(metadata.get("source", "")),
            (getattr(doc, "page_content", "") or "")[:120],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
        if len(deduped) >= k:
            break
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
        glob="visa_requirements.md",
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
    """Return the top-k relevant visa text chunks with source metadata."""
    logger.info("Running RAG retrieval query=%s k=%s provider=%s", query, k, provider)
    vs = _build_vectorstore(provider=provider)
    chunks = _load_and_split_docs()
    query_meta = _infer_query_metadata(query)
    if "entry_requirements" not in set(query_meta.get("intents", []) or []):
        logger.info("Skipping RAG retrieval because query is outside visa scope")
        return []
    candidate_k = max(k * 3, 8)

    docs: list = []
    for plan in _iter_retrieval_plans(query_meta):
        allowed_source_types = plan["allowed_source_types"]
        require_place_match = bool(plan["require_place_match"])

        vector_docs = _run_vector_retrieval(
            vectorstore=vs,
            query=query,
            k=candidate_k,
            query_meta=query_meta,
            allowed_source_types=allowed_source_types,
            require_place_match=require_place_match,
        )
        bm25_docs = _run_bm25_retrieval(
            chunks=chunks,
            query=query,
            k=candidate_k,
            query_meta=query_meta,
            allowed_source_types=allowed_source_types,
            require_place_match=require_place_match,
        )

        # Interleave the two retrieval modes so we keep both semantic and keyword hits.
        merged_plan_docs: list = []
        max_len = max(len(vector_docs), len(bm25_docs))
        for index in range(max_len):
            if index < len(vector_docs):
                merged_plan_docs.append(vector_docs[index])
            if index < len(bm25_docs):
                merged_plan_docs.append(bm25_docs[index])

        docs.extend(merged_plan_docs)
        docs = _dedupe_docs(docs, candidate_k)
        if len(docs) >= k:
            break

    docs = _dedupe_docs(docs, k)
    logger.info("RAG retrieval returned %s documents after metadata-aware retrieval", len(docs))
    return [
        {
            "content": doc.page_content,
            "source": _source_label(doc.metadata.get("source", "Unknown")),
        }
        for doc in docs[:k]
    ]
