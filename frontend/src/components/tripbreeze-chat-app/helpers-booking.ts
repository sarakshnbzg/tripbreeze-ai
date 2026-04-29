export function combineRoundTripFlight(outbound: Record<string, unknown>, returnFlight: Record<string, unknown>) {
  const outboundTotal = Number(outbound.total_price ?? outbound.price ?? 0);
  const returnTotal = Number(returnFlight.total_price ?? returnFlight.price ?? 0);
  const totalPrice = returnTotal || outboundTotal;
  const adults = Math.max(1, Number(outbound.adults ?? 1));
  const price = adults > 1 ? Number((totalPrice / adults).toFixed(2)) : totalPrice;
  return {
    ...outbound,
    return_summary: String(returnFlight.return_summary ?? outbound.return_summary ?? ""),
    return_details_available: true,
    outbound_total_price: outboundTotal,
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
