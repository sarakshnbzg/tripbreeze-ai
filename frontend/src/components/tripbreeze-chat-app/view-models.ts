import { formatCurrency } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

import {
  readRecord,
  readRecordArray,
  readString,
  selectionLabel,
} from "./helpers";

export type ItinerarySnapshotItem = {
  label: string;
  value: string;
};

export type ItinerarySection = {
  key: string;
  title: string;
  content: string;
};

export type ItineraryMapPoint = {
  latitude: number;
  longitude: number;
  label: string;
  kind: "hotel" | "activity";
  dayNumber?: number;
  detail?: string;
  mapsUrl?: string;
};

export type ItineraryViewModel = {
  finalItinerary: string;
  hasStructuredItinerary: boolean;
  fallbackNotice: { title: string; detail: string } | null;
  snapshotItems: ItinerarySnapshotItem[];
  bookingLinks: Array<{ label: string; url: string }>;
  primarySections: ItinerarySection[];
  secondarySections: ItinerarySection[];
  mapPoints: ItineraryMapPoint[];
  itineraryLegs: Array<Record<string, unknown>>;
  itineraryDays: Array<Record<string, unknown>>;
};

export function buildItineraryViewModel({
  state,
  itinerary,
  currencyCode,
}: {
  state: TravelState | null;
  itinerary: string;
  currencyCode: string;
}): ItineraryViewModel {
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
  const hasStructuredItinerary = Object.keys(itineraryData).length > 0;
  const finaliserMetadata = readRecord(state?.finaliser_metadata);
  const finalSelectedFlight = readRecord(state?.selected_flight);
  const finalSelectedHotel = readRecord(state?.selected_hotel);
  const finalSelectedFlights = readRecordArray(state?.selected_flights);
  const finalSelectedHotels = readRecordArray(state?.selected_hotels);
  const travelers = Math.max(1, Number(tripRequest.num_travelers ?? 1));
  const tripLegs = state?.trip_legs ?? [];
  const budgetLimit = Number(tripRequest.budget_limit ?? 0);
  const estimatedTotal = Number(budgetData.total_estimated_cost ?? 0);

  const snapshotItems = tripLegs.length
    ? buildMultiCitySnapshotItems({
        tripLegs,
        tripRequest,
        finalSelectedFlights,
        finalSelectedHotels,
        travelers,
        estimatedTotal,
        budgetLimit,
        currencyCode,
      })
    : buildSingleDestinationSnapshotItems({
        tripRequest,
        finalSelectedFlight,
        finalSelectedHotel,
        travelers,
        estimatedTotal,
        budgetLimit,
        currencyCode,
      });

  const bookingLinks = buildBookingLinks({
    tripLegs,
    finalSelectedFlight,
    finalSelectedHotel,
    finalSelectedFlights,
    finalSelectedHotels,
  });
  const mapPoints = buildMapPoints({
    tripLegs,
    itineraryDays,
    finalSelectedHotel,
    finalSelectedHotels,
  });

  const primarySections = [
    itineraryFlightDetails ? { key: "flight", title: "Flight details", content: itineraryFlightDetails } : null,
    itineraryHotelDetails ? { key: "hotel", title: "Hotel details", content: itineraryHotelDetails } : null,
    itineraryBudget ? { key: "budget", title: "Budget breakdown", content: itineraryBudget } : null,
    itineraryVisa ? { key: "visa", title: "Visa and entry", content: itineraryVisa } : null,
  ].filter((section): section is ItinerarySection => Boolean(section));

  const secondarySections = [
    itineraryHighlights ? { key: "highlights", title: "Destination highlights", content: itineraryHighlights } : null,
    itineraryPacking ? { key: "packing", title: "Packing tips", content: itineraryPacking } : null,
  ].filter((section): section is ItinerarySection => Boolean(section));
  const fallbackNotice = buildFallbackNotice(finaliserMetadata);

  return {
    finalItinerary,
    hasStructuredItinerary,
    fallbackNotice,
    snapshotItems,
    bookingLinks,
    primarySections,
    secondarySections,
    mapPoints,
    itineraryLegs,
    itineraryDays,
  };
}

function buildFallbackNotice(finaliserMetadata: Record<string, unknown>) {
  const usedFallback = Boolean(finaliserMetadata.used_fallback);
  if (!usedFallback) {
    return null;
  }

  const fallbackReason = readString(finaliserMetadata.fallback_reason);
  let detail =
    "TripBreeze recovered this itinerary from your approved trip details after the planner hit an issue.";

  if (fallbackReason === "no_tool_calls" || fallbackReason === "missing_final_tool") {
    detail =
      "The planner did not finish the structured itinerary step, so TripBreeze recovered this itinerary from your approved trip details.";
  } else if (fallbackReason === "structured_parse_failed") {
    detail =
      "The planner returned malformed itinerary data, so TripBreeze recovered this itinerary from your approved trip details.";
  }

  return {
    title: "Recovered itinerary",
    detail,
  };
}

function toFiniteNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildPointKey(point: ItineraryMapPoint): string {
  return [
    point.kind,
    point.label.trim().toLowerCase(),
    point.dayNumber ?? "",
    point.latitude.toFixed(5),
    point.longitude.toFixed(5),
  ].join("|");
}

function dedupePoints(points: ItineraryMapPoint[]): ItineraryMapPoint[] {
  const seen = new Set<string>();
  const deduped: ItineraryMapPoint[] = [];

  points.forEach((point) => {
    const key = buildPointKey(point);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    deduped.push(point);
  });

  return deduped;
}

function buildMapPoints({
  tripLegs,
  itineraryDays,
  finalSelectedHotel,
  finalSelectedHotels,
}: {
  tripLegs: Array<Record<string, unknown>>;
  itineraryDays: Array<Record<string, unknown>>;
  finalSelectedHotel: Record<string, unknown>;
  finalSelectedHotels: Array<Record<string, unknown>>;
}): ItineraryMapPoint[] {
  const points: ItineraryMapPoint[] = [];

  if (tripLegs.length) {
    finalSelectedHotels.forEach((hotel, index) => {
      const point = buildHotelPoint(
        hotel,
        readString(tripLegs[index]?.destination) || `Stop ${index + 1}`,
      );
      if (point) {
        points.push(point);
      }
    });
  } else {
    const point = buildHotelPoint(finalSelectedHotel);
    if (point) {
      points.push(point);
    }
  }

  itineraryDays.forEach((day, index) => {
    const dayNumber = Number(day.day_number ?? index + 1);
    const activities = readRecordArray(day.activities);
    const dayTheme = readString(day.theme);

    activities.forEach((activity, activityIndex) => {
      const latitude = toFiniteNumber(activity.latitude);
      const longitude = toFiniteNumber(activity.longitude);
      if (latitude === null || longitude === null) {
        return;
      }

      const name = readString(activity.name) || `Activity ${activityIndex + 1}`;
      const detailParts = [
        readString(activity.time_of_day),
        readString(activity.address),
        dayTheme,
      ].filter(Boolean);
      points.push({
        latitude,
        longitude,
        label: name,
        kind: "activity",
        dayNumber: Number.isFinite(dayNumber) ? dayNumber : index + 1,
        detail: detailParts.join(" · "),
        mapsUrl: buildGoogleMapsUrl({
          mapsUrl: readString(activity.maps_url),
          label: name,
          address: readString(activity.address),
          latitude,
          longitude,
        }),
      });
    });
  });

  return dedupePoints(points);
}

function buildHotelPoint(hotel: Record<string, unknown>, fallbackLabel = "Hotel"): ItineraryMapPoint | null {
  const latitude = toFiniteNumber(hotel.latitude);
  const longitude = toFiniteNumber(hotel.longitude);
  if (latitude === null || longitude === null) {
    return null;
  }

  const label = readString(hotel.name) || fallbackLabel;
  const detailParts = [
    readString(hotel.address),
    readString(hotel.description),
  ].filter(Boolean);

  return {
    latitude,
    longitude,
    label,
    kind: "hotel",
    detail: detailParts.join(" · "),
    mapsUrl: buildGoogleMapsUrl({
      label,
      address: readString(hotel.address),
      latitude,
      longitude,
    }),
  };
}

function buildGoogleMapsUrl({
  mapsUrl,
  label,
  address,
  latitude,
  longitude,
}: {
  mapsUrl?: string;
  label?: string;
  address?: string;
  latitude?: number | null;
  longitude?: number | null;
}): string {
  if (mapsUrl) {
    return mapsUrl;
  }

  if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
    return `https://www.google.com/maps/search/?api=1&query=${latitude},${longitude}`;
  }

  const query = [label, address].filter(Boolean).join(" ").trim();
  if (!query) {
    return "";
  }

  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`;
}

function buildMultiCitySnapshotItems({
  tripLegs,
  tripRequest,
  finalSelectedFlights,
  finalSelectedHotels,
  travelers,
  estimatedTotal,
  budgetLimit,
  currencyCode,
}: {
  tripLegs: Array<Record<string, unknown>>;
  tripRequest: Record<string, unknown>;
  finalSelectedFlights: Array<Record<string, unknown>>;
  finalSelectedHotels: Array<Record<string, unknown>>;
  travelers: number;
  estimatedTotal: number;
  budgetLimit: number;
  currencyCode: string;
}): ItinerarySnapshotItem[] {
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

function buildSingleDestinationSnapshotItems({
  tripRequest,
  finalSelectedFlight,
  finalSelectedHotel,
  travelers,
  estimatedTotal,
  budgetLimit,
  currencyCode,
}: {
  tripRequest: Record<string, unknown>;
  finalSelectedFlight: Record<string, unknown>;
  finalSelectedHotel: Record<string, unknown>;
  travelers: number;
  estimatedTotal: number;
  budgetLimit: number;
  currencyCode: string;
}): ItinerarySnapshotItem[] {
  const origin = String(tripRequest.origin ?? "").trim();
  const destination = String(tripRequest.destination ?? "").trim();
  const departureDate = String(tripRequest.departure_date ?? "").trim();
  const returnDate = String(tripRequest.return_date ?? "").trim();
  const selectedFlightLabel = Object.keys(finalSelectedFlight).length ? selectionLabel(finalSelectedFlight, "Selected flight") : "Chosen flight";
  const selectedHotelLabel = Object.keys(finalSelectedHotel).length ? selectionLabel(finalSelectedHotel, "Selected hotel") : "Chosen hotel";

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
    { label: "Stay", value: selectedHotelLabel },
  ];
}

function buildBookingLinks({
  tripLegs,
  finalSelectedFlight,
  finalSelectedHotel,
  finalSelectedFlights,
  finalSelectedHotels,
}: {
  tripLegs: Array<Record<string, unknown>>;
  finalSelectedFlight: Record<string, unknown>;
  finalSelectedHotel: Record<string, unknown>;
  finalSelectedFlights: Array<Record<string, unknown>>;
  finalSelectedHotels: Array<Record<string, unknown>>;
}) {
  const links: Array<{ label: string; url: string }> = [];

  if (tripLegs.length) {
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

  return links;
}
