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
  const statusLabel = flightSelected && hotelSelected ? "Complete" : "Needs choices";

  return (
    <div className="animate-soften-in rounded-[1.85rem] border border-white/80 bg-white/72 p-5 shadow-[0_18px_46px_rgba(16,33,43,0.06)]">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">Trip leg {legIndex + 1}</div>
          <div className="mt-1 text-sm font-semibold text-ink">
            Leg {legIndex + 1}: {String(leg.origin ?? "?")} to {String(leg.destination ?? "?")}
            {Number(leg.nights ?? 0) > 0
              ? ` (${Number(leg.nights)} night${Number(leg.nights) === 1 ? "" : "s"})`
              : " (Return)"}
          </div>
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${
            flightSelected && hotelSelected ? "bg-green-50 text-green-800" : "bg-white/80 text-slate"
          }`}
        >
          {statusLabel}
        </div>
      </div>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="rounded-[1.25rem] border border-line/70 bg-paper/82 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Departure:</span> {String(leg.departure_date ?? "?")}
        </div>
        <div className="rounded-[1.25rem] border border-line/70 bg-white/82 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Flight:</span> {flightSelected ? "Selected" : "Pending"}
        </div>
        <div className="rounded-[1.25rem] border border-line/70 bg-white/82 px-4 py-3 text-sm text-slate">
          <span className="font-semibold text-ink">Hotel:</span> {Boolean(leg.needs_hotel) ? (hotelSelected ? "Selected" : "Pending") : "Not needed"}
        </div>
      </div>
      {partialResultsNote ? (
        <div className="mb-4 rounded-[1.4rem] border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950">
          <span className="font-semibold">Partial results for this leg:</span> {partialResultsNote}
        </div>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate">Flights</div>
            <div className="rounded-full border border-line/70 bg-paper/84 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">
              Pick 1
            </div>
          </div>
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
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-semibold text-slate">Hotels</div>
            <div className="rounded-full border border-line/70 bg-paper/84 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">
              {Boolean(leg.needs_hotel) ? "Pick 1" : "Optional"}
            </div>
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
  return (
    <div className="space-y-5">
      {(state.trip_legs ?? []).map((leg, legIndex) => (
        <MultiCityLegPanel
          key={`leg-${legIndex}`}
          state={state}
          currencyCode={currencyCode}
          selection={selection}
          setSelection={setSelection}
          leg={leg}
          legIndex={legIndex}
        />
      ))}
    </div>
  );
}
