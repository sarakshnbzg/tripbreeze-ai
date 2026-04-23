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

  return (
    <div className="rounded-[1.75rem] bg-mist/45 p-4 ring-1 ring-white/80">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm font-semibold text-ink">
          Leg {legIndex + 1}: {String(leg.origin ?? "?")} to {String(leg.destination ?? "?")}
          {Number(leg.nights ?? 0) > 0
            ? ` (${Number(leg.nights)} night${Number(leg.nights) === 1 ? "" : "s"})`
            : " (Return)"}
        </div>
        <div
          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${
            flightSelected && hotelSelected ? "bg-green-50 text-green-800" : "bg-white/80 text-slate"
          }`}
        >
          {flightSelected && hotelSelected ? "Complete" : "Needs choices"}
        </div>
      </div>
      <div className="mb-4 text-sm text-slate">Departure: {String(leg.departure_date ?? "?")}</div>
      {partialResultsNote ? (
        <div className="mb-4 rounded-[1.4rem] border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-950">
          <span className="font-semibold">Partial results for this leg:</span> {partialResultsNote}
        </div>
      ) : null}
      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-3">
          <div className="text-sm font-semibold text-slate">Flights</div>
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
          <div className="text-sm font-semibold text-slate">Hotels</div>
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
