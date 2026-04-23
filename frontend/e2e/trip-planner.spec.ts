import { expect, test, type Page } from "@playwright/test";

const API_BASE = "http://127.0.0.1:8100";

function sse(events: Array<{ event: string; data: unknown }>) {
  return events
    .map(({ event, data }) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join("");
}

async function mockReferenceData(page: Page) {
  await page.route(`${API_BASE}/api/reference-values/*`, async (route) => {
    const url = route.request().url();
    const category = url.split("/").pop() ?? "";
    const values =
      category === "cities"
        ? ["Berlin", "Lisbon", "Porto"]
        : category === "countries"
          ? ["Germany", "Portugal"]
          : ["SkyWays", "Coastal Air"];
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ category, values }),
    });
  });
}

async function mockLogin(page: Page) {
  await page.route(`${API_BASE}/api/auth/login`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "sara@example.com",
        profile: {
          home_city: "Berlin",
          passport_country: "Germany",
          travel_class: "ECONOMY",
        },
      }),
    });
  });
}

async function mockPlannerFlow(page: Page) {
  await page.route(`${API_BASE}/api/search`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "trip_intake", label: "Understanding your trip request..." } },
        {
          event: "clarification",
          data: {
            thread_id: "thread-123",
            question: "What departure date works for you?",
            missing_fields: ["departure_date"],
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });

  await page.route(`${API_BASE}/api/search/thread-123/clarify`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "research", label: "Researching flights, hotels, and destination info..." } },
        {
          event: "state",
          data: {
            thread_id: "thread-123",
            current_step: "awaiting_review",
            trip_request: {
              origin: "Berlin",
              destination: "Lisbon",
              departure_date: "2026-06-10",
              check_out_date: "2026-06-14",
              num_travelers: 1,
              currency: "EUR",
            },
            destination_info: "### Entry requirements\nPassport should be valid for your stay.",
            budget: {
              total_estimated_cost: 860,
            },
            flight_options: [
              {
                airline: "SkyWays",
                outbound_summary: "Berlin to Lisbon · 09:00 departure",
                total_price: 320,
                booking_url: "https://example.com/flights/skyways",
              },
            ],
            hotel_options: [
              {
                name: "River Hotel",
                description: "Central boutique stay near the tram line.",
                total_price: 540,
                booking_url: "https://example.com/hotels/river",
              },
            ],
            messages: [
              {
                role: "assistant",
                content: "Select the flight and hotel that fit you best.",
              },
            ],
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });

  await page.route(`${API_BASE}/api/search/thread-123/approve`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "finalise", label: "Finalising your itinerary..." } },
        { event: "token", data: { content: "## Lisbon itinerary" } },
        { event: "token", data: { content: "\nDay 1: arrive and explore Alfama." } },
        {
          event: "state",
          data: {
            thread_id: "thread-123",
            final_itinerary: "## Lisbon itinerary\nDay 1: arrive and explore Alfama.",
            selected_flight: {
              airline: "SkyWays",
              booking_url: "https://example.com/flights/skyways",
            },
            selected_hotel: {
              name: "River Hotel",
              booking_url: "https://example.com/hotels/river",
            },
            itinerary_data: {
              flight_details: "SkyWays nonstop from Berlin to Lisbon.",
              hotel_details: "River Hotel with breakfast included.",
              budget_breakdown: "Flights and hotel stay within budget.",
              packing_tips: "Bring a light jacket for the evening breeze.",
              daily_plans: [
                {
                  day_number: 1,
                  theme: "Arrival",
                  date: "2026-06-10",
                  weather: {
                    condition: "Sunny",
                    temp_min: 18,
                    temp_max: 27,
                  },
                  activities: [
                    {
                      name: "Check in and sunset walk",
                      time_of_day: "Afternoon",
                      notes: "Settle in before heading to the riverfront.",
                    },
                  ],
                },
              ],
            },
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });
}

async function mockRevisionPlannerFlow(
  page: Page,
  capture: { approvePayload: Record<string, unknown> | null },
) {
  await page.route(`${API_BASE}/api/search`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "research", label: "Researching flights, hotels, and destination info..." } },
        {
          event: "state",
          data: {
            thread_id: "thread-revise",
            current_step: "awaiting_review",
            trip_request: {
              origin: "Berlin",
              destination: "Lisbon",
              departure_date: "2026-06-10",
              check_out_date: "2026-06-14",
              num_travelers: 1,
              currency: "EUR",
            },
            destination_info: "### Lisbon briefing\nBest for riverside walks and food markets.",
            budget: {
              total_estimated_cost: 860,
            },
            flight_options: [
              {
                airline: "SkyWays",
                outbound_summary: "Berlin to Lisbon · 09:00 departure",
                total_price: 320,
                booking_url: "https://example.com/flights/skyways",
              },
            ],
            hotel_options: [
              {
                name: "River Hotel",
                description: "Central boutique stay near the tram line.",
                total_price: 540,
                booking_url: "https://example.com/hotels/river",
              },
            ],
            messages: [
              {
                role: "assistant",
                content: "Select the flight and hotel that fit you best.",
              },
            ],
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });

  await page.route(`${API_BASE}/api/search/thread-revise/approve`, async (route) => {
    capture.approvePayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "trip_intake", label: "Reworking your plan with the new feedback..." } },
        {
          event: "state",
          data: {
            thread_id: "thread-revise",
            current_step: "awaiting_review",
            trip_request: {
              origin: "Berlin",
              destination: "Porto",
              departure_date: "2026-06-10",
              check_out_date: "2026-06-14",
              num_travelers: 1,
              currency: "EUR",
            },
            destination_info: "### Porto briefing\nA more budget-friendly option with riverside views and wine cellars.",
            budget: {
              total_estimated_cost: 640,
            },
            flight_options: [
              {
                airline: "Coastal Air",
                outbound_summary: "Berlin to Porto · 08:10 departure",
                total_price: 240,
                booking_url: "https://example.com/flights/coastal-air",
              },
            ],
            hotel_options: [
              {
                name: "Harbor Hotel",
                description: "Relaxed stay near Ribeira with breakfast included.",
                total_price: 400,
                booking_url: "https://example.com/hotels/harbor",
              },
            ],
            messages: [
              {
                role: "assistant",
                content: "I reworked the plan with cheaper Porto options.",
              },
            ],
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });
}

async function mockMultiCityPlannerFlow(
  page: Page,
  capture: {
    searchPayload: Record<string, unknown> | null;
    approvePayload: Record<string, unknown> | null;
  },
) {
  await page.route(`${API_BASE}/api/search`, async (route) => {
    capture.searchPayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "research", label: "Researching each leg of your trip..." } },
        {
          event: "state",
          data: {
            thread_id: "thread-multi",
            current_step: "awaiting_review",
            trip_request: {
              origin: "Berlin",
              departure_date: "2026-07-10",
              return_date: "2026-07-15",
              num_travelers: 1,
              currency: "EUR",
            },
            trip_legs: [
              {
                origin: "Berlin",
                destination: "Lisbon",
                departure_date: "2026-07-10",
                nights: 3,
                needs_hotel: true,
              },
              {
                origin: "Lisbon",
                destination: "Porto",
                departure_date: "2026-07-13",
                nights: 2,
                needs_hotel: true,
              },
              {
                origin: "Porto",
                destination: "Berlin",
                departure_date: "2026-07-15",
                nights: 0,
                needs_hotel: false,
              },
            ],
            destination_info: "### Portugal entry requirements\nValid passport required for the trip.",
            budget: {
              total_estimated_cost: 980,
            },
            flight_options_by_leg: [
              [
                {
                  airline: "Atlantic Air",
                  outbound_summary: "Berlin to Lisbon · 08:15 departure",
                  total_price: 220,
                  booking_url: "https://example.com/flights/atlantic-air",
                },
              ],
              [
                {
                  airline: "Coastal Hopper",
                  outbound_summary: "Lisbon to Porto · 11:00 departure",
                  total_price: 120,
                  booking_url: "https://example.com/flights/coastal-hopper",
                },
              ],
              [
                {
                  airline: "Homebound Jet",
                  outbound_summary: "Porto to Berlin · 17:40 departure",
                  total_price: 260,
                  booking_url: "https://example.com/flights/homebound-jet",
                },
              ],
            ],
            hotel_options_by_leg: [
              [
                {
                  name: "Lisbon Lights Hotel",
                  description: "Boutique stay near Baixa.",
                  total_price: 360,
                  booking_url: "https://example.com/hotels/lisbon-lights",
                },
              ],
              [
                {
                  name: "Porto Riverside Hotel",
                  description: "Waterside rooms with breakfast.",
                  total_price: 280,
                  booking_url: "https://example.com/hotels/porto-riverside",
                },
              ],
              [],
            ],
            messages: [
              {
                role: "assistant",
                content: "Choose flights and hotels for each leg before generating the itinerary.",
              },
            ],
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });

  await page.route(`${API_BASE}/api/search/thread-multi/approve`, async (route) => {
    capture.approvePayload = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { event: "node_start", data: { node: "finalise", label: "Finalising your multi-city itinerary..." } },
        { event: "token", data: { content: "## Portugal route" } },
        { event: "token", data: { content: "\nDay 1: arrive in Lisbon and settle in." } },
        {
          event: "state",
          data: {
            thread_id: "thread-multi",
            final_itinerary: "## Portugal route\nDay 1: arrive in Lisbon and settle in.",
            selected_flights: [
              {
                airline: "Atlantic Air",
                booking_url: "https://example.com/flights/atlantic-air",
              },
              {
                airline: "Coastal Hopper",
                booking_url: "https://example.com/flights/coastal-hopper",
              },
              {
                airline: "Homebound Jet",
                booking_url: "https://example.com/flights/homebound-jet",
              },
            ],
            selected_hotels: [
              {
                name: "Lisbon Lights Hotel",
                booking_url: "https://example.com/hotels/lisbon-lights",
              },
              {
                name: "Porto Riverside Hotel",
                booking_url: "https://example.com/hotels/porto-riverside",
              },
              {},
            ],
            trip_legs: [
              {
                origin: "Berlin",
                destination: "Lisbon",
                departure_date: "2026-07-10",
                nights: 3,
              },
              {
                origin: "Lisbon",
                destination: "Porto",
                departure_date: "2026-07-13",
                nights: 2,
              },
              {
                origin: "Porto",
                destination: "Berlin",
                departure_date: "2026-07-15",
                nights: 0,
              },
            ],
            itinerary_data: {
              destination_highlights: "Lisbon and Porto pair well for food, neighborhoods, and riverside views.",
              budget_breakdown: "Flights and hotels remain within the multi-city budget.",
              visa_entry_info: "Portugal is visa-free for this itinerary.",
              packing_tips: "Bring layers for breezy evenings between cities.",
              legs: [
                {
                  leg_number: 1,
                  origin: "Berlin",
                  destination: "Lisbon",
                  departure_date: "2026-07-10",
                  flight_summary: "Atlantic Air nonstop to Lisbon.",
                  hotel_summary: "Lisbon Lights Hotel near Baixa.",
                },
                {
                  leg_number: 2,
                  origin: "Lisbon",
                  destination: "Porto",
                  departure_date: "2026-07-13",
                  flight_summary: "Coastal Hopper midday to Porto.",
                  hotel_summary: "Porto Riverside Hotel near the Douro.",
                },
                {
                  leg_number: 3,
                  origin: "Porto",
                  destination: "Berlin",
                  departure_date: "2026-07-15",
                  flight_summary: "Homebound Jet evening return to Berlin.",
                  hotel_summary: "",
                },
              ],
              daily_plans: [
                {
                  day_number: 1,
                  theme: "Arrival in Lisbon",
                  date: "2026-07-10",
                  activities: [
                    {
                      name: "Check in and riverside walk",
                      time_of_day: "Afternoon",
                      notes: "Ease into the trip near Praça do Comércio.",
                    },
                  ],
                },
                {
                  day_number: 4,
                  theme: "Transfer to Porto",
                  date: "2026-07-13",
                  activities: [
                    {
                      name: "Hotel check-in and sunset by the Douro",
                      time_of_day: "Evening",
                      notes: "Keep the transfer day light.",
                    },
                  ],
                },
              ],
            },
          },
        },
        { event: "done", data: {} },
      ]),
    });
  });
}

async function signInAndOpenPlanner(page: Page) {
  await mockReferenceData(page);
  await mockLogin(page);
  await page.goto("/");

  await page.getByLabel("Username").fill("sara@example.com");
  await page.getByLabel("Password").fill("long-password");
  await page.getByRole("button", { name: "Log In" }).last().click();

  await expect(page.getByPlaceholder("Describe your trip...")).toBeVisible();
}

async function completePlannerJourney(page: Page) {
  await signInAndOpenPlanner(page);
  await mockPlannerFlow(page);

  await page.getByPlaceholder("Describe your trip...").fill("Plan a summer trip to Lisbon.");
  await page.getByRole("button", { name: "Search Trip" }).click();

  await expect(page.getByText("More information needed")).toBeVisible();
  await page.getByPlaceholder("Type your answer here...").fill("Depart on June 10 and stay 4 nights.");
  await page.getByRole("button", { name: "Continue Planning" }).click();

  await expect(page.getByText("Review your trip")).toBeVisible();
  await page.getByRole("button", { name: /skyways/i }).click();
  await page.getByRole("button", { name: /river hotel/i }).click();
  await page.getByRole("button", { name: /food/i }).click();
  await page.getByRole("button", { name: /packed/i }).click();
  await page.getByRole("button", { name: "Approve and Generate Itinerary" }).click();

  await expect(page.getByText("Final itinerary")).toBeVisible();
  await expect(page.getByText("Trip snapshot")).toBeVisible();
  await expect(page.getByText("Check in and sunset walk")).toBeVisible();
}

test("completes the planner journey through clarification and itinerary generation", async ({ page }) => {
  await completePlannerJourney(page);

  await expect(page.getByRole("link", { name: "Flight booking" })).toHaveAttribute(
    "href",
    "https://example.com/flights/skyways",
  );
  await expect(page.getByText("Packing tips")).toBeVisible();
});

test("emails the final itinerary from the review workspace", async ({ page }) => {
  await completePlannerJourney(page);

  let emailPayload: { recipient_email?: unknown; final_itinerary?: unknown } | null = null;
  await page.route(`${API_BASE}/api/itinerary/email`, async (route) => {
    emailPayload = route.request().postDataJSON() as { recipient_email?: unknown; final_itinerary?: unknown };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        message: "Sent to sara@example.com",
      }),
    });
  });

  await page.getByPlaceholder("your.email@example.com").fill("sara@example.com");
  await page.getByRole("button", { name: "Email itinerary" }).click();

  await expect.poll(() => emailPayload).not.toBeNull();
  const submittedPayload = emailPayload as unknown as {
    recipient_email?: unknown;
    final_itinerary?: unknown;
  } | null;
  if (!submittedPayload) {
    throw new Error("Expected itinerary email payload to be captured.");
  }
  expect(submittedPayload.recipient_email).toBe("sara@example.com");
  expect(String(submittedPayload.final_itinerary ?? "")).toContain("Lisbon itinerary");
});

test("revises the review plan and returns to the workspace with refreshed options", async ({ page }) => {
  const capture = { approvePayload: null as Record<string, unknown> | null };
  await signInAndOpenPlanner(page);
  await mockRevisionPlannerFlow(page, capture);

  await page.getByPlaceholder("Describe your trip...").fill("Plan a summer trip to Lisbon.");
  await page.getByRole("button", { name: "Search Trip" }).click();

  await expect(page.getByText("Review your trip")).toBeVisible();
  await page.getByRole("button", { name: /skyways/i }).click();
  await page.getByRole("button", { name: /river hotel/i }).click();
  await page.getByRole("button", { name: /food/i }).click();
  await page.getByRole("button", { name: /relaxed/i }).click();
  await page.getByPlaceholder("Add notes for the itinerary or ask for changes.").fill(
    "Find a cheaper option in Porto with a calmer pace.",
  );
  await page.getByRole("button", { name: "Ask planner to rework results" }).click();

  await expect.poll(() => capture.approvePayload).not.toBeNull();
  const submittedPayload = capture.approvePayload;
  if (!submittedPayload) {
    throw new Error("Expected revise_plan payload to be captured.");
  }

  expect(submittedPayload.feedback_type).toBe("revise_plan");
  expect(submittedPayload.user_feedback).toBe("Find a cheaper option in Porto with a calmer pace.");
  expect((submittedPayload.selected_flight as { airline?: unknown }).airline).toBe("SkyWays");
  expect((submittedPayload.selected_hotel as { name?: unknown }).name).toBe("River Hotel");
  expect((submittedPayload.trip_request as { pace?: unknown }).pace).toBe("relaxed");
  expect((submittedPayload.trip_request as { interests?: unknown }).interests).toEqual(["food"]);

  await expect(page.getByText("Porto briefing")).toBeVisible();
  await expect(page.getByRole("button", { name: /coastal air/i })).toBeVisible();
  await expect(page.getByRole("button", { name: /harbor hotel/i })).toBeVisible();
  await expect(page.getByText("Final itinerary")).not.toBeVisible();
});

test("completes a multi-city planner journey with leg-by-leg review and final itinerary output", async ({ page }) => {
  const capture = {
    searchPayload: null as Record<string, unknown> | null,
    approvePayload: null as Record<string, unknown> | null,
  };
  await signInAndOpenPlanner(page);
  await mockMultiCityPlannerFlow(page, capture);

  await page.getByText("Refine your search (optional)").click();
  await page.getByLabel("Multi-city trip").check();
  await page.getByLabel("From (Origin City)").fill("Berlin");
  await page.getByLabel("Departure Date").fill("2026-07-10");
  await page.locator('input[list="cities"]').nth(1).fill("Lisbon");
  await page.getByLabel("Nights").first().fill("3");
  await page.getByRole("button", { name: "Add another destination" }).click();
  await page.locator('input[list="cities"]').nth(2).fill("Porto");
  await page.getByLabel("Nights").nth(1).fill("2");
  await page.getByRole("button", { name: "Search Trip" }).click();

  await expect.poll(() => capture.searchPayload).not.toBeNull();
  const submittedSearch = capture.searchPayload;
  if (!submittedSearch) {
    throw new Error("Expected multi-city search payload to be captured.");
  }
  expect((submittedSearch.structured_fields as { return_to_origin?: unknown }).return_to_origin).toBe(true);
  expect(
    ((submittedSearch.structured_fields as { multi_city_legs?: Array<Record<string, unknown>> }).multi_city_legs ?? [])
      .length,
  ).toBe(2);

  await expect(page.getByText("Multi-city progress:")).toBeVisible();
  await page.getByRole("button", { name: /atlantic air/i }).click();
  await page.getByRole("button", { name: /lisbon lights hotel/i }).click();
  await page.getByRole("button", { name: /coastal hopper/i }).click();
  await page.getByRole("button", { name: /porto riverside hotel/i }).click();
  await page.getByRole("button", { name: /homebound jet/i }).click();
  await page.getByRole("button", { name: /food/i }).click();
  await page.getByRole("button", { name: /packed/i }).click();
  await page.getByRole("button", { name: "Approve and Generate Itinerary" }).click();

  await expect.poll(() => capture.approvePayload).not.toBeNull();
  const submittedApprove = capture.approvePayload;
  if (!submittedApprove) {
    throw new Error("Expected multi-city approve payload to be captured.");
  }
  expect(((submittedApprove.selected_flights as Array<Record<string, unknown>>) ?? []).length).toBe(3);
  expect(((submittedApprove.selected_hotels as Array<Record<string, unknown>>) ?? []).length).toBe(3);
  expect((submittedApprove.trip_request as { pace?: unknown }).pace).toBe("packed");

  await expect(page.getByText("Final itinerary")).toBeVisible();
  await expect(page.getByText("Trip legs")).toBeVisible();
  await expect(page.getByText("Check in and riverside walk")).toBeVisible();
  await expect(page.getByRole("link", { name: "Leg 1 flight" })).toHaveAttribute(
    "href",
    "https://example.com/flights/atlantic-air",
  );
  await expect(page.getByRole("link", { name: "Leg 2 hotel" })).toHaveAttribute(
    "href",
    "https://example.com/hotels/porto-riverside",
  );
});
