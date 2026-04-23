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

  return (
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
            <Button variant="secondary" onClick={resetTrip}>
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

        <div className="mt-6 space-y-5">
          {!showComposer && !itinerary ? (
            <div className="rounded-[1.4rem] border border-ink/10 bg-mist/55 px-4 py-3 text-sm text-slate">
              <span className="font-semibold text-ink">Ask planner to rework results</span> reruns planning from the current review with your notes.
            </div>
          ) : null}

          {showModelSettings ? (
            <ModelSettingsPanel form={form} setForm={setForm} availableModels={availableModels} />
          ) : null}

          {shouldShowMessageFeed ? <MessageFeed messages={messages} /> : null}

          {shouldShowRequestSummary ? (
            <div className="rounded-[1.75rem] border border-ink/10 bg-white/75 px-5 py-4 text-sm leading-7 text-ink shadow-sm">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-slate">Your request</div>
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
