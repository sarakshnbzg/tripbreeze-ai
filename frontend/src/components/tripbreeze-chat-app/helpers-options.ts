import { formatCurrency } from "@/lib/planner";
import type { TripOption } from "@/lib/types";

import { HOTEL_STARS } from "./constants";

export function selectionLabel(option: Record<string, unknown>, fallback: string) {
  return String(option.name ?? option.airline ?? option.operator ?? fallback);
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

export function stopLabel(stops: unknown) {
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

export function hotelRating(option: TripOption) {
  const label = hotelRatingLabel(option.rating);
  return label ? `${label}` : "";
}

export function hotelBreakfast(option: TripOption) {
  return hotelBreakfastStatus(option);
}

export function hotelStarSummary(option: TripOption) {
  const stars = Number(option.hotel_class ?? 0);
  if (!Number.isFinite(stars) || stars <= 0) {
    return "";
  }
  return `${"★".repeat(stars)} ${stars}-star hotel`;
}

export function formatHourLabel(hour: number) {
  const normalized = ((hour % 24) + 24) % 24;
  return `${String(normalized).padStart(2, "0")}:00`;
}
