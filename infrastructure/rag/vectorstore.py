"""ChromaDB vector store for visa-only retrieval."""

from __future__ import annotations

import re
import shutil
import threading
import time
from functools import lru_cache
from typing import Any

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

from model_catalog import DEFAULT_LLM_PROVIDER
from settings import (
    CHROMA_ROOT_DIR,
    KNOWLEDGE_BASE_DIR,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_VECTOR_WEIGHT,
    RAG_BM25_WEIGHT,
    RAG_EMBEDDING_BATCH_SIZE,
    RAG_EMBEDDING_MAX_RETRIES,
)
from infrastructure.llms.model_factory import create_embeddings, normalise_llm_selection
from infrastructure.logging_utils import get_logger
from infrastructure.persistence.memory_store import list_place_aliases

logger = get_logger(__name__)

# Module-level caches — guarded by locks for thread safety under FastAPI workers
_cached_chunks: list | None = None
_cached_chunks_lock = threading.Lock()
_cached_vectorstores: dict[str, Chroma] = {}
_cached_vectorstores_lock = threading.Lock()

INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "entry_requirements": (
        "visa",
        "entry requirement",
        "entry requirements",
        "passport",
        "passport validity",
        "documents needed",
        "required documents",
        "travel documents",
        "supporting documents",
        "proof of funds",
        "proof of accommodation",
        "return ticket",
        "onward ticket",
        "entry rules",
        "tourist visa",
        "tourism entry",
        "enter",
        "etias",
        "eta",
        "visa on arrival",
    ),
    "transport": ("transport", "get around", "metro", "tram", "subway", "bus", "bike"),
    "budget": ("budget", "cheap", "money-saving", "expensive", "value"),
    "safety": ("safety", "safe", "scam", "street smarts"),
    "packing": ("packing", "pack"),
    "health": (
        "health",
        "vaccination",
        "vaccinations",
        "vaccine",
        "vaccines",
        "yellow fever",
        "malaria",
        "altitude",
        "water safety",
        "health insurance",
    ),
    "flight_booking": ("flight-booking", "book flights", "flight strategy"),
    "hotel_booking": ("hotel-booking", "hotel booking", "book hotels"),
    "etiquette": ("etiquette", "cultural", "dress code", "haggling"),
    "customs": (
        "customs",
        "duty-free",
        "duty free",
        "declare",
        "declaration",
        "prohibited items",
        "allowance",
        "alcohol allowance",
        "tobacco allowance",
    ),
    "currency": (
        "currency",
        "cash",
        "atm",
        "atms",
        "exchange rate",
        "tipping",
        "card acceptance",
        "credit card",
        "debit card",
    ),
    "transit": (
        "transit",
        "layover",
        "self-transfer",
        "self transfer",
        "airside",
        "sterile area",
        "transit visa",
        "transit without visa",
        "twov",
    ),
}

PASSPORT_ENTITY_PATTERNS = (
    r"\b([a-z][a-z\s\-]{1,40})\s+passport holders?\b",
    r"\b([a-z][a-z\s\-]{1,40})\s+passport\b",
    r"\b([a-z][a-z\s\-]{1,40})\s+citizens?\b",
    r"\btravelers with a passport from\s+([a-z][a-z\s\-]{1,40})\b",
)

def _normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _extract_heading(page_content: str) -> str:
    match = re.search(r"^##\s+(.+)$", page_content or "", flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


COUNTRY_KEYED_SOURCE_TYPES: tuple[str, ...] = (
    "visa_requirements",
    "health_requirements",
    "customs_and_duty_free",
    "currency_and_money",
    "transit_rules",
)


def _detect_topics(page_content: str, source_type: str) -> list[str]:
    lowered = (page_content or "").lower()
    topics: set[str] = set()

    keyword_map = {
        "entry_requirements": ["visa-free", "visa required", "documents needed", "passport", "entry requirements", "esta", "eta", "etias"],
        "health": ["vaccination", "vaccine", "yellow fever", "malaria", "altitude", "water safety", "health insurance"],
        "customs": ["duty-free", "duty free", "customs", "declare", "declaration", "prohibited items", "allowance"],
        "currency": ["currency", "cash", "atm", "tipping", "exchange rate", "card acceptance"],
        "transit": ["transit", "layover", "self-transfer", "airside", "sterile area", "transit visa"],
    }

    for topic, keywords in keyword_map.items():
        if any(keyword in lowered for keyword in keywords):
            topics.add(topic)

    if source_type == "visa_requirements":
        topics.add("entry_requirements")
    if source_type == "health_requirements":
        topics.add("health")
    if source_type == "customs_and_duty_free":
        topics.add("customs")
    if source_type == "currency_and_money":
        topics.add("currency")
    if source_type == "transit_rules":
        topics.add("transit")

    return sorted(topics)


def _extract_doc_metadata(source_path: str, page_content: str) -> dict[str, str | list[str]]:
    heading = _extract_heading(page_content)
    source_stem = _normalise_text(source_path.split("/")[-1].replace(".md", ""))
    source_type = source_stem.replace(" ", "_")
    city = ""
    country = ""

    if source_type in COUNTRY_KEYED_SOURCE_TYPES and heading:
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
    seen: set[tuple[str, str, str]] = set()
    for path in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        source_type = path.stem.replace(" ", "_")
        if source_type not in COUNTRY_KEYED_SOURCE_TYPES:
            continue
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"^##\s+(.+)$", text, flags=re.MULTILINE):
            heading = match.group(1).strip()
            country = heading.split("(", 1)[0].strip()
            if not country:
                continue
            entry = (_normalise_text(country), "country", country)
            if entry in seen:
                continue
            seen.add(entry)
            places.append(entry)
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
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            intents.append(intent)

    return {
        "city": city,
        "country": country,
        "intents": intents,
        "passport_entities": _extract_passport_entities(query),
        "query": lowered,
    }


def _extract_passport_entities(query: str) -> list[str]:
    lowered = _normalise_text(query)
    entities: list[str] = []
    seen: set[str] = set()

    for pattern in PASSPORT_ENTITY_PATTERNS:
        for match in re.finditer(pattern, lowered, flags=re.IGNORECASE):
            candidate = _normalise_text(match.group(1))
            if not candidate:
                continue
            candidate = re.sub(
                r"\b(holder|holders|traveler|travelers|visitor|visitors|from)\b",
                "",
                candidate,
            ).strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            entities.append(candidate)

    return entities


INTENT_TO_SOURCE_TYPES: dict[str, list[str]] = {
    "entry_requirements": ["visa_requirements"],
    "health": ["health_requirements"],
    "customs": ["customs_and_duty_free"],
    "currency": ["currency_and_money"],
    "transit": ["transit_rules"],
}

RETRIEVAL_INTENTS: frozenset[str] = frozenset(INTENT_TO_SOURCE_TYPES.keys())


def _preferred_source_types(query_meta: dict[str, str | list[str]]) -> list[str]:
    query_intents = set(query_meta.get("intents", []) or [])

    non_visa_specific = query_intents & {"customs", "currency", "transit", "health"}
    if non_visa_specific:
        preferred: list[str] = []
        for intent in sorted(non_visa_specific):
            for source_type in INTENT_TO_SOURCE_TYPES.get(intent, []):
                if source_type not in preferred:
                    preferred.append(source_type)
        return preferred

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
    started_at = time.perf_counter()
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

    logger.info(
        "RAG vector retrieval completed k=%s filter_applied=%s results=%s elapsed_ms=%.2f",
        k,
        search_filter is not None,
        len(docs),
        (time.perf_counter() - started_at) * 1000,
    )

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
    started_at = time.perf_counter()
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
        logger.info("RAG BM25 retrieval skipped filtered_chunks=0 elapsed_ms=%.2f", (time.perf_counter() - started_at) * 1000)
        return []

    retriever = BM25Retriever.from_documents(filtered_chunks, k=k)
    docs = retriever.invoke(query)
    logger.info(
        "RAG BM25 retrieval completed k=%s filtered_chunks=%s results=%s elapsed_ms=%.2f",
        k,
        len(filtered_chunks),
        len(docs),
        (time.perf_counter() - started_at) * 1000,
    )
    return docs


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


def _doc_identity(doc: Any) -> tuple[str, str]:
    metadata = getattr(doc, "metadata", {}) or {}
    return (
        str(metadata.get("source", "")),
        getattr(doc, "page_content", "") or "",
    )


def _score_doc(
    doc: Any,
    *,
    query_meta: dict[str, str | list[str]],
    allowed_source_types: list[str] | None,
    retrieval_mode: str,
) -> float:
    metadata = getattr(doc, "metadata", {}) or {}
    content = _normalise_text(getattr(doc, "page_content", "") or "")
    heading = _normalise_text(str(metadata.get("heading", "")))
    doc_city = _normalise_text(str(metadata.get("city", "")))
    doc_country = _normalise_text(str(metadata.get("country", "")))
    query_city = _normalise_text(str(query_meta.get("city", "")))
    query_country = _normalise_text(str(query_meta.get("country", "")))
    passport_entities = [
        _normalise_text(str(value))
        for value in (query_meta.get("passport_entities", []) or [])
        if str(value).strip()
    ]

    score = RAG_VECTOR_WEIGHT if retrieval_mode == "vector" else RAG_BM25_WEIGHT

    if allowed_source_types and str(metadata.get("source_type", "")) in allowed_source_types:
        score += 1.0

    if query_country and doc_country == query_country:
        score += 3.0
    elif query_country and query_country in heading:
        score += 1.5

    if query_city and doc_city == query_city:
        score += 4.0
    elif query_city and query_city in heading:
        score += 2.0

    if query_city and query_country and doc_country and doc_country != query_country:
        score -= 1.5

    for entity in passport_entities:
        if re.search(rf"\b{re.escape(entity)}\s+citizens?\b", content):
            score += 2.5
            break
        if re.search(rf"\b{re.escape(entity)}\b", content):
            score += 1.0
            break

    if "documents needed" in content:
        score += 0.5

    return score


def _rank_scored_docs(scored_docs: list[tuple[float, int, Any]], k: int) -> list:
    best_docs: dict[tuple[str, str], tuple[float, int, Any]] = {}
    for score, order, doc in scored_docs:
        key = _doc_identity(doc)
        existing = best_docs.get(key)
        if existing is None or score > existing[0] or (score == existing[0] and order < existing[1]):
            best_docs[key] = (score, order, doc)

    ranked = sorted(best_docs.values(), key=lambda item: (-item[0], item[1]))
    return [doc for _, _, doc in ranked[:k]]


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
    """Add chunks in batches with retry on transient embedding errors."""
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


def _load_and_split_docs() -> list:
    """Load knowledge-base documents and split into chunks."""
    global _cached_chunks
    with _cached_chunks_lock:
        if _cached_chunks is not None:
            logger.info("Using cached RAG chunks count=%s", len(_cached_chunks))
            return _cached_chunks

        loader = DirectoryLoader(
            str(KNOWLEDGE_BASE_DIR),
            glob="*.md",
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

    with _cached_vectorstores_lock:
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
    chosen_provider, _ = normalise_llm_selection(provider, None)
    logger.info("Running RAG retrieval query=%s k=%s provider=%s", query, k, chosen_provider)
    started_at = time.perf_counter()
    vectorstore_started_at = time.perf_counter()
    vs = _build_vectorstore(provider=chosen_provider)
    logger.info("RAG vectorstore ready elapsed_ms=%.2f", (time.perf_counter() - vectorstore_started_at) * 1000)
    chunks_started_at = time.perf_counter()
    chunks = _load_and_split_docs()
    logger.info("RAG chunks ready count=%s elapsed_ms=%.2f", len(chunks), (time.perf_counter() - chunks_started_at) * 1000)
    query_meta = _infer_query_metadata(query)
    query_intents = set(query_meta.get("intents", []) or [])
    if not query_intents & RETRIEVAL_INTENTS:
        logger.info(
            "Skipping RAG retrieval because query is outside knowledge-base scope total_elapsed_ms=%.2f",
            (time.perf_counter() - started_at) * 1000,
        )
        return []
    candidate_k = max(k * 3, 8)

    scored_docs: list[tuple[float, int, Any]] = []
    next_order = 0
    for plan_index, plan in enumerate(_iter_retrieval_plans(query_meta), start=1):
        plan_started_at = time.perf_counter()
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

        merged_plan_docs: list = []
        for doc in vector_docs:
            merged_plan_docs.append(doc)
            scored_docs.append(
                (
                    _score_doc(
                        doc,
                        query_meta=query_meta,
                        allowed_source_types=allowed_source_types,
                        retrieval_mode="vector",
                    ),
                    next_order,
                    doc,
                )
            )
            next_order += 1
        for doc in bm25_docs:
            merged_plan_docs.append(doc)
            scored_docs.append(
                (
                    _score_doc(
                        doc,
                        query_meta=query_meta,
                        allowed_source_types=allowed_source_types,
                        retrieval_mode="bm25",
                    ),
                    next_order,
                    doc,
                )
            )
            next_order += 1

        docs = _rank_scored_docs(scored_docs, candidate_k)
        logger.info(
            "RAG retrieval plan completed plan=%s require_place_match=%s allowed_source_types=%s merged_docs=%s deduped_docs=%s elapsed_ms=%.2f",
            plan_index,
            require_place_match,
            allowed_source_types,
            len(merged_plan_docs),
            len(docs),
            (time.perf_counter() - plan_started_at) * 1000,
        )
        if len(docs) >= k:
            break

    docs = _rank_scored_docs(scored_docs, k)
    logger.info(
        "RAG retrieval returned %s documents after metadata-aware retrieval total_elapsed_ms=%.2f",
        len(docs),
        (time.perf_counter() - started_at) * 1000,
    )
    return [
        {
            "content": doc.page_content,
            "source": _source_label(doc.metadata.get("source", "Unknown")),
        }
        for doc in docs[:k]
    ]
