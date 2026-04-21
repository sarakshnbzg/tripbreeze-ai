import { describe, expect, it } from "vitest";

import {
  buildTripSummary,
  compressStarPreferences,
  createDefaultSelection,
  expandStarThresholds,
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

  it("returns safe error messages", () => {
    expect(safeErrorMessage(new Error("boom"))).toBe("boom");
    expect(safeErrorMessage("unknown")).toBe("Something went wrong.");
  });
});
