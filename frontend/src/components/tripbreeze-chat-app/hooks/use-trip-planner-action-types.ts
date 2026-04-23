import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { PlannerForm, SelectionState } from "@/lib/planner";
import type { StreamEvent, TravelState } from "@/lib/types";

import type { ChatMessage } from "../helpers";
import type { PlannerLoadingState } from "../ui-types";

export type UseTripPlannerActionParams = {
  authenticatedUser: string;
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
  setShowComposer: Dispatch<SetStateAction<boolean>>;
  setShowEntryRequirements: Dispatch<SetStateAction<boolean>>;
  setShowPlanningProgress: Dispatch<SetStateAction<boolean>>;
  setLoading: Dispatch<SetStateAction<PlannerLoadingState>>;
  setError: Dispatch<SetStateAction<string>>;
  handleStreamEvent: (event: StreamEvent) => void;
  archiveCurrentTokenUsage: () => void;
};
