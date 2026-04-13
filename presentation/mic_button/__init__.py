"""Voice input widget — mic button that records and transcribes to text.

Uses Streamlit's native st.audio_input (which renders as a mic button with
proper browser microphone permissions) and sends the audio to /api/transcribe.
"""

import streamlit as st

from presentation import api_client
from infrastructure.logging_utils import get_logger

logger = get_logger(__name__)


def mic_button() -> None:
    """Render a mic recording widget below the trip text area.

    When audio is recorded, it's sent to the FastAPI /api/transcribe endpoint.
    The transcript is stored in st.session_state['voice_transcript'] and the
    page reruns so the text area picks it up.
    """
    audio = st.audio_input(
        "Record your trip description",
        label_visibility="collapsed",
    )
    if audio:
        with st.spinner("Transcribing your voice..."):
            try:
                transcript = api_client.transcribe_audio(audio.read())
                st.session_state["voice_transcript"] = transcript
                st.rerun()
            except Exception as exc:
                logger.warning("Voice transcription failed: %s", exc)
                st.warning(f"Could not transcribe audio: {exc}")
