import type { SelectionState } from "@/lib/planner";
import type { ApproveRequest, TravelState, TripOption } from "@/lib/types";

import type { PlannerLoadingState } from "./ui-types";

export type ReviewWorkspaceModel = {
  hasReviewWorkspace: boolean;
  finalItinerary: string;
  state: TravelState | null;
  isRoundTrip: boolean;
  completedMultiCityLegs: number;
  hasSelectedSingleFlight: boolean;
  hasSelectedSingleHotel: boolean;
  selectedOutboundOption: Record<string, unknown>;
  selectedReturnIndex: number | null;
  selectedReturnOption: Record<string, unknown>;
  selectedHotelOption: Record<string, unknown>;
  hasOptionResults: boolean;
  currencyCode: string;
  selection: SelectionState;
  returnOptions: TripOption[];
  showPersonalisationPanel: boolean;
  canApprove: boolean;
  returnOptionsLoading: boolean;
  interests: string[];
  pace: "relaxed" | "moderate" | "packed";
  feedback: string;
  loading: PlannerLoadingState;
};

export type ReviewWorkspaceActions = {
  setSelectedReturnIndex: React.Dispatch<React.SetStateAction<number | null>>;
  setSelection: React.Dispatch<React.SetStateAction<SelectionState>>;
  setInterests: React.Dispatch<React.SetStateAction<string[]>>;
  setPace: React.Dispatch<React.SetStateAction<"relaxed" | "moderate" | "packed">>;
  setFeedback: React.Dispatch<React.SetStateAction<string>>;
  handleReview: (feedbackType: ApproveRequest["feedback_type"]) => Promise<void>;
};

export type ReviewWorkspaceRefs = {
  outboundSectionRef: React.RefObject<HTMLDivElement | null>;
  returnSectionRef: React.RefObject<HTMLDivElement | null>;
  hotelSectionRef: React.RefObject<HTMLDivElement | null>;
  personaliseSectionRef: React.RefObject<HTMLDivElement | null>;
};
