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
});
