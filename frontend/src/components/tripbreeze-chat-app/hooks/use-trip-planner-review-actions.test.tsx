import { act, renderHook } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { defaultForm, defaultSelection, type PlannerForm } from "@/lib/planner";

import { useTripPlannerReviewActions } from "./use-trip-planner-review-actions";

vi.mock("@/lib/api", () => ({
  streamApprove: vi.fn(),
  streamClarify: vi.fn(),
  streamSearch: vi.fn(async () => undefined),
}));

function createForm(overrides: Partial<PlannerForm> = {}): PlannerForm {
  return {
    ...defaultForm,
    userId: "sara",
    provider: "openai",
    model: "gpt-4o-mini",
    temperature: 0.3,
    ...overrides,
  };
}

describe("useTripPlannerReviewActions", () => {
  it("does not send stale structured fields for a pure free-text trip brief", async () => {
    const { streamSearch } = await import("@/lib/api");

    const { result } = renderHook(() =>
      useTripPlannerReviewActions({
        authenticatedUser: "sara",
        homeCity: "Berlin",
        form: createForm({
          freeText: "Paris for 3 days, then Barcelona for 4 days, then fly home.",
          departureDate: "2026-05-01",
          returnDate: "2026-05-08",
          destination: "Rome",
          directOnly: true,
          hasEditedStructuredInputs: false,
        }),
        state: null,
        itinerary: "",
        clarificationAnswer: "",
        feedback: "",
        interests: [],
        pace: "moderate",
        emailAddress: "",
        selection: defaultSelection,
        isRoundTrip: false,
        returnOptions: [],
        selectedReturnIndex: null,
        mediaRecorderRef: createRef<MediaRecorder | null>() as React.MutableRefObject<MediaRecorder | null>,
        recordedChunksRef: { current: [] },
        setForm: vi.fn(),
        setMessages: vi.fn(),
        setPlanningUpdates: vi.fn(),
        setState: vi.fn(),
        setClarificationQuestion: vi.fn(),
        setClarificationAnswer: vi.fn(),
        setFeedback: vi.fn(),
        setItinerary: vi.fn(),
        setSelection: vi.fn(),
        setShowComposer: vi.fn(),
        setShowEntryRequirements: vi.fn(),
        setShowPlanningProgress: vi.fn(),
        setLoading: vi.fn(),
        setError: vi.fn(),
        setShareMessage: vi.fn(),
        handleStreamEvent: vi.fn(),
        archiveCurrentTokenUsage: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handlePlanTrip();
    });

    expect(streamSearch).toHaveBeenCalledWith(
      expect.objectContaining({
        free_text_query: "Paris for 3 days, then Barcelona for 4 days, then fly home.",
        structured_fields: {},
      }),
      expect.any(Function),
    );
  });

  it("sends empty flight selection but keeps available hotel selection when revising partial single-city results", async () => {
    const { streamApprove } = await import("@/lib/api");

    const { result } = renderHook(() =>
      useTripPlannerReviewActions({
        authenticatedUser: "sara",
        homeCity: "Berlin",
        form: createForm(),
        state: {
          thread_id: "thread-123",
          trip_request: {
            destination: "Porto",
            pace: "relaxed",
          },
          flight_options: [],
          hotel_options: [{ name: "Harbor Hotel", total_price: 380 }],
          budget: {
            partial_results_note:
              "Hotel options are ready, but flight options are unavailable right now.",
          },
        },
        itinerary: "",
        clarificationAnswer: "",
        feedback: "Try different dates with better flights.",
        interests: ["food", "walking"],
        pace: "moderate",
        emailAddress: "",
        selection: {
          ...defaultSelection,
          hotelIndex: 0,
        },
        isRoundTrip: false,
        returnOptions: [],
        selectedReturnIndex: null,
        mediaRecorderRef: createRef<MediaRecorder | null>() as React.MutableRefObject<MediaRecorder | null>,
        recordedChunksRef: { current: [] },
        setForm: vi.fn(),
        setMessages: vi.fn(),
        setPlanningUpdates: vi.fn(),
        setState: vi.fn(),
        setClarificationQuestion: vi.fn(),
        setClarificationAnswer: vi.fn(),
        setFeedback: vi.fn(),
        setItinerary: vi.fn(),
        setSelection: vi.fn(),
        setShowComposer: vi.fn(),
        setShowEntryRequirements: vi.fn(),
        setShowPlanningProgress: vi.fn(),
        setLoading: vi.fn(),
        setError: vi.fn(),
        setShareMessage: vi.fn(),
        handleStreamEvent: vi.fn(),
        archiveCurrentTokenUsage: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleReview("revise_plan");
    });

    expect(streamApprove).toHaveBeenCalledWith(
      "thread-123",
      expect.objectContaining({
        feedback_type: "revise_plan",
        user_feedback: "Try different dates with better flights.",
        selected_flight: {},
        selected_hotel: { name: "Harbor Hotel", total_price: 380 },
        trip_request: expect.objectContaining({
          destination: "Porto",
          interests: ["food", "walking"],
          pace: "moderate",
        }),
      }),
      expect.any(Function),
    );
  });

  it("preserves per-leg empty selections when revising degraded multi-city results", async () => {
    const { streamApprove } = await import("@/lib/api");

    const { result } = renderHook(() =>
      useTripPlannerReviewActions({
        authenticatedUser: "sara",
        homeCity: "Berlin",
        form: createForm(),
        state: {
          thread_id: "thread-456",
          trip_request: {
            destination: "",
          },
          trip_legs: [
            { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3 },
            { origin: "Paris", destination: "Barcelona", departure_date: "2026-06-13", nights: 4 },
          ],
          flight_options_by_leg: [
            [],
            [{ airline: "Next Air", outbound_summary: "Paris to Barcelona", total_price: 170 }],
          ],
          hotel_options_by_leg: [
            [{ name: "Paris Stay", total_price: 420 }],
            [],
          ],
          budget: {
            partial_results_note: "Some legs have only partial results right now.",
          },
        },
        itinerary: "",
        clarificationAnswer: "",
        feedback: "Keep Paris, but find better options for the second leg.",
        interests: ["art"],
        pace: "packed",
        emailAddress: "",
        selection: {
          ...defaultSelection,
          byLegFlights: [0, 0],
          byLegHotels: [0, 0],
        },
        isRoundTrip: false,
        returnOptions: [],
        selectedReturnIndex: null,
        mediaRecorderRef: createRef<MediaRecorder | null>() as React.MutableRefObject<MediaRecorder | null>,
        recordedChunksRef: { current: [] },
        setForm: vi.fn(),
        setMessages: vi.fn(),
        setPlanningUpdates: vi.fn(),
        setState: vi.fn(),
        setClarificationQuestion: vi.fn(),
        setClarificationAnswer: vi.fn(),
        setFeedback: vi.fn(),
        setItinerary: vi.fn(),
        setSelection: vi.fn(),
        setShowComposer: vi.fn(),
        setShowEntryRequirements: vi.fn(),
        setShowPlanningProgress: vi.fn(),
        setLoading: vi.fn(),
        setError: vi.fn(),
        setShareMessage: vi.fn(),
        handleStreamEvent: vi.fn(),
        archiveCurrentTokenUsage: vi.fn(),
      }),
    );

    await act(async () => {
      await result.current.handleReview("revise_plan");
    });

    expect(streamApprove).toHaveBeenCalledWith(
      "thread-456",
      expect.objectContaining({
        feedback_type: "revise_plan",
        selected_flights: [{}, { airline: "Next Air", outbound_summary: "Paris to Barcelona", total_price: 170 }],
        selected_hotels: [{ name: "Paris Stay", total_price: 420 }, {}],
        selected_flight: {},
        selected_hotel: { name: "Paris Stay", total_price: 420 },
        trip_request: expect.objectContaining({
          interests: ["art"],
          pace: "packed",
        }),
      }),
      expect.any(Function),
    );
  });
});
