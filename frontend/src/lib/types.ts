export type LlmProvider = "openai";

export type UserProfile = {
  user_id?: string;
  home_city?: string;
  passport_country?: string;
  travel_class?: string;
  preferred_airlines?: string[];
  preferred_hotel_stars?: number[];
  preferred_outbound_time_window?: number[];
  preferred_return_time_window?: number[];
  past_trips?: Array<Record<string, unknown>>;
};

export type SearchRequest = {
  user_id: string;
  free_text_query?: string;
  structured_fields?: Record<string, unknown>;
  llm_provider: LlmProvider;
  llm_model: string;
  llm_temperature: number;
};

export type ApproveRequest = {
  user_feedback: string;
  feedback_type: "rewrite_itinerary" | "revise_plan" | "cancel";
  selected_flight?: Record<string, unknown>;
  selected_hotel?: Record<string, unknown>;
  selected_flights?: Record<string, unknown>[];
  selected_hotels?: Record<string, unknown>[];
  trip_request?: Record<string, unknown>;
  llm_provider: LlmProvider;
  llm_model: string;
  llm_temperature: number;
};

export type StreamEventType =
  | "node_start"
  | "node_message"
  | "clarification"
  | "token"
  | "state"
  | "error"
  | "done";

export type StreamEvent = {
  event: StreamEventType;
  data: Record<string, unknown>;
};

export type TripOption = {
  [key: string]: unknown;
  name?: string;
  airline?: string;
  duration?: string;
  price?: number;
  total_price?: number;
  rating?: number;
  amenities?: string[];
  description?: string;
  booking_url?: string;
  stops?: number;
  outbound_summary?: string;
  return_summary?: string;
};

export type TravelState = {
  thread_id?: string;
  current_step?: string;
  messages?: Array<{ role: string; content: string }>;
  token_usage?: Array<{
    input_tokens?: number;
    output_tokens?: number;
    cost?: number;
    node?: string;
  }>;
  trip_request?: Record<string, unknown>;
  trip_legs?: Array<Record<string, unknown>>;
  budget?: Record<string, unknown>;
  destination_info?: Record<string, unknown>;
  rag_sources?: string[];
  final_itinerary?: string;
  finaliser_metadata?: Record<string, unknown>;
  itinerary_data?: Record<string, unknown>;
  itinerary_cover?: Record<string, unknown>;
  flight_options?: TripOption[];
  hotel_options?: TripOption[];
  search_inputs?: Record<string, unknown>;
  search_inputs_by_leg?: Array<Record<string, unknown>>;
  selected_flight?: TripOption;
  selected_hotel?: TripOption;
  flight_options_by_leg?: TripOption[][];
  hotel_options_by_leg?: TripOption[][];
  selected_flights?: TripOption[];
  selected_hotels?: TripOption[];
  user_profile?: UserProfile;
};

export type AuthResponse = {
  user_id: string;
  profile: UserProfile;
  csrf_token: string;
};
