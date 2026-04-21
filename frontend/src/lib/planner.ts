import type { Dispatch, SetStateAction } from "react";

import type { StreamEvent, TravelState, TripOption } from "@/lib/types";

export type PlannerForm = {
  freeText: string;
  origin: string;
  destination: string;
  departureDate: string;
  returnDate: string;
  multiCity: boolean;
  oneWay: boolean;
  numNights: number;
  travelers: number;
  budgetLimit: number;
  currency: string;
  preferences: string;
  directOnly: boolean;
  travelClass: string;
  hotelStars: number[];
  multiCityLegs: Array<{ destination: string; nights: number }>;
  userId: string;
  provider: "openai" | "google";
  model: string;
};

export type SelectionState = {
  flightIndex: number;
  hotelIndex: number;
  byLegFlights: number[];
  byLegHotels: number[];
};

export const defaultForm: PlannerForm = {
  freeText: "",
  origin: "",
  destination: "",
  departureDate: "",
  returnDate: "",
  multiCity: false,
  oneWay: false,
  numNights: 7,
  travelers: 1,
  budgetLimit: 0,
  currency: "EUR",
  preferences: "",
  directOnly: false,
  travelClass: "ECONOMY",
  hotelStars: [],
  multiCityLegs: [{ destination: "", nights: 3 }],
  userId: "default_user",
  provider: "openai",
  model: "gpt-4o-mini",
};

export const defaultSelection: SelectionState = {
  flightIndex: -1,
  hotelIndex: -1,
  byLegFlights: [],
  byLegHotels: [],
};

export function formatCurrency(value: unknown, code = "EUR") {
  const amount = typeof value === "number" ? value : Number(value ?? 0);
  if (!Number.isFinite(amount) || amount <= 0) {
    return "TBC";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: code,
    maximumFractionDigits: 0,
  }).format(amount);
}

export function buildStructuredFields(form: PlannerForm) {
  const fields: Record<string, unknown> = {};
  const validMultiCityLegs = form.multiCityLegs
    .map((leg) => ({
      destination: leg.destination.trim(),
      nights: Number(leg.nights) || 0,
    }))
    .filter((leg) => leg.destination && leg.nights > 0);

  if (form.origin.trim()) {
    fields.origin = form.origin.trim();
  }
  if (form.multiCity) {
    if (validMultiCityLegs.length) {
      fields.multi_city_legs = validMultiCityLegs;
      fields.return_to_origin = !form.oneWay;
    }
  } else if (form.destination.trim()) {
    fields.destination = form.destination.trim();
  }
  if (form.departureDate) {
    fields.departure_date = form.departureDate;
  }
  if (form.multiCity) {
    // Return timing is derived from multi-city legs and nights.
  } else if (form.oneWay) {
    fields.is_one_way = true;
    if (form.departureDate && form.numNights > 0) {
      const departure = new Date(`${form.departureDate}T00:00:00`);
      departure.setDate(departure.getDate() + form.numNights);
      fields.check_out_date = departure.toISOString().slice(0, 10);
    }
  } else if (form.returnDate) {
    fields.return_date = form.returnDate;
  }
  if (form.travelers > 1) {
    fields.num_travelers = form.travelers;
  }
  if (form.budgetLimit > 0) {
    fields.budget_limit = form.budgetLimit;
  }
  if (form.currency) {
    fields.currency = form.currency;
  }
  if (form.preferences.trim()) {
    fields.preferences = form.preferences.trim();
  }
  if (form.directOnly) {
    fields.stops = 0;
  }
  if (form.travelClass) {
    fields.travel_class = form.travelClass;
  }
  if (form.hotelStars.length) {
    fields.hotel_stars = form.hotelStars;
  }

  return fields;
}

export function selectedOption(options: TripOption[] | undefined, index: number) {
  if (!options || options.length === 0 || index < 0) {
    return {};
  }
  return options[index] ?? {};
}

export function applyStreamEvent(
  event: StreamEvent,
  setState: Dispatch<SetStateAction<TravelState | null>>,
  setLogs: Dispatch<SetStateAction<string[]>>,
  setClarification: Dispatch<SetStateAction<string>>,
  setItinerary: Dispatch<SetStateAction<string>>,
): TravelState | null {
  if (event.event === "node_start") {
    const label = String(event.data.label ?? "Working...");
    setLogs((current) => [...current, label]);
    return null;
  }

  if (event.event === "node_message") {
    const content = String(event.data.content ?? "");
    if (content) {
      setLogs((current) => [...current, content]);
    }
    return null;
  }

  if (event.event === "clarification") {
    setClarification(String(event.data.question ?? ""));
    return null;
  }

  if (event.event === "token") {
    setItinerary((current) => `${current}${String(event.data.content ?? "")}`);
    return null;
  }

  if (event.event === "state") {
    const nextState = event.data as TravelState;
    setState(nextState);
    return nextState;
  }

  if (event.event === "error") {
    const detail = String(event.data.detail ?? "Unexpected error");
    setLogs((current) => [...current, `Error: ${detail}`]);
  }

  return null;
}
