export const CHAT_PROVIDERS = ["openai", "gemini"] as const;
export const TRAVEL_CLASSES = ["ECONOMY", "PREMIUM_ECONOMY", "BUSINESS", "FIRST"] as const;
export const CURRENCIES = ["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SGD", "AED", "NZD"] as const;
export const HOTEL_STARS = [5, 4, 3, 2, 1] as const;
export const INTEREST_OPTIONS = ["food", "history", "nature", "art", "nightlife", "shopping", "outdoors", "family"] as const;
export const PACE_OPTIONS = ["relaxed", "moderate", "packed"] as const;
export const PLANNER_PROMPT_CHIPS = [
  "I want to fly from Berlin to Tokyo from 2026-06-10 to 2026-06-17 for 2 travelers with a budget of 3000 EUR.",
  "Paris for 3 nights, Barcelona for 2 nights next month.",
  "A week in Lisbon for 2 in October, direct flights only, budget 2500 EUR.",
] as const;
export const OPENAI_MODELS = [
  "gpt-5-mini",
  "gpt-5.2",
  "gpt-5-nano",
  "gpt-4o-mini",
  "gpt-4.1-mini",
  "gpt-4.1-nano",
] as const;
export const GEMINI_MODELS = [
  "gemini-2.5-flash",
  "gemini-2.5-flash-lite",
  "gemini-2.5-pro",
] as const;
