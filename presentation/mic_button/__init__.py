"""Voice input widget — mic button that records and transcribes to text.

Uses Streamlit's native st.audio_input (which renders as a mic button with
proper browser microphone permissions) and sends the audio to /api/transcribe.
"""

import streamlit as st

from presentation import api_client
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def _handle_audio_change():
    """Callback triggered when audio is recorded. Transcribes and replaces trip text."""
    key = f"_audio_input_{st.session_state.get('_mic_generation', 0)}"
    audio_bytes = st.session_state.get(key)
    if audio_bytes:
        try:
            transcript = api_client.transcribe_audio(audio_bytes.read())
            st.session_state["trip_description"] = transcript
        except Exception as exc:
            logger.warning("Voice transcription failed: %s", exc)
        # Bump generation to recreate the widget fresh (no playback UI)
        st.session_state["_mic_generation"] = st.session_state.get("_mic_generation", 0) + 1


def mic_button() -> None:
    """Render a mic recording widget. Records audio, transcribes it,
    and replaces the trip description text."""
    generation = st.session_state.get("_mic_generation", 0)
    st.audio_input(
        "Voice input",
        help="Click to describe your trip by voice. The recording will be transcribed into the text field.",
        key=f"_audio_input_{generation}",
        on_change=_handle_audio_change,
    )
