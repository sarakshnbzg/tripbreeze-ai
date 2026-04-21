import type { ReactNode } from "react";

import { formatCurrency, type PlannerForm, type SelectionState } from "@/lib/planner";
import type { TravelState, TripOption } from "@/lib/types";

import { HOTEL_STARS } from "./constants";

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

function renderInlineMarkdown(text: string): ReactNode[] {
  const parts: ReactNode[] = [];
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

export function renderMarkdownContent(content: string) {
  const normalized = content
    .replace(/\r\n/g, "\n")
    .replace(/([^\n])\s(#{2,6}\s)/g, "$1\n$2")
    .trim();

  if (!normalized) {
    return null;
  }

  const lines = normalized.split("\n");
  const nodes: ReactNode[] = [];
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

export function selectionLabel(option: Record<string, unknown>, fallback: string) {
  return String(option.name ?? option.airline ?? option.operator ?? fallback);
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

export function combineRoundTripFlight(outbound: Record<string, unknown>, returnFlight: Record<string, unknown>) {
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

export function injectBookingLinks(
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

export function summariseTokenUsage(tokenUsage: TravelState["token_usage"] = []) {
  return {
    input_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.input_tokens ?? 0), 0),
    output_tokens: tokenUsage.reduce((sum, item) => sum + Number(item.output_tokens ?? 0), 0),
    cost: tokenUsage.reduce((sum, item) => sum + Number(item.cost ?? 0), 0),
  };
}

export function optionTotalPrice(option: Record<string, unknown>) {
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

export function flightBadges(options: TripOption[], option: TripOption) {
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

export function hotelBadges(options: TripOption[], option: TripOption) {
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

export function budgetStatusNote(note: unknown) {
  const text = String(note ?? "").trim().toLowerCase();
  return text.includes("within budget") || text.includes("exceeds your budget") || text.includes("to spare");
}

export function compressStarPreferences(stars: number[]) {
  const selected = [...new Set(stars.map((star) => Number(star)).filter((star) => HOTEL_STARS.includes(star as (typeof HOTEL_STARS)[number])))]
    .sort((a, b) => a - b);
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

export function expandStarThresholds(thresholds: number[]) {
  const expanded = new Set<number>();
  for (const threshold of thresholds) {
    if (!HOTEL_STARS.includes(threshold as (typeof HOTEL_STARS)[number])) {
      continue;
    }
    for (let value = threshold; value <= 5; value += 1) {
      expanded.add(value);
    }
  }
  return [...expanded].sort((a, b) => a - b);
}

export function budgetFlightDetail(option: Record<string, unknown>, currencyCode: string) {
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

export function budgetHotelDetail(option: Record<string, unknown>, budget: Record<string, unknown>, currencyCode: string) {
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

export function sentenceLabel(value: string) {
  if (!value) {
    return value;
  }
  return value.charAt(0).toUpperCase() + value.slice(1);
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

export function flightPricePills(option: TripOption, currencyCode: string) {
  const adults = Math.max(1, Number(option.adults ?? 1));
  const perPerson = Number(option.price ?? 0);
  const total = Number(option.total_price ?? option.price ?? 0);
  const pills = {
    standard: [] as string[],
    highlighted: "",
  };

  if (perPerson > 0) {
    pills.standard.push(`${formatCurrency(perPerson, currencyCode)}/person`);
  }
  if (total > 0 && (adults > 1 || total !== perPerson)) {
    pills.highlighted = `${formatCurrency(total, currencyCode)} total`;
  }

  return pills;
}

export function hotelMetaPills(option: TripOption, currencyCode: string, ratingLabel: string) {
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

export function hotelStarSummary(option: TripOption) {
  const stars = Number(option.hotel_class ?? 0);
  if (stars <= 0) {
    return "";
  }

  return `${"★".repeat(stars)} ${stars}-star hotel`;
}

export function isMultiCitySelectionComplete(state: TravelState | null, selection: SelectionState) {
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

export function formatHourLabel(hour: number) {
  const safeHour = Math.max(0, Math.min(23, hour));
  return `${safeHour.toString().padStart(2, "0")}:00`;
}

export function hotelRating(option: TripOption) {
  return hotelRatingLabel(option.rating);
}

export function hotelBreakfast(option: Record<string, unknown>) {
  return hotelBreakfastStatus(option);
}

export function stopLabel(stops: unknown) {
  return formatStops(stops);
}
