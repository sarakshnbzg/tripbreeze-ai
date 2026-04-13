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
    page reruns so the text area picks it up. After the text area displays it,
    streamlit_app clears it to prevent re-transcription on subsequent reruns.
    """
    audio = st.audio_input(
        "Record your trip description",
        label_visibility="collapsed",
    )
    if audio:
        audio_bytes = audio.read()
        # Only transcribe if this is a new recording (different from the last one).
        last_audio = st.session_state.get("_last_audio_bytes")
        if audio_bytes != last_audio:
            with st.spinner("Transcribing your voice..."):
                try:
                    transcript = api_client.transcribe_audio(audio_bytes)
                    st.session_state["voice_transcript"] = transcript
                    st.session_state["_last_audio_bytes"] = audio_bytes
                    st.rerun()
                except Exception as exc:
                    logger.warning("Voice transcription failed: %s", exc)
                    st.warning(f"Could not transcribe audio: {exc}")
