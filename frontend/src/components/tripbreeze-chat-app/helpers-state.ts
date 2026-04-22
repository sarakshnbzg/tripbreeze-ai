import { formatCurrency, type PlannerForm, type SelectionState } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

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
