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

async function signInAndOpenPlanner(page: Page) {
  await mockReferenceData(page);
  await mockLogin(page);
  await page.goto("/");

  await page.getByLabel("Username").fill("sara@example.com");
  await page.getByLabel("Password").fill("long-password");
  await page.getByRole("button", { name: "Log In" }).last().click();

  await expect(page.getByPlaceholder("Describe your trip...")).toBeVisible();
}

test.use({
  viewport: { width: 834, height: 1112 },
});

test("captures tablet planner, review, and itinerary states", async ({ page }) => {
  await signInAndOpenPlanner(page);
  await mockPlannerFlow(page);

  await page.screenshot({ path: "test-results/tablet-planner.png", fullPage: true });

  await page.getByPlaceholder("Describe your trip...").fill("Plan a summer trip to Lisbon.");
  await page.getByRole("button", { name: "Search Trip" }).click();

  await expect(page.getByText("One quick detail")).toBeVisible();
  await page.getByPlaceholder("Type your answer here...").fill("Depart on June 10 and stay 4 nights.");
  await page.getByRole("button", { name: "Continue Planning" }).click();

  await expect(page.getByText("Review your trip")).toBeVisible();
  await page.screenshot({ path: "test-results/tablet-review.png", fullPage: true });

  await page.getByRole("button", { name: /skyways/i }).click();
  await page.getByRole("button", { name: /river hotel/i }).click();
  await page.getByRole("button", { name: /food/i }).click();
  await page.getByRole("button", { name: /packed/i }).click();
  await page.getByRole("button", { name: "Approve and Generate Itinerary" }).click();

  await expect(page.getByText("Final itinerary")).toBeVisible();
  await page.screenshot({ path: "test-results/tablet-itinerary.png", fullPage: true });
});
