"""
transcriber.py — Audio-to-text transcription module.

Supported backends:
  faster-whisper  — Local inference via CTranslate2-accelerated Whisper.
  whisperx        — Local inference with word-level alignment and optional
                    speaker diarization (pyannote.audio 3.1).
  openai-api      — Cloud transcription via OpenAI Whisper-1 API.

Public interface:
  transcribe(audio_path, cfg) -> (transcript_text, duration_seconds | None)

Config keys (cfg = config["transcriber"]):
  backend        : "faster-whisper" | "whisperx" | "openai-api"
  model          : Whisper model size, e.g. "large-v3-turbo", "base"
  device         : "cpu" | "cuda" | "auto"
  language       : BCP-47 language code, e.g. "en", or None for auto-detect
  compute_type   : "float16" | "int8" | "float32"   (faster-whisper / whisperx)
  batch_size     : int   (whisperx only — parallel chunk count)
  diarization    : dict  (whisperx only — see config.yaml for keys)
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
    elif backend == "whisperx":
        return _transcribe_whisperx(audio_path, cfg)
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
# Backend: whisperx (local + alignment + optional diarization)
# ---------------------------------------------------------------------------

def _transcribe_whisperx(
    audio_path: Path, cfg: dict
) -> tuple[str, float | None]:
    """
    Transcribe using WhisperX: faster-whisper transcription + wav2vec2 word
    alignment + optional pyannote.audio 3.1 speaker diarization.

    When diarization is enabled each speaker turn is prefixed with
    "[SPEAKER_00]: " labels so the LLM can attribute action items per person.

    Returns:
        (transcript_text, duration_seconds | None)

    Raises:
        RuntimeError: On missing dependencies, missing HF token, or failure.
    """
    try:
        import whisperx  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "whisperx is not installed. Run: pip install whisperx"
        ) from exc

    model_size: str = cfg.get("model", "large-v3-turbo")
    compute_type: str = cfg.get("compute_type", "float16")
    batch_size: int = int(cfg.get("batch_size", 16))
    language: str | None = cfg.get("language") or None

    device: str = cfg.get("device", "auto")
    if device == "auto":
        try:
            import torch  # type: ignore[import]
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    logger.info(
        "Loading WhisperX model=%r device=%r compute_type=%r batch_size=%d",
        model_size, device, compute_type, batch_size,
    )

    try:
        model = whisperx.load_model(
            model_size, device, compute_type=compute_type, language=language
        )
        audio = whisperx.load_audio(str(audio_path))
        result = model.transcribe(audio, batch_size=batch_size)

        detected_language: str = result.get("language", language or "unknown")
        logger.info("Detected language=%r", detected_language)

        # Word-level forced alignment.
        align_model, metadata = whisperx.load_align_model(
            language_code=detected_language, device=device
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device,
            return_char_alignments=False,
        )

        # Optional speaker diarization.
        diar_cfg: dict = cfg.get("diarization", {})
        if diar_cfg.get("enabled", False):
            result = _apply_diarization(audio, result, diar_cfg, device)
            transcript = _format_diarized_transcript(result["segments"])
        else:
            transcript = " ".join(
                seg.get("text", "").strip() for seg in result["segments"]
            )

        # Duration = end time of last segment (WhisperX doesn't return it directly).
        segments = result.get("segments", [])
        duration: float | None = segments[-1].get("end") if segments else None

        logger.info(
            "WhisperX transcription complete: %d characters from %s",
            len(transcript), audio_path.name,
        )
        return transcript, duration

    except Exception as exc:
        logger.error(
            "WhisperX transcription failed for %s: %s", audio_path.name, exc
        )
        raise RuntimeError(f"Transcription failed: {exc}") from exc


def _apply_diarization(
    audio, result: dict, diar_cfg: dict, device: str
) -> dict:
    """Run pyannote.audio 3.1 diarization and assign speakers to word segments."""
    try:
        import whisperx  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError("whisperx is not installed.") from exc

    try:
        from pyannote.audio import Pipeline  # type: ignore[import]  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "pyannote.audio is not installed. "
            "Run: pip install 'pyannote.audio>=3.1'"
        ) from exc

    hf_token_env: str = diar_cfg.get("hf_token_env", "HF_TOKEN")
    hf_token: str | None = os.environ.get(hf_token_env)
    if not hf_token:
        raise RuntimeError(
            f"HuggingFace token not set. Export '{hf_token_env}' before running. "
            "Create a token at https://huggingface.co/settings/tokens and accept "
            "pyannote/speaker-diarization-3.1 and pyannote/segmentation-3.0 model terms."
        )

    min_speakers: int | None = diar_cfg.get("min_speakers") or None
    max_speakers: int | None = diar_cfg.get("max_speakers") or None

    logger.info(
        "Running speaker diarization (min=%s max=%s)", min_speakers, max_speakers
    )

    diarize_model = whisperx.DiarizationPipeline(
        use_auth_token=hf_token, device=device
    )
    diarize_segments = diarize_model(
        audio,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
    return whisperx.assign_word_speakers(diarize_segments, result)


def _format_diarized_transcript(segments: list[dict]) -> str:
    """
    Collapse word-level speaker assignments into speaker-turn lines.

    Output:
        [SPEAKER_00]: First speaker's words joined together.
        [SPEAKER_01]: Second speaker responds here.
    """
    lines: list[str] = []
    current_speaker: str | None = None
    current_words: list[str] = []

    for seg in segments:
        speaker: str = seg.get("speaker", "UNKNOWN")
        text: str = seg.get("text", "").strip()
        if not text:
            continue
        if speaker != current_speaker:
            if current_words and current_speaker is not None:
                lines.append(f"[{current_speaker}]: {' '.join(current_words)}")
            current_speaker = speaker
            current_words = [text]
        else:
            current_words.append(text)

    if current_words and current_speaker is not None:
        lines.append(f"[{current_speaker}]: {' '.join(current_words)}")

    return "\n".join(lines)


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
