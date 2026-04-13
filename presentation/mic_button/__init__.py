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
            st.session_state["voice_transcript"] = transcript
        except Exception as exc:
            logger.warning("Voice transcription failed: %s", exc)
            st.warning(f"Could not transcribe audio: {exc}")


def mic_button() -> None:
    """Render a mic recording widget below the trip text area.

    When audio recording stops, it's automatically sent to /api/transcribe.
    The transcript is stored in session state and displayed in the text area.
    """
    st.audio_input(
        "Record your trip description",
        label_visibility="collapsed",
        key="_audio_input",
        on_change=_handle_audio_change,
    )

