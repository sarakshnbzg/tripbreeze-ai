"""Trip planning flow orchestration - API calls and state management."""

import re
import time

import streamlit as st

from presentation import api_client
from infrastructure.llms.model_factory import get_provider_status
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _stream_text(text: str, delay: float = 0.008):
    """Yield text token-by-token with a small delay for a typewriter effect."""
    for token in re.split(r"(\s+)", text):
        yield token
        if token.strip():
            time.sleep(delay)


def _stream_finalisation_tokens(chunks, delay: float = 0.01):
    """Pace backend token events so the final itinerary reveals more naturally."""
    for chunk in chunks:
        yield chunk
        if not chunk or not chunk.strip():
            continue

        # Slow down slightly at section boundaries so markdown-heavy output
        # feels closer to a live assistant response than a single dump.
        if chunk.startswith("####") or chunk == "\n\n":
            time.sleep(delay * 3)
        else:
            time.sleep(delay)


def _append_assistant_message(content: str) -> None:
    st.session_state.messages.append({"role": "assistant", "content": content})


def _archive_current_token_usage() -> None:
    from presentation.streamlit_app import _summarise_token_usage, _build_token_usage_label

    state = st.session_state.get("graph_state")
    if not state or state.get("_token_usage_archived"):
        return
    usage_list = state.get("token_usage", [])
    if not usage_list:
        return

    summary = _summarise_token_usage(usage_list)
    label = _build_token_usage_label(state, index=len(st.session_state.token_usage_history) + 1)
    st.session_state.token_usage_history.insert(0, {"label": label, **summary})
    st.session_state.token_usage_history = st.session_state.token_usage_history[:5]
    state["_token_usage_archived"] = True


def run_initial_planning(
    user_message: str,
    structured_fields: dict | None = None,
    free_text_query: str | None = None,
) -> None:
    logger.info(
        "Starting initial planning for user_id=%s provider=%s model=%s",
        st.session_state.user_id,
        st.session_state.llm_provider,
        st.session_state.llm_model,
    )
    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        logger.warning("Selected provider is not ready: %s", provider_message)
        _append_assistant_message(
            f"I can't use the selected provider yet: {provider_message}"
        )
        st.error(provider_message)
        return

    request: dict = {
        "user_id": st.session_state.user_id,
        "llm_provider": st.session_state.llm_provider,
        "llm_model": st.session_state.llm_model,
        "llm_temperature": st.session_state.llm_temperature,
    }
    if structured_fields is not None:
        request["structured_fields"] = structured_fields
    if free_text_query:
        request["free_text_query"] = free_text_query

    try:
        _archive_current_token_usage()
        result: dict = {}
        clarification: dict = {}
        with st.status("Planning your trip...", expanded=True) as status:
            for event_type, data in api_client.stream_search(request):
                if event_type == "node_start":
                    st.write(data.get("label", ""))
                elif event_type == "node_message":
                    st.write(data.get("content", ""))
                elif event_type == "clarification":
                    clarification = data
                    st.session_state.thread_id = data.get("thread_id", "")
                elif event_type == "state":
                    result = data
                    st.session_state.thread_id = data.get("thread_id", "")
                elif event_type == "error":
                    raise RuntimeError(data.get("detail", "Unknown error"))
            if clarification:
                status.update(label="Need a bit more info...", state="complete", expanded=False)
            else:
                status.update(label="Trip research complete!", state="complete", expanded=False)
    except Exception as exc:
        logger.exception("Initial planning failed")
        _append_assistant_message(f"I hit an error while planning your trip: {exc}")
        st.error(f"Planning failed: {exc}")
        return

    if clarification:
        question = clarification.get("question", "Could you provide more details?")
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_question = question
        st.session_state.messages.append({"role": "assistant", "content": question})
        with st.chat_message("assistant"):
            st.write_stream(_stream_text(question))
        return

    st.session_state.graph_state = result
    logger.info("Initial planning completed current_step=%s", result.get("current_step"))
    latest_assistant_message = next(
        (
            message for message in reversed(result.get("messages", []))
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )
    if latest_assistant_message:
        st.session_state.messages.append(latest_assistant_message)
        with st.chat_message("assistant"):
            st.write_stream(_stream_text(latest_assistant_message["content"]))
    st.session_state.awaiting_review = result.get("current_step") == "awaiting_review"


def run_clarification(answer: str) -> None:
    """Send the user's clarification answer and resume planning."""
    logger.info("Sending clarification answer for thread_id=%s", st.session_state.thread_id)
    st.session_state.awaiting_clarification = False
    st.session_state.clarification_question = ""

    try:
        result: dict = {}
        clarification: dict = {}
        with st.status("Continuing trip planning...", expanded=True) as status:
            for event_type, data in api_client.stream_clarify(
                st.session_state.thread_id, answer,
            ):
                if event_type == "node_start":
                    st.write(data.get("label", ""))
                elif event_type == "node_message":
                    st.write(data.get("content", ""))
                elif event_type == "clarification":
                    clarification = data
                elif event_type == "state":
                    result = data
                elif event_type == "error":
                    raise RuntimeError(data.get("detail", "Unknown error"))
            if clarification:
                status.update(label="Need a bit more info...", state="complete", expanded=False)
            else:
                status.update(label="Trip research complete!", state="complete", expanded=False)
    except Exception as exc:
        logger.exception("Clarification failed")
        _append_assistant_message(f"I hit an error while planning your trip: {exc}")
        st.error(f"Planning failed: {exc}")
        return

    if clarification:
        question = clarification.get("question", "Could you provide more details?")
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_question = question
        st.session_state.messages.append({"role": "assistant", "content": question})
        with st.chat_message("assistant"):
            st.write_stream(_stream_text(question))
        return

    st.session_state.graph_state = result
    logger.info("Clarification resumed, current_step=%s", result.get("current_step"))
    latest_assistant_message = next(
        (
            message for message in reversed(result.get("messages", []))
            if message.get("role") == "assistant" and message.get("content")
        ),
        None,
    )
    if latest_assistant_message:
        st.session_state.messages.append(latest_assistant_message)
        with st.chat_message("assistant"):
            st.write_stream(_stream_text(latest_assistant_message["content"]))
    st.session_state.awaiting_review = result.get("current_step") == "awaiting_review"


def inject_booking_links(
    markdown: str,
    flight: dict,
    hotel: dict,
    flights: list[dict] | None = None,
    hotels: list[dict] | None = None,
) -> str:
    """Insert booking links inline after the relevant itinerary sections.

    Used only for the user-facing message - the stored `final_itinerary` (and thus
    the PDF and email exports) stays link-free.
    """
    def _insert_after_section(md: str, heading: str, link_line: str) -> str:
        idx = md.find(heading)
        if idx == -1:
            return md
        next_idx = md.find("\n#### ", idx + len(heading))
        insertion = f"\n\n{link_line}\n"
        if next_idx == -1:
            return md.rstrip() + insertion
        return md[:next_idx] + insertion + md[next_idx:]

    def _insert_into_leg(md: str, leg_number: int, link_lines: list[str]) -> str:
        if not link_lines:
            return md
        anchor = f"**Leg {leg_number}:"
        idx = md.find(anchor)
        if idx == -1:
            return md
        next_leg_idx = md.find(f"\n\n**Leg {leg_number + 1}:", idx + len(anchor))
        next_section_idx = md.find("\n\n#### ", idx + len(anchor))
        boundaries = [pos for pos in (next_leg_idx, next_section_idx) if pos != -1]
        insert_at = min(boundaries) if boundaries else len(md)
        insertion = "\n" + "\n".join(link_lines)
        return md[:insert_at] + insertion + md[insert_at:]

    flight_url = (flight or {}).get("booking_url")
    hotel_url = (hotel or {}).get("booking_url")
    result = markdown
    if flight_url:
        airline = (flight or {}).get("airline") or "this flight"
        result = _insert_after_section(
            result,
            "#### 🛫 Flight Details",
            f"🔗 **[Book {airline} on Google Flights]({flight_url})**",
        )
    if hotel_url:
        name = (hotel or {}).get("name") or "this hotel"
        result = _insert_after_section(
            result,
            "#### 🏨 Hotel Details",
            f"🔗 **[Book {name}]({hotel_url})**",
        )

    selected_flights = flights or []
    selected_hotels = hotels or []
    if selected_flights or selected_hotels:
        total_legs = max(len(selected_flights), len(selected_hotels))
        for leg_number in range(1, total_legs + 1):
            leg_flight = selected_flights[leg_number - 1] if leg_number - 1 < len(selected_flights) else {}
            leg_hotel = selected_hotels[leg_number - 1] if leg_number - 1 < len(selected_hotels) else {}
            link_lines = []
            leg_flight_url = (leg_flight or {}).get("booking_url")
            leg_hotel_url = (leg_hotel or {}).get("booking_url")
            if leg_flight_url:
                airline = (leg_flight or {}).get("airline") or "flight"
                link_lines.append(f"- 🔗 **[Book {airline} on Google Flights]({leg_flight_url})**")
            if leg_hotel_url:
                name = (leg_hotel or {}).get("name") or "hotel"
                link_lines.append(f"- 🔗 **[Book {name}]({leg_hotel_url})**")
            result = _insert_into_leg(result, leg_number, link_lines)
    return result


def run_finalisation(feedback: str = "") -> None:
    state = st.session_state.graph_state
    if not state:
        st.error("No trip data to finalise. Please start a new search.")
        return

    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        logger.warning("Selected provider is not ready for finalisation: %s", provider_message)
        _append_assistant_message(
            f"I can't use the selected provider yet: {provider_message}"
        )
        st.error(provider_message)
        return

    approve_request = {
        "user_feedback": feedback,
        "feedback_type": "rewrite_itinerary",
        "selected_flight": state.get("selected_flight", {}),
        "selected_hotel": state.get("selected_hotel", {}),
        "selected_flights": state.get("selected_flights", []),
        "selected_hotels": state.get("selected_hotels", []),
        "trip_request": state.get("trip_request", {}),
        "llm_provider": st.session_state.llm_provider,
        "llm_model": st.session_state.llm_model,
        "llm_temperature": st.session_state.llm_temperature,
    }

    try:
        def _itinerary_chunks():
            for event_type, data in api_client.stream_approve(
                st.session_state.thread_id,
                approve_request,
            ):
                if event_type == "token":
                    yield data.get("content", "")
                elif event_type == "state":
                    st.session_state.graph_state = data
                elif event_type == "error":
                    raise RuntimeError(data.get("detail", "Unknown error"))

        with st.chat_message("assistant"):
            st.write_stream(_stream_finalisation_tokens(_itinerary_chunks()))
    except Exception as exc:
        logger.exception("Finalisation failed")
        _append_assistant_message(f"I hit an error while generating the itinerary: {exc}")
        st.error(f"Finalisation failed: {exc}")
        return

    logger.info("Finalisation completed for user_id=%s", st.session_state.user_id)
    final_state = st.session_state.graph_state
    if final_state and final_state.get("final_itinerary"):
        display_markdown = inject_booking_links(
            final_state["final_itinerary"],
            final_state.get("selected_flight") or {},
            final_state.get("selected_hotel") or {},
            final_state.get("selected_flights") or [],
            final_state.get("selected_hotels") or [],
        )
        _append_assistant_message(display_markdown)

    st.session_state.awaiting_review = False
    st.session_state.trip_complete = True


def run_plan_revision(feedback: str) -> None:
    """Send review feedback back through intake/research and pause at review again."""
    state = st.session_state.graph_state
    if not state:
        st.error("No trip data to revise. Please start a new search.")
        return
    if not feedback.strip():
        st.error("Add a short note about what should change before revising the plan.")
        return

    provider_ready, provider_message = get_provider_status(st.session_state.llm_provider)
    if not provider_ready:
        logger.warning("Selected provider is not ready for revision: %s", provider_message)
        _append_assistant_message(
            f"I can't use the selected provider yet: {provider_message}"
        )
        st.error(provider_message)
        return

    approve_request = {
        "user_feedback": feedback.strip(),
        "feedback_type": "revise_plan",
        "selected_flight": state.get("selected_flight", {}),
        "selected_hotel": state.get("selected_hotel", {}),
        "selected_flights": state.get("selected_flights", []),
        "selected_hotels": state.get("selected_hotels", []),
        "trip_request": state.get("trip_request", {}),
        "llm_provider": st.session_state.llm_provider,
        "llm_model": st.session_state.llm_model,
        "llm_temperature": st.session_state.llm_temperature,
    }

    try:
        _archive_current_token_usage()
        result: dict = {}
        clarification: dict = {}
        with st.status("Revising your trip plan...", expanded=True) as status:
            for event_type, data in api_client.stream_approve(
                st.session_state.thread_id,
                approve_request,
            ):
                if event_type == "node_start":
                    st.write(data.get("label", ""))
                elif event_type == "node_message":
                    st.write(data.get("content", ""))
                elif event_type == "state":
                    result = data
                    st.session_state.graph_state = data
                elif event_type == "clarification":
                    clarification = data
                    st.session_state.thread_id = data.get("thread_id", "")
                elif event_type == "error":
                    raise RuntimeError(data.get("detail", "Unknown error"))
            if clarification:
                status.update(label="Need a bit more info...", state="complete", expanded=False)
            else:
                status.update(label="Revised options are ready to review.", state="complete", expanded=False)
    except Exception as exc:
        logger.exception("Plan revision failed")
        _append_assistant_message(f"I hit an error while revising your trip: {exc}")
        st.error(f"Revision failed: {exc}")
        return

    if clarification:
        question = clarification.get("question", "Could you provide more details?")
        st.session_state.awaiting_clarification = True
        st.session_state.clarification_question = question
        st.session_state.awaiting_review = False
        st.session_state.messages.append({"role": "assistant", "content": question})
        with st.chat_message("assistant"):
            st.write_stream(_stream_text(question))
        return

    if result:
        latest_assistant_message = next(
            (
                message for message in reversed(result.get("messages", []))
                if message.get("role") == "assistant" and message.get("content")
            ),
            None,
        )
        if latest_assistant_message:
            st.session_state.messages.append(latest_assistant_message)
            with st.chat_message("assistant"):
                st.write_stream(_stream_text(latest_assistant_message["content"]))

    st.session_state.awaiting_review = True
    st.session_state.awaiting_interests = False
