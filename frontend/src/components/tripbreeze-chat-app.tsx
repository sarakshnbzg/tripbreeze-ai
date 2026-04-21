"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  LoaderCircle,
  LogOut,
  Save,
  Settings2,
  UserRound,
} from "lucide-react";

import {
  downloadItineraryPdf,
  emailItinerary,
  fetchReturnFlights,
  getReferenceValues,
  login,
  register,
  saveProfile,
  streamApprove,
  streamClarify,
  streamSearch,
  transcribeAudio,
} from "@/lib/api";
import {
  buildStructuredFields,
  defaultForm,
  formatCurrency,
  selectedOption,
  type PlannerForm,
} from "@/lib/planner";
import type { ApproveRequest, StreamEvent, TravelState, TripOption, UserProfile } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { SelectionState } from "@/lib/planner";
import { HotelStarTierPicker, TimeWindowPicker } from "@/components/tripbreeze-chat-app/controls";
import { AuthScreen } from "@/components/tripbreeze-chat-app/auth-screen";
import { PlannerComposer } from "@/components/tripbreeze-chat-app/planner-composer";
import { FinalItineraryPanel, ReviewPanel } from "@/components/tripbreeze-chat-app/workspace";
import {
  ChatMessage,
  budgetFlightDetail,
  budgetHotelDetail,
  budgetStatusNote,
  buildItineraryFileName,
  buildTripSummary,
  buildUserMessage,
  combineRoundTripFlight,
  compressStarPreferences,
  createDefaultSelection,
  expandStarThresholds,
  injectBookingLinks,
  isMultiCitySelectionComplete,
  latestAssistantMessage,
  normaliseTimeWindow,
  optionTotalPrice,
  readRecord,
  readRecordArray,
  readString,
  renderMarkdownContent,
  safeErrorMessage,
  selectionLabel,
  sentenceLabel,
  summariseTokenUsage,
  transportLabel,
} from "@/components/tripbreeze-chat-app/helpers";
import {
  CURRENCIES,
  GOOGLE_MODELS,
  INTEREST_OPTIONS,
  OPENAI_MODELS,
  PACE_OPTIONS,
  TRAVEL_CLASSES,
} from "@/components/tripbreeze-chat-app/constants";

export function TripBreezeChatApp() {
  const [authenticatedUser, setAuthenticatedUser] = useState<string>("");
  const [profile, setProfile] = useState<UserProfile | null>(null);
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
  const [cities, setCities] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [airlines, setAirlines] = useState<string[]>([]);
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
  const [loading, setLoading] = useState<"auth" | "planning" | "clarifying" | "approving" | "saving" | "voice" | "pdf" | "email" | null>(null);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const outboundSectionRef = useRef<HTMLDivElement | null>(null);
  const returnSectionRef = useRef<HTMLDivElement | null>(null);
  const hotelSectionRef = useRef<HTMLDivElement | null>(null);
  const personaliseSectionRef = useRef<HTMLDivElement | null>(null);

  const currencyCode = String(state?.trip_request?.currency ?? form.currency ?? "EUR");
  const availableModels = form.provider === "google" ? GOOGLE_MODELS : OPENAI_MODELS;
  const selectedTransport =
    selectedTransportIndex !== null ? state?.transport_options?.[selectedTransportIndex] ?? {} : {};
  const isRoundTrip = Boolean(state?.trip_request?.return_date);
  const currentTokenSummary = useMemo(() => summariseTokenUsage(state?.token_usage), [state?.token_usage]);

  useEffect(() => {
    void Promise.all([
      getReferenceValues("cities"),
      getReferenceValues("countries"),
      getReferenceValues("airlines"),
    ])
      .then(([cityValues, countryValues, airlineValues]) => {
        setCities(cityValues);
        setCountries(countryValues);
        setAirlines(airlineValues);
      })
      .catch(() => {
        // Keep the UI usable even if reference data is unavailable.
      });
  }, []);

  useEffect(() => {
    const savedUser = window.localStorage.getItem("tripbreeze_user");
    const savedProfile = window.localStorage.getItem("tripbreeze_profile");
    if (!savedUser || !savedProfile) {
      return;
    }
    try {
      const parsedProfile = JSON.parse(savedProfile) as UserProfile;
      setAuthenticatedUser(savedUser);
      setProfile(parsedProfile);
      setForm((current) => ({
        ...current,
        userId: savedUser,
        origin: parsedProfile.home_city ?? "",
      }));
      setEmailAddress(savedUser);
    } catch {
      window.localStorage.removeItem("tripbreeze_user");
      window.localStorage.removeItem("tripbreeze_profile");
    }
  }, []);

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
  const tripRequest = readRecord(state?.trip_request);
  const budgetData = readRecord(state?.budget);
  const itineraryData = readRecord(state?.itinerary_data);
  const itineraryFlightDetails = readString(itineraryData.flight_details);
  const itineraryHotelDetails = readString(itineraryData.hotel_details);
  const itineraryHighlights = readString(itineraryData.destination_highlights);
  const itineraryBudget = readString(itineraryData.budget_breakdown);
  const itineraryVisa = readString(itineraryData.visa_entry_info);
  const itineraryPacking = readString(itineraryData.packing_tips);
  const itineraryLegs = readRecordArray(itineraryData.legs);
  const itineraryDays = readRecordArray(itineraryData.daily_plans);
  const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
  const finalSelectedFlight = readRecord(state?.selected_flight);
  const finalSelectedHotel = readRecord(state?.selected_hotel);
  const finalSelectedTransport = readRecord(state?.selected_transport);
  const finalSelectedFlights = readRecordArray(state?.selected_flights);
  const finalSelectedHotels = readRecordArray(state?.selected_hotels);
  const itinerarySnapshotItems = useMemo(() => {
    const travelers = Math.max(1, Number(tripRequest.num_travelers ?? 1));
    const tripLegs = state?.trip_legs ?? [];
    const budgetLimit = Number(tripRequest.budget_limit ?? 0);
    const estimatedTotal = Number(budgetData.total_estimated_cost ?? 0);

    if (tripLegs.length) {
      const routeParts = [
        String(tripLegs[0]?.origin ?? tripRequest.origin ?? "").trim(),
        ...tripLegs
          .filter((leg) => Number(leg.nights ?? 0) > 0)
          .map((leg) => String(leg.destination ?? "").trim())
          .filter(Boolean),
      ].filter(Boolean);
      const firstDeparture = String(tripLegs[0]?.departure_date ?? tripRequest.departure_date ?? "").trim();
      const finalStop = [...tripLegs]
        .reverse()
        .find((leg) => readString(leg.check_out_date) || readString(leg.departure_date));
      const finalDate =
        readString(finalStop?.check_out_date) || readString(tripRequest.return_date) || readString(finalStop?.departure_date);
      const selectedFlightCount = finalSelectedFlights.filter((item) => Object.keys(item).length).length;
      const selectedHotelCount = finalSelectedHotels.filter((item) => Object.keys(item).length).length;

      return [
        { label: "Route", value: routeParts.join(" -> ") || "Multi-city trip" },
        {
          label: "Dates",
          value:
            firstDeparture && finalDate && finalDate !== firstDeparture
              ? `${firstDeparture} to ${finalDate}`
              : firstDeparture || finalDate || "Dates pending",
        },
        { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
        {
          label: estimatedTotal > 0 ? "Trip estimate" : "Budget",
          value: estimatedTotal > 0 ? formatCurrency(estimatedTotal, currencyCode) : budgetLimit > 0 ? formatCurrency(budgetLimit, currencyCode) : "Flexible",
        },
        { label: "Flights", value: selectedFlightCount ? `${selectedFlightCount} leg${selectedFlightCount === 1 ? "" : "s"} selected` : "Managed per leg" },
        { label: "Hotels", value: selectedHotelCount ? `${selectedHotelCount} stay${selectedHotelCount === 1 ? "" : "s"} selected` : "Chosen per stop" },
      ];
    }

    const origin = String(tripRequest.origin ?? "").trim();
    const destination = String(tripRequest.destination ?? "").trim();
    const departureDate = String(tripRequest.departure_date ?? "").trim();
    const returnDate = String(tripRequest.return_date ?? "").trim();
    const selectedFlightLabel = Object.keys(finalSelectedFlight).length ? selectionLabel(finalSelectedFlight, "Selected flight") : "Chosen flight";
    const selectedHotelLabel = Object.keys(finalSelectedHotel).length ? selectionLabel(finalSelectedHotel, "Selected hotel") : "Chosen hotel";
    const transportValue = Object.keys(finalSelectedTransport).length
      ? `${transportLabel(finalSelectedTransport.mode)}${readString(finalSelectedTransport.operator) ? ` · ${readString(finalSelectedTransport.operator)}` : ""}`
      : "";

    return [
      { label: "Route", value: [origin, destination].filter(Boolean).join(" -> ") || "Planned trip" },
      {
        label: "Dates",
        value: departureDate && returnDate ? `${departureDate} to ${returnDate}` : departureDate || returnDate || "Dates pending",
      },
      { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
      {
        label: estimatedTotal > 0 ? "Trip estimate" : "Budget",
        value: estimatedTotal > 0 ? formatCurrency(estimatedTotal, currencyCode) : budgetLimit > 0 ? formatCurrency(budgetLimit, currencyCode) : "Flexible",
      },
      { label: "Flight", value: selectedFlightLabel },
      { label: "Stay", value: transportValue ? `${selectedHotelLabel} · ${transportValue}` : selectedHotelLabel },
    ];
  }, [
    budgetData.total_estimated_cost,
    currencyCode,
    finalSelectedFlight,
    finalSelectedFlights,
    finalSelectedHotel,
    finalSelectedHotels,
    finalSelectedTransport,
    state?.trip_legs,
    tripRequest.budget_limit,
    tripRequest.departure_date,
    tripRequest.destination,
    tripRequest.num_travelers,
    tripRequest.origin,
    tripRequest.return_date,
  ]);
  const itineraryBookingLinks = useMemo(() => {
    const links: Array<{ label: string; url: string }> = [];

    if (state?.trip_legs?.length) {
      finalSelectedFlights.forEach((flight, index) => {
        const url = readString(flight.booking_url);
        if (url) {
          links.push({ label: `Leg ${index + 1} flight`, url });
        }
      });
      finalSelectedHotels.forEach((hotel, index) => {
        const url = readString(hotel.booking_url);
        if (url) {
          links.push({ label: `Leg ${index + 1} hotel`, url });
        }
      });
      return links;
    }

    const flightUrl = readString(finalSelectedFlight.booking_url);
    if (flightUrl) {
      links.push({ label: "Flight booking", url: flightUrl });
    }

    const hotelUrl = readString(finalSelectedHotel.booking_url);
    if (hotelUrl) {
      links.push({ label: "Hotel booking", url: hotelUrl });
    }

    const transportUrl = readString(finalSelectedTransport.booking_url);
    if (transportUrl) {
      links.push({ label: `${transportLabel(finalSelectedTransport.mode)} booking`, url: transportUrl });
    }

    return links;
  }, [finalSelectedFlight, finalSelectedFlights, finalSelectedHotel, finalSelectedHotels, finalSelectedTransport, state?.trip_legs]);
  const primaryItinerarySections = [
    itineraryFlightDetails ? { key: "flight", title: "Flight details", content: itineraryFlightDetails } : null,
    itineraryHotelDetails ? { key: "hotel", title: "Hotel details", content: itineraryHotelDetails } : null,
    itineraryBudget ? { key: "budget", title: "Budget breakdown", content: itineraryBudget } : null,
    itineraryVisa ? { key: "visa", title: "Visa and entry", content: itineraryVisa } : null,
  ].filter((section): section is { key: string; title: string; content: string } => Boolean(section));
  const secondaryItinerarySections = [
    itineraryHighlights ? { key: "highlights", title: "Destination highlights", content: itineraryHighlights } : null,
    itineraryPacking ? { key: "packing", title: "Packing tips", content: itineraryPacking } : null,
  ].filter((section): section is { key: string; title: string; content: string } => Boolean(section));
  const recentPlanningUpdates = useMemo(() => {
    const filtered = planningUpdates
      .map((update) => String(update).trim())
      .filter(Boolean)
      .filter((update, index, items) => items.indexOf(update) === index);
    return filtered.slice(-4);
  }, [planningUpdates]);

  useEffect(() => {
    if (hasReviewWorkspace || itinerary) {
      setShowPlanningProgress(false);
      setShowEntryRequirements(false);
    }
  }, [hasReviewWorkspace, itinerary]);

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
  }, [hasOptionResults, isRoundTrip, selection.flightIndex, state?.trip_legs]);

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
  }, [hasOptionResults, isRoundTrip, selectedReturnIndex, state?.trip_legs]);

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
  }, [selection.hotelIndex, showPersonalisationPanel, state?.trip_legs]);

  useEffect(() => {
    async function loadReturnOptions() {
      if (
        !state?.thread_id ||
        !isRoundTrip ||
        !state.flight_options?.length ||
        selection.flightIndex < 0
      ) {
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
    state?.flight_options,
    state?.thread_id,
    state?.trip_request,
  ]);

  function persistAuth(userId: string, nextProfile: UserProfile) {
    setAuthenticatedUser(userId);
    setProfile(nextProfile);
    setForm((current) => ({ ...current, userId, origin: nextProfile.home_city ?? current.origin }));
    setEmailAddress(userId);
    window.localStorage.setItem("tripbreeze_user", userId);
    window.localStorage.setItem("tripbreeze_profile", JSON.stringify(nextProfile));
  }

  function archiveCurrentTokenUsage() {
    if (!state?.token_usage?.length) {
      return;
    }
    const summary = summariseTokenUsage(state.token_usage);
    const tripRequest = state.trip_request ?? {};
    const label =
      String(tripRequest.destination ?? "").trim() ||
      (String(tripRequest.departure_date ?? "").trim()
        ? `Search (${String(tripRequest.departure_date)})`
        : `Search ${tokenUsageHistory.length + 1}`);
    setTokenUsageHistory((current) => [{ label, ...summary }, ...current].slice(0, 5));
  }

  function logout() {
    archiveCurrentTokenUsage();
    setAuthenticatedUser("");
    setProfile(null);
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
    window.localStorage.removeItem("tripbreeze_user");
    window.localStorage.removeItem("tripbreeze_profile");
  }

  function resetTrip() {
    archiveCurrentTokenUsage();
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
    setShowComposer(true);
    setShowEntryRequirements(false);
    setShowPlanningProgress(true);
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

  async function handleVoiceInput() {
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
      <aside className="hidden w-80 shrink-0 lg:block">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.25em] text-slate">Account</p>
              <h2 className="mt-2 font-display text-2xl text-ink">{authenticatedUser}</h2>
            </div>
            <button type="button" onClick={logout} className="rounded-full border border-ink/10 p-2 text-slate transition hover:bg-white">
              <LogOut className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-6 space-y-5">
            <div>
              <button
                type="button"
                onClick={() => setShowProfilePreferences((current) => !current)}
                className="flex w-full items-center justify-between rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-left transition hover:bg-white"
              >
                <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                  <UserRound className="h-4 w-4" />
                  Preferences
                </span>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                  {showProfilePreferences ? "Hide" : "Open"}
                </span>
              </button>
              {showProfilePreferences ? (
                <div className="mt-3 space-y-3">
                  <input
                    list="cities"
                    placeholder="Home City"
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={profile?.home_city ?? ""}
                    onChange={(event) => setProfile((current) => ({ ...(current ?? {}), home_city: event.target.value }))}
                  />
                  <input
                    list="countries"
                    placeholder="Passport Country"
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={profile?.passport_country ?? ""}
                    onChange={(event) => setProfile((current) => ({ ...(current ?? {}), passport_country: event.target.value }))}
                  />
                  <select
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={profile?.travel_class ?? "ECONOMY"}
                    onChange={(event) => setProfile((current) => ({ ...(current ?? {}), travel_class: event.target.value }))}
                  >
                    {TRAVEL_CLASSES.map((travelClass) => (
                      <option key={travelClass} value={travelClass}>
                        {travelClass.replaceAll("_", " ")}
                      </option>
                    ))}
                  </select>
                  <TimeWindowPicker
                    label="Preferred Outbound Flight Time"
                    start={Number(profile?.preferred_outbound_time_window?.[0] ?? 0)}
                    end={Number(profile?.preferred_outbound_time_window?.[1] ?? 23)}
                    onChange={(nextStart, nextEnd) =>
                      setProfile((current) => ({
                        ...(current ?? {}),
                        preferred_outbound_time_window: [nextStart, nextEnd],
                      }))
                    }
                  />
                  <TimeWindowPicker
                    label="Preferred Return Flight Time"
                    start={Number(profile?.preferred_return_time_window?.[0] ?? 0)}
                    end={Number(profile?.preferred_return_time_window?.[1] ?? 23)}
                    onChange={(nextStart, nextEnd) =>
                      setProfile((current) => ({
                        ...(current ?? {}),
                        preferred_return_time_window: [nextStart, nextEnd],
                      }))
                    }
                  />
                  <select
                    multiple
                    className="h-32 w-full rounded-3xl border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={(profile?.preferred_airlines as string[] | undefined) ?? []}
                    onChange={(event) =>
                      setProfile((current) => ({
                        ...(current ?? {}),
                        preferred_airlines: Array.from(event.target.selectedOptions, (option) => option.value),
                      }))
                    }
                  >
                    {airlines.slice(0, 60).map((airline) => (
                      <option key={airline} value={airline}>
                        {airline}
                      </option>
                    ))}
                  </select>
                  <HotelStarTierPicker
                    label="Preferred Hotel Stars"
                    helper="Choose one or more default hotel tiers like 3-star and up."
                    thresholds={compressStarPreferences(((profile?.preferred_hotel_stars as number[] | undefined) ?? []))}
                    onChange={(thresholds) =>
                      setProfile((current) => ({
                        ...(current ?? {}),
                        preferred_hotel_stars: expandStarThresholds(thresholds),
                      }))
                    }
                  />
                  <Button variant="secondary" onClick={handleSaveProfile} disabled={loading === "saving"}>
                    {loading === "saving" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                    Save Profile
                  </Button>
                </div>
              ) : null}
            </div>

            {profile?.past_trips?.length ? (
              <div>
                <div className="mb-3 text-sm font-semibold text-ink">Past Trips</div>
                <div className="space-y-2">
                  {profile.past_trips.slice(-5).reverse().map((trip, index) => (
                    <div key={`${trip.destination ?? "trip"}-${index}`} className="rounded-2xl bg-white/80 p-3 text-sm">
                      <div className="font-medium text-ink">{String(trip.destination ?? "Trip")}</div>
                      <div className="text-slate">{String(trip.dates ?? "")}</div>
                      {trip.final_itinerary ? (
                        <button
                          type="button"
                          className="mt-2 text-xs font-semibold text-coral"
                          onClick={async () => {
                            try {
                              const blob = await downloadItineraryPdf(
                                String(trip.final_itinerary),
                                (trip.pdf_state as Record<string, unknown>) ?? {},
                                `${String(trip.destination ?? "trip").replaceAll(" ", "_")}_itinerary.pdf`,
                              );
                              const url = URL.createObjectURL(blob);
                              const link = document.createElement("a");
                              link.href = url;
                              link.download = `${String(trip.destination ?? "trip").replaceAll(" ", "_")}_itinerary.pdf`;
                              link.click();
                              URL.revokeObjectURL(url);
                            } catch (pastTripError) {
                              setError(safeErrorMessage(pastTripError));
                            }
                          }}
                        >
                          Download PDF
                        </button>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            {(currentTokenSummary.cost > 0 || tokenUsageHistory.length > 0) ? (
              <div>
                <button
                  type="button"
                  onClick={() => setShowTokenUsage((current) => !current)}
                  className="flex w-full items-center justify-between rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-left transition hover:bg-white"
                >
                  <span className="text-sm font-semibold text-ink">Token Usage</span>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                    {showTokenUsage ? "Hide" : "Open"}
                  </span>
                </button>
                {showTokenUsage ? (
                  <>
                    <div className="mt-3 rounded-2xl bg-white/80 p-3 text-sm text-slate">
                      <div>Current cost: ${currentTokenSummary.cost.toFixed(4)}</div>
                      <div>Input: {currentTokenSummary.input_tokens.toLocaleString()}</div>
                      <div>Output: {currentTokenSummary.output_tokens.toLocaleString()}</div>
                    </div>
                    {tokenUsageHistory.length ? (
                      <div className="mt-2 space-y-2">
                        {tokenUsageHistory.map((item) => (
                          <div key={`${item.label}-${item.cost}`} className="rounded-2xl bg-white/60 p-3 text-xs text-slate">
                            <div className="font-semibold text-ink">{item.label}</div>
                            <div>${item.cost.toFixed(4)}</div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </div>
            ) : null}

            {(hasReviewWorkspace || itinerary) && recentPlanningUpdates.length > 0 ? (
              <div className="rounded-2xl border border-ink/10 bg-white/70 p-4">
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
                      <div key={`${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2 text-sm text-slate">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>
      </aside>

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
            onVoiceInput={handleVoiceInput}
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
