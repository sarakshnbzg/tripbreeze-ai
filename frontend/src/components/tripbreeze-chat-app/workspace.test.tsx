import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { SelectionState } from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";

import { MultiCitySelectionPanel } from "./multi-city-selection-panel";
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
  it("moves to the next multi-city leg after the current leg is fully selected", () => {
    vi.useFakeTimers();
    let scrolledText = "";
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = vi.fn(function scrollIntoViewMock(this: HTMLElement) {
      scrolledText = this.textContent ?? "";
    });

    function Harness() {
      const [selection, setSelection] = useState<SelectionState>(buildSelection({ byLegFlights: [], byLegHotels: [] }));

      return (
        <MultiCitySelectionPanel
          state={{
            trip_legs: [
              { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3, needs_hotel: true },
              { origin: "Paris", destination: "Barcelona", departure_date: "2026-06-13", nights: 4, needs_hotel: true },
            ],
            flight_options_by_leg: [
              [{ airline: "Outbound Air", outbound_summary: "Berlin to Paris", total_price: 180 }],
              [{ airline: "Next Air", outbound_summary: "Paris to Barcelona", total_price: 170 }],
            ],
            hotel_options_by_leg: [
              [{ name: "Paris Stay", total_price: 420 }],
              [{ name: "Barcelona Stay", total_price: 510 }],
            ],
            flight_options: [],
            hotel_options: [],
          } as unknown as TravelState}
          currencyCode="EUR"
          selection={selection}
          setSelection={setSelection}
        />
      );
    }

    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /outbound air/i }));
    fireEvent.click(screen.getByRole("button", { name: /paris stay/i }));
    vi.runAllTimers();

    expect(scrolledText).toContain("Leg 2: Paris to Barcelona");

    HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    vi.useRealTimers();
  });

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

  it("shows source trust for each destination in a multi-city review briefing", () => {
    renderReviewPanel({
      state: {
        destination_info: `### Paris
#### 🛂 Entry Requirements
### France (Schengen Area)

- **Documents needed:** Passport required.

#### Source Trust
- Source: France-Visas
- Authority: official_government
- Official link: https://france-visas.gouv.fr/
- Last verified: 2026-04-28 (fresh)

---

### Barcelona
#### 🛂 Entry Requirements
### Spain (Schengen Area)

- **Documents needed:** Passport required.

#### Source Trust
- Source: Spain MFA
- Authority: official_government
- Official link: https://www.exteriores.gob.es/
- Last verified: 2026-04-28 (fresh)`,
        flight_options: [],
        hotel_options: [],
        budget: {},
      } as unknown as TravelState,
    });

    expect(screen.getAllByText("Paris").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Barcelona").length).toBeGreaterThan(0);
    expect(screen.getByText("France-Visas")).toBeInTheDocument();
    expect(screen.getByText("Spain MFA")).toBeInTheDocument();
    expect(screen.getAllByText("Source trust")).toHaveLength(2);
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

  it("does not show defaulted profile filters as active request filters in review", () => {
    renderReviewPanel({
      state: {
        trip_request: {
          stops: 0,
          stops_user_specified: false,
          hotel_stars: [4],
          hotel_stars_user_specified: false,
        },
        flight_options: [],
        hotel_options: [],
        budget: {},
      } as unknown as TravelState,
    });

    expect(screen.queryByText(/Active flight filters:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Hotel preferences:/)).not.toBeInTheDocument();
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
          visaBriefings: [],
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
          budgetBreakdown: null,
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
          visaBriefings: [],
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
          budgetBreakdown: null,
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
          visaBriefings: [],
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
          budgetBreakdown: null,
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
          visaBriefings: [],
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
          budgetBreakdown: null,
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
                  address: "Alfama, Lisbon, Portugal",
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

  it("refreshes the budget note when selected options change the displayed total", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        trip_request: {
          budget_limit: 3000,
          num_travelers: 1,
        },
        budget: {
          currency: "EUR",
          flight_cost: 800,
          hotel_cost: 300,
          estimated_daily_expenses: 1330,
          total_estimated: 1904,
          within_budget: true,
          budget_notes: "You're within budget with ~EUR 1096 to spare.",
        },
        selected_flight: {
          total_price: 8887,
        },
        selected_hotel: {
          total_price: 574,
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.budgetBreakdown).toEqual(
      expect.objectContaining({
        total: 10791,
        withinBudget: false,
        budgetNote: "Estimated total (€10,791) exceeds your budget (€3,000) by €7,791.",
      }),
    );
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
    expect(viewModel.visaBriefings).toEqual([]);
  });

  it("builds multi-city visa briefings from the full destination info instead of a single collapsed itinerary field", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        trip_legs: [
          { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3, needs_hotel: true },
          { origin: "Paris", destination: "Barcelona", departure_date: "2026-06-13", nights: 4, needs_hotel: true },
        ],
        destination_info: `### Paris
#### 🛂 Entry Requirements
### France (Schengen Area)

- **Documents needed:** Passport and proof of onward travel.

#### Source Trust
- Source: France-Visas
- Authority: official_government
- Official link: https://france-visas.gouv.fr/
- Last verified: 2026-04-28 (fresh)

---

### Barcelona
#### 🛂 Entry Requirements
### Spain (Schengen Area)

- **Documents needed:** Same as France (Schengen rules apply).

#### Source Trust
- Source: Spain MFA
- Authority: official_government
- Official link: https://www.exteriores.gob.es/
- Last verified: 2026-04-28 (fresh)`,
        itinerary_data: {
          visa_entry_info: "### Barcelona\nOnly the first destination made it through here.",
        },
      } as unknown as TravelState,
      itinerary: "Trip ready",
      currencyCode: "EUR",
    });

    expect(viewModel.primarySections).toEqual([]);
    expect(viewModel.visaTrust).toEqual(null);
    expect(viewModel.visaBriefings).toEqual([
      expect.objectContaining({
        destination: "Paris",
        content: expect.stringContaining("France (Schengen Area)"),
        trust: expect.objectContaining({ sourceName: "France-Visas" }),
      }),
      expect.objectContaining({
        destination: "Barcelona",
        content: expect.stringContaining("Spain (Schengen Area)"),
        trust: expect.objectContaining({ sourceName: "Spain MFA" }),
      }),
    ]);
  });

  it("renders one visa briefing card per multi-city destination in the final itinerary", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "Trip ready",
          hasStructuredItinerary: true,
          fallbackNotice: null,
          snapshotItems: [{ label: "Route", value: "Berlin -> Paris -> Barcelona" }],
          bookingLinks: [],
          primarySections: [],
          secondarySections: [],
          visaTrust: null,
          visaBriefings: [
            {
              destination: "Paris",
              content: "Passport required for France.",
              trust: {
                sourceName: "France-Visas",
                authority: "official_government",
                officialLink: "https://france-visas.gouv.fr/",
                lastVerified: "2026-04-28 (fresh)",
                isStale: false,
              },
            },
            {
              destination: "Barcelona",
              content: "Passport required for Spain.",
              trust: {
                sourceName: "Spain MFA",
                authority: "official_government",
                officialLink: "https://www.exteriores.gob.es/",
                lastVerified: "2026-04-28 (fresh)",
                isStale: false,
              },
            },
          ],
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
          budgetBreakdown: null,
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

    expect(screen.getByText("Visa and entry")).toBeInTheDocument();
    expect(screen.getByText("Paris")).toBeInTheDocument();
    expect(screen.getByText("Barcelona")).toBeInTheDocument();
    expect(screen.getByText("France-Visas")).toBeInTheDocument();
    expect(screen.getByText("Spain MFA")).toBeInTheDocument();
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
                  address: "Piazza di Trevi, 00187 Roma RM, Italy",
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
                  address: "Piazza del Colosseo, 1, 00184 Roma RM, Italy",
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
                  address: "Piazza della Rotonda, 00186 Roma RM, Italy",
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

  it("omits flexible nearby activity placeholder variants without relying on structured flags", () => {
    const viewModel = buildItineraryViewModel({
      state: {
        itinerary_data: {
          daily_plans: [
            {
              day_number: 5,
              activities: [
                {
                  name: "Flexible Nearby Activity",
                  latitude: -33.9249,
                  longitude: 18.4241,
                },
                {
                  name: "Senso-ji Temple",
                  address: "2-3-1 Asakusa, Taito City, Tokyo 111-0032, Japan",
                  latitude: 35.7148,
                  longitude: 139.7967,
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
        label: "Senso-ji Temple",
        latitude: 35.7148,
        longitude: 139.7967,
      }),
    ]);
  });
});
