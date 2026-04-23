import { LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

import { HotelStarTierPicker, TimeWindowPicker, FieldGroup } from "./controls";
import { TRAVEL_CLASSES } from "./constants";
import type {
  AuthMode,
  LoginFormState,
  PlannerLoadingState,
  RegisterFormState,
} from "./ui-types";

export function AuthScreen({
  authMode,
  setAuthMode,
  loginForm,
  setLoginForm,
  registerForm,
  setRegisterForm,
  cities,
  countries,
  airlines,
  loading,
  error,
  onLogin,
  onRegister,
}: {
  authMode: AuthMode;
  setAuthMode: (mode: AuthMode) => void;
  loginForm: LoginFormState;
  setLoginForm: React.Dispatch<React.SetStateAction<LoginFormState>>;
  registerForm: RegisterFormState;
  setRegisterForm: React.Dispatch<React.SetStateAction<RegisterFormState>>;
  cities: string[];
  countries: string[];
  airlines: string[];
  loading: PlannerLoadingState;
  error: string;
  onLogin: () => void;
  onRegister: () => void;
}) {
  return (
    <div className="mx-auto flex min-h-screen max-w-6xl items-center px-4 py-10">
      <div className="grid w-full gap-6 lg:grid-cols-[1.05fr_0.95fr]">
        <Card className="section-grid overflow-hidden border-white/80 bg-[linear-gradient(180deg,rgba(255,250,244,0.94),rgba(244,239,231,0.8))] p-8 sm:p-10">
          <h1 className="mt-5 font-display text-5xl leading-tight text-ink">TripBreeze AI</h1>
          <p className="mt-5 max-w-xl text-base leading-7 text-slate">
            Log in, set your preferences, and plan trips in a simpler chat-style workspace.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-3">
            {[
              { label: "Plan", detail: "Search flights and hotels." },
              { label: "Review", detail: "Compare and choose." },
              { label: "Finalize", detail: "Build a shareable itinerary." },
            ].map((item) => (
              <div key={item.label} className="rounded-[1.4rem] border border-white/75 bg-white/70 p-4">
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-pine">{item.label}</div>
                <div className="mt-2 text-sm leading-6 text-muted">{item.detail}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card className="border-white/85 bg-white/92 p-6 shadow-shell sm:p-8">
          <div className="mb-5 flex gap-2 rounded-full border border-line/70 bg-paper/90 p-1">
            {(["login", "register"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setAuthMode(mode)}
                className={`flex-1 rounded-full px-4 py-3 text-sm font-semibold transition ${
                  authMode === mode ? "bg-pine text-white shadow-focus" : "text-slate"
                }`}
              >
                {mode === "login" ? "Log In" : "Register"}
              </button>
            ))}
          </div>

          {authMode === "login" ? (
            <FieldGroup
              title="Welcome back"
              description="Log in to access your saved preferences, past trips, and itinerary tools."
            >
              <div className="space-y-4">
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">Username</span>
                  <input
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                    value={loginForm.userId}
                    onChange={(event) => setLoginForm((current) => ({ ...current, userId: event.target.value }))}
                  />
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">Password</span>
                  <input
                    type="password"
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                    value={loginForm.password}
                    onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
                  />
                </label>
                <Button onClick={onLogin} disabled={loading === "auth"}>
                  {loading === "auth" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Log In
                </Button>
              </div>
            </FieldGroup>
          ) : (
            <div className="space-y-4">
              <FieldGroup
                title="Account details"
                description="Create your account first, then add the travel defaults you want TripBreeze to remember."
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="md:col-span-2 block">
                    <span className="mb-2 block text-sm font-medium text-slate">Username</span>
                    <input
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.userId}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, userId: event.target.value }))}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Password</span>
                    <input
                      type="password"
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.password}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, password: event.target.value }))}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Confirm Password</span>
                    <input
                      type="password"
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.confirmPassword}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, confirmPassword: event.target.value }))}
                    />
                  </label>
                </div>
              </FieldGroup>

              <FieldGroup
                title="Travel profile"
                description="These preferences are optional, but they help TripBreeze choose better defaults from the start."
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Home City</span>
                    <input
                      list="cities"
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.homeCity}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, homeCity: event.target.value }))}
                    />
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Passport Country</span>
                    <input
                      list="countries"
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.passportCountry}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, passportCountry: event.target.value }))}
                    />
                  </label>
                  <label className="md:col-span-2 block">
                    <span className="mb-2 block text-sm font-medium text-slate">Preferred Class</span>
                    <select
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.travelClass}
                      onChange={(event) => setRegisterForm((current) => ({ ...current, travelClass: event.target.value }))}
                    >
                      {TRAVEL_CLASSES.map((travelClass) => (
                        <option key={travelClass} value={travelClass}>
                          {travelClass.replaceAll("_", " ")}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="md:col-span-2 block">
                    <span className="mb-2 block text-sm font-medium text-slate">Preferred Airlines</span>
                    <select
                      multiple
                      className="h-32 w-full rounded-3xl border border-ink/10 bg-white px-4 py-3 outline-none transition focus:border-coral"
                      value={registerForm.preferredAirlines}
                      onChange={(event) =>
                        setRegisterForm((current) => ({
                          ...current,
                          preferredAirlines: Array.from(event.target.selectedOptions, (option) => option.value),
                        }))
                      }
                    >
                      {airlines.slice(0, 60).map((airline) => (
                        <option key={airline} value={airline}>
                          {airline}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="md:col-span-2">
                    <HotelStarTierPicker
                      label="Preferred Hotel Stars"
                      helper="Choose one or more default hotel tiers like 3-star and up."
                      thresholds={registerForm.preferredHotelStars}
                      onChange={(thresholds) =>
                        setRegisterForm((current) => ({
                          ...current,
                          preferredHotelStars: thresholds,
                        }))
                      }
                    />
                  </div>
                  <div className="md:col-span-2 grid gap-4 md:grid-cols-2">
                    <TimeWindowPicker
                      label="Preferred Outbound Flight Time"
                      start={registerForm.outboundWindowStart}
                      end={registerForm.outboundWindowEnd}
                      onChange={(nextStart, nextEnd) =>
                        setRegisterForm((current) => ({
                          ...current,
                          outboundWindowStart: nextStart,
                          outboundWindowEnd: nextEnd,
                        }))
                      }
                    />
                    <TimeWindowPicker
                      label="Preferred Return Flight Time"
                      start={registerForm.returnWindowStart}
                      end={registerForm.returnWindowEnd}
                      onChange={(nextStart, nextEnd) =>
                        setRegisterForm((current) => ({
                          ...current,
                          returnWindowStart: nextStart,
                          returnWindowEnd: nextEnd,
                        }))
                      }
                    />
                  </div>
                </div>
              </FieldGroup>

              <div>
                <Button onClick={onRegister} disabled={loading === "auth"}>
                  {loading === "auth" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Register
                </Button>
              </div>
            </div>
          )}

          {error ? <p className="mt-4 text-sm text-coral">{error}</p> : null}
        </Card>
      </div>

      <datalist id="cities">
        {cities.slice(0, 200).map((city) => (
          <option key={city} value={city} />
        ))}
      </datalist>
      <datalist id="countries">
        {countries.map((country) => (
          <option key={country} value={country} />
        ))}
      </datalist>
    </div>
  );
}
