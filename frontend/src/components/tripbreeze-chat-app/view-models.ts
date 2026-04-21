import { formatCurrency } from "@/lib/planner";
import type { TravelState } from "@/lib/types";

import {
  readRecord,
  readRecordArray,
  readString,
  selectionLabel,
  transportLabel,
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

export type ItineraryViewModel = {
  finalItinerary: string;
  snapshotItems: ItinerarySnapshotItem[];
  bookingLinks: Array<{ label: string; url: string }>;
  primarySections: ItinerarySection[];
  secondarySections: ItinerarySection[];
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
  const finalSelectedFlight = readRecord(state?.selected_flight);
  const finalSelectedHotel = readRecord(state?.selected_hotel);
  const finalSelectedTransport = readRecord(state?.selected_transport);
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
        finalSelectedTransport,
        travelers,
        estimatedTotal,
        budgetLimit,
        currencyCode,
      });

  const bookingLinks = buildBookingLinks({
    tripLegs,
    finalSelectedFlight,
    finalSelectedHotel,
    finalSelectedTransport,
    finalSelectedFlights,
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

  return {
    finalItinerary,
    snapshotItems,
    bookingLinks,
    primarySections,
    secondarySections,
    itineraryLegs,
    itineraryDays,
  };
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
  finalSelectedTransport,
  travelers,
  estimatedTotal,
  budgetLimit,
  currencyCode,
}: {
  tripRequest: Record<string, unknown>;
  finalSelectedFlight: Record<string, unknown>;
  finalSelectedHotel: Record<string, unknown>;
  finalSelectedTransport: Record<string, unknown>;
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
}

function buildBookingLinks({
  tripLegs,
  finalSelectedFlight,
  finalSelectedHotel,
  finalSelectedTransport,
  finalSelectedFlights,
  finalSelectedHotels,
}: {
  tripLegs: Array<Record<string, unknown>>;
  finalSelectedFlight: Record<string, unknown>;
  finalSelectedHotel: Record<string, unknown>;
  finalSelectedTransport: Record<string, unknown>;
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

  const transportUrl = readString(finalSelectedTransport.booking_url);
  if (transportUrl) {
    links.push({ label: `${transportLabel(finalSelectedTransport.mode)} booking`, url: transportUrl });
  }

  return links;
}
