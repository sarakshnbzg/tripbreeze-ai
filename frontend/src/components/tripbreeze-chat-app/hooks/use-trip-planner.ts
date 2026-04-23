import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { PlannerForm, SelectionState } from "@/lib/planner";
import type { TravelState, UserProfile } from "@/lib/types";
import type { PlannerLoadingState } from "../ui-types";
import type { ChatMessage } from "../helpers";

import { useTripPlannerActions } from "./use-trip-planner-actions";
import { useTripPlannerState } from "./use-trip-planner-state";

type UseTripPlannerParams = {
  authenticatedUser: string;
  profile: UserProfile | null;
  form: PlannerForm;
  state: TravelState | null;
  itinerary: string;
  clarificationAnswer: string;
  feedback: string;
  interests: string[];
  pace: "relaxed" | "moderate" | "packed";
  emailAddress: string;
  selection: SelectionState;
  isRoundTrip: boolean;
  returnOptions: Array<Record<string, unknown>>;
  selectedReturnIndex: number | null;
  tokenUsageHistoryLimit?: number;
  persistAuth: (userId: string, profile: UserProfile) => void;
  clearAuthSession: () => void;
  mediaRecorderRef: MutableRefObject<MediaRecorder | null>;
  recordedChunksRef: MutableRefObject<Blob[]>;
  setForm: Dispatch<SetStateAction<PlannerForm>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setPlanningUpdates: Dispatch<SetStateAction<string[]>>;
  setState: Dispatch<SetStateAction<TravelState | null>>;
  setClarificationQuestion: Dispatch<SetStateAction<string>>;
  setClarificationAnswer: Dispatch<SetStateAction<string>>;
  setFeedback: Dispatch<SetStateAction<string>>;
  setItinerary: Dispatch<SetStateAction<string>>;
  setSelection: Dispatch<SetStateAction<SelectionState>>;
  setInterests: Dispatch<SetStateAction<string[]>>;
  setPace: Dispatch<SetStateAction<"relaxed" | "moderate" | "packed">>;
  setTokenUsageHistory: Dispatch<
    SetStateAction<Array<{ label: string; input_tokens: number; output_tokens: number; cost: number }>>
  >;
  setShowComposer: Dispatch<SetStateAction<boolean>>;
  setShowEntryRequirements: Dispatch<SetStateAction<boolean>>;
  setShowPlanningProgress: Dispatch<SetStateAction<boolean>>;
  setLoading: Dispatch<SetStateAction<PlannerLoadingState>>;
  setError: Dispatch<SetStateAction<string>>;
};

export function useTripPlanner({
  authenticatedUser,
  profile,
  form,
  state,
  itinerary,
  clarificationAnswer,
  feedback,
  interests,
  pace,
  emailAddress,
  selection,
  isRoundTrip,
  returnOptions,
  selectedReturnIndex,
  tokenUsageHistoryLimit = 5,
  persistAuth,
  clearAuthSession,
  mediaRecorderRef,
  recordedChunksRef,
  setForm,
  setMessages,
  setPlanningUpdates,
  setState,
  setClarificationQuestion,
  setClarificationAnswer,
  setFeedback,
  setItinerary,
  setSelection,
  setInterests,
  setPace,
  setTokenUsageHistory,
  setShowComposer,
  setShowEntryRequirements,
  setShowPlanningProgress,
  setLoading,
  setError,
}: UseTripPlannerParams) {
  const { archiveCurrentTokenUsage, logout, resetTrip, handleStreamEvent } = useTripPlannerState({
    authenticatedUser,
    profile,
    form,
    state,
    tokenUsageHistoryLimit,
    persistAuth,
    clearAuthSession,
    setForm,
    setMessages,
    setPlanningUpdates,
    setState,
    setClarificationQuestion,
    setClarificationAnswer,
    setFeedback,
    setItinerary,
    setSelection,
    setInterests,
    setPace,
    setTokenUsageHistory,
    setShowComposer,
    setShowEntryRequirements,
    setShowPlanningProgress,
    setError,
  });

  const {
    handlePlanTrip,
    handleClarification,
    handleReview,
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  } = useTripPlannerActions({
    authenticatedUser,
    form,
    state,
    itinerary,
    clarificationAnswer,
    feedback,
    interests,
    pace,
    emailAddress,
    selection,
    isRoundTrip,
    returnOptions,
    selectedReturnIndex,
    mediaRecorderRef,
    recordedChunksRef,
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
  });

  return {
    archiveCurrentTokenUsage,
    logout,
    resetTrip,
    handleStreamEvent,
    handlePlanTrip,
    handleClarification,
    handleReview,
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  };
}
