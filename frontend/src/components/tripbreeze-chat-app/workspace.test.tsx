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

  it("renders final itinerary snapshot, booking links, and day plan details", () => {
    render(
      <FinalItineraryPanel
        viewModel={{
          finalItinerary: "Trip ready",
          hasStructuredItinerary: true,
          snapshotItems: [
            { label: "Route", value: "Berlin -> Lisbon" },
            { label: "Dates", value: "2026-06-10 to 2026-06-15" },
          ],
          bookingLinks: [
            { label: "Flight booking", url: "https://example.com/flight" },
          ],
          primarySections: [
            { key: "flight", title: "Flight details", content: "Nonstop outbound" },
          ],
          secondarySections: [
            { key: "packing", title: "Packing tips", content: "Bring layers." },
          ],
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
          setEmailAddress: vi.fn(),
          onDownloadPdf: vi.fn(async () => undefined),
          onEmailItinerary: vi.fn(async () => undefined),
        }}
      />,
    );

    expect(screen.getByText("Trip snapshot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Flight booking" })).toHaveAttribute("href", "https://example.com/flight");
    expect(screen.getByText("Flight details")).toBeInTheDocument();
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
          snapshotItems: [],
          bookingLinks: [],
          primarySections: [],
          secondarySections: [],
          mapPoints: [],
          itineraryLegs: [],
          itineraryDays: [],
        }}
        shareState={{
          loading: "approving",
          emailAddress: "",
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
  });
});
