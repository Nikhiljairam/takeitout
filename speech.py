"""
Speech-to-text for recorded audio clips.

Uses the `SpeechRecognition` library's built-in free Google Web Speech
API recognizer — no API key required. It's fine for short personal
voice notes; accuracy on long or noisy clips will be rougher than a
paid STT service. If you'd rather use a paid/better STT (e.g. Whisper
via OpenAI, Deepgram, AssemblyAI...), swap the body of
`transcribe_audio_bytes` for that provider's call.
"""
import io

import speech_recognition as sr


class TranscriptionError(Exception):
    pass


def transcribe_audio_bytes(audio_bytes: bytes, language: str = "en-IN") -> str:
    """Transcribe a WAV/webm audio clip (as bytes, e.g. from
    st.audio_input) into text."""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(io.BytesIO(audio_bytes)) as source:
            audio = recognizer.record(source)
    except Exception as e:
        raise TranscriptionError(
            f"Couldn't read the audio clip ({e}). Try recording again, or "
            "type the entry instead."
        )

    try:
        return recognizer.recognize_google(audio, language=language)
    except sr.UnknownValueError:
        raise TranscriptionError("Couldn't make out any speech in that clip — try again or type it.")
    except sr.RequestError as e:
        raise TranscriptionError(f"Speech recognition service error: {e}")
