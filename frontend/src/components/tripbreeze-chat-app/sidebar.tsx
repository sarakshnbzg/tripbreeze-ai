import { LoaderCircle, LogOut, Save, UserRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { downloadItineraryPdf } from "@/lib/api";
import { formatCurrency } from "@/lib/planner";
import type { UserProfile } from "@/lib/types";

import { HotelStarTierPicker, TimeWindowPicker } from "./controls";
import { TRAVEL_CLASSES } from "./constants";
import { compressStarPreferences, expandStarThresholds, safeErrorMessage } from "./helpers";

type LoadingState = "auth" | "planning" | "clarifying" | "approving" | "saving" | "voice" | "pdf" | "email" | null;

export function AppSidebar({
  authenticatedUser,
  profile,
  setProfile,
  airlines,
  loading,
  onLogout,
  onSaveProfile,
  currentTokenSummary,
  tokenUsageHistory,
  showTokenUsage,
  setShowTokenUsage,
  showProfilePreferences,
  setShowProfilePreferences,
  hasReviewWorkspace,
  itinerary,
  recentPlanningUpdates,
  showPlanningProgress,
  setShowPlanningProgress,
  setError,
}: {
  authenticatedUser: string;
  profile: UserProfile | null;
  setProfile: React.Dispatch<React.SetStateAction<UserProfile | null>>;
  airlines: string[];
  loading: LoadingState;
  onLogout: () => void;
  onSaveProfile: () => Promise<void>;
  currentTokenSummary: { input_tokens: number; output_tokens: number; cost: number };
  tokenUsageHistory: Array<{ label: string; input_tokens: number; output_tokens: number; cost: number }>;
  showTokenUsage: boolean;
  setShowTokenUsage: React.Dispatch<React.SetStateAction<boolean>>;
  showProfilePreferences: boolean;
  setShowProfilePreferences: React.Dispatch<React.SetStateAction<boolean>>;
  hasReviewWorkspace: boolean;
  itinerary: string;
  recentPlanningUpdates: string[];
  showPlanningProgress: boolean;
  setShowPlanningProgress: React.Dispatch<React.SetStateAction<boolean>>;
  setError: React.Dispatch<React.SetStateAction<string>>;
}) {
  return (
    <aside className="hidden w-80 shrink-0 lg:block">
      <Card className="border-white/70 bg-white/76 p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.25em] text-slate">Account</p>
            <h2 className="mt-2 font-display text-2xl text-ink">{authenticatedUser}</h2>
          </div>
          <button type="button" onClick={onLogout} className="rounded-full border border-line/80 bg-white/70 p-2 text-slate transition hover:bg-white">
            <LogOut className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-6 space-y-5">
          <div>
            <button
              type="button"
              onClick={() => setShowProfilePreferences((current) => !current)}
              className="flex w-full items-center justify-between rounded-2xl border border-line/80 bg-paper/75 px-4 py-3 text-left transition hover:bg-white"
            >
              <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                <UserRound className="h-4 w-4" />
                Preferences
              </span>
              <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                {showProfilePreferences ? "Hide" : "Open"}
              </span>
            </button>
            {showProfilePreferences ? (
              <div className="mt-3 space-y-3">
                <input
                  list="cities"
                  placeholder="Home City"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={profile?.home_city ?? ""}
                  onChange={(event) => setProfile((current) => ({ ...(current ?? {}), home_city: event.target.value }))}
                />
                <input
                  list="countries"
                  placeholder="Passport Country"
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={profile?.passport_country ?? ""}
                  onChange={(event) => setProfile((current) => ({ ...(current ?? {}), passport_country: event.target.value }))}
                />
                <select
                  className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={profile?.travel_class ?? "ECONOMY"}
                  onChange={(event) => setProfile((current) => ({ ...(current ?? {}), travel_class: event.target.value }))}
                >
                  {TRAVEL_CLASSES.map((travelClass) => (
                    <option key={travelClass} value={travelClass}>
                      {travelClass.replaceAll("_", " ")}
                    </option>
                  ))}
                </select>
                <TimeWindowPicker
                  label="Preferred Outbound Flight Time"
                  start={Number(profile?.preferred_outbound_time_window?.[0] ?? 0)}
                  end={Number(profile?.preferred_outbound_time_window?.[1] ?? 23)}
                  onChange={(nextStart, nextEnd) =>
                    setProfile((current) => ({
                      ...(current ?? {}),
                      preferred_outbound_time_window: [nextStart, nextEnd],
                    }))
                  }
                />
                <TimeWindowPicker
                  label="Preferred Return Flight Time"
                  start={Number(profile?.preferred_return_time_window?.[0] ?? 0)}
                  end={Number(profile?.preferred_return_time_window?.[1] ?? 23)}
                  onChange={(nextStart, nextEnd) =>
                    setProfile((current) => ({
                      ...(current ?? {}),
                      preferred_return_time_window: [nextStart, nextEnd],
                    }))
                  }
                />
                <select
                  multiple
                  className="h-32 w-full rounded-3xl border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                  value={(profile?.preferred_airlines as string[] | undefined) ?? []}
                  onChange={(event) =>
                    setProfile((current) => ({
                      ...(current ?? {}),
                      preferred_airlines: Array.from(event.target.selectedOptions, (option) => option.value),
                    }))
                  }
                >
                  {airlines.slice(0, 60).map((airline) => (
                    <option key={airline} value={airline}>
                      {airline}
                    </option>
                  ))}
                </select>
                <HotelStarTierPicker
                  label="Preferred Hotel Stars"
                  helper="Choose one or more default hotel tiers like 3-star and up."
                  thresholds={compressStarPreferences(((profile?.preferred_hotel_stars as number[] | undefined) ?? []))}
                  onChange={(thresholds) =>
                    setProfile((current) => ({
                      ...(current ?? {}),
                      preferred_hotel_stars: expandStarThresholds(thresholds),
                    }))
                  }
                />
                <Button variant="secondary" onClick={() => void onSaveProfile()} disabled={loading === "saving"}>
                  {loading === "saving" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  Save Profile
                </Button>
              </div>
            ) : null}
          </div>

          {profile?.past_trips?.length ? (
            <div>
              <div className="mb-3 text-sm font-semibold text-ink">Past Trips</div>
              <div className="space-y-2">
                {profile.past_trips.slice(-5).reverse().map((trip, index) => (
                  <div key={`${trip.destination ?? "trip"}-${index}`} className="rounded-2xl border border-line/60 bg-white/82 p-3 text-sm">
                    <div className="font-medium text-ink">{String(trip.destination ?? "Trip")}</div>
                    <div className="text-slate">{String(trip.dates ?? "")}</div>
                    {trip.final_itinerary ? (
                      <button
                        type="button"
                        className="mt-2 text-xs font-semibold text-coral"
                        onClick={async () => {
                          try {
                            const blob = await downloadItineraryPdf(
                              String(trip.final_itinerary),
                              (trip.pdf_state as Record<string, unknown>) ?? {},
                              `${String(trip.destination ?? "trip").replaceAll(" ", "_")}_itinerary.pdf`,
                            );
                            const url = URL.createObjectURL(blob);
                            const link = document.createElement("a");
                            link.href = url;
                            link.download = `${String(trip.destination ?? "trip").replaceAll(" ", "_")}_itinerary.pdf`;
                            link.click();
                            URL.revokeObjectURL(url);
                          } catch (pastTripError) {
                            setError(safeErrorMessage(pastTripError));
                          }
                        }}
                      >
                        Download PDF
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {(currentTokenSummary.cost > 0 || tokenUsageHistory.length > 0) ? (
            <div>
              <button
                type="button"
                onClick={() => setShowTokenUsage((current) => !current)}
                className="flex w-full items-center justify-between rounded-2xl border border-line/80 bg-paper/75 px-4 py-3 text-left transition hover:bg-white"
              >
                <span className="text-sm font-semibold text-ink">Token Usage</span>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                  {showTokenUsage ? "Hide" : "Open"}
                </span>
              </button>
              {showTokenUsage ? (
                <>
                  <div className="mt-3 rounded-2xl border border-line/60 bg-white/82 p-3 text-sm text-slate">
                    <div>Current cost: ${currentTokenSummary.cost.toFixed(4)}</div>
                    <div>Input: {currentTokenSummary.input_tokens.toLocaleString()}</div>
                    <div>Output: {currentTokenSummary.output_tokens.toLocaleString()}</div>
                  </div>
                  {tokenUsageHistory.length ? (
                    <div className="mt-2 space-y-2">
                      {tokenUsageHistory.map((item) => (
                        <div key={`${item.label}-${item.cost}`} className="rounded-2xl border border-line/50 bg-white/65 p-3 text-xs text-slate">
                          <div className="font-semibold text-ink">{item.label}</div>
                          <div>${item.cost.toFixed(4)}</div>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </>
              ) : null}
            </div>
          ) : null}

        </div>
      </Card>
    </aside>
  );
}
