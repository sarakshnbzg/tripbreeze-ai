"""Tests for domain/nodes/trip_finaliser.py."""

from unittest.mock import MagicMock, patch

from domain.nodes.trip_finaliser import (
    _build_multi_city_daily_plans,
    render_itinerary_markdown,
    Itinerary,
    Source,
    _format_multi_city_budget,
    _multi_city_flight_summary,
    _multi_city_packing_tips,
    _parse_multi_city_destination_info,
    _selected_flight_context,
    _selected_hotel_context,
    _traveler_preference_context,
)


class TestRenderItineraryMarkdown:
    def _sample_itinerary(self, **overrides):
        defaults = {
            "trip_overview": "London to Paris, July 1-8",
            "flight_details": "BA 123, direct",
            "hotel_details": "Hotel Le Marais, 4-star",
            "destination_highlights": "Eiffel Tower, Louvre",
            "budget_breakdown": "Flight: $500, Hotel: $800",
            "visa_entry_info": "No visa required for UK citizens",
            "packing_tips": "Bring an umbrella",
            "sources": [],
        }
        defaults.update(overrides)
        return Itinerary(**defaults)

    def test_all_sections_present(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "Trip Overview" in md
        assert "Flight Details" in md
        assert "Hotel Details" in md
        assert "Destination Highlights" in md
        assert "Budget Breakdown" in md
        assert "Visa & Entry Information" in md
        assert "Packing & Preparation Tips" in md

    def test_content_included(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "London to Paris" in md
        assert "BA 123" in md
        assert "Eiffel Tower" in md

    def test_sources_included_when_present(self):
        sources = [
            Source(document="destinations.md", snippet="Paris is a top destination"),
            Source(document="visa_requirements.md", snippet="No visa needed"),
        ]
        md = render_itinerary_markdown(self._sample_itinerary(sources=sources))
        assert "Sources (from Knowledge Base)" in md
        assert "destinations.md" in md
        assert "visa_requirements.md" in md
        assert "Paris is a top destination" in md

    def test_no_sources_section_when_empty(self):
        md = render_itinerary_markdown(self._sample_itinerary(sources=[]))
        assert "Sources" not in md

    def test_sections_separated_by_blank_lines(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert "\n\n" in md

    def test_uses_smaller_section_headings(self):
        md = render_itinerary_markdown(self._sample_itinerary())
        assert md.startswith("#### ✈️ Trip Overview\n")

    def test_flight_details_render_as_bullets_when_plain_text(self):
        md = render_itinerary_markdown(
            self._sample_itinerary(
                flight_details="BA 123 departs at 09:00. It is a direct flight. Baggage is included.",
            )
        )
        assert "#### 🛫 Flight Details" in md
        assert "- BA 123 departs at 09:00." in md
        assert "- It is a direct flight." in md
        assert "- Baggage is included." in md

    def test_hotel_details_preserve_existing_markdown_lists(self):
        md = render_itinerary_markdown(
            self._sample_itinerary(
                hotel_details="- Hotel Le Marais\n- 4-star stay\n- Breakfast included",
            )
        )
        assert "#### 🏨 Hotel Details" in md
        assert "- Hotel Le Marais" in md
        assert "- 4-star stay" in md
        assert "- Breakfast included" in md


class TestItineraryModel:
    def test_default_sources_empty(self):
        it = Itinerary(
            trip_overview="test",
            flight_details="test",
            hotel_details="test",
            destination_highlights="test",
            budget_breakdown="test",
            visa_entry_info="test",
            packing_tips="test",
        )
        assert it.sources == []

    def test_model_dump_roundtrip(self):
        it = Itinerary(
            trip_overview="overview",
            flight_details="flight",
            hotel_details="hotel",
            destination_highlights="highlights",
            budget_breakdown="budget",
            visa_entry_info="visa",
            packing_tips="packing",
            sources=[Source(document="doc.md", snippet="snippet")],
        )
        data = it.model_dump()
        restored = Itinerary(**data)
        assert restored.trip_overview == "overview"
        assert len(restored.sources) == 1
        assert restored.sources[0].document == "doc.md"


class TestSelectedFlightContext:
    def test_includes_outbound_and_return_summaries_for_round_trip(self):
        context = _selected_flight_context(
            {
                "airline": "Lufthansa",
                "outbound_summary": "BER 2026-04-09 08:00 -> LHR 2026-04-09 09:00",
                "return_summary": "LHR 2026-04-10 18:00 -> BER 2026-04-10 21:00",
                "selected_return": {"airline": "Lufthansa"},
            },
            {"return_date": "2026-04-10"},
        )
        assert "Outbound flight summary:" in context
        assert "Return flight summary:" in context
        assert "BER 2026-04-09 08:00" in context
        assert "LHR 2026-04-10 18:00" in context

    def test_omits_return_summary_for_one_way(self):
        context = _selected_flight_context(
            {"outbound_summary": "BER 2026-04-09 08:00 -> LHR 2026-04-09 09:00"},
            {},
        )
        assert "Outbound flight summary:" in context
        assert "Return flight summary:" not in context


class TestMultiCityFlightSummary:
    def test_uses_outbound_summary_when_present(self):
        summary = _multi_city_flight_summary(
            {"outbound_summary": "BER 08:35 → CDG 10:25", "airline": "Air France"},
            "EUR",
        )
        assert summary == "BER 08:35 → CDG 10:25"

    def test_builds_summary_from_raw_fields_when_outbound_summary_missing(self):
        summary = _multi_city_flight_summary(
            {
                "airline": "Air France",
                "departure_time": "08:35",
                "arrival_time": "10:25",
                "duration": "1h 50m",
                "stops": 0,
                "total_price": 117,
            },
            "EUR",
        )
        assert "Air France" in summary
        assert "08:35 → 10:25" in summary
        assert "1h 50m" in summary
        assert "Direct" in summary
        assert "EUR 117 total" in summary


class TestMultiCityDerivedSections:
    def test_parses_destination_info_into_highlights_and_entry_sections(self):
        destination_info = (
            "A quick travel snapshot for each destination to help you compare options and plan your stay:\n\n"
            "### Paris\n\n"
            "#### 🌍 Overview\n"
            "Paris, France is a strong city-break choice; best time to visit is April-June. (Source: Destinations)\n\n"
            "#### 🛂 Entry Requirements\n"
            "### France (Schengen Area)\n"
            "- **US citizens:** Visa-free for up to 90 days. (Source: Visa Requirements)\n"
            "- **Documents needed:** Passport valid 3+ months beyond stay. (Source: Visa Requirements)\n\n"
            "---\n\n"
            "### Rome\n\n"
            "#### 🌍 Overview\n"
            "Rome, Italy is a strong city-break choice; best time to visit is April-May. (Source: Destinations)\n\n"
            "#### 🛂 Entry Requirements\n"
            "### Italy (Schengen Area)\n"
            "- **US citizens:** Visa-free for up to 90 days. (Source: Visa Requirements)"
        )

        highlights, visa_info = _parse_multi_city_destination_info(destination_info)

        assert "**Paris:** Paris, France is a strong city-break choice" in highlights
        assert "**Rome:** Rome, Italy is a strong city-break choice" in highlights
        assert "Source:" not in highlights
        assert "**Paris — France (Schengen Area)**" in visa_info
        assert "**US citizens:** Visa-free for up to 90 days." in visa_info
        assert "Documents needed" in visa_info

    def test_formats_multi_city_budget_for_users(self):
        budget_md = _format_multi_city_budget(
            {
                "flight_cost": 566.0,
                "hotel_cost": 458.0,
                "estimated_daily_expenses": 860.0,
                "total_estimated": 1884.0,
                "budget_notes": "You're within budget with ~EUR 1116 to spare.",
                "per_leg_breakdown": [
                    {
                        "origin": "Berlin",
                        "destination": "Paris",
                        "nights": 2,
                        "flight_cost": 161,
                        "hotel_cost": 269,
                        "daily_expenses": 440,
                        "leg_total": 870,
                    }
                ],
            },
            "EUR",
        )

        assert 'flight_cost' not in budget_md
        assert "- Flights: EUR 566" in budget_md
        assert "- Total estimated trip cost: EUR 1,884" in budget_md
        assert "**Per leg**" in budget_md
        assert "Berlin → Paris" in budget_md

    def test_builds_trip_aware_packing_tips(self):
        tips = _multi_city_packing_tips(
            {"departure_date": "2026-06-11"},
            [
                {"destination": "Paris", "nights": 2},
                {"destination": "Rome", "nights": 2},
            ],
        )

        assert "Paris, Rome" in tips
        assert "June" in tips
        assert "passports" in tips

    def test_builds_multi_city_daily_plans_from_leg_dates(self):
        plans = _build_multi_city_daily_plans(
            [
                {
                    "origin": "Berlin",
                    "destination": "Paris",
                    "departure_date": "2026-06-11",
                    "nights": 2,
                },
                {
                    "origin": "Paris",
                    "destination": "Rome",
                    "departure_date": "2026-06-13",
                    "nights": 2,
                },
                {
                    "origin": "Rome",
                    "destination": "Berlin",
                    "departure_date": "2026-06-15",
                    "nights": 0,
                },
            ]
        )

        assert len(plans) == 4
        assert plans[0].date == "2026-06-11"
        assert plans[0].theme == "Arrive in Paris from Berlin"
        assert plans[1].date == "2026-06-12"
        assert plans[1].theme == "Final full day in Paris"
        assert plans[2].date == "2026-06-13"
        assert plans[2].theme == "Arrive in Rome from Paris"
        assert plans[3].date == "2026-06-14"

    @patch("domain.nodes.trip_finaliser.fetch_weather_for_trip", return_value={})
    @patch("domain.nodes.trip_finaliser.create_chat_model")
    def test_multi_city_trip_uses_llm_structured_itinerary(self, mock_create, _mock_weather):
        response = MagicMock()
        response.tool_calls = [
            {
                "id": "mc-1",
                "name": "MultiCityItinerary",
                "args": {
                    "trip_overview": "Berlin → Paris → Rome → Berlin for 4 nights.",
                    "legs": [
                        {
                            "leg_number": 1,
                            "origin": "Berlin",
                            "destination": "Paris",
                            "departure_date": "2026-06-11",
                            "flight_summary": "Air France direct",
                            "hotel_summary": "Hotel Le Marais - 4 stars",
                            "nights": 2,
                        }
                    ],
                    "destination_highlights": "- **Paris:** Great for a short city break.",
                    "daily_plans": [
                        {"day_number": 1, "date": "2026-06-11", "theme": "Arrive in Paris", "activities": []}
                    ],
                    "budget_breakdown": "- Total estimated trip cost: EUR 1,884",
                    "visa_entry_info": "**Paris — France (Schengen Area)**\n- **US citizens:** Visa-free for up to 90 days.",
                    "packing_tips": "- Pack light layers.",
                    "sources": [],
                },
            }
        ]
        response.usage_metadata = {"input_tokens": 50, "output_tokens": 100}

        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_llm.invoke.return_value = response
        mock_create.return_value = mock_llm

        state = {
            "trip_legs": [
                {"leg_index": 0, "origin": "Berlin", "destination": "Paris", "departure_date": "2026-06-11", "nights": 2, "needs_hotel": True},
                {"leg_index": 1, "origin": "Paris", "destination": "Rome", "departure_date": "2026-06-13", "nights": 2, "needs_hotel": True},
                {"leg_index": 2, "origin": "Rome", "destination": "Berlin", "departure_date": "2026-06-15", "nights": 0, "needs_hotel": False},
            ],
            "trip_request": {
                "origin": "Berlin",
                "departure_date": "2026-06-11",
                "return_date": "2026-06-15",
                "currency": "EUR",
                "num_travelers": 2,
                "pace": "moderate",
                "interests": ["food", "art"],
            },
            "selected_flights": [{"airline": "Air France", "outbound_summary": "BER 08:00 → CDG 10:00"}],
            "selected_hotels": [{"name": "Hotel Le Marais", "rating": 4}],
            "destination_info": "### Paris\n\n#### 🌍 Overview\nParis overview.\n\n#### 🛂 Entry Requirements\n### France (Schengen Area)\n- **US citizens:** Visa-free.",
            "budget": {"total_estimated": 1884, "currency": "EUR"},
            "llm_provider": "openai",
            "llm_model": "gpt-4o-mini",
            "llm_temperature": 0.5,
            "user_profile": {},
            "rag_sources": [],
        }

        from domain.nodes.trip_finaliser import trip_finaliser

        result = trip_finaliser(state)

        assert "Berlin → Paris → Rome → Berlin for 4 nights." in result["final_itinerary"]
        assert "Arrive in Paris" in result["final_itinerary"]
        assert result["itinerary_data"]["daily_plans"][0]["date"] == "2026-06-11"
        assert result["rag_trace"] == []
        assert mock_llm.invoke.call_count == 1


class TestTravelerPreferenceContext:
    def test_summarises_profile_and_trip_preferences(self):
        context = _traveler_preference_context(
            {
                "travel_class": "BUSINESS",
                "hotel_stars": [4, 5],
                "interests": ["food", "art"],
                "pace": "relaxed",
                "preferences": "quiet boutique hotel",
            },
            {
                "preferred_airlines": ["Lufthansa"],
                "preferred_hotel_stars": [4],
                "preferred_outbound_time_window": [8, 12],
                "preferred_return_time_window": [14, 20],
            },
        )
        assert "Travel class: BUSINESS" in context
        assert "Preferred airlines: Lufthansa" in context
        assert "Requested hotel stars for this trip: 4, 5" in context
        assert "Interests: food, art" in context
        assert "Free-text preferences: quiet boutique hotel" in context


class TestSelectedHotelContext:
    def test_includes_preference_reasons_when_available(self):
        context = _selected_hotel_context(
            {
                "name": "Hotel Le Marais",
                "preference_reasons": ["matches preferred hotel class", "offers breakfast"],
            }
        )
        assert "Hotel Le Marais" in context
        assert "Preference matches: matches preferred hotel class, offers breakfast" in context
