import {
  streamApprove,
  streamClarify,
  streamSearch,
} from "@/lib/api";
import {
  buildStructuredFields,
  resetPlannerFormAfterSubmit,
  selectedOption,
} from "@/lib/planner";
import type { ApproveRequest } from "@/lib/types";

import {
  buildUserMessage,
  combineRoundTripFlight,
  createDefaultSelection,
  safeErrorMessage,
} from "../helpers";
import type { UseTripPlannerActionParams } from "./use-trip-planner-action-types";

export function useTripPlannerReviewActions({
  authenticatedUser,
  homeCity,
  form,
  state,
  clarificationAnswer,
  feedback,
  interests,
  pace,
  selection,
  isRoundTrip,
  returnOptions,
  selectedReturnIndex,
  setForm,
  setMessages,
  setPlanningUpdates,
  setState,
  setClarificationQuestion,
  setClarificationAnswer,
  setFeedback,
  setItinerary,
  setSelection,
  setShowComposer,
  setShowEntryRequirements,
  setShowPlanningProgress,
  setLoading,
  setError,
  handleStreamEvent,
  archiveCurrentTokenUsage,
}: UseTripPlannerActionParams) {
  async function handlePlanTrip() {
    const validMultiCityLegs = form.multiCityLegs.filter(
      (leg) => leg.destination.trim() && Number(leg.nights) > 0,
    );

    if (!form.freeText.trim()) {
      if (form.multiCity) {
        if (!validMultiCityLegs.length) {
          setError("Add at least one destination for your multi-city trip or describe it in free text.");
          return;
        }
      } else if (!form.destination.trim()) {
        setError("Describe your trip or fill in at least a destination.");
        return;
      }
    }

    if (!form.departureDate && !form.freeText.trim()) {
      setError("Choose a departure date or include it in your trip description.");
      return;
    }

    if (!form.multiCity && !form.oneWay && form.returnDate && form.departureDate && form.returnDate <= form.departureDate) {
      setError("Return date must be after departure date.");
      return;
    }

    if (!form.multiCity && form.oneWay && !form.freeText.trim() && form.numNights <= 0) {
      setError("One-way trips need the number of nights so hotel search and budget can be calculated.");
      return;
    }

    archiveCurrentTokenUsage();
    setError("");
    setLoading("planning");
    setShowComposer(false);
    setShowEntryRequirements(false);
    setShowPlanningProgress(true);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());

    const userMessage = buildUserMessage(form);
    setMessages((current) => [...current, { role: "user", content: userMessage }]);
    setForm((current) => resetPlannerFormAfterSubmit(current, { authenticatedUser, homeCity }));

    try {
      const structuredFields =
        form.freeText.trim() && !form.hasEditedStructuredInputs
          ? {}
          : buildStructuredFields(form);
      await streamSearch(
        {
          user_id: authenticatedUser,
          free_text_query: form.freeText || undefined,
          structured_fields: structuredFields,
          llm_provider: form.provider,
          llm_model: form.model,
          llm_temperature: form.temperature,
        },
        handleStreamEvent,
      );
    } catch (planningError) {
      setError(safeErrorMessage(planningError));
    } finally {
      setLoading(null);
    }
  }

  async function handleClarification() {
    if (!state?.thread_id || !clarificationAnswer.trim()) {
      return;
    }
    setError("");
    setLoading("clarifying");
    const answer = clarificationAnswer.trim();
    setMessages((current) => [...current, { role: "user", content: answer }]);
    setClarificationAnswer("");
    setClarificationQuestion("");

    try {
      await streamClarify(state.thread_id, answer, handleStreamEvent);
    } catch (clarifyError) {
      setError(safeErrorMessage(clarifyError));
    } finally {
      setLoading(null);
    }
  }

  async function handleReview(feedbackType: ApproveRequest["feedback_type"]) {
    if (!state?.thread_id) {
      return;
    }

    setError("");
    setLoading(feedbackType === "revise_plan" ? "planning" : "approving");
    setItinerary("");

    const request: ApproveRequest = {
      user_feedback: feedback,
      feedback_type: feedbackType,
      llm_provider: form.provider,
      llm_model: form.model,
      llm_temperature: form.temperature,
      trip_request: {
        ...(state.trip_request ?? {}),
        interests,
        pace,
      },
    };

    if (state.trip_legs?.length) {
      request.selected_flights =
        state.flight_options_by_leg?.map((legOptions, index) =>
          selectedOption(legOptions, selection.byLegFlights[index] ?? 0),
        ) ?? [];
      request.selected_hotels =
        state.hotel_options_by_leg?.map((legOptions, index) =>
          selectedOption(legOptions, selection.byLegHotels[index] ?? 0),
        ) ?? [];
      request.selected_flight = request.selected_flights[0] ?? {};
      request.selected_hotel = request.selected_hotels[0] ?? {};
    } else {
      const outbound = selectedOption(state.flight_options, selection.flightIndex);
      const returnFlight =
        isRoundTrip && selectedReturnIndex !== null ? (returnOptions[selectedReturnIndex] ?? {}) : {};
      request.selected_flight =
        isRoundTrip && selectedReturnIndex !== null
          ? combineRoundTripFlight(outbound, returnFlight)
          : outbound;
      request.selected_hotel = selectedOption(state.hotel_options, selection.hotelIndex);
    }

    try {
      await streamApprove(state.thread_id, request, handleStreamEvent);
      setFeedback("");
    } catch (approveError) {
      setError(safeErrorMessage(approveError));
    } finally {
      setLoading(null);
    }
  }

  return {
    handlePlanTrip,
    handleClarification,
    handleReview,
  };
}
