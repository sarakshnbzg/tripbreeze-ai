"use client";

import type { Dispatch, RefObject, SetStateAction } from "react";

import type { PlannerForm } from "@/lib/planner";

import type { ChatMessage } from "@/components/tripbreeze-chat-app/helpers";
import type { PlannerLoadingState } from "@/components/tripbreeze-chat-app/ui-types";
import type { ItineraryViewModel } from "@/components/tripbreeze-chat-app/view-models";
import type {
  ItineraryShareState,
  ReviewWorkspaceActions,
  ReviewWorkspaceModel,
  ReviewWorkspaceRefs,
} from "@/components/tripbreeze-chat-app/workspace-types";

export type PlannerStageControls = {
  resetTrip: () => void;
  logout: () => void;
  handleDownloadPdf: () => Promise<void>;
  handleEmailItinerary: () => Promise<void>;
  handleClarification: () => Promise<void>;
  handlePlanTrip: () => Promise<void>;
  handleVoiceInput: () => Promise<void>;
};

export type PlannerStageDisplayState = {
  showModelSettings: boolean;
  setShowModelSettings: Dispatch<SetStateAction<boolean>>;
  showComposer: boolean;
  itinerary: string;
  messages: ChatMessage[];
  originalUserMessage: ChatMessage | null;
  hasReviewWorkspace: boolean;
  clarificationTranscript: ChatMessage[];
  recentPlanningUpdates: string[];
  showPlanningProgress: boolean;
  setShowPlanningProgress: Dispatch<SetStateAction<boolean>>;
  loading: PlannerLoadingState;
  clarificationQuestion: string;
  clarificationAnswer: string;
  setClarificationAnswer: Dispatch<SetStateAction<string>>;
  recording: boolean;
  error: string;
};

export type PlannerStageModels = {
  availableModels: readonly string[];
  reviewWorkspaceModel: ReviewWorkspaceModel;
  reviewWorkspaceActions: ReviewWorkspaceActions;
  reviewWorkspaceRefs: ReviewWorkspaceRefs;
  itineraryView: ItineraryViewModel;
  itineraryShareState: ItineraryShareState;
};

export type PlannerStageProps = {
  form: PlannerForm;
  setForm: Dispatch<SetStateAction<PlannerForm>>;
  controls: PlannerStageControls;
  displayState: PlannerStageDisplayState;
  models: PlannerStageModels;
};

export type PlannerStageRequestSummaryProps = {
  originalUserMessage: ChatMessage | null;
};

export type PlannerStageReviewWorkspaceRefs = {
  outboundSectionRef: RefObject<HTMLDivElement | null>;
  returnSectionRef: RefObject<HTMLDivElement | null>;
  hotelSectionRef: RefObject<HTMLDivElement | null>;
  personaliseSectionRef: RefObject<HTMLDivElement | null>;
};
