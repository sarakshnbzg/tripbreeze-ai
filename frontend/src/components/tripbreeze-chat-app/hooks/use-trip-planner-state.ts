import type { Dispatch, SetStateAction } from "react";

import { defaultForm, type PlannerForm, type SelectionState } from "@/lib/planner";
import type { StreamEvent, TravelState, UserProfile } from "@/lib/types";

import {
  createDefaultSelection,
  latestAssistantMessage,
  summariseTokenUsage,
  type ChatMessage,
} from "../helpers";

type TokenUsageSummary = { label: string; input_tokens: number; output_tokens: number; cost: number };

type UseTripPlannerStateParams = {
  authenticatedUser: string;
  profile: UserProfile | null;
  form: PlannerForm;
  state: TravelState | null;
  tokenUsageHistoryLimit: number;
  persistAuth: (userId: string, profile: UserProfile, csrfToken?: string) => void;
  clearAuthSession: () => void;
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
  setTokenUsageHistory: Dispatch<SetStateAction<TokenUsageSummary[]>>;
  setShowComposer: Dispatch<SetStateAction<boolean>>;
  setShowEntryRequirements: Dispatch<SetStateAction<boolean>>;
  setShowPlanningProgress: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string>>;
};

export function useTripPlannerState({
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
}: UseTripPlannerStateParams) {
  function archiveCurrentTokenUsage() {
    if (!state?.token_usage?.length) {
      return;
    }

    const summary = summariseTokenUsage(state.token_usage);
    const tripRequest = state.trip_request ?? {};
    setTokenUsageHistory((current) => {
      const label =
        String(tripRequest.destination ?? "").trim() ||
        (String(tripRequest.departure_date ?? "").trim()
          ? `Search (${String(tripRequest.departure_date)})`
          : `Search ${current.length + 1}`);
      return [{ label, ...summary }, ...current].slice(0, tokenUsageHistoryLimit);
    });
  }

  function clearPlannerState({ showComposer = true }: { showComposer?: boolean } = {}) {
    const preservedProvider = form.provider;
    const preservedModel = form.model;
    const preservedTemperature = form.temperature;
    setMessages([]);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());
    setInterests([]);
    setPace("moderate");
    setError("");
    setShowComposer(showComposer);
    setShowEntryRequirements(false);
    setShowPlanningProgress(true);
    setForm({
      ...defaultForm,
      userId: authenticatedUser || defaultForm.userId,
      origin: profile?.home_city ?? "",
      provider: preservedProvider,
      model: preservedModel,
      temperature: preservedTemperature,
    });
  }

  function logout() {
    archiveCurrentTokenUsage();
    clearAuthSession();
    clearPlannerState();
  }

  function resetTrip() {
    archiveCurrentTokenUsage();
    clearPlannerState();
  }

  function handleStreamEvent(event: StreamEvent) {
    if (event.event === "node_start") {
      setPlanningUpdates((current) => [...current, String(event.data.label ?? "Working...")]);
      return;
    }
    if (event.event === "node_message") {
      const content = String(event.data.content ?? "");
      if (content) {
        setPlanningUpdates((current) => [...current, content]);
      }
      return;
    }
    if (event.event === "clarification") {
      const question = String(event.data.question ?? "");
      const threadId = String(event.data.thread_id ?? "").trim();
      if (threadId) {
        setState((current) => ({ ...(current ?? {}), thread_id: threadId }));
      }
      setClarificationQuestion(question);
      setMessages((current) => [...current, { role: "assistant", content: question }]);
      return;
    }
    if (event.event === "token") {
      setItinerary((current) => `${current}${String(event.data.content ?? "")}`);
      return;
    }
    if (event.event === "state") {
      const nextState = event.data as TravelState;
      setState(nextState);
      if (authenticatedUser && nextState.user_profile) {
        persistAuth(authenticatedUser, nextState.user_profile);
      }
      const assistant = latestAssistantMessage(nextState);
      if (assistant) {
        setMessages((current) => {
          if (current[current.length - 1]?.role === "assistant" && current[current.length - 1]?.content === assistant) {
            return current;
          }
          return [...current, { role: "assistant", content: assistant }];
        });
      }
      return;
    }
    if (event.event === "error") {
      setError(String(event.data.detail ?? "Unexpected error"));
    }
  }

  return {
    archiveCurrentTokenUsage,
    clearPlannerState,
    logout,
    resetTrip,
    handleStreamEvent,
  };
}
