"""ChromaDB vector store — builds and queries the RAG knowledge base.

Uses hybrid search (vector similarity + BM25 keyword matching) via
LangChain's EnsembleRetriever for better retrieval quality.
"""

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.retrievers import BM25Retriever
from langchain_chroma import Chroma
from langchain_classic.retrievers import EnsembleRetriever
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    KNOWLEDGE_BASE_DIR,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_TOP_K,
    RAG_VECTOR_WEIGHT,
    RAG_BM25_WEIGHT,
)
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)

# Module-level cache for chunked documents (used by BM25 retriever).
_cached_chunks: list | None = None


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


def _build_vectorstore(force_rebuild: bool = False) -> Chroma:
    """Build or load the ChromaDB vector store from knowledge-base documents."""
    logger.info("Preparing vectorstore force_rebuild=%s chroma_exists=%s", force_rebuild, CHROMA_DIR.exists())
    embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)

    if CHROMA_DIR.exists() and not force_rebuild:
        logger.info("Loading existing Chroma vectorstore from %s", CHROMA_DIR)
        return Chroma(persist_directory=str(CHROMA_DIR), embedding_function=embeddings)

    chunks = _load_and_split_docs()

    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(CHROMA_DIR),
    )


def retrieve(query: str, k: int = RAG_TOP_K) -> list[str]:
    """Return the top-k relevant text chunks using hybrid search.

    Combines vector similarity (ChromaDB) with keyword matching (BM25)
    using reciprocal rank fusion via EnsembleRetriever.
    """
    logger.info("Running RAG retrieval query=%s k=%s", query, k)
    # Vector retriever
    vs = _build_vectorstore()
    vector_retriever = vs.as_retriever(search_kwargs={"k": k})

    # BM25 keyword retriever
    chunks = _load_and_split_docs()
    bm25_retriever = BM25Retriever.from_documents(chunks, k=k)

    # Hybrid: ensemble with reciprocal rank fusion
    ensemble_retriever = EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[RAG_VECTOR_WEIGHT, RAG_BM25_WEIGHT],
    )

    docs = ensemble_retriever.invoke(query)
    logger.info("RAG retrieval returned %s documents", len(docs[:k]))
    return [doc.page_content for doc in docs[:k]]
