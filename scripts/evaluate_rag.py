"""Run offline RAG evaluation with the local retriever and optional RAGAs metrics."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from model_catalog import (
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_JUDGE_MODEL,
)
from settings import (
    RAG_EVAL_DATASET_PATH,
    RAG_EVAL_OUTPUT_DIR,
)
from infrastructure.rag.evaluation import (
    build_retrieval_snapshot,
    evaluate_with_llm_judge,
    evaluate_with_ragas,
    generate_answers,
    load_eval_dataset,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(RAG_EVAL_DATASET_PATH), help="Path to JSONL eval dataset.")
    parser.add_argument(
        "--provider",
        default=DEFAULT_LLM_PROVIDER,
        choices=["openai"],
        help="Provider to use for retrieval and answer generation.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Chat model for answer generation. Defaults to the provider's configured default.",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip answer generation and only emit retrieved contexts for inspection.",
    )
    parser.add_argument(
        "--llm-judge",
        action="store_true",
        help="Run an LLM-as-a-judge pass over generated answers and save row-level scores.",
    )
    parser.add_argument(
        "--judge-provider",
        default="",
        choices=["", "openai"],
        help="Provider for LLM-as-a-judge. Defaults to the main provider.",
    )
    parser.add_argument(
        "--judge-model",
        default="",
        help="Judge model id. Defaults to the configured judge default for the chosen judge provider.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    model = args.model or DEFAULT_LLM_MODEL[args.provider]
    judge_provider = args.judge_provider or args.provider
    judge_model = args.judge_model or DEFAULT_JUDGE_MODEL[judge_provider]
    rows = load_eval_dataset(args.dataset)
    rows = build_retrieval_snapshot(rows, provider=args.provider)

    if not args.retrieval_only:
        rows = generate_answers(rows, provider=args.provider, model=model)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    RAG_EVAL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_path = Path(RAG_EVAL_OUTPUT_DIR) / f"rag_eval_snapshot_{timestamp}.json"
    snapshot_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Saved evaluation snapshot to {snapshot_path}")

    if args.retrieval_only:
        print("Retrieval-only mode enabled; skipped RAGAs scoring.")
        return

    if args.llm_judge:
        judge_result = evaluate_with_llm_judge(
            rows,
            provider=judge_provider,
            model=judge_model,
        )
        judge_path = Path(RAG_EVAL_OUTPUT_DIR) / f"rag_eval_judge_{timestamp}.json"
        judge_path.write_text(json.dumps(judge_result, indent=2), encoding="utf-8")
        print(f"Saved LLM judge scores to {judge_path}")

    score = evaluate_with_ragas(rows, provider=args.provider, model=model)
    if hasattr(score, "_repr_dict"):
        score_dict = dict(score._repr_dict)
    elif hasattr(score, "to_pandas"):
        score_dict = score.to_pandas().mean(numeric_only=True).to_dict()
    else:
        score_dict = {"result": str(score)}
    summary_path = Path(RAG_EVAL_OUTPUT_DIR) / f"rag_eval_scores_{timestamp}.json"
    summary_path.write_text(json.dumps(score_dict, indent=2), encoding="utf-8")
    print(f"Saved RAGAs scores to {summary_path}")
    print(score)


if __name__ == "__main__":
    main()
