"""
transcriber.py — Audio-to-text transcription module.

Supported backends:
  faster-whisper  — Local inference via CTranslate2-accelerated Whisper.
  openai-api      — Cloud transcription via OpenAI Whisper-1 API.

Public interface:
  transcribe(audio_path, cfg) -> (transcript_text, duration_seconds | None)

Config keys (cfg = config["transcriber"]):
  backend   : "faster-whisper" | "openai-api"
  model     : Whisper model size string, e.g. "base", "small", "medium"
  device    : "cpu" | "cuda" | "auto"   (faster-whisper only)
  language  : BCP-47 language code, e.g. "en", or None for auto-detect
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def transcribe(audio_path: Path, cfg: dict) -> tuple[str, float | None]:
    """
    Transcribe an audio file to text.

    Args:
        audio_path: Path to the audio file.
        cfg:        The transcriber config dict (config["transcriber"]).

    Returns:
        A two-tuple of (transcript_text, duration_seconds).
        duration_seconds is None when the backend cannot supply it.

    Raises:
        ValueError:     If an unrecognised backend is specified.
        RuntimeError:   If transcription fails for any reason.
    """
    if not audio_path.exists():
        raise RuntimeError(f"Audio file not found: {audio_path}")

    backend = cfg.get("backend", "faster-whisper")
    logger.info("Transcribing %s with backend=%r", audio_path.name, backend)

    if backend == "faster-whisper":
        return _transcribe_faster_whisper(audio_path, cfg)
    elif backend == "openai-api":
        return _transcribe_openai_api(audio_path, cfg)
    else:
        raise ValueError(f"Unknown transcriber backend: {backend!r}")


# ---------------------------------------------------------------------------
# Backend: faster-whisper (local)
# ---------------------------------------------------------------------------

def _transcribe_faster_whisper(
    audio_path: Path, cfg: dict
) -> tuple[str, float | None]:
    """
    Transcribe using a locally-running faster-whisper model.

    Model weights are downloaded on first use (~75 MB for 'tiny', ~150 MB for
    'base') and cached by the faster-whisper / huggingface libraries.

    Args:
        audio_path: Path to the audio file.
        cfg:        Transcriber config dict.

    Returns:
        (transcript_text, duration_seconds)

    Raises:
        RuntimeError: On any transcription failure.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. "
            "Run: pip install faster-whisper"
        ) from exc

    model_size: str = cfg.get("model", "base")
    device: str = cfg.get("device", "cpu")
    # None means auto-detect; pass it straight through to the model.
    language: str | None = cfg.get("language") or None

    logger.info(
        "Loading faster-whisper model=%r device=%r language=%r",
        model_size,
        device,
        language if language else "auto-detect",
    )

    try:
        model = WhisperModel(model_size, device=device)

        segments_iter, info = model.transcribe(
            str(audio_path),
            language=language,
        )

        # info.language is set even when language=None (auto-detected).
        detected_language: str = getattr(info, "language", "unknown")
        duration: float = getattr(info, "duration", 0.0)

        logger.info(
            "Detected language=%r duration=%.1fs",
            detected_language,
            duration,
        )

        # Consume the lazy segments iterator, stripping leading/trailing
        # whitespace from each segment before joining.
        transcript: str = " ".join(
            segment.text.strip() for segment in segments_iter
        )

        logger.info(
            "Transcription complete: %d characters from %s",
            len(transcript),
            audio_path.name,
        )

        return transcript, duration if duration > 0 else None

    except Exception as exc:
        logger.error(
            "faster-whisper transcription failed for %s: %s",
            audio_path.name,
            exc,
        )
        raise RuntimeError(f"Transcription failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Backend: openai-api (cloud)
# ---------------------------------------------------------------------------

def _transcribe_openai_api(
    audio_path: Path, cfg: dict
) -> tuple[str, float | None]:
    """
    Transcribe using the OpenAI Whisper-1 cloud API.

    Requires the OPENAI_API_KEY environment variable to be set.
    Duration is not returned by this API, so None is always used.

    Args:
        audio_path: Path to the audio file.
        cfg:        Transcriber config dict (model key is ignored — the API
                    only exposes whisper-1 at this time).

    Returns:
        (transcript_text, None)

    Raises:
        RuntimeError: If OPENAI_API_KEY is missing or the API call fails.
    """
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "openai is not installed. Run: pip install openai"
        ) from exc

    api_key: str | None = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is not set. "
            "Export it before running the pipeline."
        )

    logger.info("Sending %s to OpenAI Whisper-1 API", audio_path.name)

    try:
        client = OpenAI(api_key=api_key)

        with audio_path.open("rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )

        text: str = transcript.text
        logger.info(
            "OpenAI transcription complete: %d characters from %s",
            len(text),
            audio_path.name,
        )

        # The OpenAI transcriptions endpoint does not return duration.
        return text, None

    except Exception as exc:
        logger.error(
            "OpenAI API transcription failed for %s: %s",
            audio_path.name,
            exc,
        )
        raise RuntimeError(f"Transcription failed: {exc}") from exc
