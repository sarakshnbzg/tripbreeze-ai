"""Tests for infrastructure/rag/evaluation.py."""

import sys
from types import ModuleType

from infrastructure.rag.evaluation import (
    build_retrieval_snapshot,
    evaluate_with_ragas,
    record_rag_event,
)


class TestRecordRagEvent:
    def test_appends_normalized_trace_event(self):
        trace = []

        record_rag_event(
            trace,
            node="research_orchestrator",
            query="Paris visa info",
            provider="openai",
            results=[{"source": "Visa Requirements", "content": "US citizens can visit visa-free."}],
        )

        assert len(trace) == 1
        assert trace[0]["node"] == "research_orchestrator"
        assert trace[0]["provider"] == "openai"
        assert trace[0]["results"][0]["source"] == "Visa Requirements"


class TestBuildRetrievalSnapshot:
    def test_adds_contexts_and_sources(self, monkeypatch):
        monkeypatch.setattr(
            "infrastructure.rag.evaluation.retrieve",
            lambda query, provider: [
                {"source": "Visa Requirements", "content": f"Visa guidance for {query}"},
            ],
        )

        rows = build_retrieval_snapshot(
            [{"user_input": "Do US citizens need a visa for Amsterdam?", "reference": "Visa answer"}],
            provider="openai",
        )

        assert rows[0]["retrieved_sources"] == ["Visa Requirements"]
        assert rows[0]["retrieved_contexts"][0] == "Visa guidance for Do US citizens need a visa for Amsterdam?"


class TestEvaluateWithRagas:
    def test_wraps_langchain_models_before_evaluating(self, monkeypatch):
        calls = {}

        class FakeDataset:
            @staticmethod
            def from_list(rows):
                calls["rows"] = rows
                return rows

        def fake_evaluate(*, dataset, metrics, llm, embeddings):
            calls["dataset"] = dataset
            calls["metrics_count"] = len(metrics)
            calls["llm"] = llm
            calls["embeddings"] = embeddings
            return "ok"

        datasets_module = ModuleType("datasets")
        datasets_module.Dataset = FakeDataset

        ragas_module = ModuleType("ragas")
        ragas_module.evaluate = fake_evaluate

        ragas_llms_module = ModuleType("ragas.llms")
        ragas_llms_module.LangchainLLMWrapper = lambda llm: ("wrapped_llm", llm)

        ragas_embeddings_module = ModuleType("ragas.embeddings")
        ragas_embeddings_module.LangchainEmbeddingsWrapper = (
            lambda embeddings: ("wrapped_embeddings", embeddings)
        )

        ragas_metrics_module = ModuleType("ragas.metrics")
        ragas_metrics_module.answer_relevancy = object()
        ragas_metrics_module.context_precision = object()
        ragas_metrics_module.context_recall = object()
        ragas_metrics_module.faithfulness = object()

        monkeypatch.setitem(sys.modules, "datasets", datasets_module)
        monkeypatch.setitem(sys.modules, "ragas", ragas_module)
        monkeypatch.setitem(sys.modules, "ragas.llms", ragas_llms_module)
        monkeypatch.setitem(sys.modules, "ragas.embeddings", ragas_embeddings_module)
        monkeypatch.setitem(sys.modules, "ragas.metrics", ragas_metrics_module)
        monkeypatch.setattr("infrastructure.rag.evaluation.create_chat_model", lambda provider, model, temperature=0: "llm")
        monkeypatch.setattr("infrastructure.rag.evaluation.create_embeddings", lambda provider: "embeddings")

        result = evaluate_with_ragas(
            [{"user_input": "Q", "response": "A", "reference": "R", "retrieved_contexts": ["C"]}],
            provider="openai",
            model="gpt-4o-mini",
        )

        assert result == "ok"
        assert calls["metrics_count"] == 4
        assert calls["llm"] == ("wrapped_llm", "llm")
        assert calls["embeddings"] == ("wrapped_embeddings", "embeddings")
