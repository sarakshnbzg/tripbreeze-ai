import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import {
  downloadItineraryPdf,
  emailItinerary,
  streamApprove,
  streamClarify,
  streamSearch,
  transcribeAudio,
} from "@/lib/api";
import {
  buildStructuredFields,
  defaultForm,
  selectedOption,
  type PlannerForm,
  type SelectionState,
} from "@/lib/planner";
import type { ApproveRequest, StreamEvent, TravelState, TripOption, UserProfile } from "@/lib/types";

import {
  buildItineraryFileName,
  buildUserMessage,
  combineRoundTripFlight,
  createDefaultSelection,
  latestAssistantMessage,
  safeErrorMessage,
  summariseTokenUsage,
} from "../helpers";

export type PlannerLoadingState =
  | "auth"
  | "planning"
  | "clarifying"
  | "approving"
  | "saving"
  | "voice"
  | "pdf"
  | "email"
  | null;

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

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
  selectedTransport: TripOption | Record<string, unknown>;
  isRoundTrip: boolean;
  returnOptions: TripOption[];
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
  setSelectedTransportIndex: Dispatch<SetStateAction<number | null>>;
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
  selectedTransport,
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
  setSelectedTransportIndex,
  setInterests,
  setPace,
  setTokenUsageHistory,
  setShowComposer,
  setShowEntryRequirements,
  setShowPlanningProgress,
  setLoading,
  setError,
}: UseTripPlannerParams) {
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
    setMessages([]);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());
    setSelectedTransportIndex(null);
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
    setSelectedTransportIndex(null);

    const userMessage = buildUserMessage(form);
    setMessages((current) => [...current, { role: "user", content: userMessage }]);
    setForm((current) => ({ ...current, freeText: "" }));

    try {
      await streamSearch(
        {
          user_id: authenticatedUser,
          free_text_query: form.freeText || undefined,
          structured_fields: buildStructuredFields(form),
          llm_provider: form.provider,
          llm_model: form.model,
          llm_temperature: 0.3,
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
    if (feedbackType === "revise_plan") {
      setShowComposer(true);
    }
    setItinerary("");

    const request: ApproveRequest = {
      user_feedback: feedback,
      feedback_type: feedbackType,
      selected_transport: selectedTransport,
      llm_provider: form.provider,
      llm_model: form.model,
      llm_temperature: 0.3,
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
    } catch (approveError) {
      setError(safeErrorMessage(approveError));
    } finally {
      setLoading(null);
    }
  }

  async function handleVoiceInput(recording: boolean, setRecording: Dispatch<SetStateAction<boolean>>) {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordedChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setLoading("voice");
        try {
          const blob = new Blob(recordedChunksRef.current, { type: "audio/webm" });
          const text = await transcribeAudio(blob);
          setForm((current) => ({
            ...current,
            freeText: [current.freeText, text].filter(Boolean).join(" ").trim(),
          }));
        } catch (voiceError) {
          setError(safeErrorMessage(voiceError));
        } finally {
          stream.getTracks().forEach((track) => track.stop());
          setLoading(null);
        }
      };

      recorder.start();
      setRecording(true);
      setError("");
    } catch {
      setError("Unable to start microphone recording.");
    }
  }

  async function handleDownloadPdf() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary) {
      return;
    }
    setError("");
    setLoading("pdf");
    try {
      const fileName = buildItineraryFileName(state);
      const blob = await downloadItineraryPdf(
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
        fileName,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (pdfError) {
      setError(safeErrorMessage(pdfError));
    } finally {
      setLoading(null);
    }
  }

  async function handleEmailItinerary() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary || !emailAddress.trim()) {
      setError("Enter an email address before sending the itinerary.");
      return;
    }
    setError("");
    setLoading("email");
    try {
      const result = await emailItinerary(
        emailAddress.trim(),
        authenticatedUser,
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
      );
      setPlanningUpdates((current) => [...current, result.message]);
    } catch (emailError) {
      setError(safeErrorMessage(emailError));
    } finally {
      setLoading(null);
    }
  }

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
