"use client";

import { Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ModelSettingsPanel } from "@/components/tripbreeze-chat-app/model-settings-panel";
import { PlannerComposer } from "@/components/tripbreeze-chat-app/planner-composer";
import { FinalItineraryPanel, ReviewPanel } from "@/components/tripbreeze-chat-app/workspace";
import {
  ClarificationPanel,
  MessageFeed,
  PlanningProgressPanel,
  TranscriptPanel,
} from "@/components/tripbreeze-chat-app/planner-stage-panels";
import type { PlannerStageProps } from "@/components/tripbreeze-chat-app/planner-stage-types";

export function PlannerStage({
  form,
  setForm,
  controls,
  displayState,
  models,
}: PlannerStageProps) {
  const {
    resetTrip,
    logout,
    handleClarification,
    handlePlanTrip,
    handleVoiceInput,
  } = controls;
  const {
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
  } = displayState;
  const {
    availableModels,
    reviewWorkspaceModel,
    reviewWorkspaceActions,
    reviewWorkspaceRefs,
    itineraryView,
    itineraryShareState,
  } = models;
  const shouldShowMessageFeed = messages.length > 0 && !hasReviewWorkspace && !itinerary;
  const shouldShowRequestSummary = (hasReviewWorkspace || Boolean(itinerary)) && originalUserMessage;
  const shouldShowReviewProgress = recentPlanningUpdates.length > 0 && !(hasReviewWorkspace || itinerary);
  const shouldShowCompactProgress = (hasReviewWorkspace || Boolean(itinerary)) && recentPlanningUpdates.length > 0;
  const currentStage = itinerary ? "finalize" : hasReviewWorkspace ? "review" : "plan";
  const compactHero = hasReviewWorkspace || Boolean(itinerary);
  const stageItems = [
    {
      key: "plan",
      label: "Plan",
      description: "Shape the brief and launch research.",
    },
    {
      key: "review",
      label: "Review",
      description: "Compare flights, hotels, and costs.",
    },
    {
      key: "finalize",
      label: "Finalize",
      description: "Turn the approved trip into an itinerary.",
    },
  ] as const;
  const tripSummaryItems = [
    {
      label: "Trip mode",
      value: form.multiCity ? "Multi-city" : form.oneWay ? "One-way" : "Round trip",
    },
    {
      label: "Travelers",
      value: `${Math.max(1, form.travelers)} traveler${Math.max(1, form.travelers) === 1 ? "" : "s"}`,
    },
    {
      label: "Budget",
      value: form.budgetLimit > 0 ? `${form.currency} ${form.budgetLimit.toLocaleString()}` : "Flexible",
    },
  ];

  return (
    <main className="min-w-0 flex-1">
      <Card className="relative overflow-hidden border-white/85 bg-white/88 p-4 shadow-shell sm:p-6 lg:p-8">
        <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-r from-sun/12 via-white/0 to-pine/10" />
        <div className="relative flex flex-col gap-4 border-b border-line/70 pb-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="eyebrow-label">Travel planning workspace</div>
            <h1 className="section-title mt-2 text-[2rem] text-ink sm:text-4xl">TripBreeze AI</h1>
            <p className="body-copy mt-2 max-w-2xl text-sm sm:text-[15px]">
              Search, compare, and refine a trip plan before turning it into a polished itinerary.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-3 lg:flex lg:flex-wrap lg:justify-end">
            <Button variant="secondary" onClick={() => setShowModelSettings((current) => !current)} className="justify-center lg:min-w-[8.75rem]">
              <Settings2 className="mr-2 h-4 w-4" />
              Settings
            </Button>
            <Button variant="secondary" onClick={resetTrip} className="justify-center lg:min-w-[8.75rem]">
              New Trip
            </Button>
            <button
              type="button"
              onClick={logout}
              className="rounded-full border border-ink/10 px-4 py-3 text-sm font-semibold text-ink transition hover:bg-white lg:hidden"
            >
              Log Out
            </button>
          </div>
        </div>

        <div className="relative mt-6 space-y-5">
          <section className={`panel-surface travel-grid rounded-[2rem] ${compactHero ? "p-4 sm:p-5" : "p-5 sm:p-6"}`}>
            <div className={`flex flex-col ${compactHero ? "gap-4" : "gap-5"} xl:flex-row xl:items-end xl:justify-between`}>
              <div className="max-w-2xl">
                <div className="eyebrow-label">Guided workspace</div>
                <h2 className={`section-title mt-2 text-ink ${compactHero ? "text-[1.65rem] sm:text-[2.1rem]" : "text-[1.9rem] sm:text-3xl"}`}>
                  Build the trip in stages, then turn it into something shareable.
                </h2>
                <p className={`body-copy mt-3 text-sm ${compactHero ? "hidden sm:block" : ""}`}>
                  Start with a quick travel brief, review the shortlisted options, and finish with a polished itinerary.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-2 sm:gap-3 xl:min-w-[28rem]">
                {tripSummaryItems.map((item) => (
                  <div key={item.label} className="rounded-[1.25rem] border border-white/80 bg-white/78 p-3 sm:rounded-[1.4rem] sm:p-4">
                    <div className="eyebrow-label">{item.label}</div>
                    <div className="mt-2 text-xs font-semibold text-ink sm:text-sm">{item.value}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className={`mt-4 grid grid-cols-3 gap-2 sm:mt-5 sm:gap-3`}>
              {stageItems.map((item, index) => {
                const isActive = item.key === currentStage;
                const isComplete =
                  (item.key === "plan" && (hasReviewWorkspace || Boolean(itinerary))) ||
                  (item.key === "review" && Boolean(itinerary));
                return (
                  <div
                    key={item.key}
                    className={`rounded-[1.2rem] border p-3 transition sm:rounded-[1.5rem] sm:p-4 ${
                      isActive
                        ? "border-pine/25 bg-pine/10 shadow-[0_18px_44px_rgba(24,77,71,0.12)]"
                        : isComplete
                          ? "border-coral/20 bg-coral/8"
                          : "border-white/80 bg-white/70"
                    }`}
                  >
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex items-start gap-2 sm:gap-3">
                        <div
                          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold sm:h-9 sm:w-9 sm:text-sm ${
                            isActive ? "bg-pine text-white" : isComplete ? "bg-coral text-white" : "bg-mist text-ink"
                          }`}
                        >
                          {index + 1}
                        </div>
                        <div className="min-w-0">
                          <div className="text-xs font-semibold text-ink sm:text-sm">{item.label}</div>
                          <div className="hidden text-xs text-slate sm:block">{item.description}</div>
                        </div>
                      </div>
                      <span
                        className={`self-start rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] sm:px-3 sm:text-[11px] sm:tracking-[0.16em] ${
                          isActive
                            ? "bg-pine text-white"
                            : isComplete
                              ? "bg-coral text-white"
                              : "bg-white text-slate"
                        }`}
                      >
                        {isActive ? "Current" : isComplete ? "Done" : "Next"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {!showComposer && !itinerary ? (
            <div className="rounded-[1.4rem] border border-pine/15 bg-pine/8 px-4 py-3 text-sm text-slate">
              <span className="font-semibold text-ink">Ask planner to rework results</span> reruns planning from the current review with your notes.
            </div>
          ) : null}

          {showModelSettings ? (
            <ModelSettingsPanel form={form} setForm={setForm} availableModels={availableModels} />
          ) : null}

          {shouldShowMessageFeed ? <MessageFeed messages={messages} /> : null}

          {shouldShowRequestSummary ? (
            <div className="rounded-[1.75rem] border border-line/80 bg-paper/92 px-5 py-4 text-sm leading-7 text-ink shadow-sm">
              <div className="eyebrow-label mb-2">Your request</div>
              {originalUserMessage?.content}
            </div>
          ) : null}

          {hasReviewWorkspace && clarificationTranscript.length > 0 ? (
            <TranscriptPanel title="Clarifications" messages={clarificationTranscript} />
          ) : null}

          {shouldShowReviewProgress ? (
            <PlanningProgressPanel
              recentPlanningUpdates={recentPlanningUpdates}
              showPlanningProgress={showPlanningProgress}
              setShowPlanningProgress={setShowPlanningProgress}
              loading={loading}
            />
          ) : null}

          {shouldShowCompactProgress ? (
            <PlanningProgressPanel
              recentPlanningUpdates={recentPlanningUpdates}
              showPlanningProgress={showPlanningProgress}
              setShowPlanningProgress={setShowPlanningProgress}
              loading={loading}
              compact
            />
          ) : null}

          <ReviewPanel model={reviewWorkspaceModel} actions={reviewWorkspaceActions} refs={reviewWorkspaceRefs} />

          <FinalItineraryPanel viewModel={itineraryView} shareState={itineraryShareState} />
        </div>

        <ClarificationPanel
          clarificationQuestion={clarificationQuestion}
          clarificationAnswer={clarificationAnswer}
          setClarificationAnswer={setClarificationAnswer}
          handleClarification={handleClarification}
          loading={loading}
        />

        <PlannerComposer
          form={form}
          setForm={setForm}
          showComposer={showComposer}
          loading={loading}
          recording={recording}
          error={error}
          onPlanTrip={() => void handlePlanTrip()}
          onVoiceInput={() => void handleVoiceInput()}
        />
      </Card>
    </main>
  );
}
