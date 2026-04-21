import { useEffect } from "react";

import { fetchReturnFlights } from "@/lib/api";
import type { SelectionState } from "@/lib/planner";
import type { TravelState, TripOption, UserProfile } from "@/lib/types";

import { normaliseTimeWindow } from "../helpers";

type LoadingState = "auth" | "planning" | "clarifying" | "approving" | "saving" | "voice" | "pdf" | "email" | null;

export function useReviewEffects({
  hasReviewWorkspace,
  itinerary,
  setShowPlanningProgress,
  setShowEntryRequirements,
  state,
  hasOptionResults,
  selection,
  isRoundTrip,
  selectedReturnIndex,
  showPersonalisationPanel,
  outboundSectionRef,
  returnSectionRef,
  hotelSectionRef,
  personaliseSectionRef,
  profile,
  currencyCode,
  setReturnOptions,
  setSelectedReturnIndex,
}: {
  hasReviewWorkspace: boolean;
  itinerary: string;
  setShowPlanningProgress: React.Dispatch<React.SetStateAction<boolean>>;
  setShowEntryRequirements: React.Dispatch<React.SetStateAction<boolean>>;
  state: TravelState | null;
  hasOptionResults: boolean;
  selection: SelectionState;
  isRoundTrip: boolean;
  selectedReturnIndex: number | null;
  showPersonalisationPanel: boolean;
  outboundSectionRef: React.RefObject<HTMLDivElement | null>;
  returnSectionRef: React.RefObject<HTMLDivElement | null>;
  hotelSectionRef: React.RefObject<HTMLDivElement | null>;
  personaliseSectionRef: React.RefObject<HTMLDivElement | null>;
  profile: UserProfile | null;
  currencyCode: string;
  setReturnOptions: React.Dispatch<React.SetStateAction<TripOption[]>>;
  setSelectedReturnIndex: React.Dispatch<React.SetStateAction<number | null>>;
}) {
  useEffect(() => {
    if (hasReviewWorkspace || itinerary) {
      setShowPlanningProgress(false);
      setShowEntryRequirements(false);
    }
  }, [hasReviewWorkspace, itinerary, setShowEntryRequirements, setShowPlanningProgress]);

  useEffect(() => {
    if (state?.trip_legs?.length || !hasOptionResults || selection.flightIndex < 0) {
      return;
    }

    const target = isRoundTrip ? returnSectionRef.current : hotelSectionRef.current;
    if (!target) {
      return;
    }

    window.setTimeout(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [hasOptionResults, hotelSectionRef, isRoundTrip, returnSectionRef, selection.flightIndex, state?.trip_legs]);

  useEffect(() => {
    if (state?.trip_legs?.length || !hasOptionResults || !isRoundTrip || selectedReturnIndex === null) {
      return;
    }
    if (!hotelSectionRef.current) {
      return;
    }

    window.setTimeout(() => {
      hotelSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [hasOptionResults, hotelSectionRef, isRoundTrip, selectedReturnIndex, state?.trip_legs]);

  useEffect(() => {
    if (state?.trip_legs?.length || !showPersonalisationPanel || selection.hotelIndex < 0) {
      return;
    }
    if (!personaliseSectionRef.current) {
      return;
    }

    window.setTimeout(() => {
      personaliseSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [personaliseSectionRef, selection.hotelIndex, showPersonalisationPanel, state?.trip_legs]);

  useEffect(() => {
    async function loadReturnOptions() {
      if (!state?.thread_id || !isRoundTrip || !state.flight_options?.length || selection.flightIndex < 0) {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
        return;
      }

      const selectedOutbound = state.flight_options[selection.flightIndex];
      const departureToken = String(selectedOutbound?.departure_token ?? "");
      if (!departureToken) {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
        return;
      }

      try {
        const returnTimeWindow = normaliseTimeWindow(profile?.preferred_return_time_window);
        const options = await fetchReturnFlights(state.thread_id, {
          origin: String(state.trip_request?.origin ?? ""),
          destination: String(state.trip_request?.destination ?? ""),
          departure_date: String(state.trip_request?.departure_date ?? ""),
          return_date: String(state.trip_request?.return_date ?? ""),
          departure_token: departureToken,
          adults: Number(state.trip_request?.num_travelers ?? 1),
          travel_class: String(state.trip_request?.travel_class ?? "ECONOMY"),
          currency: currencyCode,
          return_time_window: returnTimeWindow ? [...returnTimeWindow] : null,
        });
        setReturnOptions(options as TripOption[]);
        setSelectedReturnIndex(null);
      } catch {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
      }
    }

    void loadReturnOptions();
  }, [
    currencyCode,
    isRoundTrip,
    profile?.preferred_return_time_window,
    selection.flightIndex,
    setReturnOptions,
    setSelectedReturnIndex,
    state?.flight_options,
    state?.thread_id,
    state?.trip_request,
  ]);
}
