import dynamic from "next/dynamic";
import { LoaderCircle, Mail, Plane } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatCurrency, selectedOption, type SelectionState } from "@/lib/planner";
import type { ApproveRequest, TravelState, TripOption } from "@/lib/types";
import type { ItineraryViewModel } from "./view-models";

import { ReviewOptionCard } from "./controls";
import { INTEREST_OPTIONS, PACE_OPTIONS } from "./constants";
import {
  budgetFlightDetail,
  budgetHotelDetail,
  budgetStatusNote,
  combineRoundTripFlight,
  optionTotalPrice,
  readRecord,
  readRecordArray,
  readString,
  renderMarkdownContent,
  selectionLabel,
  sentenceLabel,
  transportLabel,
} from "./helpers";

const ItineraryMap = dynamic(() => import("./itinerary-map"), { ssr: false });

export type WorkspaceLoadingState =
  | "auth"
  | "planning"
  | "clarifying"
  | "approving"
  | "saving"
  | "voice"
  | "pdf"
  | "email"
  | null;

export type ReviewWorkspaceModel = {
  hasReviewWorkspace: boolean;
  finalItinerary: string;
  state: TravelState | null;
  isRoundTrip: boolean;
  completedMultiCityLegs: number;
  hasSelectedSingleFlight: boolean;
  hasSelectedSingleHotel: boolean;
  selectedOutboundOption: Record<string, unknown>;
  selectedReturnIndex: number | null;
  selectedReturnOption: Record<string, unknown>;
  selectedHotelOption: Record<string, unknown>;
  hasOptionResults: boolean;
  currencyCode: string;
  selection: SelectionState;
  returnOptions: TripOption[];
  showPersonalisationPanel: boolean;
  selectedTransportIndex: number | null;
  canApprove: boolean;
  returnOptionsLoading: boolean;
  interests: string[];
  pace: (typeof PACE_OPTIONS)[number];
  feedback: string;
  loading: WorkspaceLoadingState;
};

export type ReviewWorkspaceActions = {
  setSelectedReturnIndex: React.Dispatch<React.SetStateAction<number | null>>;
  setSelection: React.Dispatch<React.SetStateAction<SelectionState>>;
  setSelectedTransportIndex: React.Dispatch<React.SetStateAction<number | null>>;
  setInterests: React.Dispatch<React.SetStateAction<string[]>>;
  setPace: React.Dispatch<React.SetStateAction<(typeof PACE_OPTIONS)[number]>>;
  setFeedback: React.Dispatch<React.SetStateAction<string>>;
  handleReview: (feedbackType: ApproveRequest["feedback_type"]) => Promise<void>;
};

export type ReviewWorkspaceRefs = {
  outboundSectionRef: React.RefObject<HTMLDivElement | null>;
  returnSectionRef: React.RefObject<HTMLDivElement | null>;
  hotelSectionRef: React.RefObject<HTMLDivElement | null>;
  personaliseSectionRef: React.RefObject<HTMLDivElement | null>;
};

export function ReviewPanel({
  model,
  actions,
  refs,
}: {
  model: ReviewWorkspaceModel;
  actions: ReviewWorkspaceActions;
  refs: ReviewWorkspaceRefs;
}) {
  const {
    hasReviewWorkspace,
    finalItinerary,
    state,
    isRoundTrip,
    completedMultiCityLegs,
    hasSelectedSingleFlight,
    hasSelectedSingleHotel,
    selectedOutboundOption,
    selectedReturnIndex,
    selectedReturnOption,
    selectedHotelOption,
    hasOptionResults,
    currencyCode,
    selection,
    returnOptions,
    showPersonalisationPanel,
    selectedTransportIndex,
    canApprove,
    returnOptionsLoading,
    interests,
    pace,
    feedback,
    loading,
  } = model;
  const {
    setSelectedReturnIndex,
    setSelection,
    setSelectedTransportIndex,
    setInterests,
    setPace,
    setFeedback,
    handleReview,
  } = actions;
  const {
    outboundSectionRef,
    returnSectionRef,
    hotelSectionRef,
    personaliseSectionRef,
  } = refs;

  if (!hasReviewWorkspace || finalItinerary || !state) {
    return null;
  }

  return (
    <>
      {state.destination_info ? (
        <div className="rounded-[1.75rem] border border-ink/10 bg-white/80 p-5">
          <div className="mb-3 text-lg font-semibold text-ink">Destination briefing</div>
          <div className="text-sm leading-7 text-ink">
            {renderMarkdownContent(String(state.destination_info)) ?? String(state.destination_info)}
          </div>
        </div>
      ) : null}

      <div className="rounded-[1.9rem] border border-ink/10 bg-gradient-to-b from-white to-[#fbf8f3] p-5 shadow-[0_20px_50px_rgba(16,33,43,0.08)]">
        <div className="mb-5 flex items-center gap-2 text-lg font-semibold text-ink">
          <Plane className="h-5 w-5 text-coral" />
          Review your trip
        </div>
        <div className="mb-5 flex flex-wrap gap-2">
          {(state.trip_legs?.length
            ? ["1. Select flights", "2. Select hotels", "3. Personalise itinerary"]
            : isRoundTrip
              ? ["1. Select outbound flight", "2. Select return flight", "3. Select hotel", "4. Personalise itinerary"]
              : ["1. Select flight", "2. Select hotel", "3. Personalise itinerary"]
          ).map((step) => (
            <div key={step} className="rounded-full border border-ink/10 bg-white/75 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate sm:text-xs sm:tracking-[0.14em]">
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
            {isRoundTrip ? ` • ${selectedReturnIndex !== null ? selectionLabel(selectedReturnOption, "Return selected") : "No return yet"}` : ""}
            {` • ${hasSelectedSingleHotel ? selectionLabel(selectedHotelOption, "Hotel selected") : "No hotel yet"}`}
          </div>
        )}

        {hasOptionResults ? (
          state.trip_legs?.length ? (
            <div className="space-y-5">
              {state.trip_legs.map((leg, legIndex) => (
                <div key={`leg-${legIndex}`} className="rounded-[1.75rem] bg-mist/45 p-4 ring-1 ring-white/80">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                    <div className="text-sm font-semibold text-ink">
                      Leg {legIndex + 1}: {String(leg.origin ?? "?")} to {String(leg.destination ?? "?")}
                      {Number(leg.nights ?? 0) > 0 ? ` (${Number(leg.nights)} night${Number(leg.nights) === 1 ? "" : "s"})` : " (Return)"}
                    </div>
                    <div className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${
                      typeof selection.byLegFlights[legIndex] === "number" &&
                      selection.byLegFlights[legIndex] >= 0 &&
                      (!leg.needs_hotel || (typeof selection.byLegHotels[legIndex] === "number" && selection.byLegHotels[legIndex] >= 0))
                        ? "bg-green-50 text-green-800"
                        : "bg-white/80 text-slate"
                    }`}>
                      {typeof selection.byLegFlights[legIndex] === "number" &&
                      selection.byLegFlights[legIndex] >= 0 &&
                      (!leg.needs_hotel || (typeof selection.byLegHotels[legIndex] === "number" && selection.byLegHotels[legIndex] >= 0))
                        ? "Complete"
                        : "Needs choices"}
                    </div>
                  </div>
                  <div className="mb-4 text-sm text-slate">Departure: {String(leg.departure_date ?? "?")}</div>
                  <div className="grid gap-4 xl:grid-cols-2">
                    <div className="space-y-3">
                      <div className="text-sm font-semibold text-slate">Flights</div>
                      {(state.flight_options_by_leg?.[legIndex] ?? []).length ? (
                        (state.flight_options_by_leg?.[legIndex] ?? []).slice(0, 5).map((option, optionIndex) => (
                          <ReviewOptionCard
                            key={`flight-${legIndex}-${optionIndex}`}
                            option={option}
                            title={`Flight ${optionIndex + 1}`}
                            variant="flight"
                            allOptions={state.flight_options_by_leg?.[legIndex] ?? []}
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
                        typeof selection.byLegFlights[legIndex] !== "number" || selection.byLegFlights[legIndex] < 0 ? (
                          <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-slate">
                            Select a flight for this leg before choosing a hotel.
                          </div>
                        ) : (
                          (state.hotel_options_by_leg?.[legIndex] ?? []).length ? (
                            (state.hotel_options_by_leg?.[legIndex] ?? []).slice(0, 5).map((option, optionIndex) => (
                              <ReviewOptionCard
                                key={`hotel-${legIndex}-${optionIndex}`}
                                option={option}
                                title={`Hotel ${optionIndex + 1}`}
                                variant="hotel"
                                allOptions={state.hotel_options_by_leg?.[legIndex] ?? []}
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
                        )
                      ) : (
                        <div className="rounded-[1.5rem] bg-white/70 p-4 text-sm text-slate">No hotel needed for this leg (return flight).</div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-5">
              <div ref={outboundSectionRef} className="space-y-3">
                <div className="text-sm font-semibold text-slate">
                  Flights {isRoundTrip ? "(choose outbound)" : ""}
                </div>
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

              {isRoundTrip ? (
                <div ref={returnSectionRef} className="space-y-3">
                  <div className="text-sm font-semibold text-slate">Return Flights</div>
                  {selection.flightIndex >= 0 ? (
                    returnOptionsLoading ? (
                      <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
                        <div className="flex items-center gap-2 font-semibold text-ink">
                          <LoaderCircle className="h-4 w-4 animate-spin text-coral" />
                          Loading return flights...
                        </div>
                        <div className="mt-2">
                          We’re finding matching return options for the outbound flight you selected.
                        </div>
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
              ) : null}

              {selection.flightIndex >= 0 ? (
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
              ) : (
                <div ref={hotelSectionRef} className="space-y-3">
                  <div className="text-sm font-semibold text-slate">Hotels</div>
                  <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-slate">
                    Select a flight first to review hotel options.
                  </div>
                </div>
              )}

              {Array.isArray(state.transport_options) && state.transport_options.length > 0 ? (
                <div className="space-y-3">
                  <div className="text-sm font-semibold text-slate">Ground transport (optional)</div>
                  <div className="text-xs text-slate">
                    Compare ground options alongside flights. Tap to select, tap again to clear.
                  </div>
                  {state.transport_options.slice(0, 5).map((option, index) => (
                    <ReviewOptionCard
                      key={`transport-${index}`}
                      option={option}
                      title={`Transport ${index + 1}`}
                      variant="transport"
                      allOptions={state.transport_options ?? []}
                      currencyCode={currencyCode}
                      selected={selectedTransportIndex === index}
                      onSelect={() =>
                        setSelectedTransportIndex(selectedTransportIndex === index ? null : index)
                      }
                    />
                  ))}
                </div>
              ) : null}
            </div>
          )
        ) : (
          <div className="rounded-[1.6rem] border border-dashed border-ink/15 bg-white/75 p-5 text-sm text-slate">
            <div className="font-semibold text-ink">No bookable options are ready yet</div>
            <div className="mt-2 leading-7">
              The planner finished this search without flight or hotel results you can choose from here.
            </div>
          </div>
        )}

        {showPersonalisationPanel ? (
          <div ref={personaliseSectionRef} className="mt-5 rounded-[1.8rem] border border-ink/10 bg-gradient-to-br from-mist/90 to-white p-5">
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
                        setInterests((current: string[]) => (
                          active ? current.filter((value: string) => value !== interest) : [...current, interest]
                        ))
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
        ) : null}

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
      </div>
    </>
  );
}

export function FinalItineraryPanel({
  viewModel,
  shareState,
}: {
  viewModel: ItineraryViewModel;
  shareState: {
    loading: WorkspaceLoadingState;
    emailAddress: string;
    setEmailAddress: React.Dispatch<React.SetStateAction<string>>;
    onDownloadPdf: () => Promise<void>;
    onEmailItinerary: () => Promise<void>;
  };
}) {
  const {
    finalItinerary,
    snapshotItems: itinerarySnapshotItems,
    bookingLinks: itineraryBookingLinks,
    primarySections: primaryItinerarySections,
    secondarySections: secondaryItinerarySections,
    mapPoints,
    itineraryLegs,
    itineraryDays,
  } = viewModel;
  const {
    loading,
    emailAddress,
    setEmailAddress,
    onDownloadPdf,
    onEmailItinerary,
  } = shareState;

  if (!finalItinerary) {
    return null;
  }

  return (
    <div className="rounded-[1.9rem] border border-ink/10 bg-gradient-to-br from-[#fffaf4] via-white to-[#f6f1ea] p-5 shadow-[0_24px_60px_rgba(16,33,43,0.08)]">
      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-lg font-semibold text-ink">Final itinerary</div>
          <div className="text-sm text-slate">Your approved trip plan is ready to read, download, or email.</div>
        </div>
        <div className="rounded-[1.5rem] border border-ink/10 bg-white/85 p-4 xl:min-w-[24rem]">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Save or share</div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={() => void onDownloadPdf()} disabled={loading !== null}>
              {loading === "pdf" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
              Download PDF
            </Button>
            <div className="flex flex-1 flex-wrap gap-3">
              <input
                type="email"
                placeholder="your.email@example.com"
                className="min-w-[220px] flex-1 rounded-full border border-ink/10 bg-mist/60 px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={emailAddress}
                onChange={(event) => setEmailAddress(event.target.value)}
              />
              <Button onClick={() => void onEmailItinerary()} disabled={loading !== null}>
                {loading === "email" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
                Email itinerary
              </Button>
            </div>
          </div>
        </div>
      </div>

      <div className="mb-4 rounded-[1.6rem] border border-white/80 bg-white/85 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
        <div className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip snapshot</div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {itinerarySnapshotItems.map((item) => (
            <div key={item.label} className="rounded-[1.3rem] border border-ink/10 bg-[#fffdf9] p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate">{item.label}</div>
              <div className="mt-2 text-sm font-semibold leading-6 text-ink">{item.value}</div>
            </div>
          ))}
        </div>
        {itineraryBookingLinks.length ? (
          <div className="mt-4 border-t border-ink/8 pt-4">
            <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-slate">Booking links</div>
            <div className="flex flex-wrap gap-2">
              {itineraryBookingLinks.map((link) => (
                <a
                  key={`${link.label}-${link.url}`}
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-coral/25 bg-coral/10 px-3 py-2 text-xs font-semibold text-coral transition hover:bg-coral/15"
                >
                  {link.label}
                </a>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {primaryItinerarySections.length ? (
        <div className="mb-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip logistics</div>
          <div className="grid gap-4 xl:grid-cols-2">
            {primaryItinerarySections.map((section) => (
              <div key={section.key} className="rounded-[1.6rem] border border-white/80 bg-white/80 p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">{section.title}</div>
                <div className="mt-2 text-sm leading-7 text-ink">{renderMarkdownContent(section.content) ?? section.content}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {secondaryItinerarySections.length ? (
        <div className="mb-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip extras</div>
          <div className="grid gap-4 xl:grid-cols-2">
            {secondaryItinerarySections.map((section) => (
              <div key={section.key} className="rounded-[1.6rem] border border-white/80 bg-white/80 p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">{section.title}</div>
                <div className="mt-2 text-sm leading-7 text-ink">{renderMarkdownContent(section.content) ?? section.content}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {mapPoints.length ? (
        <div className="mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip map</div>
            <div className="text-xs text-slate">{mapPoints.length} stop{mapPoints.length === 1 ? "" : "s"}</div>
          </div>
          <ItineraryMap points={mapPoints} />
        </div>
      ) : null}

      {itineraryLegs.length ? (
        <div className="mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip legs</div>
          <div className="grid gap-3 lg:grid-cols-2">
            {itineraryLegs.map((leg, index) => (
              <div key={`itinerary-leg-${index}`} className="rounded-[1.3rem] border border-ink/10 bg-[#fffaf4] p-4 text-sm text-slate">
                <div className="font-semibold text-ink">
                  Leg {Number(leg.leg_number ?? index + 1)}: {readString(leg.origin)} to {readString(leg.destination)}
                </div>
                {readString(leg.departure_date) ? <div className="mt-1">{readString(leg.departure_date)}</div> : null}
                {readString(leg.flight_summary) ? <div className="mt-2">{readString(leg.flight_summary)}</div> : null}
                {readString(leg.hotel_summary) ? <div className="mt-2">{readString(leg.hotel_summary)}</div> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {itineraryDays.length ? (
        <div className="mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Day-by-day plan</div>
            <div className="text-xs text-slate">{itineraryDays.length} day{itineraryDays.length === 1 ? "" : "s"}</div>
          </div>
          <div className="space-y-4">
            {itineraryDays.map((day, index) => {
              const activities = readRecordArray(day.activities);
              const weather = readRecord(day.weather);
              return (
                <div key={`itinerary-day-${index}`} className="rounded-[1.4rem] border border-ink/10 bg-[#fffdf9] p-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <div className="font-semibold text-ink">
                        Day {Number(day.day_number ?? index + 1)}
                        {readString(day.theme) ? ` · ${readString(day.theme)}` : ""}
                      </div>
                      {readString(day.date) ? <div className="mt-1 text-sm text-slate">{readString(day.date)}</div> : null}
                    </div>
                    {Object.keys(weather).length ? (
                      <div className="rounded-full bg-mist px-3 py-2 text-xs font-semibold text-ink">
                        {readString(weather.condition)}
                        {weather.temp_min !== undefined && weather.temp_max !== undefined
                          ? ` · ${weather.temp_min}° to ${weather.temp_max}°`
                          : ""}
                      </div>
                    ) : null}
                  </div>
                  {activities.length ? (
                    <div className="mt-4 grid gap-3 lg:grid-cols-2">
                      {activities.map((activity, activityIndex) => (
                        <div key={`activity-${index}-${activityIndex}`} className="rounded-[1.2rem] bg-white p-3 text-sm text-slate ring-1 ring-ink/8">
                          <div className="flex items-center justify-between gap-3">
                            <div className="font-semibold text-ink">{readString(activity.name) || `Activity ${activityIndex + 1}`}</div>
                            {readString(activity.time_of_day) ? (
                              <div className="rounded-full bg-mist px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">
                                {readString(activity.time_of_day)}
                              </div>
                            ) : null}
                          </div>
                          {readString(activity.notes) ? <div className="mt-2 leading-6">{readString(activity.notes)}</div> : null}
                          {readString(activity.address) ? <div className="mt-2 text-xs text-slate">{readString(activity.address)}</div> : null}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="mt-3 text-sm text-slate">No activities listed for this day.</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}
