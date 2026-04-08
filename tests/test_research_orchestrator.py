"""Tests for domain/nodes/research_orchestrator.py — error handling paths."""

from unittest.mock import patch, MagicMock

from domain.nodes.research_orchestrator import destination_research, research_orchestrator


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


class TestIterationExhaustion:
    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_produces_result_after_exhausting_iterations(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        """When the LLM never calls SubmitResearchResult, the orchestrator
        should still return a valid result after exhausting all iterations."""
        # Every response calls a real tool but never submits
        def make_tool_response():
            return _make_ai_message(
                tool_calls=[{"name": "search_flights", "args": {}, "id": "call_loop"}]
            )

        mock_sf.return_value = {
            "flight_options": [],
            "messages": [{"role": "assistant", "content": "No flights found."}],
        }

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [make_tool_response() for _ in range(6)]
        mock_create.return_value = mock_llm

        result = research_orchestrator(_base_state())

        assert result["current_step"] == "research_complete"
        assert mock_llm.invoke.call_count == 6

    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_logs_warning_on_exhaustion(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        """Exhausting iterations should log a warning."""
        def make_tool_response():
            return _make_ai_message(
                tool_calls=[{"name": "search_flights", "args": {}, "id": "call_loop"}]
            )

        mock_sf.return_value = {
            "flight_options": [],
            "messages": [{"role": "assistant", "content": "No flights found."}],
        }

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [make_tool_response() for _ in range(6)]
        mock_create.return_value = mock_llm

        with patch("domain.nodes.research_orchestrator.logger") as mock_logger:
            research_orchestrator(_base_state())
            mock_logger.warning.assert_any_call(
                "Research orchestrator exhausted all %s iterations without a final result",
                6,
            )


class TestDestinationResearch:
    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_prepares_destination_briefing_from_retrieved_chunks(self, mock_create, mock_retrieve):
        mock_retrieve.return_value = [
            {
                "content": "Paris has strong metro coverage. (Source: Travel Tips)",
                "source": "Travel Tips",
            }
        ]
        submit_call = _make_ai_message(
            tool_calls=[{
                "name": "SubmitResearchResult",
                "args": {
                    "summary": "Prepared destination briefing.",
                    "transport_tips": "Use the metro for most city travel. (Source: Travel Tips)",
                },
                "id": "call_1",
            }]
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = submit_call
        mock_create.return_value = mock_llm

        result = destination_research(_base_state())

        assert result["current_step"] == "destination_research_complete"
        assert result["rag_used"] is True
        assert result["rag_sources"] == ["Travel Tips"]
        assert "#### 🚇 Getting Around" in result["destination_info"]
        assert "Prepared destination briefing." in result["messages"][0]["content"]

    def test_skips_when_destination_missing(self):
        state = _base_state()
        state["trip_request"]["destination"] = ""

        result = destination_research(state)

        assert result["current_step"] == "destination_research_complete"
        assert result["destination_info"] == ""
        assert result["rag_used"] is False
        assert "destination is missing" in result["messages"][0]["content"].lower()
