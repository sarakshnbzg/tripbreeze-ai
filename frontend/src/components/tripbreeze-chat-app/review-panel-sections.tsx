import { LoaderCircle, Plane } from "lucide-react";

import { Button } from "@/components/ui/button";
import { INTEREST_OPTIONS, PACE_OPTIONS } from "./constants";
import {
  renderMarkdownContent,
  readRecord,
  readRecordArray,
  selectionLabel,
  sentenceLabel,
} from "./helpers";
import { extractDestinationTrustSections, extractSourceTrust, SourceTrustCard } from "./source-trust";
import type { ReviewWorkspaceActions, ReviewWorkspaceModel, ReviewWorkspaceRefs } from "./workspace-types";

function formatTitleCase(value: string) {
  return value
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatTravelerCount(value: unknown) {
  const count = Math.max(1, Number(value ?? 1));
  return `${count} traveler${count === 1 ? "" : "s"}`;
}

function formatStopsSummary(value: unknown) {
  const stops = Number(value);
  if (!Number.isFinite(stops) || stops < 0) {
    return "";
  }
  return stops === 0 ? "Direct only" : `${stops} stop max`;
}

function activeFlightFilters(state: ReviewWorkspaceModel["state"]) {
  const trip = (state?.trip_request ?? {}) as Record<string, unknown>;
  const filters: string[] = [];

  const travelClass = String(trip.travel_class ?? "").trim();
  if (travelClass && travelClass !== "ECONOMY") {
    filters.push(`${formatTitleCase(travelClass)} cabin`);
  }

  const maxDuration = Number(trip.max_duration ?? 0);
  if (Number.isFinite(maxDuration) && maxDuration > 0) {
    const hours = Math.floor(maxDuration / 60);
    const minutes = maxDuration % 60;
    filters.push(minutes ? `Max ${hours}h ${minutes}m` : `Max ${hours}h`);
  }

  const stops = Number(trip.stops);
  const stopsUserSpecified = trip.stops_user_specified === true;
  if (stopsUserSpecified && Number.isFinite(stops) && stops >= 0) {
    filters.push(stops === 0 ? "Direct only" : `${stops} stop max`);
  }

  const excludedAirlines = Array.isArray(trip.exclude_airlines)
    ? trip.exclude_airlines.map((value) => String(value).trim()).filter(Boolean)
    : [];
  if (excludedAirlines.length) {
    filters.push(`Exclude ${excludedAirlines.join(", ")}`);
  }

  const includedAirlines = Array.isArray(trip.include_airlines)
    ? trip.include_airlines.map((value) => String(value).trim()).filter(Boolean)
    : [];
  if (includedAirlines.length) {
    filters.push(`Only ${includedAirlines.join(", ")}`);
  }

  return filters;
}

function activeHotelFilters(state: ReviewWorkspaceModel["state"]) {
  const trip = (state?.trip_request ?? {}) as Record<string, unknown>;
  const filters: string[] = [];

  const hotelBudgetTier = String(trip.hotel_budget_tier ?? "").trim();
  if (hotelBudgetTier) {
    filters.push(formatTitleCase(hotelBudgetTier));
  }

  const hotelArea = String(trip.hotel_area ?? "").trim();
  if (hotelArea) {
    filters.push(`Near ${hotelArea}`);
  }

  const hotelStarsUserSpecified = trip.hotel_stars_user_specified === true;
  const hotelStars = Array.isArray(trip.hotel_stars)
    ? trip.hotel_stars.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0)
    : [];
  if (hotelStarsUserSpecified && hotelStars.length) {
    const minStars = Math.min(...hotelStars);
    filters.push(`${minStars}-star and up`);
  }

  return filters;
}

export function DestinationBriefingPanel({ destinationInfo }: { destinationInfo: unknown }) {
  if (!destinationInfo) {
    return null;
  }

  const content = String(destinationInfo);
  const parsed = extractSourceTrust(content);
  const destinationSections = extractDestinationTrustSections(content).filter((section) => section.trust);

  return (
    <div className="panel-surface rounded-[1.85rem] p-5">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate">Prepared earlier</div>
          <div className="mt-2 text-lg font-semibold text-ink">Destination briefing</div>
        </div>
        <div className="rounded-full border border-pine/15 bg-pine/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-pine">
          Entry guidance
        </div>
      </div>
      <div className="space-y-4">
        {destinationSections.length > 1 ? (
          <div className="space-y-4">
            {destinationSections.map((section) => (
              <div key={`${section.title}-${section.trust?.sourceName ?? "trust"}`} className="space-y-3">
                <div className="text-sm font-semibold text-ink">{section.title}</div>
                {section.content ? (
                  <div className="text-sm leading-7 text-ink">
                    {renderMarkdownContent(section.content) ?? section.content}
                  </div>
                ) : null}
                {section.trust ? <SourceTrustCard trust={section.trust} compact /> : null}
              </div>
            ))}
          </div>
        ) : null}
        {destinationSections.length <= 1 ? (
          <>
            <div className="text-sm leading-7 text-ink">{renderMarkdownContent(parsed.content) ?? parsed.content}</div>
            {parsed.trust ? <SourceTrustCard trust={parsed.trust} compact /> : null}
          </>
        ) : null}
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

  const filters = activeFlightFilters(state);
  const hotelFilters = activeHotelFilters(state);
  const selectionSummary = state.trip_legs?.length
    ? `${completedMultiCityLegs} completed leg${completedMultiCityLegs === 1 ? "" : "s"} out of ${state.trip_legs.length}`
    : [
        hasSelectedSingleFlight ? selectionLabel(selectedOutboundOption, "Flight selected") : "No flight yet",
        isRoundTrip
          ? selectedReturnIndex !== null
            ? selectionLabel(selectedReturnOption, "Return selected")
            : "No return yet"
          : null,
        hasSelectedSingleHotel ? selectionLabel(selectedHotelOption, "Hotel selected") : "No hotel yet",
      ]
        .filter(Boolean)
        .join(" • ");

  const steps = state.trip_legs?.length
    ? ["1. Select flights", "2. Select hotels", "3. Personalise itinerary"]
    : isRoundTrip
      ? ["1. Select outbound flight", "2. Select return flight", "3. Select hotel", "4. Personalise itinerary"]
      : ["1. Select flight", "2. Select hotel", "3. Personalise itinerary"];

  return (
    <>
      <div className="mb-5 rounded-[1.7rem] border border-white/80 bg-white/74 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-lg font-semibold text-ink">
              <Plane className="h-5 w-5 text-coral" />
              Review your trip
            </div>
            <div className="mt-1 text-sm text-muted">Pick the right options first, then personalise the itinerary details.</div>
          </div>
          <div className="rounded-full border border-pine/15 bg-pine/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-pine">
            Decision workspace
          </div>
        </div>

        <div className="mt-5 grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <div className="rounded-[1.4rem] border border-line/70 bg-paper/82 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">Selection progress</div>
            <div className="mt-2 text-sm leading-7 text-ink">{selectionSummary}</div>
          </div>
          <div className="rounded-[1.4rem] border border-line/70 bg-white/84 p-4">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">Current flow</div>
            <div className="mt-3 flex flex-wrap gap-2">
              {steps.map((step) => (
                <div
                  key={step}
                  className="rounded-full border border-line/70 bg-white px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate sm:text-xs sm:tracking-[0.14em]"
                >
                  {step}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {filters.length ? (
        <div className="mb-5 rounded-[1.4rem] border border-line/70 bg-white/88 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Active flight filters:</span>{" "}
          {filters.join(" • ")}
        </div>
      ) : null}

      {hotelFilters.length ? (
        <div className="mb-5 rounded-[1.4rem] border border-line/70 bg-white/88 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Hotel preferences:</span>{" "}
          {hotelFilters.join(" • ")}
        </div>
      ) : null}
      {state.trip_legs?.length ? (
        <div className="mb-5 rounded-[1.4rem] border border-pine/12 bg-pine/8 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Multi-city progress:</span>{" "}
          {completedMultiCityLegs} of {state.trip_legs.length} legs fully selected
        </div>
      ) : null}
    </>
  );
}

export function EmptyOptionsPanel() {
  return (
    <div className="rounded-[1.6rem] border border-dashed border-line bg-paper/85 p-5 text-sm text-slate">
      <div className="font-semibold text-ink">No bookable options are ready yet</div>
      <div className="mt-2 leading-7">
        The planner finished this search without flight or hotel results you can choose from here.
      </div>
    </div>
  );
}

export function PartialResultsPanel({ note }: { note: string }) {
  if (!note) {
    return null;
  }

  return (
    <div className="mb-5 rounded-[1.4rem] border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950">
      <span className="font-semibold">Partial results available:</span> {note}
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
      className="mt-5 rounded-[1.8rem] border border-pine/12 bg-gradient-to-br from-paper via-mist/90 to-white p-5"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">Personalise the itinerary</div>
          <div className="mt-1 text-sm text-slate">
            Shape the trip around what you want to do and how full you want the days to feel.
          </div>
        </div>
        <div className="rounded-[1.2rem] border border-line/60 bg-white/88 px-3 py-2 text-xs text-slate">
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
                    ? "border-pine bg-pine text-white shadow-[0_14px_30px_rgba(24,77,71,0.18)]"
                    : "border-line/70 bg-white text-slate hover:border-pine/35 hover:bg-white"
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
                  : "border-line/70 bg-white text-slate hover:border-coral/40"
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
    <div className="mt-5 rounded-[1.8rem] border border-white/80 bg-white/74 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">Finish this review</div>
          <div className="mt-1 text-sm text-slate">
            Approve the current selections to generate the itinerary, or send the planner back with revision notes.
          </div>
        </div>
        <div
          className={`rounded-full px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] ${
            canApprove ? "border border-pine/15 bg-pine/10 text-pine" : "border border-line/70 bg-paper/80 text-slate"
          }`}
        >
          {canApprove ? "Ready to approve" : "Selections still needed"}
        </div>
      </div>

      <textarea
        className="mt-5 h-24 w-full rounded-[1.6rem] border border-ink/10 bg-white/88 px-4 py-3 text-sm outline-none transition focus:border-coral"
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
    </div>
  );
}
