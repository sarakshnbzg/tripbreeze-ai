"""Tests for domain/nodes/research_orchestrator.py — error handling paths."""

from unittest.mock import patch, MagicMock

from domain.nodes.research_orchestrator import research_orchestrator


def _make_ai_message(tool_calls=None, content=""):
    """Create a fake AIMessage with optional tool_calls and usage_metadata."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    msg.usage_metadata = {"input_tokens": 10, "output_tokens": 5}
    return msg


def _base_state():
    return {
        "trip_request": {
            "origin": "London",
            "destination": "Paris",
            "departure_date": "2025-06-01",
            "return_date": "2025-06-08",
        },
        "user_profile": {},
        "llm_provider": "openai",
        "llm_model": "gpt-4o-mini",
    }


class TestUnknownToolCall:
    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_unknown_tool_sends_error_message_and_continues(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        """When the LLM hallucinates a tool name, the orchestrator should
        send an error ToolMessage and continue to the next iteration."""
        # First response: LLM calls a hallucinated tool
        hallucinated_call = _make_ai_message(
            tool_calls=[{"name": "search_weather", "args": {}, "id": "call_1"}]
        )
        # Second response: LLM submits the final result
        submit_call = _make_ai_message(
            tool_calls=[{
                "name": "SubmitResearchResult",
                "args": {"summary": "Research done."},
                "id": "call_2",
            }]
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [hallucinated_call, submit_call]
        mock_create.return_value = mock_llm

        result = research_orchestrator(_base_state())

        # Should not crash, and should produce a valid result
        assert result["current_step"] == "research_complete"
        assert "Research done." in result["messages"][0]["content"]
        # LLM was called twice (hallucinated tool → retry → submit)
        assert mock_llm.invoke.call_count == 2


class TestSubmitResearchResultToolMessage:
    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_submit_result_produces_tool_message(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        """SubmitResearchResult should produce a ToolMessage in the conversation."""
        submit_call = _make_ai_message(
            tool_calls=[{
                "name": "SubmitResearchResult",
                "args": {
                    "summary": "All done.",
                    "destination_overview": "Paris is lovely.",
                },
                "id": "call_1",
            }]
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = submit_call
        mock_create.return_value = mock_llm

        result = research_orchestrator(_base_state())

        assert result["current_step"] == "research_complete"
        assert "Paris is lovely." in result["destination_info"]
        # Only one LLM call needed
        assert mock_llm.invoke.call_count == 1
