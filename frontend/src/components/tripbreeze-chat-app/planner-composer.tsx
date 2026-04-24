import { AudioLines, LoaderCircle, Plus, Send, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { PlannerForm } from "@/lib/planner";

import { HotelStarTierPicker } from "./controls";
import { CURRENCIES, TRAVEL_CLASSES } from "./constants";
import { compressStarPreferences, expandStarThresholds } from "./helpers";
import type { PlannerLoadingState } from "./ui-types";

export function PlannerComposer({
  form,
  setForm,
  showComposer,
  loading,
  recording,
  error,
  onPlanTrip,
  onVoiceInput,
}: {
  form: PlannerForm;
  setForm: React.Dispatch<React.SetStateAction<PlannerForm>>;
  showComposer: boolean;
  loading: PlannerLoadingState;
  recording: boolean;
  error: string;
  onPlanTrip: () => void;
  onVoiceInput: () => void;
}) {
  if (!showComposer) {
    return null;
  }

  return (
    <div className="mt-6 rounded-[1.9rem] border border-pine/12 bg-[linear-gradient(180deg,rgba(255,250,244,0.96),rgba(244,239,231,0.82))] p-5 shadow-focus">
      <textarea
        className="h-28 w-full rounded-3xl border border-line/80 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral focus:shadow-[0_0_0_4px_rgba(215,108,78,0.12)]"
        placeholder="Describe your trip..."
        value={form.freeText}
        onChange={(event) => setForm((current) => ({ ...current, freeText: event.target.value }))}
      />

      <details className="mt-4 rounded-3xl border border-white/70 bg-white/74 p-4">
        <summary className="cursor-pointer text-sm font-semibold text-ink">Refine your search (optional)</summary>
        <div className="mt-4 space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.multiCity}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    multiCity: event.target.checked,
                    destination: event.target.checked ? "" : current.destination,
                    returnDate: event.target.checked ? "" : current.returnDate,
                  }))
                }
              />
              Multi-city trip
            </label>
            <label className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.oneWay}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    oneWay: event.target.checked,
                    returnDate: !current.multiCity && event.target.checked ? "" : current.returnDate,
                  }))
                }
              />
              {form.multiCity ? "Open-jaw trip" : "One-way trip"}
            </label>
            <label className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-3 text-sm text-slate">
              <input
                type="checkbox"
                checked={form.directOnly}
                onChange={(event) => setForm((current) => ({ ...current, directOnly: event.target.checked }))}
              />
              Direct flights only
            </label>
          </div>

          <div className={`grid gap-3 ${form.multiCity ? "md:grid-cols-2" : "md:grid-cols-2 xl:grid-cols-4"}`}>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">From (Origin City)</span>
              <input
                list="cities"
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.origin}
                onChange={(event) => setForm((current) => ({ ...current, origin: event.target.value }))}
              />
            </label>
            {!form.multiCity ? (
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">To (Destination City)</span>
                <input
                  list="cities"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.destination}
                  onChange={(event) => setForm((current) => ({ ...current, destination: event.target.value }))}
                />
              </label>
            ) : null}
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Departure Date</span>
              <input
                type="date"
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.departureDate}
                onChange={(event) => setForm((current) => ({ ...current, departureDate: event.target.value }))}
              />
            </label>
            {!form.multiCity ? form.oneWay ? (
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">Number of Nights</span>
                <input
                  type="number"
                  min={1}
                  max={30}
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.numNights}
                  onChange={(event) => setForm((current) => ({ ...current, numNights: Number(event.target.value || 7) }))}
                />
              </label>
            ) : (
              <label className="block">
                <span className="mb-2 block text-sm font-medium text-slate">Return Date</span>
                <input
                  type="date"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={form.returnDate}
                  onChange={(event) => setForm((current) => ({ ...current, returnDate: event.target.value }))}
                />
              </label>
            ) : null}
          </div>

          {form.multiCity ? (
            <div className="space-y-3">
              <div className="rounded-2xl bg-mist/60 px-4 py-3 text-sm text-slate">
                Add destinations in order of visit. Return date is calculated automatically from your destinations and nights.
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
                        setForm((current) => ({
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
                        setForm((current) => ({
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
                      setForm((current) => ({
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
                  setForm((current) => ({
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

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Travelers</span>
              <input
                type="number"
                min={1}
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.travelers}
                onChange={(event) => setForm((current) => ({ ...current, travelers: Number(event.target.value || 1) }))}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Budget (0 = flexible)</span>
              <input
                type="number"
                min={0}
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.budgetLimit}
                onChange={(event) => setForm((current) => ({ ...current, budgetLimit: Number(event.target.value || 0) }))}
              />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Currency</span>
              <select
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.currency}
                onChange={(event) => setForm((current) => ({ ...current, currency: event.target.value }))}
              >
                {CURRENCIES.map((currency) => (
                  <option key={currency} value={currency}>
                    {currency}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Max Flight Duration (hours)</span>
              <input
                type="number"
                min={0}
                step={0.5}
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.maxFlightDurationHours}
                onChange={(event) =>
                  setForm((current) => ({ ...current, maxFlightDurationHours: Number(event.target.value || 0) }))
                }
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Special Requests (optional)</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              value={form.preferences}
              onChange={(event) => setForm((current) => ({ ...current, preferences: event.target.value }))}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Exclude Airlines</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              placeholder="e.g. Ryanair, easyJet"
              value={form.excludeAirlines}
              onChange={(event) => setForm((current) => ({ ...current, excludeAirlines: event.target.value }))}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-medium text-slate">Include Airlines</span>
            <input
              className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
              placeholder="e.g. Lufthansa, Air France"
              value={form.includeAirlines}
              onChange={(event) => setForm((current) => ({ ...current, includeAirlines: event.target.value }))}
            />
          </label>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <label className="block">
              <span className="mb-2 block text-sm font-medium text-slate">Travel Class</span>
              <select
                className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={form.travelClass}
                onChange={(event) => setForm((current) => ({ ...current, travelClass: event.target.value }))}
              >
                {TRAVEL_CLASSES.map((travelClass) => (
                  <option key={travelClass} value={travelClass}>
                    {travelClass.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <HotelStarTierPicker
            label="Hotel Stars"
            helper="Choose one or more tiers like 4-star and up, or leave it on Any."
            thresholds={compressStarPreferences(form.hotelStars)}
            onChange={(thresholds) =>
              setForm((current) => ({
                ...current,
                hotelStars: expandStarThresholds(thresholds),
              }))
            }
          />
        </div>
      </details>

      <div className="mt-4 flex flex-wrap gap-3">
        <Button onClick={onPlanTrip} disabled={loading !== null} className="min-w-[10rem]">
          {loading === "planning" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
          Search Trip
        </Button>
        <Button variant="secondary" onClick={onVoiceInput} disabled={loading === "voice"}>
          {loading === "voice" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <AudioLines className="mr-2 h-4 w-4" />}
          {recording ? "Stop Recording" : "Voice Input"}
        </Button>
      </div>

      {error ? <p className="mt-4 text-sm text-coral">{error}</p> : null}
    </div>
  );
}
