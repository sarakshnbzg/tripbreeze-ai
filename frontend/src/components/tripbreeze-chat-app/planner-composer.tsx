import { AudioLines, LoaderCircle, Plus, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { resetPlannerFormForFreshFreeText, type PlannerForm } from "@/lib/planner";

import { HotelStarTierPicker } from "./controls";
import { CURRENCIES, PLANNER_PROMPT_CHIPS, TRAVEL_CLASSES } from "./constants";
import { compressStarPreferences, expandStarThresholds } from "./helpers";
import type { PlannerLoadingState } from "./ui-types";

type PlannerComposerProps = {
  form: PlannerForm;
  setForm: React.Dispatch<React.SetStateAction<PlannerForm>>;
  showComposer: boolean;
  loading: PlannerLoadingState;
  recording: boolean;
  error: string;
  username: string;
  onPlanTrip: () => void;
  onVoiceInput: () => void;
};

function buildActiveAdvancedFilters(form: PlannerForm): string[] {
  return [
    form.multiCity ? "Multi-city" : null,
    form.oneWay ? (form.multiCity ? "Open-jaw" : "One-way") : null,
    form.directOnly ? "Direct only" : null,
    form.maxFlightDurationHours > 0 ? `Under ${form.maxFlightDurationHours}h` : null,
    form.includeAirlines.trim() ? "Included airlines" : null,
    form.excludeAirlines.trim() ? "Excluded airlines" : null,
    form.hotelStars.length ? "Hotel stars" : null,
  ].filter((value): value is string => Boolean(value));
}

function PromptChipList({
  onSelect,
}: {
  onSelect: (chip: string) => void;
}) {
  return (
    <div className="mt-4">
      <div className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate/60">Examples</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:flex xl:flex-wrap">
        {PLANNER_PROMPT_CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            onClick={() => onSelect(chip)}
            className="rounded-full border border-white/80 bg-white/80 px-4 py-2 text-sm text-slate transition hover:border-coral/35 hover:text-ink"
          >
            {chip}
          </button>
        ))}
      </div>
    </div>
  );
}

function AdvancedFiltersSummary({
  activeFilters,
}: {
  activeFilters: string[];
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="text-sm font-semibold text-ink">Advanced trip filters</div>
        <div className="mt-1 text-sm text-slate">
          Airline, timing, hotel, or multi-city options.
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        {activeFilters.length ? (
          activeFilters.map((filter) => (
            <span key={filter} className="rounded-full border border-coral/20 bg-coral/10 px-3 py-1 text-xs font-semibold text-coral">
              {filter}
            </span>
          ))
        ) : (
          <span className="rounded-full border border-line/70 bg-white px-3 py-1 text-xs font-semibold text-slate">
            Optional
          </span>
        )}
      </div>
    </div>
  );
}

export function PlannerComposer({
  form,
  setForm,
  showComposer,
  loading,
  recording,
  error,
  username,
  onPlanTrip,
  onVoiceInput,
}: PlannerComposerProps) {
  if (!showComposer) {
    return null;
  }

  const updateStructuredForm = (
    updater: (current: PlannerForm) => PlannerForm,
  ) => {
    setForm((current) => ({
      ...updater(current),
      hasEditedStructuredInputs: true,
    }));
  };

  const activeAdvancedFilters = buildActiveAdvancedFilters(form);

  return (
    <div className="relative mt-6 overflow-hidden rounded-[1.8rem] border border-line/70 bg-white/72 p-5 shadow-card sm:p-6">
      <div className="planner-watermark" aria-hidden="true" />
      <div>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="eyebrow-label">Plan a trip</div>
            <h3 className="mt-2 font-display text-3xl text-ink">
              {username ? `Where to next, ${username}?` : "Start with the trip brief"}
            </h3>
          </div>
        </div>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-slate">
          Describe your trip, or use the filters below.
        </p>
        <textarea
          className="mt-4 h-36 w-full rounded-[1.8rem] border border-line/80 bg-white px-5 py-4 text-sm leading-7 outline-none transition focus:border-coral focus:shadow-[0_0_0_4px_rgba(215,108,78,0.12)]"
          placeholder="Describe your trip..."
          value={form.freeText}
          onChange={(event) =>
            setForm((current) => resetPlannerFormForFreshFreeText(current, event.target.value))
          }
        />
        <PromptChipList
          onSelect={(chip) =>
            setForm((current) => resetPlannerFormForFreshFreeText(current, chip))
          }
        />
      </div>

      <details className="mt-5 rounded-[1.6rem] border border-line/70 bg-paper/70 p-4">
        <summary className="cursor-pointer list-none">
          <AdvancedFiltersSummary activeFilters={activeAdvancedFilters} />
        </summary>
        <div className="mt-4 space-y-4">
          <div className="rounded-[1.4rem] border border-line/60 bg-white/72 p-4">
            <div className="eyebrow-label">Optional Trip Details</div>
            <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">From</span>
                <input
                  list="cities"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.origin}
                  onChange={(event) => updateStructuredForm((current) => ({ ...current, origin: event.target.value }))}
                />
              </label>
              {!form.multiCity ? (
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">To</span>
                  <input
                    list="cities"
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={form.destination}
                    onChange={(event) => updateStructuredForm((current) => ({ ...current, destination: event.target.value }))}
                  />
                </label>
              ) : null}
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">Departure</span>
                <input
                  type="date"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.departureDate}
                  onChange={(event) => updateStructuredForm((current) => ({ ...current, departureDate: event.target.value }))}
                />
              </label>
              {!form.multiCity ? form.oneWay ? (
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">Nights</span>
                  <input
                    type="number"
                    min={1}
                    max={30}
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={form.numNights}
                    onChange={(event) => updateStructuredForm((current) => ({ ...current, numNights: Number(event.target.value || 7) }))}
                  />
                </label>
              ) : (
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">Return</span>
                  <input
                    type="date"
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={form.returnDate}
                    onChange={(event) => updateStructuredForm((current) => ({ ...current, returnDate: event.target.value }))}
                  />
                </label>
              ) : null}
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">Travelers</span>
                <input
                  type="number"
                  min={1}
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.travelers}
                  onChange={(event) => updateStructuredForm((current) => ({ ...current, travelers: Number(event.target.value || 1) }))}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">Budget</span>
                <input
                  type="number"
                  min={0}
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.budgetLimit}
                  onChange={(event) => updateStructuredForm((current) => ({ ...current, budgetLimit: Number(event.target.value || 0) }))}
                />
              </label>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <label className="inline-flex items-center gap-2 rounded-full border border-ink/8 bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.multiCity}
                onChange={(event) =>
                  updateStructuredForm((current) => ({
                    ...current,
                    multiCity: event.target.checked,
                    destination: event.target.checked ? "" : current.destination,
                    returnDate: event.target.checked ? "" : current.returnDate,
                  }))
                }
              />
              Multi-city trip
            </label>
            <label className="inline-flex items-center gap-2 rounded-full border border-ink/8 bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.oneWay}
                onChange={(event) =>
                  updateStructuredForm((current) => ({
                    ...current,
                    oneWay: event.target.checked,
                    returnDate: !current.multiCity && event.target.checked ? "" : current.returnDate,
                  }))
                }
              />
              {form.multiCity ? "Open-jaw trip" : "One-way trip"}
            </label>
            <label className="inline-flex items-center gap-2 rounded-full border border-ink/8 bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.directOnly}
                onChange={(event) => updateStructuredForm((current) => ({ ...current, directOnly: event.target.checked }))}
              />
              Direct flights only
            </label>
          </div>

          {form.multiCity ? (
            <div className="space-y-3">
              <div className="rounded-2xl bg-mist/60 px-4 py-3 text-sm text-slate">
                Add destinations in order. Return date auto-calculated.
              </div>
              {form.multiCityLegs.map((leg, index) => (
                <div
                  key={`multi-city-leg-${index}`}
                  className="grid items-end gap-3 md:grid-cols-[minmax(0,1fr)_160px_56px]"
                >
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Destination {index + 1}</span>
                    <input
                      list="cities"
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={leg.destination}
                      onChange={(event) =>
                        updateStructuredForm((current) => ({
                          ...current,
                          multiCityLegs: current.multiCityLegs.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, destination: event.target.value } : item,
                          ),
                        }))
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Nights</span>
                    <input
                      type="number"
                      min={1}
                      max={30}
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={leg.nights}
                      onChange={(event) =>
                        updateStructuredForm((current) => ({
                          ...current,
                          multiCityLegs: current.multiCityLegs.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, nights: Number(event.target.value || 1) } : item,
                          ),
                        }))
                      }
                    />
                  </label>
                  <button
                  type="button"
                  onClick={() =>
                      updateStructuredForm((current) => ({
                        ...current,
                        multiCityLegs:
                          current.multiCityLegs.length > 1
                            ? current.multiCityLegs.filter((_, itemIndex) => itemIndex !== index)
                            : current.multiCityLegs,
                      }))
                    }
                    className="inline-flex h-[52px] items-center justify-center rounded-full border border-ink/10 bg-white text-slate transition hover:border-coral hover:text-coral disabled:cursor-not-allowed disabled:opacity-40"
                    disabled={form.multiCityLegs.length === 1}
                    aria-label={`Remove destination ${index + 1}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  updateStructuredForm((current) => ({
                    ...current,
                    multiCityLegs:
                      current.multiCityLegs.length >= 5
                        ? current.multiCityLegs
                        : [...current.multiCityLegs, { destination: "", nights: 3 }],
                  }))
                }
                disabled={form.multiCityLegs.length >= 5}
              >
                <Plus className="mr-2 h-4 w-4" />
                Add another destination
              </Button>
            </div>
          ) : null}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            <label className="block">
              <span className="mb-2 flex min-h-[3rem] items-end text-sm font-medium text-slate">Currency</span>
              <select
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.currency}
                onChange={(event) => updateStructuredForm((current) => ({ ...current, currency: event.target.value }))}
              >
                {CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 flex min-h-[3rem] items-end text-sm font-medium text-slate">Max Flight Duration (hours)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.maxFlightDurationHours}
                onChange={(event) =>
                  updateStructuredForm((current) => ({ ...current, maxFlightDurationHours: Number(event.target.value || 0) }))
                }
              />
            </label>
            <label className="block">
              <span className="mb-2 flex min-h-[3rem] items-end text-sm font-medium text-slate">Travel Class</span>
              <select
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.travelClass}
                onChange={(event) => updateStructuredForm((current) => ({ ...current, travelClass: event.target.value }))}
              >
                {TRAVEL_CLASSES.map((travelClass) => (
                  <option key={travelClass} value={travelClass}>
                    {travelClass.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Special Requests (optional)</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              value={form.preferences}
              onChange={(event) => updateStructuredForm((current) => ({ ...current, preferences: event.target.value }))}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Exclude Airlines</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              placeholder="e.g. Ryanair, easyJet"
              value={form.excludeAirlines}
              onChange={(event) => updateStructuredForm((current) => ({ ...current, excludeAirlines: event.target.value }))}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Include Airlines</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              placeholder="e.g. Lufthansa, Air France"
              value={form.includeAirlines}
              onChange={(event) => updateStructuredForm((current) => ({ ...current, includeAirlines: event.target.value }))}
            />
          </label>

          <HotelStarTierPicker
            label="Hotel Stars"
            helper="Pick one or more tiers, or leave on Any."
            thresholds={compressStarPreferences(form.hotelStars)}
            onChange={(thresholds) =>
              updateStructuredForm((current) => ({
                ...current,
                hotelStars: expandStarThresholds(thresholds),
              }))
            }
          />
        </div>
      </details>

      <div className="mt-5 flex flex-col gap-4 rounded-[1.5rem] border border-line/70 bg-paper/66 p-4 lg:gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div className="min-w-0 xl:max-w-[42rem]">
          <div className="text-sm font-semibold text-ink">Run planner</div>
          <div className="mt-1 text-sm leading-7 text-slate">
            Searches flights, hotels, and entry requirements.
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 xl:flex xl:flex-nowrap xl:shrink-0">
          <Button
            onClick={onPlanTrip}
            disabled={loading !== null}
            className="min-w-[9.5rem] justify-center whitespace-nowrap px-5 py-2.5"
          >
          {loading === "planning" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          Search Trip
          </Button>
          <Button
            variant="secondary"
            onClick={onVoiceInput}
            disabled={loading === "voice"}
            className="min-w-[8.5rem] justify-center whitespace-nowrap px-4 py-2.5"
          >
            {loading === "voice" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <AudioLines className="mr-2 h-4 w-4" />}
            {recording ? "Stop Recording" : "Voice Input"}
          </Button>
        </div>
      </div>

      {error ? <p className="mt-4 text-sm text-coral">{error}</p> : null}
    </div>
  );
}
