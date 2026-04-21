"use client";

import { useMemo, useRef, useState } from "react";
import {
  LoaderCircle,
  Settings2,
} from "lucide-react";

import {
  login,
  register,
  saveProfile,
} from "@/lib/api";
import {
  defaultForm,
  selectedOption,
  type PlannerForm,
} from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { SelectionState } from "@/lib/planner";
import { AuthScreen } from "@/components/tripbreeze-chat-app/auth-screen";
import { PlannerComposer } from "@/components/tripbreeze-chat-app/planner-composer";
import { AppSidebar } from "@/components/tripbreeze-chat-app/sidebar";
import { FinalItineraryPanel, ReviewPanel } from "@/components/tripbreeze-chat-app/workspace";
import { useAuthSession } from "@/components/tripbreeze-chat-app/hooks/use-auth-session";
import { useReferenceData } from "@/components/tripbreeze-chat-app/hooks/use-reference-data";
import { useReviewEffects } from "@/components/tripbreeze-chat-app/hooks/use-review-effects";
import { useTripPlanner, type PlannerLoadingState } from "@/components/tripbreeze-chat-app/hooks/use-trip-planner";
import {
  ChatMessage,
  createDefaultSelection,
  expandStarThresholds,
  isMultiCitySelectionComplete,
  latestAssistantMessage,
  renderMarkdownContent,
  safeErrorMessage,
  summariseTokenUsage,
} from "@/components/tripbreeze-chat-app/helpers";
import {
  GOOGLE_MODELS,
  OPENAI_MODELS,
  PACE_OPTIONS,
} from "@/components/tripbreeze-chat-app/constants";
import { buildItineraryViewModel } from "@/components/tripbreeze-chat-app/view-models";

export function TripBreezeChatApp() {
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [loginForm, setLoginForm] = useState({ userId: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    userId: "",
    password: "",
    confirmPassword: "",
    homeCity: "",
    passportCountry: "",
    travelClass: "ECONOMY",
    preferredAirlines: [] as string[],
    preferredHotelStars: [] as number[],
    outboundWindowStart: 0,
    outboundWindowEnd: 23,
    returnWindowStart: 0,
    returnWindowEnd: 23,
  });
  const [form, setForm] = useState<PlannerForm>(defaultForm);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [planningUpdates, setPlanningUpdates] = useState<string[]>([]);
  const [state, setState] = useState<TravelState | null>(null);
  const [clarificationQuestion, setClarificationQuestion] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [feedback, setFeedback] = useState("");
  const [itinerary, setItinerary] = useState("");
  const [selection, setSelection] = useState<SelectionState>(() => createDefaultSelection());
  const [selectedTransportIndex, setSelectedTransportIndex] = useState<number | null>(null);
  const [returnOptions, setReturnOptions] = useState<TripOption[]>([]);
  const [selectedReturnIndex, setSelectedReturnIndex] = useState<number | null>(null);
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

  const currencyCode = String(state?.trip_request?.currency ?? form.currency ?? "EUR");
  const availableModels = form.provider === "google" ? GOOGLE_MODELS : OPENAI_MODELS;
  const selectedTransport =
    selectedTransportIndex !== null ? state?.transport_options?.[selectedTransportIndex] ?? {} : {};
  const isRoundTrip = Boolean(state?.trip_request?.return_date);
  const currentTokenSummary = useMemo(() => summariseTokenUsage(state?.token_usage), [state?.token_usage]);

  const hasOptionResults = useMemo(
    () =>
      Boolean(
        state &&
        (
          state.flight_options?.length ||
          state.hotel_options?.length ||
          state.flight_options_by_leg?.length ||
          state.hotel_options_by_leg?.length
        ),
      ),
    [state],
  );
  const hasReviewWorkspace = useMemo(
    () =>
      Boolean(
        state &&
        (
          hasOptionResults ||
          state.transport_options?.length ||
          state.destination_info ||
          state.budget ||
          state.rag_sources?.length ||
          latestAssistantMessage(state)
        ),
      ),
    [hasOptionResults, state],
  );
  const canApprove = useMemo(() => {
    if (!state) {
      return false;
    }
    if (state.trip_legs?.length) {
      return isMultiCitySelectionComplete(state, selection);
    }
    const hasSelectedFlight =
      Boolean(state.flight_options?.length) &&
      selection.flightIndex >= 0 &&
      selection.flightIndex < (state.flight_options?.length ?? 0);
    const hasSelectedHotel =
      Boolean(state.hotel_options?.length) &&
      selection.hotelIndex >= 0 &&
      selection.hotelIndex < (state.hotel_options?.length ?? 0);
    const hasReturn =
      !isRoundTrip ||
      selectedReturnIndex !== null ||
      Boolean(
        selection.flightIndex >= 0 ? state.flight_options?.[selection.flightIndex]?.return_details_available : false,
      );
    return hasSelectedFlight && hasSelectedHotel && hasReturn;
  }, [isRoundTrip, selectedReturnIndex, selection, state]);
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
  const showPersonalisationPanel = state?.trip_legs?.length ? canApprove : hasSelectedSingleFlight && hasSelectedSingleHotel && hasSelectedSingleReturn;
  const selectedOutboundOption = hasSelectedSingleFlight ? selectedOption(state?.flight_options, selection.flightIndex) : {};
  const selectedReturnOption = selectedReturnIndex !== null ? returnOptions[selectedReturnIndex] ?? {} : {};
  const selectedHotelOption = hasSelectedSingleHotel ? selectedOption(state?.hotel_options, selection.hotelIndex) : {};
  const completedMultiCityLegs = (state?.trip_legs ?? []).filter((leg, index) => {
    const hasFlight = typeof selection.byLegFlights[index] === "number" && selection.byLegFlights[index] >= 0;
    const needsHotel = Boolean(leg.needs_hotel);
    const hasHotel = !needsHotel || (typeof selection.byLegHotels[index] === "number" && selection.byLegHotels[index] >= 0);
    return hasFlight && hasHotel;
  }).length;
  const itineraryView = useMemo(
    () => buildItineraryViewModel({ state, itinerary, currencyCode }),
    [currencyCode, itinerary, state],
  );
  const {
    finalItinerary,
    snapshotItems: itinerarySnapshotItems,
    bookingLinks: itineraryBookingLinks,
    primarySections: primaryItinerarySections,
    secondarySections: secondaryItinerarySections,
    itineraryLegs,
    itineraryDays,
  } = itineraryView;
  const recentPlanningUpdates = useMemo(() => {
    const filtered = planningUpdates
      .map((update) => String(update).trim())
      .filter(Boolean)
      .filter((update, index, items) => items.indexOf(update) === index);
    return filtered.slice(-4);
  }, [planningUpdates]);

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
  });

  async function handleLogin() {
    setError("");
    setLoading("auth");
    try {
      const result = await login(loginForm.userId.trim(), loginForm.password);
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleRegister() {
    setError("");
    if (registerForm.password !== registerForm.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading("auth");
    try {
      const result = await register(registerForm.userId.trim(), registerForm.password, {
        home_city: registerForm.homeCity,
        passport_country: registerForm.passportCountry,
        travel_class: registerForm.travelClass,
        preferred_airlines: registerForm.preferredAirlines,
        preferred_hotel_stars: expandStarThresholds(registerForm.preferredHotelStars),
        preferred_outbound_time_window: [
          registerForm.outboundWindowStart,
          registerForm.outboundWindowEnd,
        ],
        preferred_return_time_window: [
          registerForm.returnWindowStart,
          registerForm.returnWindowEnd,
        ],
      });
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleSaveProfile() {
    if (!authenticatedUser || !profile) {
      return;
    }
    setError("");
    setLoading("saving");
    try {
      const result = await saveProfile(authenticatedUser, profile);
      persistAuth(result.user_id, result.profile);
    } catch (saveError) {
      setError(safeErrorMessage(saveError));
    } finally {
      setLoading(null);
    }
  }
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
  });

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
    <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6">
      <AppSidebar
        authenticatedUser={authenticatedUser}
        profile={profile}
        setProfile={setProfile}
        airlines={airlines}
        loading={loading}
        onLogout={logout}
        onSaveProfile={handleSaveProfile}
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

      <main className="min-w-0 flex-1">
        <Card className="p-6 sm:p-8">
          <div className="flex flex-col gap-4 border-b border-ink/10 pb-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="font-display text-4xl text-ink">TripBreeze AI</h1>
            </div>
            <div className="flex gap-3">
              <Button variant="secondary" onClick={() => setShowModelSettings((current) => !current)}>
                <Settings2 className="mr-2 h-4 w-4" />
                Settings
              </Button>
              {!showComposer ? (
                <Button variant="secondary" onClick={() => setShowComposer(true)}>
                  Change trip details
                </Button>
              ) : null}
              <Button variant="secondary" onClick={resetTrip}>
                New Trip
              </Button>
              <button type="button" onClick={logout} className="rounded-full border border-ink/10 px-4 py-3 text-sm font-semibold text-ink transition hover:bg-white lg:hidden">
                Log Out
              </button>
            </div>
          </div>

          <div className="mt-6 space-y-5">
            {!showComposer && !itinerary ? (
              <div className="rounded-[1.4rem] border border-ink/10 bg-mist/55 px-4 py-3 text-sm text-slate">
                <span className="font-semibold text-ink">Change trip details</span> reopens the form so you can adjust dates, cities, or filters.
                {" "}
                <span className="font-semibold text-ink">Ask planner to rework results</span> reruns planning from the current review with your notes.
              </div>
            ) : null}

            {showModelSettings ? (
              <div className="rounded-[1.6rem] border border-ink/10 bg-mist/55 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                  <Settings2 className="h-4 w-4" />
                  Settings
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Provider</span>
                    <select
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={form.provider}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          provider: event.target.value as PlannerForm["provider"],
                          model: event.target.value === "google" ? GOOGLE_MODELS[0] : OPENAI_MODELS[0],
                        }))
                      }
                    >
                      <option value="openai">OpenAI</option>
                      <option value="google">Google</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Model</span>
                    <select
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={form.model}
                      onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                    >
                      {availableModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            ) : null}

            {messages.length > 0 ? (
              hasReviewWorkspace || itinerary ? null : (
                <div className="space-y-3">
                  {messages.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={`max-w-4xl rounded-[1.75rem] px-5 py-4 text-sm leading-7 shadow-sm ${
                        message.role === "user"
                          ? "ml-auto bg-ink text-white shadow-[0_16px_36px_rgba(16,33,43,0.18)]"
                          : "border border-ink/8 bg-white text-ink"
                      }`}
                    >
                      <div
                        className={`mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] ${
                          message.role === "user" ? "text-white/60" : "text-slate"
                        }`}
                      >
                        {message.role === "user" ? "You" : "TripBreeze"}
                      </div>
                      {message.role === "assistant" ? renderMarkdownContent(message.content) : message.content}
                    </div>
                  ))}
                </div>
              )
            ) : null}

            {recentPlanningUpdates.length > 0 && !(hasReviewWorkspace || itinerary) ? (
              <div className="rounded-[1.75rem] border border-ink/10 bg-gradient-to-r from-mist/90 to-white/80 p-5">
                <button
                  type="button"
                  onClick={() => setShowPlanningProgress((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    Planning progress
                  </div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                    {showPlanningProgress ? "Hide" : "Show"}
                  </span>
                </button>
                {showPlanningProgress ? (
                  <div className="mt-3 space-y-2 text-sm text-slate">
                    {recentPlanningUpdates.map((update, index) => (
                      <div key={`${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {(hasReviewWorkspace || itinerary) && recentPlanningUpdates.length > 0 ? (
              <div className="rounded-[1.6rem] border border-ink/10 bg-white/70 p-4 lg:hidden">
                <button
                  type="button"
                  onClick={() => setShowPlanningProgress((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                      <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                      Planning progress
                    </div>
                    <div className="mt-1 text-xs text-slate">Latest workflow milestones from the planner.</div>
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">
                    {showPlanningProgress ? "Hide" : "Show"}
                  </span>
                </button>
                {showPlanningProgress ? (
                  <div className="mt-4 space-y-2">
                    {recentPlanningUpdates.map((update, index) => (
                      <div key={`mobile-${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2 text-sm text-slate">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            <ReviewPanel
              hasReviewWorkspace={hasReviewWorkspace}
              finalItinerary={finalItinerary}
              state={state}
              isRoundTrip={isRoundTrip}
              completedMultiCityLegs={completedMultiCityLegs}
              hasSelectedSingleFlight={hasSelectedSingleFlight}
              hasSelectedSingleHotel={hasSelectedSingleHotel}
              selectedOutboundOption={selectedOutboundOption}
              selectedReturnIndex={selectedReturnIndex}
              setSelectedReturnIndex={setSelectedReturnIndex}
              selectedReturnOption={selectedReturnOption}
              selectedHotelOption={selectedHotelOption}
              hasOptionResults={hasOptionResults}
              currencyCode={currencyCode}
              selection={selection}
              setSelection={setSelection}
              returnOptions={returnOptions}
              showPersonalisationPanel={showPersonalisationPanel}
              selectedTransportIndex={selectedTransportIndex}
              setSelectedTransportIndex={setSelectedTransportIndex}
              canApprove={canApprove}
              interests={interests}
              setInterests={setInterests}
              pace={pace}
              setPace={setPace}
              feedback={feedback}
              setFeedback={setFeedback}
              loading={loading}
              handleReview={handleReview}
              outboundSectionRef={outboundSectionRef}
              returnSectionRef={returnSectionRef}
              hotelSectionRef={hotelSectionRef}
              personaliseSectionRef={personaliseSectionRef}
            />

            <FinalItineraryPanel
              finalItinerary={finalItinerary}
              loading={loading}
              emailAddress={emailAddress}
              setEmailAddress={setEmailAddress}
              onDownloadPdf={handleDownloadPdf}
              onEmailItinerary={handleEmailItinerary}
              itinerarySnapshotItems={itinerarySnapshotItems}
              itineraryBookingLinks={itineraryBookingLinks}
              primaryItinerarySections={primaryItinerarySections}
              secondaryItinerarySections={secondaryItinerarySections}
              itineraryLegs={itineraryLegs}
              itineraryDays={itineraryDays}
            />
          </div>

          {clarificationQuestion ? (
            <div className="mt-6 rounded-[1.75rem] border border-coral/30 bg-coral/10 p-5">
              <div className="text-sm font-semibold text-coral">More information needed</div>
              <div className="mt-2 text-sm text-slate">Answer this to continue planning your current trip.</div>
              <textarea
                className="mt-3 h-24 w-full rounded-3xl border border-white/80 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={clarificationAnswer}
                onChange={(event) => setClarificationAnswer(event.target.value)}
                placeholder="Type your answer here..."
              />
              <div className="mt-4">
                <Button onClick={handleClarification} disabled={loading !== null || !clarificationAnswer.trim()}>
                  {loading === "clarifying" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Continue Planning
                </Button>
              </div>
            </div>
          ) : null}

          <PlannerComposer
            form={form}
            setForm={setForm}
            showComposer={showComposer}
            loading={loading}
            recording={recording}
            error={error}
            onPlanTrip={handlePlanTrip}
            onVoiceInput={() => void handleVoiceInput(recording, setRecording)}
          />
        </Card>
      </main>

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
