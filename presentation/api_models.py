"""Request and response models for the FastAPI backend."""

from typing import Any

from pydantic import BaseModel


class SearchRequest(BaseModel):
    user_id: str = "default_user"
    free_text_query: str | None = None
    structured_fields: dict[str, Any] | None = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3


class ApproveRequest(BaseModel):
    user_feedback: str = ""
    feedback_type: str = "rewrite_itinerary"
    selected_flight: dict[str, Any] = {}
    selected_hotel: dict[str, Any] = {}
    selected_transport: dict[str, Any] = {}
    selected_flights: list[dict[str, Any]] = []
    selected_hotels: list[dict[str, Any]] = []
    trip_request: dict[str, Any] | None = None
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.3


class ClarifyRequest(BaseModel):
    answer: str


class ReturnFlightRequest(BaseModel):
    origin: str
    destination: str
    departure_date: str
    return_date: str
    departure_token: str
    adults: int = 1
    travel_class: str = "ECONOMY"
    currency: str = "EUR"
    return_time_window: list[int] | None = None


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    profile: dict[str, Any] | None = None


class SaveProfileRequest(BaseModel):
    profile: dict[str, Any]


class ItineraryPdfRequest(BaseModel):
    final_itinerary: str
    graph_state: dict[str, Any] | None = None
    file_name: str = "trip_itinerary.pdf"


class ItineraryEmailRequest(BaseModel):
    recipient_email: str
    recipient_name: str = ""
    final_itinerary: str
    graph_state: dict[str, Any] | None = None
