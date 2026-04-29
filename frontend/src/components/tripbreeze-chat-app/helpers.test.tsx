import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import {
  buildResolvedRequestDataPoints,
  buildResolvedRequestSummary,
  buildTripSummary,
  compressStarPreferences,
  createDefaultSelection,
  expandStarThresholds,
  renderMarkdownContent,
  safeErrorMessage,
} from "./helpers";

describe("tripbreeze helpers", () => {
  it("creates an empty default selection", () => {
    expect(createDefaultSelection()).toEqual({
      flightIndex: -1,
      hotelIndex: -1,
      byLegFlights: [],
      byLegHotels: [],
    });
  });

  it("compresses and re-expands hotel star thresholds", () => {
    const compressed = compressStarPreferences([3, 4, 5]);
    expect(compressed).toEqual([3]);
    expect(expandStarThresholds(compressed)).toEqual([3, 4, 5]);
  });

  it("builds a readable single-destination summary", () => {
    const summary = buildTripSummary(
      {
        trip_request: {
          origin: "Berlin",
          destination: "Paris",
          departure_date: "2026-06-10",
          return_date: "2026-06-15",
          num_travelers: 2,
          budget_limit: 1500,
        },
      },
      "EUR",
    );

    expect(summary).toContain("Berlin -> Paris");
    expect(summary).toContain("2026-06-10 to 2026-06-15");
    expect(summary).toContain("2 travelers");
  });

  it("builds a multi-city summary from trip legs", () => {
    const summary = buildTripSummary(
      {
        trip_request: {
          origin: "Berlin",
          departure_date: "2026-06-10",
          num_travelers: 1,
        },
        trip_legs: [
          { origin: "Berlin", destination: "Paris", departure_date: "2026-06-10", nights: 3 },
          { origin: "Paris", destination: "Barcelona", departure_date: "2026-06-13", nights: 4 },
        ],
      },
      "EUR",
    );

    expect(summary).toContain("Berlin");
    expect(summary).toContain("Paris -> Barcelona");
    expect(summary).toContain("1 traveler");
  });

  it("prefers the resolved trip request over the initial typed message", () => {
    const summary = buildResolvedRequestSummary(
      {
        trip_request: {
          origin: "Vienna",
          destination: "Tokyo",
          departure_date: "2026-10-10",
          return_date: "2026-10-18",
          num_travelers: 1,
        },
      },
      "EUR",
      "Fly from Vienna to Tokyo for 8 nights in October with a mid-range hotel near Shibuya.",
    );

    expect(summary).toContain("Vienna -> Tokyo");
    expect(summary).toContain("2026-10-10 to 2026-10-18");
    expect(summary).not.toContain("mid-range hotel near Shibuya");
  });

  it("builds resolved request data points from interpreted trip details", () => {
    const items = buildResolvedRequestDataPoints(
      {
        trip_request: {
          origin: "Vienna",
          destination: "Tokyo",
          departure_date: "2026-10-10",
          return_date: "2026-10-18",
          num_travelers: 2,
          hotel_stars: [4, 5],
          hotel_stars_user_specified: true,
          hotel_budget_tier: "MID_RANGE",
          hotel_area: "Shibuya",
          budget_limit: 3000,
        },
      },
      "EUR",
    );

    expect(items).toEqual(
      expect.arrayContaining([
        { label: "Route", value: "Vienna -> Tokyo" },
        { label: "Dates", value: "2026-10-10 to 2026-10-18" },
        { label: "Travelers", value: "2 travelers" },
        { label: "Hotel stars", value: "4-star and up" },
        { label: "Hotel tier", value: "Mid Range" },
        { label: "Hotel area", value: "Shibuya" },
      ]),
    );
  });

  it("builds multi-city request data points from trip legs", () => {
    const items = buildResolvedRequestDataPoints(
      {
        trip_request: {
          departure_date: "2026-07-01",
          return_date: "2026-07-08",
          num_travelers: 2,
          hotel_stars: [3, 4, 5],
          hotel_stars_user_specified: true,
        },
        trip_legs: [
          { origin: "Berlin", destination: "Paris", departure_date: "2026-07-01", nights: 3 },
          { origin: "Paris", destination: "Barcelona", departure_date: "2026-07-04", nights: 4 },
          { origin: "Barcelona", destination: "Berlin", departure_date: "2026-07-08", nights: 0 },
        ],
      },
      "EUR",
    );

    expect(items).toEqual(
      expect.arrayContaining([
        { label: "Route", value: "Berlin -> Paris -> Barcelona -> Berlin" },
        { label: "Dates", value: "2026-07-01 to 2026-07-08" },
        { label: "Travelers", value: "2 travelers" },
        { label: "Stops", value: "2 cities" },
        { label: "Hotel stars", value: "3-star and up" },
      ]),
    );
  });

  it("falls back to the original typed message when no structured trip request exists", () => {
    const summary = buildResolvedRequestSummary(
      null,
      "EUR",
      "Fly from Vienna to Tokyo for 8 nights in October with a mid-range hotel near Shibuya.",
    );

    expect(summary).toBe("Fly from Vienna to Tokyo for 8 nights in October with a mid-range hotel near Shibuya.");
  });

  it("renders split booking urls as compact links", () => {
    render(
      <>
        {renderMarkdownContent(`- Property: River Hotel
- Booking:
https://example.com/hotels/river?very=long&url=true`)}
      </>,
    );

    const link = screen.getByRole("link", { name: "Open booking link" });
    expect(link).toHaveAttribute("href", "https://example.com/hotels/river?very=long&url=true");
    expect(screen.queryByText(/https:\/\/example.com\/hotels/)).not.toBeInTheDocument();
  });

  it("returns safe error messages", () => {
    expect(safeErrorMessage(new Error("boom"))).toBe("boom");
    expect(safeErrorMessage("unknown")).toBe("Something went wrong.");
  });
});
