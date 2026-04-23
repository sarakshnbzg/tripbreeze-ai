import { LoaderCircle } from "lucide-react";

import type { SelectionState } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

import { ReviewOptionCard } from "./controls";
import type { ReviewWorkspaceActions, ReviewWorkspaceModel, ReviewWorkspaceRefs } from "./workspace-types";

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
    <div ref={outboundSectionRef} className="space-y-3">
      <div className="text-sm font-semibold text-slate">Flights {isRoundTrip ? "(choose outbound)" : ""}</div>
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
    <div ref={returnSectionRef} className="space-y-3">
      <div className="text-sm font-semibold text-slate">Return Flights</div>
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
      <div ref={hotelSectionRef} className="space-y-3">
        <div className="text-sm font-semibold text-slate">Hotels</div>
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
    );
  }

  return (
    <div ref={hotelSectionRef} className="space-y-3">
      <div className="text-sm font-semibold text-slate">Hotels</div>
      <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
        Select a flight first to review hotel options.
      </div>
    </div>
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
