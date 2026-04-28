import { describe, expect, it } from "vitest";

import { buildStructuredFields, type PlannerForm } from "@/lib/planner";

function buildForm(overrides: Partial<PlannerForm> = {}): PlannerForm {
  return {
    freeText: "",
    origin: "Berlin",
    destination: "Vienna",
    departureDate: "2026-04-27",
    returnDate: "",
    multiCity: false,
    oneWay: true,
    numNights: 2,
    travelers: 1,
    budgetLimit: 0,
    currency: "EUR",
    preferences: "",
    includeAirlines: "",
    excludeAirlines: "",
    maxFlightDurationHours: 0,
    directOnly: false,
    travelClass: "ECONOMY",
    hotelStars: [],
    multiCityLegs: [{ destination: "", nights: 3 }],
    userId: "default_user",
    provider: "openai",
    model: "gpt-4o-mini",
    temperature: 0.3,
    ...overrides,
  };
}

describe("planner helpers", () => {
  it("computes one-way check-out date from the departure date without timezone drift", () => {
    const fields = buildStructuredFields(buildForm());

    expect(fields.check_out_date).toBe("2026-04-29");
  });

  it("does not set an empty check-out date when the departure date is invalid", () => {
    const fields = buildStructuredFields(buildForm({ departureDate: "not-a-date" }));

    expect(fields).not.toHaveProperty("check_out_date");
  });

  it("adds max flight duration and excluded airlines from refine controls", () => {
    const fields = buildStructuredFields(
      buildForm({
        maxFlightDurationHours: 10,
        excludeAirlines: "Ryanair, easyJet",
      }),
    );

    expect(fields.max_duration).toBe(600);
    expect(fields.preferences).toContain("Exclude these airlines: Ryanair, easyJet.");
  });

  it("adds included airlines from refine controls", () => {
    const fields = buildStructuredFields(
      buildForm({
        includeAirlines: "Lufthansa, Air France",
      }),
    );

    expect(fields.preferences).toContain("Only include these airlines: Lufthansa, Air France.");
  });

  it("merges special requests with excluded airlines into one preferences string", () => {
    const fields = buildStructuredFields(
      buildForm({
        preferences: "Window seat if possible.",
        includeAirlines: "Lufthansa",
        excludeAirlines: "Ryanair",
      }),
    );

    expect(fields.preferences).toBe(
      "Window seat if possible. Only include these airlines: Lufthansa. Exclude these airlines: Ryanair.",
    );
  });

  it("does not send the default economy cabin as an active refinement", () => {
    const fields = buildStructuredFields(buildForm({ travelClass: "ECONOMY" }));

    expect(fields).not.toHaveProperty("travel_class");
  });

  it("sends travel class when the user chooses a non-default cabin", () => {
    const fields = buildStructuredFields(buildForm({ travelClass: "BUSINESS" }));

    expect(fields.travel_class).toBe("BUSINESS");
  });
});
