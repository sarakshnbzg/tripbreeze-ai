import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultForm } from "@/lib/planner";

import { PlannerStage } from "./planner-stage";

describe("PlannerStage", () => {
  it("renders clarification before planning progress when a follow-up answer is needed", () => {
    render(
      <PlannerStage
        form={defaultForm}
        setForm={vi.fn()}
        controls={{
          resetTrip: vi.fn(),
          logout: vi.fn(),
          handleDownloadPdf: vi.fn(async () => undefined),
          handleEmailItinerary: vi.fn(async () => undefined),
          handleClarification: vi.fn(async () => undefined),
          handlePlanTrip: vi.fn(async () => undefined),
          handleVoiceInput: vi.fn(async () => undefined),
        }}
        displayState={{
          showModelSettings: false,
          setShowModelSettings: vi.fn(),
          showComposer: false,
          itinerary: "",
          messages: [
            { role: "user", content: "I want to travel to London." },
            { role: "assistant", content: "I'd love to help plan your trip!" },
          ],
          originalUserMessage: { role: "user", content: "I want to travel to London." },
          hasReviewWorkspace: false,
          clarificationTranscript: [],
          recentPlanningUpdates: ["Loading your traveler profile..."],
          showPlanningProgress: true,
          setShowPlanningProgress: vi.fn(),
          loading: null,
          clarificationQuestion: "Could you tell me where you're flying from, when you'd like to depart, and when you'd like to return?",
          clarificationAnswer: "From Berlin",
          setClarificationAnswer: vi.fn(),
          recording: false,
          error: "",
          username: "",
          homeCity: "",
        }}
        models={{
          availableProviders: ["openai", "gemini"],
          availableModels: ["gpt-4o-mini"],
          reviewWorkspaceModel: {
            hasReviewWorkspace: false,
            finalItinerary: "",
            state: null,
            isRoundTrip: false,
            completedMultiCityLegs: 0,
            hasSelectedSingleFlight: false,
            hasSelectedSingleHotel: false,
            selectedOutboundOption: {},
            selectedReturnIndex: null,
            selectedReturnOption: {},
            selectedHotelOption: {},
            hasOptionResults: false,
            partialResultsNote: "",
            currencyCode: "EUR",
            selection: { flightIndex: -1, hotelIndex: -1, byLegFlights: [], byLegHotels: [] },
            returnOptions: [],
            showPersonalisationPanel: false,
            canApprove: false,
            returnOptionsLoading: false,
            interests: [],
            pace: "moderate",
            feedback: "",
            loading: null,
          },
          reviewWorkspaceActions: {
            setSelectedReturnIndex: vi.fn(),
            setSelection: vi.fn(),
            setInterests: vi.fn(),
            setPace: vi.fn(),
            setFeedback: vi.fn(),
            handleReview: vi.fn(async () => undefined),
          },
          reviewWorkspaceRefs: {
            outboundSectionRef: { current: null },
            returnSectionRef: { current: null },
            hotelSectionRef: { current: null },
            personaliseSectionRef: { current: null },
          },
          itineraryView: {
            finalItinerary: "",
            hasStructuredItinerary: false,
            fallbackNotice: null,
            snapshotItems: [],
            bookingLinks: [],
            primarySections: [],
            secondarySections: [],
            visaTrust: null,
            visaBriefings: [],
            mapPoints: [],
            itineraryLegs: [],
            itineraryDays: [],
            budgetBreakdown: null,
          },
          itineraryShareState: {
            loading: null,
            emailAddress: "",
            shareMessage: "",
            setEmailAddress: vi.fn(),
            onDownloadPdf: vi.fn(async () => undefined),
            onEmailItinerary: vi.fn(async () => undefined),
          },
        }}
      />,
    );

    const clarificationHeading = screen.getByText("One quick detail");
    const progressHeading = screen.getByText("Planning progress");

    expect(
      clarificationHeading.compareDocumentPosition(progressHeading) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
