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
});
