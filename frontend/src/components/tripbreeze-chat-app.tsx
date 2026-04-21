"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AudioLines,
  LoaderCircle,
  LogOut,
  Mail,
  Plane,
  Plus,
  Save,
  Send,
  Settings2,
  UserRound,
  WandSparkles,
  X,
} from "lucide-react";

import {
  downloadItineraryPdf,
  emailItinerary,
  fetchReturnFlights,
  getReferenceValues,
  login,
  register,
  saveProfile,
  streamApprove,
  streamClarify,
  streamSearch,
  transcribeAudio,
} from "@/lib/api";
import {
  buildStructuredFields,
  defaultForm,
  formatCurrency,
  selectedOption,
  type PlannerForm,
  type SelectionState,
} from "@/lib/planner";
import type { ApproveRequest, StreamEvent, TravelState, TripOption, UserProfile } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
};

function createDefaultSelection(): SelectionState {
  return {
    flightIndex: -1,
    hotelIndex: -1,
    byLegFlights: [],
    byLegHotels: [],
  };
}

const TRAVEL_CLASSES = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"];
const CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SGD", "AED", "NZD"];
const HOTEL_STARS = [5, 4, 3, 2, 1];
const INTEREST_OPTIONS = ["food", "history", "nature", "art", "nightlife", "shopping", "outdoors", "family"];
const PACE_OPTIONS = ["relaxed", "moderate", "packed"] as const;
const OPENAI_MODELS = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano"];
const GOOGLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite"];

function safeErrorMessage(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Something went wrong.";
}

function renderInlineMarkdown(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  match = pattern.exec(text);
  while (match) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**") && token.endsWith("**")) {
      parts.push(<strong key={`${match.index}-bold`}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      parts.push(
        <code key={`${match.index}-code`} className="rounded bg-black/5 px-1 py-0.5 text-[0.95em]">
          {token.slice(1, -1)}
        </code>,
      );
    } else if (token.startsWith("[") && token.includes("](") && token.endsWith(")")) {
      const closingBracket = token.indexOf("](");
      const label = token.slice(1, closingBracket);
      const href = token.slice(closingBracket + 2, -1);
      parts.push(
        <a
          key={`${match.index}-link`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-coral underline-offset-2 hover:underline"
        >
          {label}
        </a>,
      );
    }

    lastIndex = pattern.lastIndex;
    match = pattern.exec(text);
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function renderMarkdownContent(content: string) {
  const normalized = content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s(#{2,6}\s)/g, "$1\n$2")
    .trim();

  if (!normalized) {
    return null;
  }

  const lines = normalized.split("\n");
  const nodes: React.ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();

    if (!line) {
      index += 1;
      continue;
    }

    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const className =
        level === 1
          ? "text-xl font-semibold"
          : level === 2
            ? "text-lg font-semibold"
            : level === 3
              ? "text-base font-semibold"
              : "text-sm font-semibold";
      nodes.push(
        <div key={`heading-${index}`} className={`${className} mt-1`}>
          {renderInlineMarkdown(text)}
        </div>,
      );
      index += 1;
      continue;
    }

    if (/^\|.*\|$/.test(line)) {
      const tableLines: string[] = [];
      while (index < lines.length && /^\|.*\|$/.test(lines[index].trim())) {
        tableLines.push(lines[index].trim());
        index += 1;
      }

      const rows = tableLines
        .filter((row, rowIndex) => rowIndex !== 1 || !/^(\|\s*:?-+:?\s*)+\|?$/.test(row))
        .map((row) => row.split("|").slice(1, -1).map((cell) => cell.trim()));

      if (rows.length) {
        const [header, ...body] = rows;
        nodes.push(
          <div key={`table-${index}`} className="overflow-x-auto">
            <table className="mt-2 min-w-full border-collapse text-sm">
              <thead>
                <tr>
                  {header.map((cell, cellIndex) => (
                    <th key={`th-${cellIndex}`} className="border-b border-black/10 px-2 py-2 text-left font-semibold">
                      {renderInlineMarkdown(cell)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((row, rowIndex) => (
                  <tr key={`tr-${rowIndex}`} className="border-b border-black/5">
                    {row.map((cell, cellIndex) => (
                      <td key={`td-${rowIndex}-${cellIndex}`} className="px-2 py-2 align-top">
                        {renderInlineMarkdown(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      }
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      nodes.push(
        <ul key={`list-${index}`} className="ml-5 list-disc space-y-1">
          {items.map((item, itemIndex) => (
            <li key={`li-${itemIndex}`}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    const paragraphLines: string[] = [];
    while (index < lines.length) {
      const current = lines[index].trim();
      if (!current || /^(#{1,6})\s+/.test(current) || /^\|.*\|$/.test(current) || /^[-*]\s+/.test(current)) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }

    const paragraph = paragraphLines.join(" ");
    nodes.push(
      <p key={`p-${index}`} className="leading-7">
        {renderInlineMarkdown(paragraph)}
      </p>,
    );
  }

  return <div className="space-y-3 whitespace-pre-wrap">{nodes}</div>;
}

function buildTripSummary(state: TravelState | null, currencyCode: string) {
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

function selectionLabel(option: Record<string, unknown>, fallback: string) {
  return String(option.name ?? option.airline ?? option.operator ?? fallback);
}

function latestAssistantMessage(state: TravelState | null) {
  const message = [...(state?.messages ?? [])]
    .reverse()
    .find((item) => item.role === "assistant" && item.content);
  return message?.content ?? "";
}

function buildUserMessage(form: PlannerForm) {
  return form.freeText.trim() || `Plan a trip from ${form.origin || "my city"} to ${form.destination || "somewhere"}.`;
}

function normaliseTimeWindow(rawWindow: unknown): [number, number] | null {
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

function combineRoundTripFlight(outbound: Record<string, unknown>, returnFlight: Record<string, unknown>) {
  const totalPrice = Number(
    returnFlight.total_price ?? outbound.total_price ?? outbound.price ?? 0,
  );
  const adults = Math.max(1, Number(outbound.adults ?? 1));
  const price = adults > 1 ? Number((totalPrice / adults).toFixed(2)) : totalPrice;
  return {
    ...outbound,
    return_summary: String(returnFlight.return_summary ?? outbound.return_summary ?? ""),
    return_details_available: true,
    selected_return: returnFlight,
    total_price: totalPrice,
    price,
    currency: returnFlight.currency ?? outbound.currency,
  };
}

function insertBookingLinksAfterSection(markdown: string, heading: string, linkLine: string) {
  const index = markdown.indexOf(heading);
  if (index === -1) {
    return markdown;
  }
  const nextIndex = markdown.indexOf("\n#### ", index + heading.length);
  const insertion = `\n\n${linkLine}\n`;
  if (nextIndex === -1) {
    return `${markdown.trimEnd()}${insertion}`;
  }
  return `${markdown.slice(0, nextIndex)}${insertion}${markdown.slice(nextIndex)}`;
}

function insertBookingLinksIntoLeg(markdown: string, legNumber: number, linkLines: string[]) {
  if (!linkLines.length) {
    return markdown;
  }

  const anchor = `**Leg ${legNumber}:`;
  const index = markdown.indexOf(anchor);
  if (index === -1) {
    return markdown;
  }

  const nextLegIndex = markdown.indexOf(`\n\n**Leg ${legNumber + 1}:`, index + anchor.length);
  const nextSectionIndex = markdown.indexOf("\n\n#### ", index + anchor.length);
  const boundaries = [nextLegIndex, nextSectionIndex].filter((position) => position !== -1);
  const insertAt = boundaries.length ? Math.min(...boundaries) : markdown.length;
  const insertion = `\n${linkLines.join("\n")}`;
  return `${markdown.slice(0, insertAt)}${insertion}${markdown.slice(insertAt)}`;
}

function injectBookingLinks(
  markdown: string,
  flight: Record<string, unknown>,
  hotel: Record<string, unknown>,
  flights: Array<Record<string, unknown>> = [],
  hotels: Array<Record<string, unknown>> = [],
) {
  let result = markdown;
  const flightUrl = String(flight.booking_url ?? "").trim();
  const hotelUrl = String(hotel.booking_url ?? "").trim();

  if (flightUrl) {
    const airline = String(flight.airline ?? "this flight");
    result = insertBookingLinksAfterSection(
      result,
      "#### 🛫 Flight Details",
      `🔗 **[Book ${airline} on Google Flights](${flightUrl})**`,
    );
  }

  if (hotelUrl) {
    const hotelName = String(hotel.name ?? "this hotel");
    result = insertBookingLinksAfterSection(
      result,
      "#### 🏨 Hotel Details",
      `🔗 **[Book ${hotelName}](${hotelUrl})**`,
    );
  }

  const totalLegs = Math.max(flights.length, hotels.length);
  for (let legNumber = 1; legNumber <= totalLegs; legNumber += 1) {
    const legFlight = flights[legNumber - 1] ?? {};
    const legHotel = hotels[legNumber - 1] ?? {};
    const linkLines: string[] = [];

    const legFlightUrl = String(legFlight.booking_url ?? "").trim();
    if (legFlightUrl) {
      const airline = String(legFlight.airline ?? `flight for leg ${legNumber}`);
      linkLines.push(`🔗 **[Book ${airline} on Google Flights](${legFlightUrl})**`);
    }

    const legHotelUrl = String(legHotel.booking_url ?? "").trim();
    if (legHotelUrl) {
      const hotelName = String(legHotel.name ?? `hotel for leg ${legNumber}`);
      linkLines.push(`🔗 **[Book ${hotelName}](${legHotelUrl})**`);
    }

    result = insertBookingLinksIntoLeg(result, legNumber, linkLines);
  }

  return result;
}

function summariseTokenUsage(tokenUsage: TravelState["token_usage"] = []) {
  return {
    input_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.input_tokens ?? 0), 0),
    output_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.output_tokens ?? 0), 0),
    cost: tokenUsage.reduce((sum, item) => sum + Number(item.cost ?? 0), 0),
  };
}

function optionTotalPrice(option: Record<string, unknown>) {
  return Number(option.total_price ?? option.price ?? 0);
}

function durationToMinutes(option: Record<string, unknown>) {
  const rawDuration = String(option.duration ?? "");
  let hours = 0;
  let minutes = 0;

  for (const part of rawDuration.split(" ")) {
    if (part.endsWith("h")) {
      hours = Number(part.slice(0, -1)) || 0;
    } else if (part.endsWith("m")) {
      minutes = Number(part.slice(0, -1)) || 0;
    }
  }

  return hours * 60 + minutes;
}

function formatStops(stops: unknown) {
  const safeStops = Number(stops ?? 0);
  if (safeStops === 0) {
    return "Direct";
  }
  return safeStops === 1 ? "1 stop" : `${safeStops} stops`;
}

function hotelRatingLabel(rating: unknown) {
  const score = Number(rating);
  if (!Number.isFinite(score) || score <= 0) {
    return "";
  }
  if (score >= 4.5) {
    return "Excellent";
  }
  if (score >= 4) {
    return "Very Good";
  }
  if (score >= 3.5) {
    return "Good";
  }
  if (score >= 3) {
    return "Fair";
  }
  return "Poor";
}

function hotelBreakfastStatus(option: Record<string, unknown>) {
  const amenities = Array.isArray(option.amenities)
    ? option.amenities.map((item) => String(item).trim().toLowerCase()).filter(Boolean)
    : [];
  if (!amenities.length) {
    return "";
  }
  const breakfastItems = amenities.filter((item) => item.includes("breakfast"));
  if (!breakfastItems.length) {
    return "";
  }
  const includedKeywords = ["included", "free", "complimentary"];
  return breakfastItems.some((item) => includedKeywords.some((keyword) => item.includes(keyword)))
    ? "Breakfast included"
    : "Breakfast available";
}

function flightBadges(options: TripOption[], option: TripOption) {
  const badges: string[] = [];
  const prices = options.map((item) => optionTotalPrice(item)).filter((value) => value > 0);
  const durations = options.map((item) => durationToMinutes(item)).filter((value) => value > 0);

  if (prices.length && optionTotalPrice(option) === Math.min(...prices)) {
    badges.push("Best price");
  }
  if (durations.length && durationToMinutes(option) === Math.min(...durations)) {
    badges.push("Shortest");
  }
  if (Number(option.stops ?? 0) === 0) {
    badges.push("Direct");
  }
  return badges;
}

function hotelBadges(options: TripOption[], option: TripOption) {
  const badges: string[] = [];
  const prices = options
    .map((item) => Number(item.total_price ?? 0))
    .filter((value) => Number.isFinite(value) && value > 0);
  const ratings = options
    .map((item) => Number(item.rating ?? 0))
    .filter((value) => Number.isFinite(value) && value > 0);

  if (prices.length && Number(option.total_price ?? 0) === Math.min(...prices)) {
    badges.push("Best price");
  }
  if (ratings.length && Number(option.rating ?? 0) === Math.max(...ratings)) {
    badges.push("Top rated");
  }
  return badges;
}

function transportBadges(options: TripOption[], option: TripOption) {
  const badges: string[] = [];
  const prices = options.map((item) => optionTotalPrice(item)).filter((value) => value > 0);
  const durations = options.map((item) => durationToMinutes(item)).filter((value) => value > 0);

  if (prices.length && optionTotalPrice(option) === Math.min(...prices)) {
    badges.push("Best price");
  }
  if (durations.length && durationToMinutes(option) === Math.min(...durations)) {
    badges.push("Shortest");
  }
  if (Number(option.stops ?? 0) === 0) {
    badges.push("Direct");
  }
  return badges;
}

function budgetStatusNote(note: unknown) {
  const text = String(note ?? "").trim().toLowerCase();
  return text.includes("within budget") || text.includes("exceeds your budget") || text.includes("to spare");
}

function compressStarPreferences(stars: number[]) {
  const selected = [...new Set(stars.map((star) => Number(star)).filter((star) => HOTEL_STARS.includes(star)))].sort(
    (a, b) => a - b,
  );
  const thresholds: number[] = [];
  const covered = new Set<number>();

  for (const star of selected) {
    if (covered.has(star)) {
      continue;
    }
    thresholds.push(star);
    for (let value = star; value <= 5; value += 1) {
      covered.add(value);
    }
  }

  return thresholds;
}

function expandStarThresholds(thresholds: number[]) {
  const expanded = new Set<number>();
  for (const threshold of thresholds) {
    if (!HOTEL_STARS.includes(threshold)) {
      continue;
    }
    for (let value = threshold; value <= 5; value += 1) {
      expanded.add(value);
    }
  }
  return [...expanded].sort((a, b) => a - b);
}

function HotelStarTierPicker({
  label,
  helper,
  thresholds,
  onChange,
}: {
  label: string;
  helper?: string;
  thresholds: number[];
  onChange: (thresholds: number[]) => void;
}) {
  const selected = [...new Set(thresholds)].sort((a, b) => a - b);
  const selectedTier = selected[0] ?? null;

  return (
    <div>
      <div className="mb-2 block text-sm font-medium text-slate">{label}</div>
      {helper ? <div className="mb-3 text-sm text-slate">{helper}</div> : null}
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        <button
          type="button"
          onClick={() => onChange([])}
          className={`rounded-2xl px-4 py-3 text-left text-sm transition ${
            selectedTier === null ? "bg-ink text-white" : "border border-ink/10 bg-white text-slate"
          }`}
        >
          <div className="font-semibold">Any</div>
          <div className={`mt-1 text-xs ${selectedTier === null ? "text-white/75" : "text-slate"}`}>
            No hotel star preference
          </div>
        </button>
        {HOTEL_STARS.slice().sort((a, b) => a - b).map((star) => {
          const active = selectedTier === star;
          return (
            <button
              key={star}
              type="button"
              onClick={() => onChange(active ? [] : [star])}
              className={`rounded-2xl px-4 py-3 text-left text-sm transition ${
                active ? "bg-ink text-white" : "border border-ink/10 bg-white text-slate"
              }`}
            >
              <div className="font-semibold">{star}-star and up</div>
              <div className={`mt-1 text-xs ${active ? "text-white/75" : "text-slate"}`}>
                Minimum {star}-star hotels
              </div>
            </button>
          );
        })}
      </div>
      {selectedTier !== null ? (
        <div className="mt-3 text-sm text-slate">
          Selected: {selectedTier}-star and up
        </div>
      ) : (
        <div className="mt-3 text-sm text-slate">Selected: Any hotel tier</div>
      )}
    </div>
  );
}

function budgetFlightDetail(option: Record<string, unknown>, currencyCode: string) {
  if (!Object.keys(option).length) {
    return "Selected itinerary total";
  }

  const adults = Math.max(1, Number(option.adults ?? 1));
  const perPerson = Number(option.price ?? 0);
  if (adults > 1 && perPerson > 0) {
    return `${adults} traveller(s) x ${formatCurrency(perPerson, currencyCode)}/person`;
  }
  if (perPerson > 0) {
    return `1 traveller x ${formatCurrency(perPerson, currencyCode)}`;
  }
  return "Selected itinerary total";
}

function budgetHotelDetail(option: Record<string, unknown>, budget: Record<string, unknown>, currencyCode: string) {
  if (!Object.keys(option).length) {
    return "Full stay for selected room/search";
  }

  const pricePerNight = Number(option.price_per_night ?? 0);
  const nights = Math.max(0, Number(budget.daily_expense_days ?? 0));
  if (pricePerNight > 0 && nights > 0) {
    return `${nights} night(s) x ${formatCurrency(pricePerNight, currencyCode)}/night`;
  }
  return "Full stay for selected room/search";
}

function transportLabel(mode: unknown) {
  const safeMode = String(mode ?? "").toLowerCase();
  if (safeMode === "train") {
    return "Train";
  }
  if (safeMode === "bus") {
    return "Bus";
  }
  if (safeMode === "ferry") {
    return "Ferry";
  }
  return safeMode ? safeMode[0].toUpperCase() + safeMode.slice(1) : "Transport";
}

function sentenceLabel(value: string) {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function readString(value: unknown) {
  return String(value ?? "").trim();
}

function readRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function readRecordArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}

function buildItineraryFileName(state: TravelState | null) {
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

function flightPricePills(option: TripOption, currencyCode: string) {
  const adults = Math.max(1, Number(option.adults ?? 1));
  const perPerson = Number(option.price ?? 0);
  const total = Number(option.total_price ?? option.price ?? 0);
  const pills = {
    standard: [] as string[],
    highlighted: "" as string,
  };

  if (perPerson > 0) {
    pills.standard.push(`${formatCurrency(perPerson, currencyCode)}/person`);
  }
  if (total > 0 && (adults > 1 || total !== perPerson)) {
    pills.highlighted = `${formatCurrency(total, currencyCode)} total`;
  }

  return pills;
}

function hotelMetaPills(option: TripOption, currencyCode: string, ratingLabel: string) {
  const stars = Number(option.hotel_class ?? 0);
  const rating = Number(option.rating ?? 0);
  const pricePerNight = Number(option.price_per_night ?? 0);
  const pills: string[] = [];

  if (stars > 0) {
    pills.push(`${stars}-star`);
  }
  if (rating > 0) {
    pills.push(ratingLabel ? `${rating} ${ratingLabel}` : String(rating));
  }
  if (pricePerNight > 0) {
    pills.push(`${formatCurrency(pricePerNight, currencyCode)}/night`);
  }

  return pills;
}

function isMultiCitySelectionComplete(state: TravelState | null, selection: SelectionState) {
  if (!state?.trip_legs?.length) {
    return false;
  }

  return state.trip_legs.every((leg, index) => {
    const legFlights = state.flight_options_by_leg?.[index] ?? [];
    const legHotels = state.hotel_options_by_leg?.[index] ?? [];
    const needsHotel = Boolean(leg.needs_hotel);
    const hasFlight = legFlights.length > 0;
    const hasHotel = !needsHotel || legHotels.length > 0;
    const selectedFlightIndex = selection.byLegFlights[index];
    const selectedHotelIndex = selection.byLegHotels[index];
    const pickedFlight =
      hasFlight &&
      typeof selectedFlightIndex === "number" &&
      selectedFlightIndex >= 0 &&
      selectedFlightIndex < legFlights.length;
    const pickedHotel =
      !needsHotel ||
      (hasHotel &&
        typeof selectedHotelIndex === "number" &&
        selectedHotelIndex >= 0 &&
        selectedHotelIndex < legHotels.length);
    return pickedFlight && pickedHotel;
  });
}

function ReviewOptionCard({
  option,
  title,
  variant,
  allOptions,
  selected,
  onSelect,
  currencyCode,
}: {
  option: TripOption;
  title: string;
  variant: "flight" | "hotel" | "transport";
  allOptions: TripOption[];
  selected: boolean;
  onSelect: () => void;
  currencyCode: string;
}) {
  const badges =
    variant === "flight"
      ? flightBadges(allOptions, option)
      : variant === "hotel"
        ? hotelBadges(allOptions, option)
        : transportBadges(allOptions, option);
  const flightSummary =
    variant === "flight"
      ? String(option.outbound_summary ?? option.return_summary ?? option.description ?? option.duration ?? "Details available")
      : "";
  const ratingLabel = variant === "hotel" ? hotelRatingLabel(option.rating) : "";
  const breakfastStatus = variant === "hotel" ? hotelBreakfastStatus(option) : "";
  const mode = variant === "transport" ? transportLabel(option.mode) : "";
  const stars = Number(option.hotel_class ?? 0);
  const bookingLabel =
    variant === "flight"
      ? "View on Google Flights"
      : variant === "hotel"
        ? "View on Google Hotels"
        : "View on Google Maps Transit";
  const flightPriceMeta = variant === "flight" ? flightPricePills(option, currencyCode) : null;
  const metaPills =
    variant === "flight"
      ? [
          option.duration ? String(option.duration) : "",
          typeof option.stops === "number" ? formatStops(option.stops) : "",
          ...(flightPriceMeta?.standard ?? []),
        ].filter(Boolean)
      : [];
  const hotelPills =
    variant === "hotel" ? hotelMetaPills(option, currencyCode, ratingLabel) : [];
  const hotelAddress = variant === "hotel" ? String(option.address ?? "").trim() : "";
  const hotelTotalPrice = variant === "hotel" ? Number(option.total_price ?? option.price ?? 0) : 0;
  const hotelSummary =
    variant === "hotel"
      ? hotelAddress || String(option.description ?? "Details available").trim()
      : "";
  const hotelDescription =
    variant === "hotel" ? String(option.description ?? "").trim() : "";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full rounded-[1.6rem] border p-4 text-left transition ${
        selected
          ? "border-coral bg-gradient-to-br from-[#fff3ee] to-[#fff8f2] shadow-[0_18px_45px_rgba(215,108,78,0.14)]"
          : "border-ink/10 bg-white hover:-translate-y-0.5 hover:border-coral/40 hover:shadow-[0_14px_34px_rgba(16,33,43,0.08)]"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="font-semibold text-ink">{String(option.name ?? option.airline ?? title)}</div>
          <div className="mt-1 text-sm text-slate">
            {variant === "flight"
              ? flightSummary
              : variant === "hotel"
                ? hotelSummary
                : String(option.description ?? option.duration ?? "Details available")}
          </div>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
            selected ? "bg-coral text-white" : "bg-mist text-slate"
          }`}
        >
          {selected ? "Selected" : "Option"}
        </span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate">
        {badges.map((badge) => (
          <span
            key={badge}
            className={`rounded-full px-3 py-1 font-semibold ${
              variant === "flight" || variant === "hotel"
                ? "bg-coral text-white shadow-[0_8px_18px_rgba(215,108,78,0.22)]"
                : "bg-white/80 text-ink"
            }`}
          >
            {badge}
          </span>
        ))}
        {variant === "transport" && mode ? <span>{mode}</span> : null}
        {variant === "flight"
          ? metaPills.map((pill) => (
              <span key={pill} className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                {pill}
              </span>
            ))
          : variant === "hotel"
            ? (
              <>
                {hotelPills.map((pill) => (
                  <span key={pill} className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                    {pill}
                  </span>
                ))}
                {breakfastStatus ? (
                  <span className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                    {breakfastStatus}
                  </span>
                ) : null}
                {hotelTotalPrice > 0 ? (
                  <span className="rounded-full bg-ink px-3 py-1 font-semibold text-white">
                    {formatCurrency(hotelTotalPrice, currencyCode)} total
                  </span>
                ) : null}
              </>
            )
          : (
            <>
              {option.duration ? <span>{String(option.duration)}</span> : null}
              {typeof option.stops === "number" ? (
                <span>{formatStops(option.stops)}</span>
              ) : null}
              <span className="rounded-full bg-white/80 px-3 py-1 font-semibold text-ink">
                {formatCurrency(option.total_price ?? option.price, currencyCode)}
              </span>
            </>
          )}
        {variant === "flight" && flightPriceMeta?.highlighted ? (
          <span className="rounded-full bg-ink px-3 py-1 font-semibold text-white">
            {flightPriceMeta.highlighted}
          </span>
        ) : null}
      </div>
      {variant === "hotel" ? (
        <div className="mt-3 space-y-1 text-sm text-slate">
          {hotelDescription && hotelDescription !== hotelSummary ? (
            <div className="leading-6">{hotelDescription}</div>
          ) : null}
        </div>
      ) : null}
      {variant === "transport" ? (
        <div className="mt-3 space-y-1 text-sm text-slate">
          {option.segments_summary ? <div>Route: {String(option.segments_summary)}</div> : null}
          {(option.departure_time || option.arrival_time) ? (
            <div>
              Depart: {String(option.departure_time ?? "?")} · Arrive: {String(option.arrival_time ?? "?")}
            </div>
          ) : null}
        </div>
      ) : null}
      {String(option.booking_url ?? "").trim() ? (
        <div className="mt-3 text-sm">
          <a
            href={String(option.booking_url)}
            target="_blank"
            rel="noreferrer"
            className="font-semibold text-coral underline-offset-2 hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            {bookingLabel}
          </a>
        </div>
      ) : null}
    </button>
  );
}

function formatHourLabel(hour: number) {
  const safeHour = Math.max(0, Math.min(23, hour));
  return `${safeHour.toString().padStart(2, "0")}:00`;
}

function TimeWindowPicker({
  label,
  start,
  end,
  onChange,
}: {
  label: string;
  start: number;
  end: number;
  onChange: (nextStart: number, nextEnd: number) => void;
}) {
  const safeStart = Math.max(0, Math.min(23, start));
  const safeEnd = Math.max(safeStart, Math.min(23, end));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-slate">{label}</span>
        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-ink">
          {formatHourLabel(safeStart)} to {formatHourLabel(safeEnd)}
        </span>
      </div>
      <div className="space-y-3 rounded-3xl border border-ink/10 bg-white px-4 py-4">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-slate">From</div>
          <input
            type="range"
            min={0}
            max={23}
            value={safeStart}
            className="w-full accent-[#d76c4e]"
            onChange={(event) => {
              const nextStart = Number(event.target.value);
              onChange(nextStart, Math.max(nextStart, safeEnd));
            }}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-slate">To</div>
          <input
            type="range"
            min={0}
            max={23}
            value={safeEnd}
            className="w-full accent-[#10212b]"
            onChange={(event) => {
              const nextEnd = Number(event.target.value);
              onChange(Math.min(safeStart, nextEnd), nextEnd);
            }}
          />
        </div>
      </div>
    </div>
  );
}

function FieldGroup({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-[1.75rem] border border-ink/10 bg-white/70 p-4">
      <div className="mb-4">
        <div className="text-sm font-semibold text-ink">{title}</div>
        {description ? <div className="mt-1 text-sm text-slate">{description}</div> : null}
      </div>
      {children}
    </div>
  );
}

export function TripBreezeChatApp() {
  const [authenticatedUser, setAuthenticatedUser] = useState<string>("");
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [loginForm, setLoginForm] = useState({ userId: "", password: "" });
  const [registerForm, setRegisterForm] = useState({
    userId: "",
    password: "",
    confirmPassword: "",
    homeCity: "",
    passportCountry: "",
    travelClass: "ECONOMY",
    preferredAirlines: [] as string[],
    preferredHotelStars: [] as number[],
    outboundWindowStart: 0,
    outboundWindowEnd: 23,
    returnWindowStart: 0,
    returnWindowEnd: 23,
  });
  const [cities, setCities] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [airlines, setAirlines] = useState<string[]>([]);
  const [form, setForm] = useState<PlannerForm>(defaultForm);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [planningUpdates, setPlanningUpdates] = useState<string[]>([]);
  const [state, setState] = useState<TravelState | null>(null);
  const [clarificationQuestion, setClarificationQuestion] = useState("");
  const [clarificationAnswer, setClarificationAnswer] = useState("");
  const [feedback, setFeedback] = useState("");
  const [itinerary, setItinerary] = useState("");
  const [selection, setSelection] = useState<SelectionState>(() => createDefaultSelection());
  const [selectedTransportIndex, setSelectedTransportIndex] = useState<number | null>(null);
  const [returnOptions, setReturnOptions] = useState<TripOption[]>([]);
  const [selectedReturnIndex, setSelectedReturnIndex] = useState<number | null>(null);
  const [interests, setInterests] = useState<string[]>([]);
  const [pace, setPace] = useState<(typeof PACE_OPTIONS)[number]>("moderate");
  const [emailAddress, setEmailAddress] = useState("");
  const [tokenUsageHistory, setTokenUsageHistory] = useState<
    Array<{ label: string; input_tokens: number; output_tokens: number; cost: number }>
  >([]);
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [showProfilePreferences, setShowProfilePreferences] = useState(false);
  const [showComposer, setShowComposer] = useState(true);
  const [showEntryRequirements, setShowEntryRequirements] = useState(false);
  const [showPlanningProgress, setShowPlanningProgress] = useState(true);
  const [showTokenUsage, setShowTokenUsage] = useState(false);
  const [loading, setLoading] = useState<"auth" | "planning" | "clarifying" | "approving" | "saving" | "voice" | "pdf" | "email" | null>(null);
  const [error, setError] = useState("");
  const [recording, setRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const outboundSectionRef = useRef<HTMLDivElement | null>(null);
  const returnSectionRef = useRef<HTMLDivElement | null>(null);
  const hotelSectionRef = useRef<HTMLDivElement | null>(null);
  const personaliseSectionRef = useRef<HTMLDivElement | null>(null);

  const currencyCode = String(state?.trip_request?.currency ?? form.currency ?? "EUR");
  const availableModels = form.provider === "google" ? GOOGLE_MODELS : OPENAI_MODELS;
  const selectedTransport =
    selectedTransportIndex !== null ? state?.transport_options?.[selectedTransportIndex] ?? {} : {};
  const isRoundTrip = Boolean(state?.trip_request?.return_date);
  const currentTokenSummary = useMemo(() => summariseTokenUsage(state?.token_usage), [state?.token_usage]);

  useEffect(() => {
    void Promise.all([
      getReferenceValues("cities"),
      getReferenceValues("countries"),
      getReferenceValues("airlines"),
    ])
      .then(([cityValues, countryValues, airlineValues]) => {
        setCities(cityValues);
        setCountries(countryValues);
        setAirlines(airlineValues);
      })
      .catch(() => {
        // Keep the UI usable even if reference data is unavailable.
      });
  }, []);

  useEffect(() => {
    const savedUser = window.localStorage.getItem("tripbreeze_user");
    const savedProfile = window.localStorage.getItem("tripbreeze_profile");
    if (!savedUser || !savedProfile) {
      return;
    }
    try {
      const parsedProfile = JSON.parse(savedProfile) as UserProfile;
      setAuthenticatedUser(savedUser);
      setProfile(parsedProfile);
      setForm((current) => ({
        ...current,
        userId: savedUser,
        origin: parsedProfile.home_city ?? "",
      }));
      setEmailAddress(savedUser);
    } catch {
      window.localStorage.removeItem("tripbreeze_user");
      window.localStorage.removeItem("tripbreeze_profile");
    }
  }, []);

  const hasOptionResults = useMemo(
    () =>
      Boolean(
        state &&
        (
          state.flight_options?.length ||
          state.hotel_options?.length ||
          state.flight_options_by_leg?.length ||
          state.hotel_options_by_leg?.length
        ),
      ),
    [state],
  );
  const hasReviewWorkspace = useMemo(
    () =>
      Boolean(
        state &&
        (
          hasOptionResults ||
          state.transport_options?.length ||
          state.destination_info ||
          state.budget ||
          state.rag_sources?.length ||
          latestAssistantMessage(state)
        ),
      ),
    [hasOptionResults, state],
  );
  const canApprove = useMemo(() => {
    if (!state) {
      return false;
    }
    if (state.trip_legs?.length) {
      return isMultiCitySelectionComplete(state, selection);
    }
    const hasSelectedFlight =
      Boolean(state.flight_options?.length) &&
      selection.flightIndex >= 0 &&
      selection.flightIndex < (state.flight_options?.length ?? 0);
    const hasSelectedHotel =
      Boolean(state.hotel_options?.length) &&
      selection.hotelIndex >= 0 &&
      selection.hotelIndex < (state.hotel_options?.length ?? 0);
    const hasReturn =
      !isRoundTrip ||
      selectedReturnIndex !== null ||
      Boolean(
        selection.flightIndex >= 0 ? state.flight_options?.[selection.flightIndex]?.return_details_available : false,
      );
    return hasSelectedFlight && hasSelectedHotel && hasReturn;
  }, [isRoundTrip, selectedReturnIndex, selection, state]);
  const hasSelectedSingleFlight =
    !state?.trip_legs?.length &&
    Boolean(state?.flight_options?.length) &&
    selection.flightIndex >= 0 &&
    selection.flightIndex < (state?.flight_options?.length ?? 0);
  const hasSelectedSingleHotel =
    !state?.trip_legs?.length &&
    Boolean(state?.hotel_options?.length) &&
    selection.hotelIndex >= 0 &&
    selection.hotelIndex < (state?.hotel_options?.length ?? 0);
  const hasSelectedSingleReturn =
    !isRoundTrip ||
    selectedReturnIndex !== null ||
    Boolean(hasSelectedSingleFlight ? state?.flight_options?.[selection.flightIndex]?.return_details_available : false);
  const showPersonalisationPanel = state?.trip_legs?.length ? canApprove : hasSelectedSingleFlight && hasSelectedSingleHotel && hasSelectedSingleReturn;
  const selectedOutboundOption = hasSelectedSingleFlight ? selectedOption(state?.flight_options, selection.flightIndex) : {};
  const selectedReturnOption = selectedReturnIndex !== null ? returnOptions[selectedReturnIndex] ?? {} : {};
  const selectedHotelOption = hasSelectedSingleHotel ? selectedOption(state?.hotel_options, selection.hotelIndex) : {};
  const completedMultiCityLegs = (state?.trip_legs ?? []).filter((leg, index) => {
    const hasFlight = typeof selection.byLegFlights[index] === "number" && selection.byLegFlights[index] >= 0;
    const needsHotel = Boolean(leg.needs_hotel);
    const hasHotel = !needsHotel || (typeof selection.byLegHotels[index] === "number" && selection.byLegHotels[index] >= 0);
    return hasFlight && hasHotel;
  }).length;
  const tripRequest = readRecord(state?.trip_request);
  const budgetData = readRecord(state?.budget);
  const itineraryData = readRecord(state?.itinerary_data);
  const itineraryFlightDetails = readString(itineraryData.flight_details);
  const itineraryHotelDetails = readString(itineraryData.hotel_details);
  const itineraryHighlights = readString(itineraryData.destination_highlights);
  const itineraryBudget = readString(itineraryData.budget_breakdown);
  const itineraryVisa = readString(itineraryData.visa_entry_info);
  const itineraryPacking = readString(itineraryData.packing_tips);
  const itineraryLegs = readRecordArray(itineraryData.legs);
  const itineraryDays = readRecordArray(itineraryData.daily_plans);
  const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
  const finalSelectedFlight = readRecord(state?.selected_flight);
  const finalSelectedHotel = readRecord(state?.selected_hotel);
  const finalSelectedTransport = readRecord(state?.selected_transport);
  const finalSelectedFlights = readRecordArray(state?.selected_flights);
  const finalSelectedHotels = readRecordArray(state?.selected_hotels);
  const itinerarySnapshotItems = useMemo(() => {
    const travelers = Math.max(1, Number(tripRequest.num_travelers ?? 1));
    const tripLegs = state?.trip_legs ?? [];
    const budgetLimit = Number(tripRequest.budget_limit ?? 0);
    const estimatedTotal = Number(budgetData.total_estimated_cost ?? 0);

    if (tripLegs.length) {
      const routeParts = [
        String(tripLegs[0]?.origin ?? tripRequest.origin ?? "").trim(),
        ...tripLegs
          .filter((leg) => Number(leg.nights ?? 0) > 0)
          .map((leg) => String(leg.destination ?? "").trim())
          .filter(Boolean),
      ].filter(Boolean);
      const firstDeparture = String(tripLegs[0]?.departure_date ?? tripRequest.departure_date ?? "").trim();
      const finalStop = [...tripLegs]
        .reverse()
        .find((leg) => readString(leg.check_out_date) || readString(leg.departure_date));
      const finalDate =
        readString(finalStop?.check_out_date) || readString(tripRequest.return_date) || readString(finalStop?.departure_date);
      const selectedFlightCount = finalSelectedFlights.filter((item) => Object.keys(item).length).length;
      const selectedHotelCount = finalSelectedHotels.filter((item) => Object.keys(item).length).length;

      return [
        { label: "Route", value: routeParts.join(" -> ") || "Multi-city trip" },
        {
          label: "Dates",
          value:
            firstDeparture && finalDate && finalDate !== firstDeparture
              ? `${firstDeparture} to ${finalDate}`
              : firstDeparture || finalDate || "Dates pending",
        },
        { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
        {
          label: estimatedTotal > 0 ? "Trip estimate" : "Budget",
          value: estimatedTotal > 0 ? formatCurrency(estimatedTotal, currencyCode) : budgetLimit > 0 ? formatCurrency(budgetLimit, currencyCode) : "Flexible",
        },
        { label: "Flights", value: selectedFlightCount ? `${selectedFlightCount} leg${selectedFlightCount === 1 ? "" : "s"} selected` : "Managed per leg" },
        { label: "Hotels", value: selectedHotelCount ? `${selectedHotelCount} stay${selectedHotelCount === 1 ? "" : "s"} selected` : "Chosen per stop" },
      ];
    }

    const origin = String(tripRequest.origin ?? "").trim();
    const destination = String(tripRequest.destination ?? "").trim();
    const departureDate = String(tripRequest.departure_date ?? "").trim();
    const returnDate = String(tripRequest.return_date ?? "").trim();
    const selectedFlightLabel = Object.keys(finalSelectedFlight).length ? selectionLabel(finalSelectedFlight, "Selected flight") : "Chosen flight";
    const selectedHotelLabel = Object.keys(finalSelectedHotel).length ? selectionLabel(finalSelectedHotel, "Selected hotel") : "Chosen hotel";
    const transportValue = Object.keys(finalSelectedTransport).length
      ? `${transportLabel(finalSelectedTransport.mode)}${readString(finalSelectedTransport.operator) ? ` · ${readString(finalSelectedTransport.operator)}` : ""}`
      : "";

    return [
      { label: "Route", value: [origin, destination].filter(Boolean).join(" -> ") || "Planned trip" },
      {
        label: "Dates",
        value: departureDate && returnDate ? `${departureDate} to ${returnDate}` : departureDate || returnDate || "Dates pending",
      },
      { label: "Travelers", value: `${travelers} traveler${travelers === 1 ? "" : "s"}` },
      {
        label: estimatedTotal > 0 ? "Trip estimate" : "Budget",
        value: estimatedTotal > 0 ? formatCurrency(estimatedTotal, currencyCode) : budgetLimit > 0 ? formatCurrency(budgetLimit, currencyCode) : "Flexible",
      },
      { label: "Flight", value: selectedFlightLabel },
      { label: "Stay", value: transportValue ? `${selectedHotelLabel} · ${transportValue}` : selectedHotelLabel },
    ];
  }, [
    budgetData.total_estimated_cost,
    currencyCode,
    finalSelectedFlight,
    finalSelectedFlights,
    finalSelectedHotel,
    finalSelectedHotels,
    finalSelectedTransport,
    state?.trip_legs,
    tripRequest.budget_limit,
    tripRequest.departure_date,
    tripRequest.destination,
    tripRequest.num_travelers,
    tripRequest.origin,
    tripRequest.return_date,
  ]);
  const itineraryBookingLinks = useMemo(() => {
    const links: Array<{ label: string; url: string }> = [];

    if (state?.trip_legs?.length) {
      finalSelectedFlights.forEach((flight, index) => {
        const url = readString(flight.booking_url);
        if (url) {
          links.push({ label: `Leg ${index + 1} flight`, url });
        }
      });
      finalSelectedHotels.forEach((hotel, index) => {
        const url = readString(hotel.booking_url);
        if (url) {
          links.push({ label: `Leg ${index + 1} hotel`, url });
        }
      });
      return links;
    }

    const flightUrl = readString(finalSelectedFlight.booking_url);
    if (flightUrl) {
      links.push({ label: "Flight booking", url: flightUrl });
    }

    const hotelUrl = readString(finalSelectedHotel.booking_url);
    if (hotelUrl) {
      links.push({ label: "Hotel booking", url: hotelUrl });
    }

    const transportUrl = readString(finalSelectedTransport.booking_url);
    if (transportUrl) {
      links.push({ label: `${transportLabel(finalSelectedTransport.mode)} booking`, url: transportUrl });
    }

    return links;
  }, [finalSelectedFlight, finalSelectedFlights, finalSelectedHotel, finalSelectedHotels, finalSelectedTransport, state?.trip_legs]);
  const primaryItinerarySections = [
    itineraryFlightDetails ? { key: "flight", title: "Flight details", content: itineraryFlightDetails } : null,
    itineraryHotelDetails ? { key: "hotel", title: "Hotel details", content: itineraryHotelDetails } : null,
    itineraryBudget ? { key: "budget", title: "Budget breakdown", content: itineraryBudget } : null,
    itineraryVisa ? { key: "visa", title: "Visa and entry", content: itineraryVisa } : null,
  ].filter((section): section is { key: string; title: string; content: string } => Boolean(section));
  const secondaryItinerarySections = [
    itineraryHighlights ? { key: "highlights", title: "Destination highlights", content: itineraryHighlights } : null,
    itineraryPacking ? { key: "packing", title: "Packing tips", content: itineraryPacking } : null,
  ].filter((section): section is { key: string; title: string; content: string } => Boolean(section));
  const recentPlanningUpdates = useMemo(() => {
    const filtered = planningUpdates
      .map((update) => String(update).trim())
      .filter(Boolean)
      .filter((update, index, items) => items.indexOf(update) === index);
    return filtered.slice(-4);
  }, [planningUpdates]);

  useEffect(() => {
    if (hasReviewWorkspace || itinerary) {
      setShowPlanningProgress(false);
      setShowEntryRequirements(false);
    }
  }, [hasReviewWorkspace, itinerary]);

  useEffect(() => {
    if (state?.trip_legs?.length || !hasOptionResults || selection.flightIndex < 0) {
      return;
    }

    const target = isRoundTrip ? returnSectionRef.current : hotelSectionRef.current;
    if (!target) {
      return;
    }

    window.setTimeout(() => {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [hasOptionResults, isRoundTrip, selection.flightIndex, state?.trip_legs]);

  useEffect(() => {
    if (state?.trip_legs?.length || !hasOptionResults || !isRoundTrip || selectedReturnIndex === null) {
      return;
    }
    if (!hotelSectionRef.current) {
      return;
    }

    window.setTimeout(() => {
      hotelSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [hasOptionResults, isRoundTrip, selectedReturnIndex, state?.trip_legs]);

  useEffect(() => {
    if (state?.trip_legs?.length || !showPersonalisationPanel || selection.hotelIndex < 0) {
      return;
    }
    if (!personaliseSectionRef.current) {
      return;
    }

    window.setTimeout(() => {
      personaliseSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  }, [selection.hotelIndex, showPersonalisationPanel, state?.trip_legs]);

  useEffect(() => {
    async function loadReturnOptions() {
      if (
        !state?.thread_id ||
        !isRoundTrip ||
        !state.flight_options?.length ||
        selection.flightIndex < 0
      ) {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
        return;
      }

      const selectedOutbound = state.flight_options[selection.flightIndex];
      const departureToken = String(selectedOutbound?.departure_token ?? "");
      if (!departureToken) {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
        return;
      }

      try {
        const returnTimeWindow = normaliseTimeWindow(profile?.preferred_return_time_window);
        const options = await fetchReturnFlights(state.thread_id, {
          origin: String(state.trip_request?.origin ?? ""),
          destination: String(state.trip_request?.destination ?? ""),
          departure_date: String(state.trip_request?.departure_date ?? ""),
          return_date: String(state.trip_request?.return_date ?? ""),
          departure_token: departureToken,
          adults: Number(state.trip_request?.num_travelers ?? 1),
          travel_class: String(state.trip_request?.travel_class ?? "ECONOMY"),
          currency: currencyCode,
          return_time_window: returnTimeWindow ? [...returnTimeWindow] : null,
        });
        setReturnOptions(options as TripOption[]);
        setSelectedReturnIndex(null);
      } catch {
        setReturnOptions([]);
        setSelectedReturnIndex(null);
      }
    }

    void loadReturnOptions();
  }, [
    currencyCode,
    isRoundTrip,
    profile?.preferred_return_time_window,
    selection.flightIndex,
    state?.flight_options,
    state?.thread_id,
    state?.trip_request,
  ]);

  function persistAuth(userId: string, nextProfile: UserProfile) {
    setAuthenticatedUser(userId);
    setProfile(nextProfile);
    setForm((current) => ({ ...current, userId, origin: nextProfile.home_city ?? current.origin }));
    setEmailAddress(userId);
    window.localStorage.setItem("tripbreeze_user", userId);
    window.localStorage.setItem("tripbreeze_profile", JSON.stringify(nextProfile));
  }

  function archiveCurrentTokenUsage() {
    if (!state?.token_usage?.length) {
      return;
    }
    const summary = summariseTokenUsage(state.token_usage);
    const tripRequest = state.trip_request ?? {};
    const label =
      String(tripRequest.destination ?? "").trim() ||
      (String(tripRequest.departure_date ?? "").trim()
        ? `Search (${String(tripRequest.departure_date)})`
        : `Search ${tokenUsageHistory.length + 1}`);
    setTokenUsageHistory((current) => [{ label, ...summary }, ...current].slice(0, 5));
  }

  function logout() {
    archiveCurrentTokenUsage();
    setAuthenticatedUser("");
    setProfile(null);
    setMessages([]);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());
    setSelectedTransportIndex(null);
    setInterests([]);
    setPace("moderate");
    setError("");
    window.localStorage.removeItem("tripbreeze_user");
    window.localStorage.removeItem("tripbreeze_profile");
  }

  function resetTrip() {
    archiveCurrentTokenUsage();
    setMessages([]);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());
    setSelectedTransportIndex(null);
    setInterests([]);
    setPace("moderate");
    setError("");
    setShowComposer(true);
    setShowEntryRequirements(false);
    setShowPlanningProgress(true);
  }

  function handleStreamEvent(event: StreamEvent) {
    if (event.event === "node_start") {
      setPlanningUpdates((current) => [...current, String(event.data.label ?? "Working...")]);
      return;
    }
    if (event.event === "node_message") {
      const content = String(event.data.content ?? "");
      if (content) {
        setPlanningUpdates((current) => [...current, content]);
      }
      return;
    }
    if (event.event === "clarification") {
      const question = String(event.data.question ?? "");
      setClarificationQuestion(question);
      setMessages((current) => [...current, { role: "assistant", content: question }]);
      return;
    }
    if (event.event === "token") {
      setItinerary((current) => `${current}${String(event.data.content ?? "")}`);
      return;
    }
    if (event.event === "state") {
      const nextState = event.data as TravelState;
      setState(nextState);
      if (authenticatedUser && nextState.user_profile) {
        persistAuth(authenticatedUser, nextState.user_profile);
      }
      const assistant = latestAssistantMessage(nextState);
      if (assistant) {
        setMessages((current) => {
          if (current[current.length - 1]?.role === "assistant" && current[current.length - 1]?.content === assistant) {
            return current;
          }
          return [...current, { role: "assistant", content: assistant }];
        });
      }
      return;
    }
    if (event.event === "error") {
      setError(String(event.data.detail ?? "Unexpected error"));
    }
  }

  async function handleLogin() {
    setError("");
    setLoading("auth");
    try {
      const result = await login(loginForm.userId.trim(), loginForm.password);
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleRegister() {
    setError("");
    if (registerForm.password !== registerForm.confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setLoading("auth");
    try {
      const result = await register(registerForm.userId.trim(), registerForm.password, {
        home_city: registerForm.homeCity,
        passport_country: registerForm.passportCountry,
        travel_class: registerForm.travelClass,
        preferred_airlines: registerForm.preferredAirlines,
        preferred_hotel_stars: expandStarThresholds(registerForm.preferredHotelStars),
        preferred_outbound_time_window: [
          registerForm.outboundWindowStart,
          registerForm.outboundWindowEnd,
        ],
        preferred_return_time_window: [
          registerForm.returnWindowStart,
          registerForm.returnWindowEnd,
        ],
      });
      persistAuth(result.user_id, result.profile);
    } catch (authError) {
      setError(safeErrorMessage(authError));
    } finally {
      setLoading(null);
    }
  }

  async function handleSaveProfile() {
    if (!authenticatedUser || !profile) {
      return;
    }
    setError("");
    setLoading("saving");
    try {
      const result = await saveProfile(authenticatedUser, profile);
      persistAuth(result.user_id, result.profile);
    } catch (saveError) {
      setError(safeErrorMessage(saveError));
    } finally {
      setLoading(null);
    }
  }

  async function handlePlanTrip() {
    const validMultiCityLegs = form.multiCityLegs.filter(
      (leg) => leg.destination.trim() && Number(leg.nights) > 0,
    );

    if (!form.freeText.trim()) {
      if (form.multiCity) {
        if (!validMultiCityLegs.length) {
          setError("Add at least one destination for your multi-city trip or describe it in free text.");
          return;
        }
      } else if (!form.destination.trim()) {
        setError("Describe your trip or fill in at least a destination.");
        return;
      }
    }

    if (!form.departureDate && !form.freeText.trim()) {
      setError("Choose a departure date or include it in your trip description.");
      return;
    }

    if (!form.multiCity && !form.oneWay && form.returnDate && form.departureDate && form.returnDate <= form.departureDate) {
      setError("Return date must be after departure date.");
      return;
    }

    if (!form.multiCity && form.oneWay && !form.freeText.trim() && form.numNights <= 0) {
      setError("One-way trips need the number of nights so hotel search and budget can be calculated.");
      return;
    }

    archiveCurrentTokenUsage();
    setError("");
    setLoading("planning");
    setShowComposer(false);
    setShowEntryRequirements(false);
    setShowPlanningProgress(true);
    setPlanningUpdates([]);
    setState(null);
    setClarificationQuestion("");
    setClarificationAnswer("");
    setFeedback("");
    setItinerary("");
    setSelection(createDefaultSelection());
    setSelectedTransportIndex(null);

    const userMessage = buildUserMessage(form);
    setMessages((current) => [...current, { role: "user", content: userMessage }]);
    setForm((current) => ({ ...current, freeText: "" }));

    try {
      await streamSearch(
        {
          user_id: authenticatedUser,
          free_text_query: form.freeText || undefined,
          structured_fields: buildStructuredFields(form),
          llm_provider: form.provider,
          llm_model: form.model,
          llm_temperature: 0.3,
        },
        handleStreamEvent,
      );
    } catch (planningError) {
      setError(safeErrorMessage(planningError));
    } finally {
      setLoading(null);
    }
  }

  async function handleClarification() {
    if (!state?.thread_id || !clarificationAnswer.trim()) {
      return;
    }
    setError("");
    setLoading("clarifying");
    const answer = clarificationAnswer.trim();
    setMessages((current) => [...current, { role: "user", content: answer }]);
    setClarificationAnswer("");
    setClarificationQuestion("");

    try {
      await streamClarify(state.thread_id, answer, handleStreamEvent);
    } catch (clarifyError) {
      setError(safeErrorMessage(clarifyError));
    } finally {
      setLoading(null);
    }
  }

  async function handleReview(feedbackType: ApproveRequest["feedback_type"]) {
    if (!state?.thread_id) {
      return;
    }
    setError("");
    setLoading(feedbackType === "revise_plan" ? "planning" : "approving");
    if (feedbackType === "revise_plan") {
      setShowComposer(true);
    }
    setItinerary("");

    const request: ApproveRequest = {
      user_feedback: feedback,
      feedback_type: feedbackType,
      selected_transport: selectedTransport,
      llm_provider: form.provider,
      llm_model: form.model,
      llm_temperature: 0.3,
      trip_request: {
        ...(state.trip_request ?? {}),
        interests,
        pace,
      },
    };

    if (state.trip_legs?.length) {
      request.selected_flights =
        state.flight_options_by_leg?.map((legOptions, index) =>
          selectedOption(legOptions, selection.byLegFlights[index] ?? 0),
        ) ?? [];
      request.selected_hotels =
        state.hotel_options_by_leg?.map((legOptions, index) =>
          selectedOption(legOptions, selection.byLegHotels[index] ?? 0),
        ) ?? [];
      request.selected_flight = request.selected_flights[0] ?? {};
      request.selected_hotel = request.selected_hotels[0] ?? {};
    } else {
      const outbound = selectedOption(state.flight_options, selection.flightIndex);
      const returnFlight =
        isRoundTrip && selectedReturnIndex !== null ? (returnOptions[selectedReturnIndex] ?? {}) : {};
      request.selected_flight =
        isRoundTrip && selectedReturnIndex !== null
          ? combineRoundTripFlight(outbound, returnFlight)
          : outbound;
      request.selected_hotel = selectedOption(state.hotel_options, selection.hotelIndex);
    }

    try {
      await streamApprove(state.thread_id, request, handleStreamEvent);
    } catch (approveError) {
      setError(safeErrorMessage(approveError));
    } finally {
      setLoading(null);
    }
  }

  async function handleVoiceInput() {
    if (recording) {
      mediaRecorderRef.current?.stop();
      setRecording(false);
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setError("Voice recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      recordedChunksRef.current = [];
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        setLoading("voice");
        try {
          const blob = new Blob(recordedChunksRef.current, { type: "audio/webm" });
          const text = await transcribeAudio(blob);
          setForm((current) => ({
            ...current,
            freeText: [current.freeText, text].filter(Boolean).join(" ").trim(),
          }));
        } catch (voiceError) {
          setError(safeErrorMessage(voiceError));
        } finally {
          stream.getTracks().forEach((track) => track.stop());
          setLoading(null);
        }
      };

      recorder.start();
      setRecording(true);
      setError("");
    } catch {
      setError("Unable to start microphone recording.");
    }
  }

  async function handleDownloadPdf() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary) {
      return;
    }
    setError("");
    setLoading("pdf");
    try {
      const fileName = buildItineraryFileName(state);
      const blob = await downloadItineraryPdf(
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
        fileName,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch (pdfError) {
      setError(safeErrorMessage(pdfError));
    } finally {
      setLoading(null);
    }
  }

  async function handleEmailItinerary() {
    const finalItinerary = itinerary || String(state?.final_itinerary ?? "");
    if (!finalItinerary || !emailAddress.trim()) {
      setError("Enter an email address before sending the itinerary.");
      return;
    }
    setError("");
    setLoading("email");
    try {
      const result = await emailItinerary(
        emailAddress.trim(),
        authenticatedUser,
        finalItinerary,
        (state ?? {}) as Record<string, unknown>,
      );
      setPlanningUpdates((current) => [...current, result.message]);
    } catch (emailError) {
      setError(safeErrorMessage(emailError));
    } finally {
      setLoading(null);
    }
  }

  if (!authenticatedUser) {
    return (
      <div className="mx-auto flex min-h-screen max-w-6xl items-center px-4 py-10">
        <div className="grid w-full gap-6 lg:grid-cols-[1.05fr_0.95fr]">
          <Card className="section-grid p-8 sm:p-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-ink/10 bg-white/70 px-4 py-2 text-xs font-semibold uppercase tracking-[0.25em] text-slate">
              <WandSparkles className="h-4 w-4" />
              New frontend, familiar flow
            </div>
            <h1 className="mt-5 font-display text-5xl leading-tight text-ink">TripBreeze AI</h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate">
              Log in or register, set your travel preferences, then plan your trip in a simple chat-style workspace with voice input, trip form refinement, review, and itinerary generation.
            </p>
          </Card>

          <Card className="p-6 sm:p-8">
            <div className="mb-5 flex gap-2 rounded-full bg-white/80 p-1">
              {(["login", "register"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setAuthMode(mode)}
                  className={`flex-1 rounded-full px-4 py-3 text-sm font-semibold transition ${
                    authMode === mode ? "bg-ink text-white" : "text-slate"
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
                  <Button onClick={handleLogin} disabled={loading === "auth"}>
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
                  <Button onClick={handleRegister} disabled={loading === "auth"}>
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

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl gap-6 px-4 py-6">
      <aside className="hidden w-80 shrink-0 lg:block">
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.25em] text-slate">Account</p>
              <h2 className="mt-2 font-display text-2xl text-ink">{authenticatedUser}</h2>
            </div>
            <button type="button" onClick={logout} className="rounded-full border border-ink/10 p-2 text-slate transition hover:bg-white">
              <LogOut className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-6 space-y-5">
            <div>
              <button
                type="button"
                onClick={() => setShowProfilePreferences((current) => !current)}
                className="flex w-full items-center justify-between rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-left transition hover:bg-white"
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
                  <Button variant="secondary" onClick={handleSaveProfile} disabled={loading === "saving"}>
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
                    <div key={`${trip.destination ?? "trip"}-${index}`} className="rounded-2xl bg-white/80 p-3 text-sm">
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
                  className="flex w-full items-center justify-between rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-left transition hover:bg-white"
                >
                  <span className="text-sm font-semibold text-ink">Token Usage</span>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                    {showTokenUsage ? "Hide" : "Open"}
                  </span>
                </button>
                {showTokenUsage ? (
                  <>
                    <div className="mt-3 rounded-2xl bg-white/80 p-3 text-sm text-slate">
                      <div>Current cost: ${currentTokenSummary.cost.toFixed(4)}</div>
                      <div>Input: {currentTokenSummary.input_tokens.toLocaleString()}</div>
                      <div>Output: {currentTokenSummary.output_tokens.toLocaleString()}</div>
                    </div>
                    {tokenUsageHistory.length ? (
                      <div className="mt-2 space-y-2">
                        {tokenUsageHistory.map((item) => (
                          <div key={`${item.label}-${item.cost}`} className="rounded-2xl bg-white/60 p-3 text-xs text-slate">
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

            {(hasReviewWorkspace || itinerary) && recentPlanningUpdates.length > 0 ? (
              <div className="rounded-2xl border border-ink/10 bg-white/70 p-4">
                <button
                  type="button"
                  onClick={() => setShowPlanningProgress((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                      <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                      Planning progress
                    </div>
                    <div className="mt-1 text-xs text-slate">Latest workflow milestones from the planner.</div>
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">
                    {showPlanningProgress ? "Hide" : "Show"}
                  </span>
                </button>
                {showPlanningProgress ? (
                  <div className="mt-4 space-y-2">
                    {recentPlanningUpdates.map((update, index) => (
                      <div key={`${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2 text-sm text-slate">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </Card>
      </aside>

      <main className="min-w-0 flex-1">
        <Card className="p-6 sm:p-8">
          <div className="flex flex-col gap-4 border-b border-ink/10 pb-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="font-display text-4xl text-ink">TripBreeze AI</h1>
            </div>
            <div className="flex gap-3">
              <Button variant="secondary" onClick={() => setShowModelSettings((current) => !current)}>
                <Settings2 className="mr-2 h-4 w-4" />
                Settings
              </Button>
              {!showComposer ? (
                <Button variant="secondary" onClick={() => setShowComposer(true)}>
                  Change trip details
                </Button>
              ) : null}
              <Button variant="secondary" onClick={resetTrip}>
                New Trip
              </Button>
              <button type="button" onClick={logout} className="rounded-full border border-ink/10 px-4 py-3 text-sm font-semibold text-ink transition hover:bg-white lg:hidden">
                Log Out
              </button>
            </div>
          </div>

          <div className="mt-6 space-y-5">
            {!showComposer && !itinerary ? (
              <div className="rounded-[1.4rem] border border-ink/10 bg-mist/55 px-4 py-3 text-sm text-slate">
                <span className="font-semibold text-ink">Change trip details</span> reopens the form so you can adjust dates, cities, or filters.
                {" "}
                <span className="font-semibold text-ink">Ask planner to rework results</span> reruns planning from the current review with your notes.
              </div>
            ) : null}

            {showModelSettings ? (
              <div className="rounded-[1.6rem] border border-ink/10 bg-mist/55 p-4">
                <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink">
                  <Settings2 className="h-4 w-4" />
                  Settings
                </div>
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Provider</span>
                    <select
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={form.provider}
                      onChange={(event) =>
                        setForm((current) => ({
                          ...current,
                          provider: event.target.value as PlannerForm["provider"],
                          model: event.target.value === "google" ? GOOGLE_MODELS[0] : OPENAI_MODELS[0],
                        }))
                      }
                    >
                      <option value="openai">OpenAI</option>
                      <option value="google">Google</option>
                    </select>
                  </label>
                  <label className="block">
                    <span className="mb-2 block text-sm font-medium text-slate">Model</span>
                    <select
                      className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                      value={form.model}
                      onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                    >
                      {availableModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            ) : null}

            {messages.length > 0 ? (
              hasReviewWorkspace || itinerary ? null : (
                <div className="space-y-3">
                  {messages.map((message, index) => (
                    <div
                      key={`${message.role}-${index}`}
                      className={`max-w-4xl rounded-[1.75rem] px-5 py-4 text-sm leading-7 shadow-sm ${
                        message.role === "user"
                          ? "ml-auto bg-ink text-white shadow-[0_16px_36px_rgba(16,33,43,0.18)]"
                          : "border border-ink/8 bg-white text-ink"
                      }`}
                    >
                      <div
                        className={`mb-2 text-[11px] font-semibold uppercase tracking-[0.22em] ${
                          message.role === "user" ? "text-white/60" : "text-slate"
                        }`}
                      >
                        {message.role === "user" ? "You" : "TripBreeze"}
                      </div>
                      {message.role === "assistant" ? renderMarkdownContent(message.content) : message.content}
                    </div>
                  ))}
                </div>
              )
            ) : null}

            {recentPlanningUpdates.length > 0 && !(hasReviewWorkspace || itinerary) ? (
              <div className="rounded-[1.75rem] border border-ink/10 bg-gradient-to-r from-mist/90 to-white/80 p-5">
                <button
                  type="button"
                  onClick={() => setShowPlanningProgress((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    Planning progress
                  </div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate">
                    {showPlanningProgress ? "Hide" : "Show"}
                  </span>
                </button>
                {showPlanningProgress ? (
                  <div className="mt-3 space-y-2 text-sm text-slate">
                    {recentPlanningUpdates.map((update, index) => (
                      <div key={`${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {(hasReviewWorkspace || itinerary) && recentPlanningUpdates.length > 0 ? (
              <div className="rounded-[1.6rem] border border-ink/10 bg-white/70 p-4 lg:hidden">
                <button
                  type="button"
                  onClick={() => setShowPlanningProgress((current) => !current)}
                  className="flex w-full items-center justify-between gap-3 text-left"
                >
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-ink">
                      <LoaderCircle className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                      Planning progress
                    </div>
                    <div className="mt-1 text-xs text-slate">Latest workflow milestones from the planner.</div>
                  </div>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate">
                    {showPlanningProgress ? "Hide" : "Show"}
                  </span>
                </button>
                {showPlanningProgress ? (
                  <div className="mt-4 space-y-2">
                    {recentPlanningUpdates.map((update, index) => (
                      <div key={`mobile-${update}-${index}`} className="rounded-[1.1rem] border border-ink/8 bg-white/80 px-3 py-2 text-sm text-slate">
                        {update}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}

            {hasReviewWorkspace && !finalItinerary && state?.destination_info ? (
              <div className="rounded-[1.75rem] border border-ink/10 bg-white/80 p-5">
                <div className="mb-3 text-lg font-semibold text-ink">Destination briefing</div>
                <div className="text-sm leading-7 text-ink">
                  {renderMarkdownContent(String(state.destination_info)) ?? String(state.destination_info)}
                </div>
              </div>
            ) : null}

            {hasReviewWorkspace && !finalItinerary ? (
              <div className="rounded-[1.9rem] border border-ink/10 bg-gradient-to-b from-white to-[#fbf8f3] p-5 shadow-[0_20px_50px_rgba(16,33,43,0.08)]">
                <div className="mb-5 flex items-center gap-2 text-lg font-semibold text-ink">
                  <Plane className="h-5 w-5 text-coral" />
                  Review your trip
                </div>
                <div className="mb-5 flex flex-wrap gap-2">
                  {(state?.trip_legs?.length
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
                {state?.trip_legs?.length ? (
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
                  state?.trip_legs?.length ? (
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
                                      setSelection((current) => {
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
                                          setSelection((current) => {
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
                        {(state?.flight_options ?? []).length ? (
                          (state?.flight_options ?? []).slice(0, 5).map((option, index) => (
                            <ReviewOptionCard
                              key={`flight-${index}`}
                              option={option}
                              title={`Flight ${index + 1}`}
                              variant="flight"
                              allOptions={state?.flight_options ?? []}
                              currencyCode={currencyCode}
                              selected={selection.flightIndex === index}
                              onSelect={() => {
                                setSelection((current) => ({
                                  ...current,
                                  flightIndex: index,
                                }));
                                setSelectedReturnIndex(null);
                              }}
                            />
                          ))
                        ) : (
                          <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-coral">
                            {Number((state?.budget as Record<string, unknown> | undefined)?.flights_before_budget_filter ?? 0) > 0 &&
                            Number((state?.budget as Record<string, unknown> | undefined)?.flights_after_budget_filter ?? 0) === 0
                              ? "Flights were found, but none fit the selected total trip budget."
                              : "No flights found. Try different dates or cities."}
                          </div>
                        )}
                      </div>

                      {isRoundTrip ? (
                        <div ref={returnSectionRef} className="space-y-3">
                          <div className="text-sm font-semibold text-slate">Return Flights</div>
                          {selection.flightIndex >= 0 ? (
                            returnOptions.length ? (
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
                                {String(state?.flight_options?.[selection.flightIndex]?.departure_token ?? "").trim()
                                  ? "No return flights were found for this outbound option. Choose another outbound flight to load a different return set."
                                  : "Return options will load after you choose an outbound flight."}
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
                          {(state?.hotel_options ?? []).length ? (
                            (state?.hotel_options ?? []).slice(0, 5).map((option, index) => (
                              <ReviewOptionCard
                                key={`hotel-${index}`}
                                option={option}
                                title={`Hotel ${index + 1}`}
                                variant="hotel"
                                allOptions={state?.hotel_options ?? []}
                                currencyCode={currencyCode}
                                selected={selection.hotelIndex === index}
                                onSelect={() => setSelection((current) => ({ ...current, hotelIndex: index }))}
                              />
                            ))
                          ) : (
                            <div className="rounded-[1.5rem] bg-mist/60 p-4 text-sm text-coral">
                              {Number((state?.budget as Record<string, unknown> | undefined)?.hotels_before_budget_filter ?? 0) > 0 &&
                              Number((state?.budget as Record<string, unknown> | undefined)?.hotels_after_budget_filter ?? 0) === 0
                                ? "Hotels were found, but none fit the selected total trip budget."
                                : "No hotels found. Try different dates or destination."}
                            </div>
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
                    </div>
                  )
                ) : (
                  <div className="rounded-[1.6rem] border border-dashed border-ink/15 bg-white/75 p-5 text-sm text-slate">
                    <div className="font-semibold text-ink">No bookable options are ready yet</div>
                    <div className="mt-2 leading-7">
                      The planner finished this search without flight or hotel results you can choose from here. You can still review the trip summary and notes above, then change the trip details or ask the planner to rework the results.
                    </div>
                  </div>
                )}

                {state?.transport_options?.length ? (
                  <div className="mt-5 space-y-3">
                    <div className="text-sm font-semibold text-slate">Ground Transport</div>
                    <div className="text-sm text-slate">
                      Compare trains, buses, and ferries alongside flights. Leave unselected if you'd rather fly.
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
                        onSelect={() => setSelectedTransportIndex((current) => (current === index ? null : index))}
                      />
                    ))}
                    <div>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => setSelectedTransportIndex(null)}
                        disabled={selectedTransportIndex === null}
                      >
                        Clear transport selection
                      </Button>
                    </div>
                  </div>
                ) : null}

                {state?.budget ? (
                  state.trip_legs?.length ? (
                    <div className="mt-5 rounded-[1.6rem] bg-white/75 p-4 text-sm text-slate">
                      {(() => {
                        const budget = state.budget as Record<string, unknown>;
                        const selectedFlights =
                          state.flight_options_by_leg?.map((options, index) => selectedOption(options, selection.byLegFlights[index] ?? 0)) ?? [];
                        const selectedHotels =
                          state.hotel_options_by_leg?.map((options, index) => selectedOption(options, selection.byLegHotels[index] ?? 0)) ?? [];
                        const totalFlightCost = selectedFlights.reduce((sum, item) => sum + optionTotalPrice(item), 0);
                        const totalHotelCost = selectedHotels.reduce((sum, item) => sum + Number(item.total_price ?? 0), 0);
                        const dailyExpenses = Number(budget.estimated_daily_expenses ?? 0);
                        const total = totalFlightCost + totalHotelCost + dailyExpenses;
                        const budgetLimit = Number(state.trip_request?.budget_limit ?? 0);
                        const remaining = budgetLimit - total;

                        return (
                          <>
                            <div className="mb-3 text-sm font-semibold text-ink">Budget Summary</div>
                            <div className="space-y-2">
                              <div className="flex items-center justify-between"><span>Flights ({state.trip_legs?.length} legs)</span><span className="font-semibold text-ink">{formatCurrency(totalFlightCost, currencyCode)}</span></div>
                              <div className="flex items-center justify-between"><span>Hotels</span><span className="font-semibold text-ink">{formatCurrency(totalHotelCost, currencyCode)}</span></div>
                              <div className="flex items-center justify-between"><span>Daily expenses</span><span className="font-semibold text-ink">{formatCurrency(dailyExpenses, currencyCode)}</span></div>
                              <div className="flex items-center justify-between border-t border-ink/10 pt-2 text-base"><span className="font-semibold text-ink">Total</span><span className="font-semibold text-ink">{formatCurrency(total, currencyCode)}</span></div>
                            </div>
                            {budgetLimit > 0 ? (
                              <div className={`mt-3 rounded-2xl px-3 py-2 ${remaining >= 0 ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>
                                {remaining >= 0
                                  ? `Selected options are within budget with ${formatCurrency(remaining, currencyCode)} to spare.`
                                  : `Selected options are over budget by ${formatCurrency(Math.abs(remaining), currencyCode)}.`}
                              </div>
                            ) : null}
                          </>
                        );
                      })()}
                    </div>
                  ) : showPersonalisationPanel ? (
                    <div className="mt-5 rounded-[1.6rem] bg-white/75 p-4 text-sm text-slate">
                      {(() => {
                        const budget = state.budget as Record<string, unknown>;
                        const selectedOutbound = selectedOption(state.flight_options, selection.flightIndex);
                        const selectedReturn =
                          isRoundTrip && selectedReturnIndex !== null ? returnOptions[selectedReturnIndex] ?? {} : {};
                        const selectedFlight =
                          isRoundTrip && selectedReturnIndex !== null
                            ? combineRoundTripFlight(selectedOutbound, selectedReturn)
                            : selectedOutbound;
                        const selectedHotel = selectedOption(state.hotel_options, selection.hotelIndex);
                        const selectedTransportOption =
                          selectedTransportIndex !== null ? state.transport_options?.[selectedTransportIndex] ?? {} : {};
                        const flightPrice = optionTotalPrice(selectedFlight);
                        const hotelPrice = Number(selectedHotel.total_price ?? 0);
                        const transportPrice = optionTotalPrice(selectedTransportOption);
                        const dailyExpenses = Number(budget.estimated_daily_expenses ?? 0);
                        const total = flightPrice + hotelPrice + transportPrice + dailyExpenses;
                        const budgetLimit = Number(state.trip_request?.budget_limit ?? 0);
                        const remaining = budgetLimit - total;
                        const dailyTravelers = Number(budget.daily_expense_travelers ?? 0);
                        const dailyDays = Number(budget.daily_expense_days ?? 0);
                        const dailyRate = Number(budget.daily_expense_per_traveler ?? 0);
                        const dailyDetail =
                          dailyTravelers && dailyDays && dailyRate
                            ? `${dailyTravelers} traveller(s) x ${dailyDays} day(s) x ${formatCurrency(dailyRate, currencyCode)}/day`
                            : "Estimated meals, local transport, and incidentals";

                        return (
                          <>
                            <div className="mb-3 text-sm font-semibold text-ink">Budget Summary</div>
                            <div className="space-y-2">
                              <div className="flex items-start justify-between gap-4"><span>Flight<br /><span className="text-xs text-slate">{budgetFlightDetail(selectedFlight, currencyCode)}</span></span><span className="font-semibold text-ink">{formatCurrency(flightPrice, currencyCode)}</span></div>
                              {selectedTransportIndex !== null ? (
                                <div className="flex items-start justify-between gap-4"><span>{transportLabel(selectedTransportOption.mode)}<br /><span className="text-xs text-slate">{String(selectedTransportOption.operator ?? "")} {selectedTransportOption.segments_summary ? `- ${String(selectedTransportOption.segments_summary)}` : ""}</span></span><span className="font-semibold text-ink">{formatCurrency(transportPrice, currencyCode)}</span></div>
                              ) : null}
                              <div className="flex items-start justify-between gap-4"><span>Hotel<br /><span className="text-xs text-slate">{budgetHotelDetail(selectedHotel, budget, currencyCode)}</span></span><span className="font-semibold text-ink">{formatCurrency(hotelPrice, currencyCode)}</span></div>
                              <div className="flex items-start justify-between gap-4"><span>Daily expenses<br /><span className="text-xs text-slate">{dailyDetail}</span></span><span className="font-semibold text-ink">{formatCurrency(dailyExpenses, currencyCode)}</span></div>
                              <div className="flex items-center justify-between border-t border-ink/10 pt-2 text-base"><span className="font-semibold text-ink">Selected trip estimate</span><span className="font-semibold text-ink">{formatCurrency(total, currencyCode)}</span></div>
                            </div>
                            {budgetLimit > 0 ? (
                              <div className={`mt-3 rounded-2xl px-3 py-2 ${remaining >= 0 ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"}`}>
                                {remaining >= 0
                                  ? `Selected options are within budget with ${formatCurrency(remaining, currencyCode)} to spare.`
                                  : `Selected options are over budget by ${formatCurrency(Math.abs(remaining), currencyCode)}.`}
                              </div>
                            ) : null}
                            {String(budget.budget_notes ?? "").trim() && !budgetStatusNote(budget.budget_notes) ? (
                              <div className="mt-3 rounded-2xl bg-mist/70 px-3 py-2 text-slate">
                                {String(budget.budget_notes)}
                              </div>
                            ) : null}
                          </>
                        );
                      })()}
                    </div>
                  ) : null
                ) : null}
                {state?.trip_legs?.length && !canApprove ? (
                  <div className="mt-3 text-sm text-coral">Please select a flight and hotel for each leg before approving.</div>
                ) : null}
                {isRoundTrip && selection.flightIndex >= 0 && selectedReturnIndex === null ? (
                  <div className="mt-3 text-sm text-coral">Choose a return flight before approving this round trip.</div>
                ) : null}

                {showPersonalisationPanel ? (
                  <>
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
                          {interests.length ? interests.map(sentenceLabel).join(", ") : "No interests yet"}{" "}
                          • {sentenceLabel(pace)} pace
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
                                  setInterests((current) =>
                                    active ? current.filter((value) => value !== interest) : [...current, interest],
                                  )
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

                    <textarea
                      className="mt-5 h-24 w-full rounded-[1.6rem] border border-ink/10 bg-white/80 px-4 py-3 text-sm outline-none transition focus:border-coral"
                      placeholder="Add notes for the itinerary or ask for changes."
                      value={feedback}
                      onChange={(event) => setFeedback(event.target.value)}
                    />

                    <div className="mt-4 flex flex-wrap gap-3">
	                      <Button
	                        onClick={() => handleReview("rewrite_itinerary")}
	                        disabled={loading !== null || !canApprove}
                      >
                        {loading === "approving" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                        Approve and Generate Itinerary
	                      </Button>
	                      <Button variant="secondary" onClick={() => handleReview("revise_plan")} disabled={loading !== null}>
                        Ask planner to rework results
	                      </Button>
	                    </div>
                  </>
                ) : null}
              </div>
            ) : null}

	            {finalItinerary ? (
	              <div className="rounded-[1.9rem] border border-ink/10 bg-gradient-to-br from-[#fffaf4] via-white to-[#f6f1ea] p-5 shadow-[0_24px_60px_rgba(16,33,43,0.08)]">
		                <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
		                  <div>
		                    <div className="text-lg font-semibold text-ink">Final itinerary</div>
		                    <div className="text-sm text-slate">Your approved trip plan is ready to read, download, or email.</div>
		                  </div>
		                  <div className="rounded-[1.5rem] border border-ink/10 bg-white/85 p-4 xl:min-w-[24rem]">
		                    <div className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate">Save or share</div>
		                    <div className="flex flex-wrap gap-3">
		                      <Button variant="secondary" onClick={handleDownloadPdf} disabled={loading !== null}>
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
		                        <Button onClick={handleEmailItinerary} disabled={loading !== null}>
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
	            ) : null}
          </div>

          {clarificationQuestion ? (
            <div className="mt-6 rounded-[1.75rem] border border-coral/30 bg-coral/10 p-5">
              <div className="text-sm font-semibold text-coral">More information needed</div>
              <div className="mt-2 text-sm text-slate">Answer this to continue planning your current trip.</div>
              <textarea
                className="mt-3 h-24 w-full rounded-3xl border border-white/80 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                value={clarificationAnswer}
                onChange={(event) => setClarificationAnswer(event.target.value)}
                placeholder="Type your answer here..."
              />
              <div className="mt-4">
                <Button onClick={handleClarification} disabled={loading !== null || !clarificationAnswer.trim()}>
                  {loading === "clarifying" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : null}
                  Continue Planning
                </Button>
              </div>
            </div>
          ) : null}

          {showComposer ? (
            <div className="mt-6 rounded-[1.75rem] border border-ink/10 bg-mist/70 p-5">
              <textarea
                className="h-28 w-full rounded-3xl border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                placeholder="Describe your trip..."
                value={form.freeText}
                onChange={(event) => setForm((current) => ({ ...current, freeText: event.target.value }))}
              />

              <details className="mt-4 rounded-3xl bg-white/70 p-4">
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
                </div>

                <label className="block">
                  <span className="mb-2 block text-sm font-medium text-slate">Special Requests (optional)</span>
                  <input
                    className="w-full rounded-full border border-ink/10 bg-white px-4 py-3 text-sm outline-none transition focus:border-coral"
                    value={form.preferences}
                    onChange={(event) => setForm((current) => ({ ...current, preferences: event.target.value }))}
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
                <Button onClick={handlePlanTrip} disabled={loading !== null}>
                  {loading === "planning" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                  Search Trip
                </Button>
                <Button variant="secondary" onClick={handleVoiceInput} disabled={loading === "voice"}>
                  {loading === "voice" ? <LoaderCircle className="mr-2 h-4 w-4 animate-spin" /> : <AudioLines className="mr-2 h-4 w-4" />}
                  {recording ? "Stop Recording" : "Voice Input"}
                </Button>
              </div>

              {error ? <p className="mt-4 text-sm text-coral">{error}</p> : null}
            </div>
          ) : null}
        </Card>
      </main>

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
      <datalist id="airlines">
        {airlines.map((airline) => (
          <option key={airline} value={airline} />
        ))}
      </datalist>
    </div>
  );
}
