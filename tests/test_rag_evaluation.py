"""Tests for infrastructure/rag/evaluation.py."""

import sys
from types import ModuleType

from infrastructure.rag.evaluation import (
    _extract_json_object,
    build_retrieval_snapshot,
    evaluate_itinerary_with_llm_judge,
    evaluate_with_llm_judge,
    evaluate_with_ragas,
    generate_answers,
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


class TestGenerateAnswers:
    def test_prompt_requests_complete_grounded_details(self, monkeypatch):
        captured = {}

        class FakeResponse:
            content = "Grounded answer"

        monkeypatch.setattr(
            "infrastructure.rag.evaluation.create_chat_model",
            lambda provider, model, temperature=0: "answer-llm",
        )

        def fake_invoke(llm, prompt):
            captured["llm"] = llm
            captured["prompt"] = prompt
            return FakeResponse()

        monkeypatch.setattr("infrastructure.rag.evaluation.invoke_with_retry", fake_invoke)

        rows = generate_answers(
            [
                {
                    "user_input": "What are the entry requirements for a US passport holder visiting Paris?",
                    "retrieved_contexts": ["France visa-free for US citizens. Documents needed: passport valid 3+ months."],
                }
            ],
            provider="openai",
            model="gpt-4.1-mini",
        )

        assert rows[0]["response"] == "Grounded answer"
        assert captured["llm"] == "answer-llm"
        assert "passport validity requirements" in captured["prompt"]
        assert "required or supporting documents" in captured["prompt"]
        assert "Do not invent missing details" in captured["prompt"]


class TestJudgeJsonExtraction:
    def test_extracts_plain_json_object(self):
        parsed = _extract_json_object('{"overall_score": 4}')
        assert parsed["overall_score"] == 4

    def test_extracts_json_from_fenced_block(self):
        parsed = _extract_json_object('```json\n{"overall_score": 5}\n```')
        assert parsed["overall_score"] == 5


class TestEvaluateWithLlmJudge:
    def test_returns_row_level_and_aggregate_scores(self, monkeypatch):
        class FakeResponse:
            content = (
                '{"faithfulness_to_context": 5, "answer_correctness": 4, '
                '"answer_completeness": 4, "groundedness": 5, "overall_score": 4, '
                '"pass": true, "strengths": ["Grounded"], "issues": ["Minor omission"], '
                '"rationale": "Mostly correct and grounded."}'
            )

        monkeypatch.setattr("infrastructure.rag.evaluation.create_chat_model", lambda provider, model, temperature=0: "judge-llm")
        monkeypatch.setattr("infrastructure.rag.evaluation.invoke_with_retry", lambda llm, prompt: FakeResponse())

        result = evaluate_with_llm_judge(
            [
                {
                    "user_input": "Do US citizens need a visa for Portugal?",
                    "reference": "US citizens can usually visit visa-free for short stays.",
                    "retrieved_contexts": ["Portugal allows short visa-free stays for US citizens."],
                    "response": "US citizens can usually visit visa-free for short stays.",
                }
            ],
            provider="openai",
            model="gpt-4.1-mini",
        )

        assert result["judge_provider"] == "openai"
        assert result["judge_model"] == "gpt-4.1-mini"
        assert result["sample_count"] == 1
        assert result["pass_rate"] == 1.0
        assert result["average_scores"]["overall_score"] == 4.0
        assert result["rows"][0]["judge"]["pass"] is True
        assert result["rows"][0]["judge"]["strengths"] == ["Grounded"]


class TestEvaluateItineraryWithLlmJudge:
    def test_returns_itinerary_quality_scores(self, monkeypatch):
        class FakeResponse:
            content = (
                '{"constraint_following": 5, "trip_relevance": 4, '
                '"structure_quality": 5, "personalization": 4, "groundedness": 5, '
                '"overall_score": 4, "pass": true, "strengths": ["Good structure"], '
                '"issues": ["Could be more personalized"], '
                '"rationale": "The itinerary is coherent and broadly fits the trip."}'
            )

        monkeypatch.setattr(
            "infrastructure.rag.evaluation.create_chat_model",
            lambda provider, model, temperature=0: "judge-llm",
        )
        monkeypatch.setattr(
            "infrastructure.rag.evaluation.invoke_with_retry",
            lambda llm, prompt: FakeResponse(),
        )

        result = evaluate_itinerary_with_llm_judge(
            input_state={
                "trip_request": {"destination": "Lisbon", "interests": ["food"]},
                "user_feedback": "Keep the final day light.",
                "destination_info": "Lisbon overview",
                "budget": {"total_estimated": 1200},
                "attraction_candidates": [{"name": "Time Out Market"}],
            },
            final_itinerary="#### Trip Overview\nLisbon food trip",
            itinerary_data={"daily_plans": [{"day_number": 1}]},
            provider="openai",
            model="gpt-4.1-mini",
        )

        assert result["judge_provider"] == "openai"
        assert result["judge_model"] == "gpt-4.1-mini"
        assert result["result"]["pass"] is True
        assert result["result"]["constraint_following"] == 5
        assert result["result"]["overall_score"] == 4
