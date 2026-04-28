import { describe, expect, it } from "vitest";

import {
  buildStructuredFields,
  resetPlannerFormForFreshFreeText,
  resetPlannerFormAfterSubmit,
  type PlannerForm,
} from "@/lib/planner";

function buildForm(overrides: Partial<PlannerForm> = {}): PlannerForm {
  return {
    freeText: "",
    hasEditedStructuredInputs: false,
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

  it("clears stale advanced filters after submit while preserving identity and model settings", () => {
    const nextForm = resetPlannerFormAfterSubmit(
      buildForm({
        freeText: "Fly from Vienna to Tokyo",
        destination: "Tokyo",
        departureDate: "2026-10-04",
        directOnly: true,
        includeAirlines: "ANA",
        excludeAirlines: "Ryanair",
        maxFlightDurationHours: 10,
        travelClass: "BUSINESS",
        hotelStars: [4],
        provider: "openai",
        model: "gpt-4.1",
        temperature: 0.6,
      }),
      {
        authenticatedUser: "user-123",
        homeCity: "Berlin",
      },
    );

    expect(nextForm.freeText).toBe("");
    expect(nextForm.destination).toBe("");
    expect(nextForm.departureDate).toBe("");
    expect(nextForm.directOnly).toBe(false);
    expect(nextForm.includeAirlines).toBe("");
    expect(nextForm.excludeAirlines).toBe("");
    expect(nextForm.maxFlightDurationHours).toBe(0);
    expect(nextForm.travelClass).toBe("ECONOMY");
    expect(nextForm.hotelStars).toEqual([]);
    expect(nextForm.userId).toBe("user-123");
    expect(nextForm.origin).toBe("Berlin");
    expect(nextForm.provider).toBe("openai");
    expect(nextForm.model).toBe("gpt-4.1");
    expect(nextForm.temperature).toBe(0.6);
  });

  it("starts a fresh free-text brief by clearing stale advanced filters on first input", () => {
    const nextForm = resetPlannerFormForFreshFreeText(
      buildForm({
        directOnly: true,
        hotelStars: [4],
        includeAirlines: "ANA",
        maxFlightDurationHours: 10,
        model: "gpt-4.1",
        temperature: 0.6,
      }),
      "Fly from Vienna to Tokyo for 8 nights in October.",
    );

    expect(nextForm.freeText).toBe("Fly from Vienna to Tokyo for 8 nights in October.");
    expect(nextForm.directOnly).toBe(false);
    expect(nextForm.hotelStars).toEqual([]);
    expect(nextForm.includeAirlines).toBe("");
    expect(nextForm.maxFlightDurationHours).toBe(0);
    expect(nextForm.origin).toBe("Berlin");
    expect(nextForm.model).toBe("gpt-4.1");
    expect(nextForm.temperature).toBe(0.6);
  });

  it("treats a replaced free-text brief as a fresh query when no structured inputs were explicitly edited", () => {
    const nextForm = resetPlannerFormForFreshFreeText(
      buildForm({
        freeText: "Old trip to Rome",
        departureDate: "2026-05-01",
        returnDate: "2026-05-05",
        destination: "Rome",
        directOnly: true,
        hasEditedStructuredInputs: false,
      }),
      "Paris for 3 days, then Barcelona for 4 days, then fly home.",
    );

    expect(nextForm.freeText).toBe("Paris for 3 days, then Barcelona for 4 days, then fly home.");
    expect(nextForm.departureDate).toBe("");
    expect(nextForm.returnDate).toBe("");
    expect(nextForm.destination).toBe("");
    expect(nextForm.directOnly).toBe(false);
    expect(nextForm.hasEditedStructuredInputs).toBe(false);
  });

  it("preserves structured inputs while editing a free-text brief when the user explicitly set them", () => {
    const nextForm = resetPlannerFormForFreshFreeText(
      buildForm({
        freeText: "Trip to Rome",
        departureDate: "2026-05-01",
        hasEditedStructuredInputs: true,
      }),
      "Trip to Rome in early May",
    );

    expect(nextForm.freeText).toBe("Trip to Rome in early May");
    expect(nextForm.departureDate).toBe("2026-05-01");
    expect(nextForm.hasEditedStructuredInputs).toBe(true);
  });
});
