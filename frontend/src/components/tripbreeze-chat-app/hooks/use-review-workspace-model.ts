import { useMemo } from "react";

import { selectedOption, type SelectionState } from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";

import { latestAssistantMessage } from "../helpers";
import type { PlannerLoadingState } from "../ui-types";
import type { ReviewWorkspaceModel } from "../workspace-types";

export function useReviewWorkspaceModel({
  state,
  itinerary,
  currencyCode,
  selection,
  returnOptions,
  selectedReturnIndex,
  returnOptionsLoading,
  interests,
  pace,
  feedback,
  loading,
  messages,
  planningUpdates,
}: {
  state: TravelState | null;
  itinerary: string;
  currencyCode: string;
  selection: SelectionState;
  returnOptions: TripOption[];
  selectedReturnIndex: number | null;
  returnOptionsLoading: boolean;
  interests: string[];
  pace: "relaxed" | "moderate" | "packed";
  feedback: string;
  loading: PlannerLoadingState;
  messages: Array<{ role: "user" | "assistant"; content: string }>;
  planningUpdates: string[];
}) {
  return useMemo(() => {
    const hasOptionResults = Boolean(
      state &&
      (
        state.flight_options?.length ||
        state.hotel_options?.length ||
        state.flight_options_by_leg?.length ||
        state.hotel_options_by_leg?.length
      )
    );
    const partialResultsNote = String(state?.budget?.partial_results_note ?? "").trim();
    const hasReviewWorkspace = Boolean(
      state &&
      state.current_step === "awaiting_review" &&
      (
        hasOptionResults ||
        state.destination_info ||
        state.budget ||
        state.rag_sources?.length ||
        latestAssistantMessage(state)
      )
    );
    const isRoundTrip = Boolean(state?.trip_request?.return_date);
    const hasSelectedSingleFlight =
      !state?.trip_legs?.length &&
      Boolean(state?.flight_options?.length) &&
      selection.flightIndex >= 0 &&
      selection.flightIndex < (state?.flight_options?.length ?? 0);
    const hasSelectedSingleHotel =
      !state?.trip_legs?.length &&
      Boolean(state?.hotel_options?.length) &&
      selection.hotelIndex >= 0 &&
      selection.hotelIndex < (state?.hotel_options?.length ?? 0);
    const hasSelectedSingleReturn =
      !isRoundTrip ||
      selectedReturnIndex !== null ||
      Boolean(hasSelectedSingleFlight ? state?.flight_options?.[selection.flightIndex]?.return_details_available : false);
    const canApprove = state?.trip_legs?.length
      ? (state.trip_legs ?? []).every((leg, index) => {
          const hasFlight = typeof selection.byLegFlights[index] === "number" && selection.byLegFlights[index] >= 0;
          const needsHotel = Boolean(leg.needs_hotel);
          const hasHotel = !needsHotel || (typeof selection.byLegHotels[index] === "number" && selection.byLegHotels[index] >= 0);
          return hasFlight && hasHotel;
        })
      : (
          Boolean(state?.flight_options?.length) &&
          selection.flightIndex >= 0 &&
          selection.flightIndex < (state?.flight_options?.length ?? 0) &&
          Boolean(state?.hotel_options?.length) &&
          selection.hotelIndex >= 0 &&
          selection.hotelIndex < (state?.hotel_options?.length ?? 0) &&
          hasSelectedSingleReturn
        );
    const showPersonalisationPanel = state?.trip_legs?.length
      ? canApprove
      : hasSelectedSingleFlight && hasSelectedSingleHotel && hasSelectedSingleReturn;
    const selectedOutboundOption = hasSelectedSingleFlight ? selectedOption(state?.flight_options, selection.flightIndex) : {};
    const selectedReturnOption = selectedReturnIndex !== null ? returnOptions[selectedReturnIndex] ?? {} : {};
    const selectedHotelOption = hasSelectedSingleHotel ? selectedOption(state?.hotel_options, selection.hotelIndex) : {};
    const completedMultiCityLegs = (state?.trip_legs ?? []).filter((leg, index) => {
      const hasFlight = typeof selection.byLegFlights[index] === "number" && selection.byLegFlights[index] >= 0;
      const needsHotel = Boolean(leg.needs_hotel);
      const hasHotel = !needsHotel || (typeof selection.byLegHotels[index] === "number" && selection.byLegHotels[index] >= 0);
      return hasFlight && hasHotel;
    }).length;
    const latestStateAssistantMessage = latestAssistantMessage(state);
    const clarificationTranscript = messages.slice(1).filter((message) => (
      !(
        (hasReviewWorkspace || itinerary) &&
        message.role === "assistant" &&
        latestStateAssistantMessage &&
        message.content === latestStateAssistantMessage
      )
    ));
    const recentPlanningUpdates = planningUpdates
      .map((update) => String(update).trim())
      .filter(Boolean)
      .filter((update, index, items) => items.indexOf(update) === index)
      .slice(-4);

    const reviewWorkspaceModel: ReviewWorkspaceModel = {
      hasReviewWorkspace,
      finalItinerary: itinerary,
      state,
      isRoundTrip,
      completedMultiCityLegs,
      hasSelectedSingleFlight,
      hasSelectedSingleHotel,
      selectedOutboundOption,
      selectedReturnIndex,
      selectedReturnOption,
      selectedHotelOption,
      hasOptionResults,
      partialResultsNote,
      currencyCode,
      selection,
      returnOptions,
      showPersonalisationPanel,
      canApprove,
      returnOptionsLoading,
      interests,
      pace,
      feedback,
      loading,
    };

    return {
      isRoundTrip,
      hasOptionResults,
      hasReviewWorkspace,
      showPersonalisationPanel,
      clarificationTranscript,
      recentPlanningUpdates,
      reviewWorkspaceModel,
    };
  }, [
    state,
    itinerary,
    currencyCode,
    selection,
    returnOptions,
    selectedReturnIndex,
    returnOptionsLoading,
    interests,
    pace,
    feedback,
    loading,
    messages,
    planningUpdates,
  ]);
}
