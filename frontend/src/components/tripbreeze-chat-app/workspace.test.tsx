import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SelectionState } from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";

import { buildItineraryViewModel } from "./view-models";
import { FinalItineraryPanel, ReviewPanel, type ReviewWorkspaceModel } from "./workspace";

function buildSelection(overrides: Partial<SelectionState> = {}): SelectionState {
  return {
    flightIndex: -1,
    hotelIndex: -1,
    byLegFlights: [],
    byLegHotels: [],
    ...overrides,
  };
}

function buildReviewWorkspaceModel(overrides: Partial<ReviewWorkspaceModel> = {}): ReviewWorkspaceModel {
  return {
    hasReviewWorkspace: true,
    finalItinerary: "",
    state: {
      destination_info: "### Entry\nPassport required.",
      flight_options: [],
      hotel_options: [],
      budget: {},
    } as unknown as TravelState,
    isRoundTrip: false,
    completedMultiCityLegs: 0,
    hasSelectedSingleFlight: false,
    hasSelectedSingleHotel: false,
    selectedOutboundOption: {},
    selectedReturnIndex: null,
    selectedReturnOption: {},
    selectedHotelOption: {},
    hasOptionResults: false,
    partialResultsNote: "",
    currencyCode: "EUR",
    selection: buildSelection(),
    returnOptions: [],
    showPersonalisationPanel: false,
    canApprove: false,
    returnOptionsLoading: false,
    interests: [],
    pace: "moderate",
    feedback: "",
    loading: null,
    ...overrides,
  };
}

function renderReviewPanel(overrides: Partial<ReviewWorkspaceModel> = {}) {
  const setSelectedReturnIndex = vi.fn();
  const setSelection = vi.fn();
  const setInterests = vi.fn();
  const setPace = vi.fn();
  const setFeedback = vi.fn();
  const handleReview = vi.fn();

  render(
    <ReviewPanel
      model={buildReviewWorkspaceModel(overrides)}
      actions={{
        setSelectedReturnIndex,
        setSelection,
        setInterests,
        setPace,
        setFeedback,
        handleReview,
      }}
      refs={{
        outboundSectionRef: { current: null },
        returnSectionRef: { current: null },
        hotelSectionRef: { current: null },
        personaliseSectionRef: { current: null },
      }}
    />,
  );

  return {
    setSelectedReturnIndex,
    setSelection,
    setInterests,
    setPace,
    setFeedback,
    handleReview,
  };
}

describe("workspace panels", () => {
  it("renders the destination briefing in the review workspace", () => {
    renderReviewPanel();

    expect(screen.getByText("Destination briefing")).toBeInTheDocument();
    expect(screen.getByText("Passport required.")).toBeInTheDocument();
  });

  it("surfaces visa source trust clearly in the review workspace", () => {
    renderReviewPanel({
      state: {
        destination_info: `### Entry
Passport required.

#### Source Trust
- Source: France-Visas
- Authority: official_government
- Official link: https://france-visas.gouv.fr/
- Last verified: 2026-04-28 (fresh)`,
        flight_options: [],
        hotel_options: [],
        budget: {},
      } as unknown as TravelState,
    });

    expect(screen.getByText("Source trust")).toBeInTheDocument();
    expect(screen.getByText("France-Visas")).toBeInTheDocument();
    expect(screen.getByText("2026-04-28 (fresh)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check official source" })).toHaveAttribute(
      "href",
      "https://france-visas.gouv.fr/",
    );
  });

  it("lets the user choose a return option in round-trip review", () => {
    const returnOption: TripOption = {
      airline: "Return Air",
      outbound_summary: "Madrid to Berlin",
      total_price: 220,
    };

    const { setSelectedReturnIndex } = renderReviewPanel({
      state: {
        flight_options: [{ airline: "Outbound Air", outbound_summary: "Berlin to Madrid", total_price: 200 }],
        hotel_options: [{ name: "City Stay", total_price: 400 }],
      } as TravelState,
      isRoundTrip: true,
      hasOptionResults: true,
      hasSelectedSingleFlight: true,
      hasSelectedSingleHotel: false,
      selection: buildSelection({ flightIndex: 0 }),
      returnOptions: [returnOption],
    });

    fireEvent.click(screen.getByRole("button", { name: /return air/i }));

    expect(setSelectedReturnIndex).toHaveBeenCalledWith(0);
  });

  it("renders multi-city review progress and leg sections", () => {
    renderReviewPanel({
      state: {
        trip_legs: [
          { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3, needs_hotel: true },
          { origin: "Paris", destination: "Berlin", departure_date: "2026-06-13", nights: 0, needs_hotel: false },
        ],
        flight_options_by_leg: [
          [{ airline: "Outbound Air", outbound_summary: "Berlin to Paris", total_price: 180 }],
          [{ airline: "Return Air", outbound_summary: "Paris to Berlin", total_price: 170 }],
        ],
        hotel_options_by_leg: [
          [{ name: "Paris Stay", total_price: 420 }],
          [],
        ],
        flight_options: [],
        hotel_options: [],
      } as unknown as TravelState,
      hasOptionResults: true,
      completedMultiCityLegs: 1,
      selection: buildSelection({ byLegFlights: [0, 0], byLegHotels: [0] }),
    });

    expect(screen.getByText(/Multi-city progress:/)).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 legs fully selected/)).toBeInTheDocument();
    expect(screen.getByText(/Leg 1: Berlin to Paris/)).toBeInTheDocument();
    expect(screen.getByText(/Leg 2: Paris to Berlin/)).toBeInTheDocument();
    expect(screen.getByText("Paris Stay")).toBeInTheDocument();
  });

  it("shows leg-specific partial-results guidance in multi-city review", () => {
    renderReviewPanel({
      state: {
        trip_legs: [
          { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3, needs_hotel: true },
        ],
        flight_options_by_leg: [[]],
        hotel_options_by_leg: [[{ name: "Paris Stay", total_price: 420 }]],
        budget: {
          partial_results_note: "Some legs have only partial results right now (1 of 1). Review each leg for details or revise the search.",
          per_leg_breakdown: [
            {
              partial_results_note:
                "Hotel options are ready for this leg, but flight options are unavailable right now.",
            },
          ],
        },
      } as unknown as TravelState,
      hasOptionResults: true,
      partialResultsNote: "Some legs have only partial results right now (1 of 1). Review each leg for details or revise the search.",
      completedMultiCityLegs: 0,
      selection: buildSelection(),
    });

    expect(screen.getByText(/Some legs have only partial results right now/)).toBeInTheDocument();
    expect(screen.getByText(/Partial results for this leg:/)).toBeInTheDocument();
    expect(screen.getByText(/Hotel options are ready for this leg, but flight options are unavailable right now./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paris stay/i })).toBeInTheDocument();
  });

  it("shows partial-results guidance and preserves hotel options when flights are unavailable", () => {
    renderReviewPanel({
      state: {
        destination_info: "### Porto\nBudget-friendly riverside stay.",
        flight_options: [],
        hotel_options: [{ name: "Harbor Hotel", total_price: 380 }],
        budget: {
          partial_results_note:
            "Hotel options are ready, but flight options are unavailable right now. You can revise the search to try different dates, budget, or destination.",
        },
      } as unknown as TravelState,
      hasOptionResults: true,
      partialResultsNote:
        "Hotel options are ready, but flight options are unavailable right now. You can revise the search to try different dates, budget, or destination.",
    });

    expect(screen.getByText(/Partial results available:/)).toBeInTheDocument();
    expect(screen.getByText(/Hotel options are ready, but flight options are unavailable right now./)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /harbor hotel/i })).toBeInTheDocument();
    expect(screen.getByText("No flights found. Try different dates or cities.")).toBeInTheDocument();
  });

  it("renders final itinerary snapshot, booking links, and day plan details", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "Trip ready",
          hasStructuredItinerary: true,
          fallbackNotice: null,
          snapshotItems: [
            { label: "Route", value: "Berlin -> Lisbon" },
            { label: "Dates", value: "2026-06-10 to 2026-06-15" },
          ],
          bookingLinks: [
            { label: "Flight booking", url: "https://example.com/flight" },
          ],
          primarySections: [
            { key: "flight", title: "Flight details", content: "Nonstop outbound" },
            { key: "visa", title: "Visa and entry", content: "Passport valid for 3 months after departure." },
          ],
          secondarySections: [
            { key: "packing", title: "Packing tips", content: "Bring layers." },
          ],
          visaTrust: {
            sourceName: "France-Visas",
            authority: "official_government",
            officialLink: "https://france-visas.gouv.fr/",
            lastVerified: "2026-04-28 (fresh)",
            isStale: false,
          },
          mapPoints: [
            {
              latitude: 38.7223,
              longitude: -9.1393,
              label: "Lisbon stay",
              kind: "hotel",
              detail: "City center",
              mapsUrl: "https://www.google.com/maps/search/?api=1&query=38.7223,-9.1393",
            },
          ],
          itineraryLegs: [
            {
              leg_number: 1,
              origin: "Berlin",
              destination: "Lisbon",
              departure_date: "2026-06-10",
              flight_summary: "Morning departure",
            },
          ],
          itineraryDays: [
            {
              day_number: 1,
              theme: "Arrival",
              date: "2026-06-10",
              weather: {
                condition: "Sunny",
                temp_min: 18,
                temp_max: 26,
              },
              activities: [
                {
                  name: "Check in",
                  time_of_day: "Afternoon",
                  notes: "Drop bags and explore nearby.",
                  maps_url: "https://www.google.com/maps/search/?api=1&query=Lisbon",
                },
              ],
            },
          ],
        }}
        shareState={{
          loading: null,
          emailAddress: "",
          shareMessage: "",
          setEmailAddress: vi.fn(),
          onDownloadPdf: vi.fn(async () => undefined),
          onEmailItinerary: vi.fn(async () => undefined),
        }}
      />,
    );

    expect(screen.getByText("Trip snapshot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Flight booking" })).toHaveAttribute("href", "https://example.com/flight");
    expect(screen.getByText("Flight details")).toBeInTheDocument();
    expect(screen.getByText("Visa and entry")).toBeInTheDocument();
    expect(screen.getByText("Source trust")).toBeInTheDocument();
    expect(screen.getByText("France-Visas")).toBeInTheDocument();
    expect(screen.getByText("Packing tips")).toBeInTheDocument();
    expect(screen.getByText("Trip map")).toBeInTheDocument();
    expect(screen.getByText(/Leg 1: Berlin to Lisbon/)).toBeInTheDocument();
    expect(screen.getByText(/Day 1 · Arrival/)).toBeInTheDocument();
    expect(screen.getByText("Check in")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Google Maps" })).toHaveAttribute(
      "href",
      "https://www.google.com/maps/search/?api=1&query=Lisbon",
    );
  });

  it("shows a streaming shell until structured itinerary data is ready", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "#### Trip Overview\nBerlin to Lisbon",
          hasStructuredItinerary: false,
          fallbackNotice: null,
          snapshotItems: [],
          bookingLinks: [],
          primarySections: [],
          secondarySections: [],
          visaTrust: null,
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
        }}
        shareState={{
          loading: "approving",
          emailAddress: "",
          shareMessage: "",
          setEmailAddress: vi.fn(),
          onDownloadPdf: vi.fn(async () => undefined),
          onEmailItinerary: vi.fn(async () => undefined),
        }}
      />,
    );

    expect(screen.getByText("Generating final itinerary...")).toBeInTheDocument();
    expect(screen.getByText("Live draft")).toBeInTheDocument();
    expect(screen.queryByText("Trip snapshot")).not.toBeInTheDocument();
    expect(screen.getByText("Berlin to Lisbon")).toBeInTheDocument();
  });

  it("renders a recovery notice when the final itinerary used fallback generation", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "Recovered trip",
          hasStructuredItinerary: true,
          fallbackNotice: {
            title: "Recovered itinerary",
            detail: "The planner did not finish the structured itinerary step, so TripBreeze recovered this itinerary from your approved trip details.",
          },
          snapshotItems: [{ label: "Route", value: "Berlin -> Paris" }],
          bookingLinks: [],
          primarySections: [],
          secondarySections: [],
          visaTrust: null,
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
        }}
        shareState={{
          loading: null,
          emailAddress: "",
          shareMessage: "",
          setEmailAddress: vi.fn(),
          onDownloadPdf: vi.fn(async () => undefined),
          onEmailItinerary: vi.fn(async () => undefined),
        }}
      />,
    );

    expect(screen.getByText("Recovered itinerary")).toBeInTheDocument();
    expect(
      screen.getByText(
        "The planner did not finish the structured itinerary step, so TripBreeze recovered this itinerary from your approved trip details.",
      ),
    ).toBeInTheDocument();
  });

  it("shows itinerary email success in the share panel", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "Recovered trip",
          hasStructuredItinerary: true,
          fallbackNotice: null,
          snapshotItems: [{ label: "Route", value: "Berlin -> Paris" }],
          bookingLinks: [],
          primarySections: [],
          secondarySections: [],
          visaTrust: null,
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
        }}
        shareState={{
          loading: null,
          emailAddress: "sara@example.com",
          shareMessage: "Sent to sara@example.com",
          setEmailAddress: vi.fn(),
          onDownloadPdf: vi.fn(async () => undefined),
          onEmailItinerary: vi.fn(async () => undefined),
        }}
      />,
    );

    expect(screen.getByText("Sent to sara@example.com")).toBeInTheDocument();
  });

  it("builds Google Maps links for trip map points", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        selected_hotel: {
          name: "Lisbon stay",
          latitude: 38.7223,
          longitude: -9.1393,
          address: "City center",
        },
        itinerary_data: {
          daily_plans: [
            {
              day_number: 1,
              activities: [
                {
                  name: "Alfama walk",
                  latitude: 38.711,
                  longitude: -9.13,
                  maps_url: "https://www.google.com/maps/search/?api=1&query=Alfama",
                },
              ],
            },
          ],
        },
        finaliser_metadata: {
          used_fallback: true,
          fallback_reason: "structured_parse_failed",
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.mapPoints).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          label: "Lisbon stay",
          mapsUrl: "https://www.google.com/maps/search/?api=1&query=38.7223,-9.1393",
        }),
        expect.objectContaining({
          label: "Alfama walk",
          mapsUrl: "https://www.google.com/maps/search/?api=1&query=Alfama",
        }),
      ]),
    );
    expect(viewModel.hasStructuredItinerary).toBe(true);
    expect(viewModel.fallbackNotice).toEqual({
      title: "Recovered itinerary",
      detail:
        "The planner returned malformed itinerary data, so TripBreeze recovered this itinerary from your approved trip details.",
    });
  });

  it("extracts visa trust metadata into a dedicated itinerary field", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          visa_entry_info: `Passport required.

#### Source Trust
- Source: Portugal Ministry of Foreign Affairs
- Authority: official_government
- Official link: https://vistos.mne.gov.pt/
- Last verified: 2026-04-28 (stale - please re-check official rules)`,
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.primarySections).toEqual([
      expect.objectContaining({
        key: "visa",
        content: "Passport required.",
      }),
    ]);
    expect(viewModel.visaTrust).toEqual({
      sourceName: "Portugal Ministry of Foreign Affairs",
      authority: "official_government",
      officialLink: "https://vistos.mne.gov.pt/",
      lastVerified: "2026-04-28 (stale - please re-check official rules)",
      isStale: true,
    });
  });

  it("omits generic travel logistics from trip map points", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          daily_plans: [
            {
              day_number: 3,
              activities: [
                {
                  name: "Baggage storage",
                  latitude: -3.119,
                  longitude: 11.887,
                },
                {
                  name: "Trevi Fountain",
                  latitude: 41.9009,
                  longitude: 12.4833,
                },
              ],
            },
          ],
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.mapPoints).toEqual([
      expect.objectContaining({
        label: "Trevi Fountain",
        latitude: 41.9009,
        longitude: 12.4833,
      }),
    ]);
  });

  it("omits flexible nearby placeholder activities from trip map points", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          daily_plans: [
            {
              day_number: 4,
              theme: "Departure Day",
              activities: [
                {
                  name: "Flexible Activity Nearby",
                  is_mappable: false,
                  latitude: -3.5,
                  longitude: 10.2,
                },
                {
                  name: "Colosseum",
                  latitude: 41.8902,
                  longitude: 12.4922,
                },
              ],
            },
          ],
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.mapPoints).toEqual([
      expect.objectContaining({
        label: "Colosseum",
        latitude: 41.8902,
        longitude: 12.4922,
      }),
    ]);
  });

  it("prefers the structured is_mappable flag over label matching for trip map points", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          daily_plans: [
            {
              day_number: 2,
              activities: [
                {
                  name: "Sunset walk",
                  is_mappable: false,
                  latitude: 38.71,
                  longitude: -9.14,
                },
                {
                  name: "Belem Tower",
                  is_mappable: true,
                  latitude: 38.6916,
                  longitude: -9.216,
                },
              ],
            },
          ],
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.mapPoints).toEqual([
      expect.objectContaining({
        label: "Belem Tower",
        latitude: 38.6916,
        longitude: -9.216,
      }),
    ]);
  });

  it("still omits legacy logistics labels without structured flags for older itinerary data", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          daily_plans: [
            {
              day_number: 2,
              activities: [
                {
                  name: "Baggage storage",
                  latitude: 41.9,
                  longitude: 12.48,
                },
                {
                  name: "Pantheon",
                  latitude: 41.8986,
                  longitude: 12.4769,
                },
              ],
            },
          ],
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.mapPoints).toEqual([
      expect.objectContaining({
        label: "Pantheon",
        latitude: 41.8986,
        longitude: 12.4769,
      }),
    ]);
  });
});
