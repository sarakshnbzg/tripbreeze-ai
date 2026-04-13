"""Voice input widget — mic button that records and transcribes to text.

Uses Streamlit's native st.audio_input (which renders as a mic button with
proper browser microphone permissions) and sends the audio to /api/transcribe.
"""

import streamlit as st

from presentation import api_client
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _handle_audio_change():
    """Callback triggered when audio is recorded. Transcribes and updates session state."""
    audio_bytes = st.session_state.get("_audio_input")
    if audio_bytes:
        try:
            transcript = api_client.transcribe_audio(audio_bytes.read())
            current_text = st.session_state.get("trip_description", "")

            # Show replace/append options if there's existing text
            if current_text.strip():
                st.session_state["_pending_transcript"] = transcript
                st.session_state["_show_transcript_options"] = True
            else:
                # No existing text, just use the transcript
                st.session_state["trip_description"] = transcript
                st.session_state["_audio_recorded"] = True
        except Exception as exc:
            logger.warning("Voice transcription failed: %s", exc)
            st.warning(f"Could not transcribe audio: {exc}")


def mic_button() -> None:
    """Render a mic recording widget with replace/append options.

    After transcription, hides the audio playback and shows action buttons.
    """
    # Only show the record button if no successful recording yet
    if not st.session_state.get("_audio_recorded"):
        st.audio_input(
            "Record your trip description",
            label_visibility="collapsed",
            key="_audio_input",
            on_change=_handle_audio_change,
        )

    # Show replace/append buttons if pending transcript
    if st.session_state.get("_show_transcript_options"):
        pending = st.session_state.get("_pending_transcript", "")
        current = st.session_state.get("trip_description", "")

        st.write("Apply to text:")
        col_replace, col_append, col_cancel = st.columns(3)

        with col_replace:
            if st.button("Replace", use_container_width=True):
                st.session_state["trip_description"] = pending
                st.session_state["_show_transcript_options"] = False
                st.rerun()
        with col_append:
            if st.button("Append", use_container_width=True):
                st.session_state["trip_description"] = f"{current} {pending}".strip()
                st.session_state["_show_transcript_options"] = False
                st.rerun()
        with col_cancel:
            if st.button("Discard", use_container_width=True):
                st.session_state["_show_transcript_options"] = False
                st.session_state["_audio_recorded"] = False
                st.rerun()



