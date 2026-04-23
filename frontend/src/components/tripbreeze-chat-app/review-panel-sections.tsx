import { LoaderCircle, Plane } from "lucide-react";

import { Button } from "@/components/ui/button";
import { INTEREST_OPTIONS, PACE_OPTIONS } from "./constants";
import {
  renderMarkdownContent,
  selectionLabel,
  sentenceLabel,
} from "./helpers";
import type { ReviewWorkspaceActions, ReviewWorkspaceModel, ReviewWorkspaceRefs } from "./workspace-types";

export function DestinationBriefingPanel({ destinationInfo }: { destinationInfo: unknown }) {
  if (!destinationInfo) {
    return null;
  }

  return (
    <div className="rounded-[1.75rem] border border-ink/10 bg-white/80 p-5">
      <div className="mb-3 text-lg font-semibold text-ink">Destination briefing</div>
      <div className="text-sm leading-7 text-ink">
        {renderMarkdownContent(String(destinationInfo)) ?? String(destinationInfo)}
      </div>
    </div>
  );
}

export function ReviewWorkspaceHeader({ model }: { model: ReviewWorkspaceModel }) {
  const {
    state,
    isRoundTrip,
    completedMultiCityLegs,
    hasSelectedSingleFlight,
    hasSelectedSingleHotel,
    selectedOutboundOption,
    selectedReturnIndex,
    selectedReturnOption,
    selectedHotelOption,
  } = model;

  if (!state) {
    return null;
  }

  const steps = state.trip_legs?.length
    ? ["1. Select flights", "2. Select hotels", "3. Personalise itinerary"]
    : isRoundTrip
      ? ["1. Select outbound flight", "2. Select return flight", "3. Select hotel", "4. Personalise itinerary"]
      : ["1. Select flight", "2. Select hotel", "3. Personalise itinerary"];

  return (
    <>
      <div className="mb-5 flex items-center gap-2 text-lg font-semibold text-ink">
        <Plane className="h-5 w-5 text-coral" />
        Review your trip
      </div>
      <div className="mb-5 flex flex-wrap gap-2">
        {steps.map((step) => (
          <div
            key={step}
            className="rounded-full border border-ink/10 bg-white/75 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate sm:text-xs sm:tracking-[0.14em]"
          >
            {step}
          </div>
        ))}
      </div>
      {state.trip_legs?.length ? (
        <div className="mb-5 rounded-[1.4rem] border border-ink/10 bg-white/70 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Multi-city progress:</span>{" "}
          {completedMultiCityLegs} of {state.trip_legs.length} legs fully selected
        </div>
      ) : (
        <div className="mb-5 rounded-[1.4rem] border border-ink/10 bg-white/70 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Selected so far:</span>{" "}
          {hasSelectedSingleFlight ? selectionLabel(selectedOutboundOption, "Flight selected") : "No flight yet"}
          {isRoundTrip
            ? ` • ${selectedReturnIndex !== null ? selectionLabel(selectedReturnOption, "Return selected") : "No return yet"}`
            : ""}
          {` • ${hasSelectedSingleHotel ? selectionLabel(selectedHotelOption, "Hotel selected") : "No hotel yet"}`}
        </div>
      )}
    </>
  );
}

export function EmptyOptionsPanel() {
  return (
    <div className="rounded-[1.6rem] border border-dashed border-ink/15 bg-white/75 p-5 text-sm text-slate">
      <div className="font-semibold text-ink">No bookable options are ready yet</div>
      <div className="mt-2 leading-7">
        The planner finished this search without flight or hotel results you can choose from here.
      </div>
    </div>
  );
}

export function PersonalisationPanel({
  model,
  actions,
  personaliseSectionRef,
}: {
  model: ReviewWorkspaceModel;
  actions: ReviewWorkspaceActions;
  personaliseSectionRef: ReviewWorkspaceRefs["personaliseSectionRef"];
}) {
  const { showPersonalisationPanel, interests, pace } = model;
  const { setInterests, setPace } = actions;

  if (!showPersonalisationPanel) {
    return null;
  }

  return (
    <div
      ref={personaliseSectionRef}
      className="mt-5 rounded-[1.8rem] border border-ink/10 bg-gradient-to-br from-mist/90 to-white p-5"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">Personalise the itinerary</div>
          <div className="mt-1 text-sm text-slate">
            Shape the trip around what you want to do and how full you want the days to feel.
          </div>
        </div>
        <div className="rounded-[1.2rem] bg-white/85 px-3 py-2 text-xs text-slate">
          <span className="font-semibold text-ink">Selected:</span>{" "}
          {interests.length ? interests.map(sentenceLabel).join(", ") : "No interests yet"} • {sentenceLabel(pace)} pace
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Interests</div>
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          {INTEREST_OPTIONS.map((interest) => {
            const active = interests.includes(interest);
            return (
              <button
                key={interest}
                type="button"
                onClick={() =>
                  setInterests((current: string[]) =>
                    active ? current.filter((value: string) => value !== interest) : [...current, interest],
                  )
                }
                className={`rounded-[1.2rem] border px-4 py-3 text-left text-sm transition ${
                  active
                    ? "border-ink bg-ink text-white shadow-[0_14px_30px_rgba(16,33,43,0.16)]"
                    : "border-ink/10 bg-white text-slate hover:border-coral/40 hover:bg-white"
                }`}
              >
                <div className="font-semibold">{sentenceLabel(interest)}</div>
                <div className={`mt-1 text-xs ${active ? "text-white/70" : "text-slate"}`}>
                  {active ? "Included in your itinerary" : "Tap to include"}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Pace</div>
        <div className="grid gap-2 md:grid-cols-3">
          {PACE_OPTIONS.map((paceOption) => (
            <button
              key={paceOption}
              type="button"
              onClick={() => setPace(paceOption)}
              className={`rounded-[1.2rem] border px-4 py-3 text-left text-sm transition ${
                pace === paceOption
                  ? "border-coral bg-coral text-white shadow-[0_14px_30px_rgba(215,108,78,0.18)]"
                  : "border-ink/10 bg-white text-slate hover:border-coral/40"
              }`}
            >
              <div className="font-semibold">{sentenceLabel(paceOption)}</div>
              <div className={`mt-1 text-xs ${pace === paceOption ? "text-white/75" : "text-slate"}`}>
                {paceOption === "relaxed"
                  ? "Lighter days with more breathing room"
                  : paceOption === "moderate"
                    ? "A balanced mix of highlights and downtime"
                    : "A fuller schedule with more activities"}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReviewActionsPanel({
  model,
  actions,
}: {
  model: ReviewWorkspaceModel;
  actions: ReviewWorkspaceActions;
}) {
  const { showPersonalisationPanel, feedback, loading, canApprove } = model;
  const { setFeedback, handleReview } = actions;

  return (
    <>
      <textarea
        className="mt-5 h-24 w-full rounded-[1.6rem] border border-ink/10 bg-white/80 px-4 py-3 text-sm outline-none transition focus:border-coral"
        placeholder={
          showPersonalisationPanel
            ? "Add notes for the itinerary or ask for changes."
            : "Tell the planner what to change (e.g. different dates, cheaper hotels, another city)."
        }
        value={feedback}
        onChange={(event) => setFeedback(event.target.value)}
      />

      <div className="mt-4 flex flex-wrap gap-3">
        <Button onClick={() => void handleReview("rewrite_itinerary")} disabled={loading !== null || !canApprove}>
          {loading === "approving" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
          Approve and Generate Itinerary
        </Button>
        <Button variant="secondary" onClick={() => void handleReview("revise_plan")} disabled={loading !== null}>
          Ask planner to rework results
        </Button>
      </div>
    </>
  );
}
