"use client";

import { useMemo, useRef, useState } from "react";

import { defaultForm, type PlannerForm, type SelectionState } from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";
import { AuthScreen } from "@/components/tripbreeze-chat-app/auth-screen";
import {
  OPENAI_MODELS,
  PACE_OPTIONS,
} from "@/components/tripbreeze-chat-app/constants";
import { useAuthController } from "@/components/tripbreeze-chat-app/hooks/use-auth-controller";
import { useAuthSession } from "@/components/tripbreeze-chat-app/hooks/use-auth-session";
import { useReferenceData } from "@/components/tripbreeze-chat-app/hooks/use-reference-data";
import { useReviewEffects } from "@/components/tripbreeze-chat-app/hooks/use-review-effects";
import { useReviewWorkspaceModel } from "@/components/tripbreeze-chat-app/hooks/use-review-workspace-model";
import { useTripPlanner } from "@/components/tripbreeze-chat-app/hooks/use-trip-planner";
import {
  createDefaultSelection,
  summariseTokenUsage,
  type ChatMessage,
} from "@/components/tripbreeze-chat-app/helpers";
import { PlannerStage } from "@/components/tripbreeze-chat-app/planner-stage";
import type {
  PlannerStageControls,
  PlannerStageDisplayState,
  PlannerStageModels,
} from "@/components/tripbreeze-chat-app/planner-stage-types";
import { AppSidebar } from "@/components/tripbreeze-chat-app/sidebar";
import type { PlannerLoadingState } from "@/components/tripbreeze-chat-app/ui-types";
import { buildItineraryViewModel } from "@/components/tripbreeze-chat-app/view-models";
import type {
  ReviewWorkspaceActions,
  ReviewWorkspaceRefs,
} from "@/components/tripbreeze-chat-app/workspace";

export function TripBreezeChatApp() {
  const [form, setForm] = useState<PlannerForm>(defaultForm);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [planningUpdates, setPlanningUpdates] = useState<string[]>([]);
  const [state, setState] = useState<TravelState | null>(null);
  const [clarificationQuestion, setClarificationQuestion] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [feedback, setFeedback] = useState("");
  const [itinerary, setItinerary] = useState("");
  const [selection, setSelection] = useState<SelectionState>(() => createDefaultSelection());
  const [returnOptions, setReturnOptions] = useState<TripOption[]>([]);
  const [selectedReturnIndex, setSelectedReturnIndex] = useState<number | null>(null);
  const [returnOptionsLoading, setReturnOptionsLoading] = useState(false);
  const [interests, setInterests] = useState<string[]>([]);
  const [pace, setPace] = useState<(typeof PACE_OPTIONS)[number]>("moderate");
  const [emailAddress, setEmailAddress] = useState("");
  const [tokenUsageHistory, setTokenUsageHistory] = useState<
    Array<{ label: string; input_tokens: number; output_tokens: number; cost: number }>
  >([]);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [showProfilePreferences, setShowProfilePreferences] = useState(false);
  const [showComposer, setShowComposer] = useState(true);
  const [showEntryRequirements, setShowEntryRequirements] = useState(false);
  const [showPlanningProgress, setShowPlanningProgress] = useState(true);
  const [showTokenUsage, setShowTokenUsage] = useState(false);
  const [loading, setLoading] = useState<PlannerLoadingState>(null);
  const [error, setError] = useState("");
  const [shareMessage, setShareMessage] = useState("");
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const outboundSectionRef = useRef<HTMLDivElement | null>(null);
  const returnSectionRef = useRef<HTMLDivElement | null>(null);
  const hotelSectionRef = useRef<HTMLDivElement | null>(null);
  const personaliseSectionRef = useRef<HTMLDivElement | null>(null);

  const { cities, countries, airlines } = useReferenceData();
  const {
    authenticatedUser,
    profile,
    setProfile,
    persistAuth,
    clearAuthSession,
  } = useAuthSession({
    setForm,
    setEmailAddress,
  });
  const {
    authMode,
    setAuthMode,
    loginForm,
    setLoginForm,
    registerForm,
    setRegisterForm,
    handleLogin,
    handleRegister,
    handleSaveProfile,
    profileSaveMessage,
    clearProfileSaveMessage,
  } = useAuthController({
    authenticatedUser,
    profile,
    persistAuth,
    setLoading,
    setError,
  });

  const currencyCode = String(state?.trip_request?.currency ?? form.currency ?? "EUR");
  const availableModels = OPENAI_MODELS;
  const originalUserMessage = messages.find((message) => message.role === "user") ?? null;
  const currentTokenSummary = useMemo(() => summariseTokenUsage(state?.token_usage), [state?.token_usage]);
  const itineraryView = useMemo(
    () => buildItineraryViewModel({ state, itinerary, currencyCode }),
    [currencyCode, itinerary, state],
  );
  const {
    isRoundTrip,
    hasOptionResults,
    hasReviewWorkspace,
    showPersonalisationPanel,
    clarificationTranscript,
    recentPlanningUpdates,
    reviewWorkspaceModel,
  } = useReviewWorkspaceModel({
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
  });
  const reviewWorkspaceRefs: ReviewWorkspaceRefs = {
    outboundSectionRef,
    returnSectionRef,
    hotelSectionRef,
    personaliseSectionRef,
  };

  useReviewEffects({
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
    setReturnOptionsLoading,
  });

  const {
    logout,
    resetTrip,
    handlePlanTrip,
    handleClarification,
    handleReview,
    handleVoiceInput,
    handleDownloadPdf,
    handleEmailItinerary,
  } = useTripPlanner({
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
    setShareMessage,
  });
  const reviewWorkspaceActions: ReviewWorkspaceActions = {
    setSelectedReturnIndex,
    setSelection,
    setInterests,
    setPace,
    setFeedback,
    handleReview,
  };
  const plannerStageControls: PlannerStageControls = {
    resetTrip,
    logout,
    handleDownloadPdf,
    handleEmailItinerary,
    handleClarification,
    handlePlanTrip,
    handleVoiceInput: () => handleVoiceInput(recording, setRecording),
  };
  const plannerStageDisplayState: PlannerStageDisplayState = {
    showModelSettings,
    setShowModelSettings,
    showComposer,
    itinerary,
    messages,
    originalUserMessage,
    hasReviewWorkspace,
    clarificationTranscript,
    recentPlanningUpdates,
    showPlanningProgress,
    setShowPlanningProgress,
    loading,
    clarificationQuestion,
    clarificationAnswer,
    setClarificationAnswer,
    recording,
    error,
  };
  const plannerStageModels: PlannerStageModels = {
    availableModels,
    reviewWorkspaceModel,
    reviewWorkspaceActions,
    reviewWorkspaceRefs,
    itineraryView,
    itineraryShareState: {
      loading,
      emailAddress,
      shareMessage,
      setEmailAddress: (value) => {
        setShareMessage("");
        setEmailAddress(value);
      },
      onDownloadPdf: handleDownloadPdf,
      onEmailItinerary: handleEmailItinerary,
    },
  };

  if (!authenticatedUser) {
    return (
      <AuthScreen
        authMode={authMode}
        setAuthMode={setAuthMode}
        loginForm={loginForm}
        setLoginForm={setLoginForm}
        registerForm={registerForm}
        setRegisterForm={setRegisterForm}
        cities={cities}
        countries={countries}
        airlines={airlines}
        loading={loading}
        error={error}
        onLogin={handleLogin}
        onRegister={handleRegister}
      />
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6 xl:px-6">
      <AppSidebar
        authenticatedUser={authenticatedUser}
        profile={profile}
        setProfile={setProfile}
        onProfileEdit={clearProfileSaveMessage}
        airlines={airlines}
        loading={loading}
        onLogout={logout}
        onSaveProfile={handleSaveProfile}
        profileSaveMessage={profileSaveMessage}
        currentTokenSummary={currentTokenSummary}
        tokenUsageHistory={tokenUsageHistory}
        showTokenUsage={showTokenUsage}
        setShowTokenUsage={setShowTokenUsage}
        showProfilePreferences={showProfilePreferences}
        setShowProfilePreferences={setShowProfilePreferences}
        hasReviewWorkspace={hasReviewWorkspace}
        itinerary={itinerary}
        recentPlanningUpdates={recentPlanningUpdates}
        showPlanningProgress={showPlanningProgress}
        setShowPlanningProgress={setShowPlanningProgress}
        setError={setError}
      />

      <div className="planner-shell min-w-0 flex-1">
        <PlannerStage
          form={form}
          setForm={setForm}
          controls={plannerStageControls}
          displayState={plannerStageDisplayState}
          models={plannerStageModels}
        />
      </div>

      <datalist id="cities">
        {cities.slice(0, 200).map((city) => (
          <option key={city} value={city} />
        ))}
      </datalist>
      <datalist id="countries">
        {countries.map((country) => (
          <option key={country} value={country} />
        ))}
      </datalist>
      <datalist id="airlines">
        {airlines.map((airline) => (
          <option key={airline} value={airline} />
        ))}
      </datalist>
    </div>
  );
}
