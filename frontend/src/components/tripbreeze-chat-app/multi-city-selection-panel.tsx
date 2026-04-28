import { useEffect, useRef } from "react";

import type { SelectionState } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

import { ReviewOptionCard } from "./controls";
import type { ReviewWorkspaceActions } from "./workspace-types";

function MultiCityLegPanel({
  state,
  currencyCode,
  selection,
  setSelection,
  leg,
  legIndex,
}: {
  state: TravelState;
  currencyCode: string;
  selection: SelectionState;
  setSelection: ReviewWorkspaceActions["setSelection"];
  leg: Record<string, unknown>;
  legIndex: number;
}) {
  const flightSelected =
    typeof selection.byLegFlights[legIndex] === "number" && selection.byLegFlights[legIndex] >= 0;
  const flightOptions = state.flight_options_by_leg?.[legIndex] ?? [];
  const hotelOptions = state.hotel_options_by_leg?.[legIndex] ?? [];
  const canShowHotels = flightSelected || !flightOptions.length;
  const legBudget = Array.isArray((state.budget as { per_leg_breakdown?: Array<Record<string, unknown>> } | undefined)?.per_leg_breakdown)
    ? ((state.budget as { per_leg_breakdown?: Array<Record<string, unknown>> }).per_leg_breakdown?.[legIndex] ?? {})
    : {};
  const partialResultsNote = String(legBudget.partial_results_note ?? "").trim();
  const hotelSelected =
    !leg.needs_hotel ||
    (typeof selection.byLegHotels[legIndex] === "number" && selection.byLegHotels[legIndex] >= 0);
  const statusLabel = flightSelected && hotelSelected ? "Ready" : "In progress";
  const stepSummary = [
    `Depart ${String(leg.departure_date ?? "?")}`,
    flightSelected ? "Flight selected" : "Choose flight",
    Boolean(leg.needs_hotel) ? (hotelSelected ? "Hotel selected" : "Choose hotel") : "No hotel needed",
  ].join(" • ");

  return (
    <div className="animate-soften-in rounded-[1.65rem] border border-line/70 bg-white/78 p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">Trip leg {legIndex + 1}</div>
          <div className="mt-1 text-base font-semibold text-ink">
            Leg {legIndex + 1}: {String(leg.origin ?? "?")} to {String(leg.destination ?? "?")}
            {Number(leg.nights ?? 0) > 0
              ? ` (${Number(leg.nights)} night${Number(leg.nights) === 1 ? "" : "s"})`
              : " (Return)"}
          </div>
          <div className="mt-1 text-sm text-slate">{stepSummary}</div>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${
            flightSelected && hotelSelected ? "bg-green-50 text-green-800" : "bg-paper/80 text-slate"
          }`}
        >
          {statusLabel}
        </div>
      </div>
      {partialResultsNote ? (
        <div className="mb-4 rounded-[1.4rem] border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950">
          <span className="font-semibold">Partial results for this leg:</span> {partialResultsNote}
        </div>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-3">
          <div className="text-sm font-semibold text-ink">Choose flight</div>
          {flightOptions.length ? (
            flightOptions.slice(0, 5).map((option, optionIndex) => (
              <ReviewOptionCard
                key={`flight-${legIndex}-${optionIndex}`}
                option={option}
                title={`Flight ${optionIndex + 1}`}
                variant="flight"
                allOptions={flightOptions}
                currencyCode={currencyCode}
                selected={selection.byLegFlights[legIndex] === optionIndex}
                onSelect={() =>
                  setSelection((current: SelectionState) => {
                    const next = [...current.byLegFlights];
                    next[legIndex] = optionIndex;
                    return { ...current, byLegFlights: next };
                  })
                }
              />
            ))
          ) : (
            <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-coral">No flights found for this leg.</div>
          )}
        </div>
        <div className="space-y-3">
          <div className="text-sm font-semibold text-ink">
            {Boolean(leg.needs_hotel) ? "Choose hotel" : "Hotel"}
          </div>
          {Boolean(leg.needs_hotel) ? (
            !canShowHotels ? (
              <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-slate">
                Select a flight for this leg before choosing a hotel.
              </div>
            ) : hotelOptions.length ? (
              hotelOptions.slice(0, 5).map((option, optionIndex) => (
                <ReviewOptionCard
                  key={`hotel-${legIndex}-${optionIndex}`}
                  option={option}
                  title={`Hotel ${optionIndex + 1}`}
                  variant="hotel"
                  allOptions={hotelOptions}
                  currencyCode={currencyCode}
                  selected={selection.byLegHotels[legIndex] === optionIndex}
                  onSelect={() =>
                    setSelection((current: SelectionState) => {
                      const next = [...current.byLegHotels];
                      next[legIndex] = optionIndex;
                      return { ...current, byLegHotels: next };
                    })
                  }
                />
              ))
            ) : (
              <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-coral">No hotels found for this destination.</div>
            )
          ) : (
            <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-slate">No hotel needed for this leg (return flight).</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function MultiCitySelectionPanel({
  state,
  currencyCode,
  selection,
  setSelection,
}: {
  state: TravelState;
  currencyCode: string;
  selection: SelectionState;
  setSelection: ReviewWorkspaceActions["setSelection"];
}) {
  const legRefs = useRef<Array<HTMLDivElement | null>>([]);
  const previousCompletionRef = useRef<boolean[]>([]);
  const tripLegs = state.trip_legs ?? [];

  useEffect(() => {
    const completion = tripLegs.map((leg, index) => {
      const hasFlight = typeof selection.byLegFlights[index] === "number" && selection.byLegFlights[index] >= 0;
      const needsHotel = Boolean(leg.needs_hotel);
      const hasHotel = !needsHotel || (typeof selection.byLegHotels[index] === "number" && selection.byLegHotels[index] >= 0);
      return hasFlight && hasHotel;
    });

    const previous = previousCompletionRef.current;
    const newlyCompletedIndex = completion.findIndex((done, index) => done && !previous[index]);
    previousCompletionRef.current = completion;

    if (newlyCompletedIndex < 0) {
      return;
    }

    const nextIncompleteIndex = completion.findIndex((done, index) => index > newlyCompletedIndex && !done);
    if (nextIncompleteIndex < 0) {
      return;
    }

    const target = legRefs.current[nextIncompleteIndex];
    if (!target) {
      return;
    }

    window.setTimeout(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [selection.byLegFlights, selection.byLegHotels, tripLegs]);

  return (
    <div className="space-y-5">
      {(state.trip_legs ?? []).map((leg, legIndex) => (
        <div
          key={`leg-${legIndex}`}
          ref={(node) => {
            legRefs.current[legIndex] = node;
          }}
        >
          <MultiCityLegPanel
            state={state}
            currencyCode={currencyCode}
            selection={selection}
            setSelection={setSelection}
            leg={leg}
            legIndex={legIndex}
          />
        </div>
      ))}
    </div>
  );
}
