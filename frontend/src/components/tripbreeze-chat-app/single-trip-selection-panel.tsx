import { LoaderCircle } from "lucide-react";

import type { SelectionState } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

import { ReviewOptionCard } from "./controls";
import type { ReviewWorkspaceActions, ReviewWorkspaceModel, ReviewWorkspaceRefs } from "./workspace-types";

function ReviewSectionShell({
  title,
  subtitle,
  badge,
  children,
}: {
  title: string;
  subtitle: string;
  badge: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-[1.8rem] border border-white/80 bg-white/76 p-4 shadow-[0_18px_46px_rgba(16,33,43,0.06)] sm:p-5">
      <div className="animate-soften-in">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">{title}</div>
          <div className="mt-1 text-sm text-slate">{subtitle}</div>
        </div>
        <div className="rounded-full border border-line/70 bg-paper/84 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate">
          {badge}
        </div>
      </div>
      {children}
      </div>
    </section>
  );
}

function OutboundFlightSection({
  state,
  isRoundTrip,
  currencyCode,
  selection,
  setSelection,
  outboundSectionRef,
}: {
  state: TravelState;
  isRoundTrip: boolean;
  currencyCode: string;
  selection: SelectionState;
  setSelection: ReviewWorkspaceActions["setSelection"];
  outboundSectionRef: ReviewWorkspaceRefs["outboundSectionRef"];
}) {
  return (
    <ReviewSectionShell
      title={isRoundTrip ? "Outbound flights" : "Flights"}
      subtitle={isRoundTrip ? "Choose the outbound option that sets up the rest of the trip." : "Choose the flight that best fits timing, price, and comfort."}
      badge={`${Math.min((state.flight_options ?? []).length, 5)} shown`}
    >
      <div ref={outboundSectionRef} className="space-y-3">
        {(state.flight_options ?? []).length ? (
          (state.flight_options ?? []).slice(0, 5).map((option, index) => (
            <ReviewOptionCard
              key={`flight-${index}`}
              option={option}
              title={`Flight ${index + 1}`}
              variant="flight"
              allOptions={state.flight_options ?? []}
              currencyCode={currencyCode}
              selected={selection.flightIndex === index}
              onSelect={() => {
                setSelection((current: SelectionState) => ({ ...current, flightIndex: index }));
              }}
            />
          ))
        ) : (
          <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-coral">No flights found. Try different dates or cities.</div>
        )}
      </div>
    </ReviewSectionShell>
  );
}

function ReturnFlightSection({
  selection,
  returnOptionsLoading,
  returnOptions,
  selectedReturnIndex,
  setSelectedReturnIndex,
  currencyCode,
  returnSectionRef,
}: {
  selection: SelectionState;
  returnOptionsLoading: boolean;
  returnOptions: ReviewWorkspaceModel["returnOptions"];
  selectedReturnIndex: number | null;
  setSelectedReturnIndex: ReviewWorkspaceActions["setSelectedReturnIndex"];
  currencyCode: string;
  returnSectionRef: ReviewWorkspaceRefs["returnSectionRef"];
}) {
  return (
    <ReviewSectionShell
      title="Return flights"
      subtitle="Return options line up with the outbound choice you picked above."
      badge={selectedReturnIndex !== null ? "Return selected" : "Pick 1"}
    >
      <div ref={returnSectionRef} className="space-y-3">
        {selection.flightIndex >= 0 ? (
          returnOptionsLoading ? (
            <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
              <div className="flex items-center gap-2 font-semibold text-ink">
                <LoaderCircle className="h-4 w-4 animate-spin text-coral" />
                Loading return flights...
              </div>
              <div className="mt-2">We’re finding matching return options for the outbound flight you selected.</div>
            </div>
          ) : returnOptions.length ? (
            returnOptions.slice(0, 5).map((option, index) => (
              <ReviewOptionCard
                key={`return-${index}`}
                option={option}
                title={`Return ${index + 1}`}
                variant="flight"
                allOptions={returnOptions}
                currencyCode={currencyCode}
                selected={selectedReturnIndex === index}
                onSelect={() => setSelectedReturnIndex(index)}
              />
            ))
          ) : (
            <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
              Return options will load after you choose an outbound flight.
            </div>
          )
        ) : (
          <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
            Select an outbound flight first to review return options.
          </div>
        )}
      </div>
    </ReviewSectionShell>
  );
}

function HotelSelectionSection({
  state,
  isRoundTrip,
  currencyCode,
  selection,
  setSelection,
  returnOptionsLoading,
  hotelSectionRef,
}: {
  state: TravelState;
  isRoundTrip: boolean;
  currencyCode: string;
  selection: SelectionState;
  setSelection: ReviewWorkspaceActions["setSelection"];
  returnOptionsLoading: boolean;
  hotelSectionRef: ReviewWorkspaceRefs["hotelSectionRef"];
}) {
  const canShowHotels = selection.flightIndex >= 0 || !(state.flight_options ?? []).length;

  if (canShowHotels) {
    return (
      <ReviewSectionShell
        title="Hotels"
        subtitle="Compare the stay options once the flight side of the trip is in place."
        badge={selection.hotelIndex >= 0 ? "Hotel selected" : `${Math.min((state.hotel_options ?? []).length, 5)} shown`}
      >
        <div ref={hotelSectionRef} className="space-y-3">
          {isRoundTrip && returnOptionsLoading ? (
            <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
              Return flights are loading. Hotel options will stay here once those are ready.
            </div>
          ) : (state.hotel_options ?? []).length ? (
            (state.hotel_options ?? []).slice(0, 5).map((option, index) => (
              <ReviewOptionCard
                key={`hotel-${index}`}
                option={option}
                title={`Hotel ${index + 1}`}
                variant="hotel"
                allOptions={state.hotel_options ?? []}
                currencyCode={currencyCode}
                selected={selection.hotelIndex === index}
                onSelect={() => setSelection((current: SelectionState) => ({ ...current, hotelIndex: index }))}
              />
            ))
          ) : (
            <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-coral">No hotels found. Try different dates or destination.</div>
          )}
        </div>
      </ReviewSectionShell>
    );
  }

  return (
    <ReviewSectionShell
      title="Hotels"
      subtitle="Hotel selection unlocks after you choose the right flight."
      badge="Waiting"
    >
      <div ref={hotelSectionRef} className="space-y-3">
        <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
          Select a flight first to review hotel options.
        </div>
      </div>
    </ReviewSectionShell>
  );
}

export function SingleTripSelectionPanel({
  model,
  actions,
  refs,
}: {
  model: ReviewWorkspaceModel;
  actions: ReviewWorkspaceActions;
  refs: ReviewWorkspaceRefs;
}) {
  const {
    state,
    isRoundTrip,
    currencyCode,
    selection,
    returnOptions,
    returnOptionsLoading,
    selectedReturnIndex,
  } = model;
  const { setSelectedReturnIndex, setSelection } = actions;
  const { outboundSectionRef, returnSectionRef, hotelSectionRef } = refs;

  if (!state) {
    return null;
  }

  return (
    <div className="space-y-5">
      <OutboundFlightSection
        state={state}
        isRoundTrip={isRoundTrip}
        currencyCode={currencyCode}
        selection={selection}
        setSelection={setSelection}
        outboundSectionRef={outboundSectionRef}
      />
      {isRoundTrip ? (
        <ReturnFlightSection
          selection={selection}
          returnOptionsLoading={returnOptionsLoading}
          returnOptions={returnOptions}
          selectedReturnIndex={selectedReturnIndex}
          setSelectedReturnIndex={setSelectedReturnIndex}
          currencyCode={currencyCode}
          returnSectionRef={returnSectionRef}
        />
      ) : null}
      <HotelSelectionSection
        state={state}
        isRoundTrip={isRoundTrip}
        currencyCode={currencyCode}
        selection={selection}
        setSelection={setSelection}
        returnOptionsLoading={returnOptionsLoading}
        hotelSectionRef={hotelSectionRef}
      />
    </div>
  );
}
