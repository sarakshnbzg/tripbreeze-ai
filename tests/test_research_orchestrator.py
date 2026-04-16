"""Tests for domain/nodes/research_orchestrator.py."""

from unittest.mock import patch, MagicMock

from domain.nodes.research_orchestrator import (
    _lookup_entry_requirements,
    _ordered_unique_destinations,
    research_orchestrator,
)


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
        assert "### France (Schengen Area)" in result["destination_info"]
        # Only one LLM call needed
        assert mock_llm.invoke.call_count == 1


class TestPreciseDestinationBriefing:
    def test_orders_unique_multi_city_destinations_by_trip_sequence(self):
        result = _ordered_unique_destinations(
            [
                {"destination": "Barcelona", "needs_hotel": True},
                {"destination": "Madrid", "needs_hotel": True},
                {"destination": "Barcelona", "needs_hotel": True},
                {"destination": "Berlin", "needs_hotel": False},
            ]
        )

        assert result == ["Barcelona", "Madrid"]

    def test_lookup_entry_requirements_filters_to_passport_country(self):
        entry = _lookup_entry_requirements("Paris", "US")

        assert "### France (Schengen Area)" in entry
        assert "US citizens" in entry
        assert "Canadian citizens" not in entry
        assert "Indian citizens" not in entry
        assert "Documents needed" in entry

    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_orchestrator_overrides_noisy_destination_briefing_with_precise_lookup(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        submit_call = _make_ai_message(
            tool_calls=[{
                "name": "SubmitResearchResult",
                "args": {
                    "summary": "All done.",
                    "destination_overview": "Local transport: Paris Metro is efficient.",
                    "entry_requirements": "Italy (Schengen Area): US, Canadian, EU, UK, Australian, Indian citizens...",
                },
                "id": "call_1",
            }]
        )

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = submit_call
        mock_create.return_value = mock_llm

        result = research_orchestrator(
            {
                **_base_state(),
                "user_profile": {"passport_country": "US"},
            }
        )

        assert "Local transport" not in result["destination_info"]
        assert "### France (Schengen Area)" in result["destination_info"]
        assert "US citizens" in result["destination_info"]
        assert "Canadian citizens" not in result["destination_info"]
        assert "Italy (Schengen Area)" not in result["destination_info"]

    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_leg_hotels")
    @patch("domain.nodes.research_orchestrator.search_leg_flights")
    def test_multi_city_briefing_uses_exact_city_sections_not_noisy_rag_fallback(
        self, mock_leg_flights, mock_leg_hotels, mock_retrieve
    ):
        mock_leg_flights.return_value = []
        mock_leg_hotels.return_value = []
        mock_retrieve.side_effect = [
            [{"content": "## Iran\n- **US citizens:** Tourist visa required.", "source": "Visa Requirements"}],
            [{"content": "Wrong Barcelona visa", "source": "Visa Requirements"}],
        ]

        result = research_orchestrator(
            {
                "trip_request": {
                    "origin": "Berlin",
                    "destination": "Madrid",
                    "departure_date": "2025-06-11",
                    "num_travelers": 2,
                },
                "trip_legs": [
                    {
                        "leg_index": 0,
                        "origin": "Berlin",
                        "destination": "Barcelona",
                        "departure_date": "2025-06-11",
                        "nights": 3,
                        "needs_hotel": True,
                    },
                    {
                        "leg_index": 1,
                        "origin": "Barcelona",
                        "destination": "Madrid",
                        "departure_date": "2025-06-14",
                        "nights": 2,
                        "needs_hotel": True,
                    },
                ],
                "user_profile": {"passport_country": "US"},
                "llm_provider": "openai",
                "llm_model": "gpt-4o-mini",
            }
        )

        assert result["current_step"] == "research_complete"
        assert result["destination_info"].index("### Barcelona") < result["destination_info"].index("### Madrid")
        assert "### Spain (Schengen Area)" in result["destination_info"]
        assert "Marrakech" not in result["destination_info"]
        assert "Iran" not in result["destination_info"]


class TestRagTrace:
    @patch("domain.nodes.research_orchestrator.retrieve")
    @patch("domain.nodes.research_orchestrator.search_hotels")
    @patch("domain.nodes.research_orchestrator.search_flights")
    @patch("domain.nodes.research_orchestrator.create_chat_model")
    def test_retrieve_knowledge_records_rag_trace(
        self, mock_create, mock_sf, mock_sh, mock_retrieve
    ):
        call_rag = _make_ai_message(
            tool_calls=[{"name": "retrieve_knowledge", "args": {"query": "Paris visa info"}, "id": "call_1"}]
        )
        submit_call = _make_ai_message(
            tool_calls=[{
                "name": "SubmitResearchResult",
                "args": {"summary": "Done."},
                "id": "call_2",
            }]
        )

        mock_retrieve.return_value = [
            {"content": "US citizens can visit visa-free.", "source": "Visa Requirements"},
        ]
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.side_effect = [call_rag, submit_call]
        mock_create.return_value = mock_llm

        result = research_orchestrator(
            {
                **_base_state(),
                "user_profile": {"passport_country": "US"},
            }
        )

        assert len(result["rag_trace"]) == 1
        assert result["rag_trace"][0]["node"] == "research_orchestrator"
        assert "Paris" in result["rag_trace"][0]["query"]
        assert result["rag_trace"][0]["results"][0]["source"] == "Visa Requirements"


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
