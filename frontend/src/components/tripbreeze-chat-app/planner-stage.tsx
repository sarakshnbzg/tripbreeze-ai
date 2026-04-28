"use client";

import { Settings2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ModelSettingsPanel } from "@/components/tripbreeze-chat-app/model-settings-panel";
import { PlannerComposer } from "@/components/tripbreeze-chat-app/planner-composer";
import { FinalItineraryPanel, ReviewPanel } from "@/components/tripbreeze-chat-app/workspace";
import { buildResolvedRequestDataPoints, buildResolvedRequestSummary } from "@/components/tripbreeze-chat-app/helpers";
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
  const resolvedRequestSummary = buildResolvedRequestSummary(
    reviewWorkspaceModel.state,
    reviewWorkspaceModel.currencyCode,
    originalUserMessage?.content ?? "",
  );
  const resolvedRequestDataPoints = buildResolvedRequestDataPoints(
    reviewWorkspaceModel.state,
    reviewWorkspaceModel.currencyCode,
  );
  const shouldShowMessageFeed = messages.length > 0 && !hasReviewWorkspace && !itinerary;
  const shouldShowRequestSummary = (hasReviewWorkspace || Boolean(itinerary)) && resolvedRequestSummary;
  const shouldShowReviewProgress = recentPlanningUpdates.length > 0 && !(hasReviewWorkspace || itinerary);
  const shouldShowCompactProgress = (hasReviewWorkspace || Boolean(itinerary)) && recentPlanningUpdates.length > 0;
  const shouldDeferProgressUntilAfterClarification = Boolean(clarificationQuestion);

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
              <div>{resolvedRequestSummary}</div>
              {resolvedRequestDataPoints.length ? (
                <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {resolvedRequestDataPoints.map((item) => (
                    <div key={`${item.label}-${item.value}`} className="rounded-[1.2rem] border border-line/70 bg-white/72 px-4 py-3">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">{item.label}</div>
                      <div className="mt-1 text-sm font-medium text-ink">{item.value}</div>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}

          {hasReviewWorkspace && clarificationTranscript.length > 0 ? (
            <TranscriptPanel title="Clarifications" messages={clarificationTranscript} />
          ) : null}

          {shouldShowReviewProgress && !shouldDeferProgressUntilAfterClarification ? (
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

        {shouldShowReviewProgress && shouldDeferProgressUntilAfterClarification ? (
          <PlanningProgressPanel
            recentPlanningUpdates={recentPlanningUpdates}
            showPlanningProgress={showPlanningProgress}
            setShowPlanningProgress={setShowPlanningProgress}
            loading={loading}
          />
        ) : null}

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
