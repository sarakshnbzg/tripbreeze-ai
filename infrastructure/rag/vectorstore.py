"""ChromaDB vector store — builds and queries the RAG knowledge base.

Uses hybrid search (vector similarity + BM25 keyword matching) via
LangChain's EnsembleRetriever for better retrieval quality.
"""

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
)
from infrastructure.llms.model_factory import create_embeddings, normalise_llm_selection
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

# Module-level caches
_cached_chunks: list | None = None
_cached_vectorstores: dict[str, Chroma] = {}
_cached_bm25: BM25Retriever | None = None


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
    _cached_chunks = splitter.split_documents(docs)
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
        chroma_dir.parent.mkdir(parents=True, exist_ok=True)
        vs = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=str(chroma_dir),
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
    vector_retriever = vs.as_retriever(search_kwargs={"k": k})

    # BM25 keyword retriever (cached; k is set per-query)
    if _cached_bm25 is None:
        chunks = _load_and_split_docs()
        _cached_bm25 = BM25Retriever.from_documents(chunks, k=k)
    _cached_bm25.k = k
    bm25_retriever = _cached_bm25

    # Hybrid: ensemble with reciprocal rank fusion
    ensemble_retriever = EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[RAG_VECTOR_WEIGHT, RAG_BM25_WEIGHT],
    )

    docs = ensemble_retriever.invoke(query)
    logger.info("RAG retrieval returned %s documents", len(docs[:k]))
    return [
        {
            "content": doc.page_content,
            "source": _source_label(doc.metadata.get("source", "Unknown")),
        }
        for doc in docs[:k]
    ]
