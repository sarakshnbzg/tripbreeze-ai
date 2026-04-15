"""Helpers for tracing and evaluating the local RAG pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import RAG_EVAL_DATASET_PATH
from infrastructure.llms.model_factory import create_chat_model, create_embeddings, invoke_with_retry
from infrastructure.logging_utils import get_logger
from infrastructure.rag.vectorstore import retrieve

logger = get_logger(__name__)


def record_rag_event(
    rag_trace: list[dict[str, Any]],
    *,
    node: str,
    query: str,
    provider: str | None,
    results: list[dict[str, str]],
) -> None:
    """Append a normalized retrieval event to the shared RAG trace."""
    rag_trace.append(
        {
            "node": node,
            "query": query,
            "provider": provider or "",
            "results": [
                {
                    "source": item.get("source", ""),
                    "content": item.get("content", ""),
                }
                for item in results
            ],
        }
    )


def load_eval_dataset(path: str | Path = RAG_EVAL_DATASET_PATH) -> list[dict[str, Any]]:
    """Load newline-delimited JSON eval samples."""
    dataset_path = Path(path)
    rows: list[dict[str, Any]] = []
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(json.loads(stripped))
    return rows


def build_retrieval_snapshot(
    samples: list[dict[str, Any]],
    *,
    provider: str,
) -> list[dict[str, Any]]:
    """Run the retriever for each sample and return the enriched rows."""
    prepared: list[dict[str, Any]] = []
    for sample in samples:
        query = str(sample["user_input"]).strip()
        retrieval_results = retrieve(query, provider=provider)
        prepared.append(
            {
                **sample,
                "retrieved_contexts": [item["content"] for item in retrieval_results],
                "retrieved_sources": [item["source"] for item in retrieval_results],
            }
        )
    return prepared


def generate_answers(
    rows: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
) -> list[dict[str, Any]]:
    """Generate grounded answers from retrieved contexts for RAGAs scoring."""
    llm = create_chat_model(provider, model, temperature=0)
    enriched: list[dict[str, Any]] = []
    for row in rows:
        contexts = row.get("retrieved_contexts") or []
        prompt = (
            "Answer the travel question using only the provided context.\n"
            "If the context is insufficient, say so clearly.\n\n"
            f"Question: {row['user_input']}\n\n"
            "Context:\n"
            + "\n\n".join(f"[{idx}] {context}" for idx, context in enumerate(contexts, start=1))
        )
        response = invoke_with_retry(llm, prompt)
        enriched.append({**row, "response": getattr(response, "content", "")})
    return enriched


def evaluate_with_ragas(
    rows: list[dict[str, Any]],
    *,
    provider: str,
    model: str,
) -> Any:
    """Evaluate prepared rows with RAGAs when the optional dependency is installed."""
    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        raise RuntimeError(
            "RAG evaluation requires optional packages. Install them with "
            "`uv sync --group eval` before running `scripts/evaluate_rag.py`."
        ) from exc

    dataset = Dataset.from_list(rows)
    ragas_llm = LangchainLLMWrapper(create_chat_model(provider, model, temperature=0))
    ragas_embeddings = LangchainEmbeddingsWrapper(create_embeddings(provider))
    return evaluate(
        dataset=dataset,
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
        llm=ragas_llm,
        embeddings=ragas_embeddings,
    )
