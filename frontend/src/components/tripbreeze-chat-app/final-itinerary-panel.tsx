import dynamic from "next/dynamic";
import { LoaderCircle, Mail } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatCurrency } from "@/lib/planner";

import {
  readRecord,
  readRecordArray,
  readString,
  renderMarkdownContent,
} from "./helpers";
import { SourceTrustCard } from "./source-trust";
import type { BudgetBreakdownData } from "./view-models";
import type { FinalItineraryPanelProps } from "./workspace-types";

const ItineraryMap = dynamic(() => import("./itinerary-map"), { ssr: false });

export function FinalItineraryPanel({
  viewModel,
  shareState,
}: FinalItineraryPanelProps) {
  const {
    finalItinerary,
    hasStructuredItinerary,
    fallbackNotice,
    snapshotItems: itinerarySnapshotItems,
    bookingLinks: itineraryBookingLinks,
    primarySections: primaryItinerarySections,
    secondarySections: secondaryItinerarySections,
    visaTrust,
    visaBriefings,
    mapPoints,
    itineraryLegs,
    itineraryDays,
    budgetBreakdown,
  } = viewModel;
  const {
    loading,
    emailAddress,
    shareMessage,
    setEmailAddress,
    onDownloadPdf,
    onEmailItinerary,
  } = shareState;

  if (!finalItinerary) {
    return null;
  }

  if (!hasStructuredItinerary) {
    return (
      <div className="animate-fade-up rounded-[1.9rem] border border-ink/10 bg-gradient-to-br from-[#fffaf4] via-white to-[#f6f1ea] p-5 shadow-[0_24px_60px_rgba(16,33,43,0.08)]">
        <div className="rounded-[1.6rem] border border-white/80 bg-white/85 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)]">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="flex items-center gap-2 text-lg font-semibold text-ink">
                <LoaderCircle className="h-5 w-5 animate-spin text-coral" />
                Generating final itinerary...
              </div>
              <div className="mt-1 text-sm text-slate">
                We&apos;re streaming your itinerary now and will switch to the full structured view as soon as it&apos;s ready.
              </div>
            </div>
            <div className="rounded-full border border-coral/20 bg-coral/10 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-coral">
              Draft streaming
            </div>
          </div>

          <div className="mt-5 rounded-[1.4rem] border border-ink/10 bg-[#fffdf9] p-4">
            <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Live draft</div>
            <div className="text-sm leading-7 text-ink">
              {renderMarkdownContent(finalItinerary) ?? finalItinerary}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="animate-fade-up rounded-[1.9rem] border border-ink/10 bg-gradient-to-br from-[#fffaf4] via-white to-[#f6f1ea] p-4 shadow-[0_24px_60px_rgba(16,33,43,0.08)] sm:p-5">
      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-lg font-semibold text-ink">Final itinerary</div>
          <div className="text-sm text-slate">Your approved trip plan is ready to read, download, or email.</div>
        </div>
        <div className="rounded-[1.5rem] border border-line/70 bg-white/88 p-4 xl:min-w-[24rem]">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Save or share</div>
          <div className="flex flex-wrap gap-3">
            <Button variant="secondary" onClick={() => void onDownloadPdf()} disabled={loading !== null} className="w-full justify-center sm:w-auto">
              {loading === "pdf" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
              Download PDF
            </Button>
            <div className="flex flex-1 flex-wrap gap-3">
              <input
                type="email"
                placeholder="your.email@example.com"
                className="min-w-0 flex-1 rounded-full border border-ink/10 bg-mist/60 px-4 py-3 text-sm outline-none transition focus:border-coral sm:min-w-[220px]"
                value={emailAddress}
                onChange={(event) => setEmailAddress(event.target.value)}
              />
              <Button onClick={() => void onEmailItinerary()} disabled={loading !== null} className="w-full justify-center sm:w-auto">
                {loading === "email" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Mail className="mr-2 h-4 w-4" />}
                Email itinerary
              </Button>
            </div>
          </div>
          {shareMessage ? (
            <div className="mt-3 rounded-[1.1rem] border border-pine/20 bg-pine/8 px-4 py-3 text-sm text-pine">
              {shareMessage}
            </div>
          ) : null}
        </div>
      </div>

      {fallbackNotice ? (
        <div className="mb-4 rounded-[1.6rem] border border-amber-200 bg-amber-50/85 p-4 text-sm text-amber-950">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-800">{fallbackNotice.title}</div>
          <div className="mt-2 leading-7">{fallbackNotice.detail}</div>
        </div>
      ) : null}

      <div className="animate-fade-up stagger-1 mb-4 rounded-[1.6rem] border border-white/80 bg-white/85 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] sm:p-5">
        <div className="mb-4 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip snapshot</div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {itinerarySnapshotItems.map((item) => (
            <div key={item.label} className="lift-card rounded-[1.3rem] border border-ink/10 bg-[#fffdf9] p-3 sm:p-4">
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
        <div className="animate-fade-up stagger-2 mb-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip logistics</div>
          <div className="grid gap-4 xl:grid-cols-2">
            {primaryItinerarySections.map((section) => (
              <div key={section.key} className="lift-card rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">{section.title}</div>
                <div className="mt-2 text-sm leading-7 text-ink">{renderMarkdownContent(section.content) ?? section.content}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {budgetBreakdown ? (
        <div className="animate-fade-up stagger-2 mb-4">
          <BudgetBreakdownCard data={budgetBreakdown} />
        </div>
      ) : null}

      {visaTrust ? (
        <div className="animate-fade-up stagger-2 mb-4">
          <SourceTrustCard trust={visaTrust} />
        </div>
      ) : null}

      {visaBriefings.length ? (
        <div className="animate-fade-up stagger-2 mb-4">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Visa and entry</div>
          <div className="space-y-4">
            {visaBriefings.map((briefing) => (
              <div
                key={briefing.destination}
                className="lift-card rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5"
              >
                <div className="text-base font-semibold text-ink">{briefing.destination}</div>
                <div className="mt-3 text-sm leading-7 text-ink">
                  {renderMarkdownContent(briefing.content) ?? briefing.content}
                </div>
                {briefing.trust ? (
                  <div className="mt-4">
                    <SourceTrustCard trust={briefing.trust} compact />
                  </div>
                ) : null}
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
              <div key={section.key} className="lift-card rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
                <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">{section.title}</div>
                <div className="mt-2 text-sm leading-7 text-ink">{renderMarkdownContent(section.content) ?? section.content}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {mapPoints.length ? (
        <div className="animate-fade-up stagger-3 mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip map</div>
            <div className="text-xs text-slate">{mapPoints.length} stop{mapPoints.length === 1 ? "" : "s"}</div>
          </div>
          <ItineraryMap points={mapPoints} />
        </div>
      ) : null}

      {itineraryLegs.length ? (
        <div className="animate-fade-up stagger-3 mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
          <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Trip legs</div>
          <div className="grid gap-3 lg:grid-cols-2">
            {itineraryLegs.map((leg, index) => (
              <div key={`itinerary-leg-${index}`} className="lift-card rounded-[1.3rem] border border-ink/10 bg-[#fffaf4] p-3 text-sm text-slate sm:p-4">
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
        <div className="animate-fade-up stagger-3 mb-4 rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Day-by-day plan</div>
            <div className="text-xs text-slate">{itineraryDays.length} day{itineraryDays.length === 1 ? "" : "s"}</div>
          </div>
          <div className="space-y-4">
            {itineraryDays.map((day, index) => {
              const activities = readRecordArray(day.activities);
              const weather = readRecord(day.weather);
              return (
                <div key={`itinerary-day-${index}`} className="lift-card rounded-[1.4rem] border border-ink/10 bg-[#fffdf9] p-3 sm:p-4">
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
                        <div key={`activity-${index}-${activityIndex}`} className="lift-card rounded-[1.2rem] bg-white p-3 text-sm text-slate ring-1 ring-ink/8">
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
                          {readString(activity.maps_url) ? (
                            <a
                              href={readString(activity.maps_url)}
                              target="_blank"
                              rel="noreferrer"
                              className="mt-3 inline-flex text-xs font-semibold text-coral underline-offset-2 hover:underline"
                            >
                              Open in Google Maps
                            </a>
                          ) : null}
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

function BudgetBreakdownCard({ data }: { data: BudgetBreakdownData }) {
  const { lineItems, total, budgetLimit, currency, withinBudget, budgetNote, perLeg, fallbackText } = data;

  if (fallbackText) {
    return (
      <div className="lift-card rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Budget breakdown</div>
        <div className="mt-2 text-sm leading-7 text-ink">{renderMarkdownContent(fallbackText) ?? fallbackText}</div>
      </div>
    );
  }

  const pct = budgetLimit > 0 && total > 0 ? Math.min(100, Math.round((total / budgetLimit) * 100)) : null;
  const overBudget = withinBudget === false;

  return (
    <div className="lift-card rounded-[1.6rem] border border-white/80 bg-white/80 p-4 sm:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">Budget breakdown</div>
        {withinBudget !== null ? (
          <div className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] ${overBudget ? "border border-red-200 bg-red-50 text-red-700" : "border border-pine/20 bg-pine/10 text-pine"}`}>
            {overBudget ? "Over budget" : "Within budget"}
          </div>
        ) : null}
      </div>

      <div className="space-y-2">
        {lineItems.map((item) => (
          <div key={item.label} className="flex items-center justify-between rounded-[1rem] bg-mist/50 px-4 py-3">
            <div className="flex items-center gap-2 text-sm text-ink">
              <span>{item.icon}</span>
              <span>{item.label}</span>
            </div>
            <div className="text-sm font-semibold text-ink">{formatCurrency(item.amount, currency)}</div>
          </div>
        ))}

        <div className="flex items-center justify-between rounded-[1rem] border border-ink/10 bg-[#fffaf4] px-4 py-3">
          <div className="text-sm font-semibold text-ink">Total estimate</div>
          <div className="text-base font-bold text-ink">{formatCurrency(total, currency)}</div>
        </div>
      </div>

      {pct !== null ? (
        <div className="mt-4">
          <div className="mb-1 flex items-center justify-between text-[11px] text-slate">
            <span>{formatCurrency(total, currency)} of {formatCurrency(budgetLimit, currency)} budget</span>
            <span>{pct}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-mist">
            <div
              className={`h-full rounded-full transition-all ${overBudget ? "bg-red-400" : "bg-pine"}`}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ) : null}

      {perLeg.length > 0 ? (
        <div className="mt-4 border-t border-ink/8 pt-4">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate">Per leg</div>
          <div className="space-y-2">
            {perLeg.map((leg) => (
              <div key={leg.route} className="rounded-[1rem] bg-mist/40 px-4 py-3 text-sm">
                <div className="mb-1 font-semibold text-ink">{leg.route}{leg.nights > 0 ? ` · ${leg.nights} night${leg.nights === 1 ? "" : "s"}` : ""}</div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-slate">
                  {leg.flightCost > 0 ? <span>✈️ {formatCurrency(leg.flightCost, currency)}</span> : null}
                  {leg.hotelCost > 0 ? <span>🏨 {formatCurrency(leg.hotelCost, currency)}</span> : null}
                  {leg.dailyExpenses > 0 ? <span>🍽️ {formatCurrency(leg.dailyExpenses, currency)}</span> : null}
                  <span className="font-semibold text-ink">= {formatCurrency(leg.legTotal, currency)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {budgetNote ? (
        <div className={`mt-4 rounded-[1.1rem] border px-4 py-3 text-sm leading-6 ${overBudget ? "border-red-200 bg-red-50/60 text-red-800" : "border-pine/20 bg-pine/8 text-pine"}`}>
          {budgetNote}
        </div>
      ) : null}
    </div>
  );
}
