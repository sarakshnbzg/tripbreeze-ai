import { formatCurrency, type PlannerForm, type SelectionState } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type RequestDataPoint = {
  label: string;
  value: string;
};

function hotelStarsSummary(source: Record<string, unknown>) {
  const hotelStars = Array.isArray(source.hotel_stars)
    ? source.hotel_stars.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0)
    : [];
  const explicitlyRequested = source.hotel_stars_user_specified === true;
  if (!explicitlyRequested || !hotelStars.length) {
    return "";
  }
  return `${Math.min(...hotelStars)}-star and up`;
}

export function createDefaultSelection(): SelectionState {
  return {
    flightIndex: -1,
    hotelIndex: -1,
    byLegFlights: [],
    byLegHotels: [],
  };
}

export function safeErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong.";
}

export function buildTripSummary(state: TravelState | null, currencyCode: string) {
  const tripRequest = state?.trip_request ?? {};
  const origin = String(tripRequest.origin ?? "").trim();
  const destination = String(tripRequest.destination ?? "").trim();
  const departureDate = String(tripRequest.departure_date ?? "").trim();
  const returnDate = String(tripRequest.return_date ?? "").trim();
  const travelers = Number(tripRequest.num_travelers ?? 1);
  const budget = Number(tripRequest.budget_limit ?? 0);
  const tripLegs = state?.trip_legs ?? [];

  if (tripLegs.length) {
    const firstOrigin = String(tripLegs[0]?.origin ?? origin).trim();
    const destinations = tripLegs
      .filter((leg) => Number(leg.nights ?? 0) > 0)
      .map((leg) => String(leg.destination ?? "").trim())
      .filter(Boolean);
    const departure = String(tripLegs[0]?.departure_date ?? departureDate).trim();
    return [
      firstOrigin || "Trip",
      destinations.length ? destinations.join(" -> ") : "Multi-city",
      departure || "",
      `${travelers} traveler${travelers === 1 ? "" : "s"}`,
      budget > 0 ? formatCurrency(budget, currencyCode) : "Flexible budget",
    ]
      .filter(Boolean)
      .join("  •  ");
  }

  return [
    [origin, destination].filter(Boolean).join(" -> "),
    departureDate && returnDate ? `${departureDate} to ${returnDate}` : departureDate || "",
    `${travelers} traveler${travelers === 1 ? "" : "s"}`,
    budget > 0 ? formatCurrency(budget, currencyCode) : "Flexible budget",
  ]
    .filter(Boolean)
    .join("  •  ");
}

export function buildResolvedRequestSummary(
  state: TravelState | null,
  currencyCode: string,
  fallbackMessage = "",
) {
  const tripRequest = readRecord(state?.trip_request);
  const tripLegs = state?.trip_legs ?? [];
  const hasStructuredTrip =
    tripLegs.length > 0 ||
    [
      tripRequest.origin,
      tripRequest.destination,
      tripRequest.departure_date,
      tripRequest.return_date,
    ].some((value) => readString(value));

  if (hasStructuredTrip) {
    return buildTripSummary(state, currencyCode);
  }

  return fallbackMessage.trim();
}

export function buildResolvedRequestDataPoints(
  state: TravelState | null,
  currencyCode: string,
): RequestDataPoint[] {
  const tripRequest = readRecord(state?.trip_request);
  const tripLegs = state?.trip_legs ?? [];
  const searchInputs = readRecord(state?.search_inputs);
  const flightInputs = readRecord(searchInputs.flight);
  const hotelInputs = readRecord(searchInputs.hotel);

  if (tripLegs.length) {
    const route = tripLegs
      .map((leg, index) => {
        const origin = readString(leg.origin);
        const destination = readString(leg.destination);
        return index === 0 ? [origin, destination].filter(Boolean).join(" -> ") : destination;
      })
      .filter(Boolean)
      .join(" -> ");
    const travelers = Math.max(1, Number(tripRequest.num_travelers ?? 1));
    const dates = [readString(tripRequest.departure_date), readString(tripRequest.return_date)].filter(Boolean).join(" to ");
    const hotelTier = readString(tripRequest.hotel_budget_tier).replaceAll("_", " ").toLowerCase();
    const hotelArea = readString(tripRequest.hotel_area);
    const hotelStars = hotelStarsSummary(tripRequest);

    return [
      route ? { label: "Route", value: route } : null,
      dates ? { label: "Dates", value: dates } : null,
      { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
      { label: "Stops", value: `${tripLegs.filter((leg) => Number(leg.nights ?? 0) > 0).length} cities` },
      hotelStars ? { label: "Hotel stars", value: hotelStars } : null,
      hotelTier ? { label: "Hotel tier", value: hotelTier.replace(/\b\w/g, (char) => char.toUpperCase()) } : null,
      hotelArea ? { label: "Hotel area", value: hotelArea } : null,
      tripRequest.budget_limit ? { label: "Budget", value: formatCurrency(tripRequest.budget_limit, currencyCode) } : null,
    ].filter((item): item is RequestDataPoint => Boolean(item));
  }

  const origin = readString(flightInputs.origin || tripRequest.origin);
  const destination = readString(flightInputs.destination || tripRequest.destination);
  const departureDate = readString(flightInputs.departure_date || tripRequest.departure_date);
  const returnDate = readString(flightInputs.return_date || tripRequest.return_date);
  const travelers = Math.max(1, Number(flightInputs.num_travelers || tripRequest.num_travelers || 1));
  const cabin = readString(flightInputs.travel_class || tripRequest.travel_class).replaceAll("_", " ").toLowerCase();
  const hotelTier = readString(hotelInputs.hotel_budget_tier || tripRequest.hotel_budget_tier).replaceAll("_", " ").toLowerCase();
  const hotelArea = readString(hotelInputs.hotel_area || tripRequest.hotel_area);
  const hotelStars = hotelStarsSummary(tripRequest);

  return [
    origin || destination ? { label: "Route", value: [origin, destination].filter(Boolean).join(" -> ") } : null,
    departureDate || returnDate ? { label: "Dates", value: [departureDate, returnDate].filter(Boolean).join(" to ") } : null,
    { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
    cabin ? { label: "Cabin", value: cabin.replace(/\b\w/g, (char) => char.toUpperCase()) } : null,
    hotelStars ? { label: "Hotel stars", value: hotelStars } : null,
    hotelTier ? { label: "Hotel tier", value: hotelTier.replace(/\b\w/g, (char) => char.toUpperCase()) } : null,
    hotelArea ? { label: "Hotel area", value: hotelArea } : null,
    tripRequest.budget_limit ? { label: "Budget", value: formatCurrency(tripRequest.budget_limit, currencyCode) } : null,
  ].filter((item): item is RequestDataPoint => Boolean(item));
}

export function latestAssistantMessage(state: TravelState | null) {
  const message = [...(state?.messages ?? [])]
    .reverse()
    .find((item) => item.role === "assistant" && item.content);
  return message?.content ?? "";
}

export function buildUserMessage(form: PlannerForm) {
  return form.freeText.trim() || `Plan a trip from ${form.origin || "my city"} to ${form.destination || "somewhere"}.`;
}

export function normaliseTimeWindow(rawWindow: unknown): [number, number] | null {
  if (!Array.isArray(rawWindow) || rawWindow.length !== 2) {
    return null;
  }
  const start = Number(rawWindow[0]);
  const end = Number(rawWindow[1]);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > 23 || start > end) {
    return null;
  }
  return [start, end];
}

export function summariseTokenUsage(tokenUsage: TravelState["token_usage"] = []) {
  return {
    input_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.input_tokens ?? 0), 0),
    output_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.output_tokens ?? 0), 0),
    cost: tokenUsage.reduce((sum, item) => sum + Number(item.cost ?? 0), 0),
  };
}

export function readString(value: unknown) {
  return String(value ?? "").trim();
}

export function readRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function readRecordArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

export function buildItineraryFileName(state: TravelState | null) {
  const tripRequest = readRecord(state?.trip_request);
  const destination = readString(tripRequest.destination).replace(/\s+/g, "_");
  const departure = readString(tripRequest.departure_date);
  const returnDate = readString(tripRequest.return_date);
  const parts = ["tripbreeze"];

  if (destination) {
    parts.push(destination);
  }
  if (departure) {
    parts.push(departure);
  }
  if (returnDate) {
    parts.push(returnDate);
  }

  return `${parts.join("_")}.pdf`;
}
