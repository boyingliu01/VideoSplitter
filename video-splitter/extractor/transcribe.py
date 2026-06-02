"""Whisper transcription with progress reporting."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from video_splitter.config import SplitConfig


def transcribe(
    audio_path: str,
    config: SplitConfig,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """Transcribe audio using faster-whisper.

    Args:
        audio_path: Path to the WAV audio file.
        config: SplitConfig instance with model and language settings.
        progress_callback: Optional callback receiving a float in [0, 1].

    Returns:
        Dict with keys ``language``, ``duration``, ``segments``.
        Each segment is a dict with ``text``, ``start``, ``end``.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        config.model_size,
        device=config.device,
        compute_type=config.compute_type,
    )

    segments_out: list[Dict[str, Any]] = []
    segments, info = model.transcribe(
        audio_path,
        language=config.language,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    total_duration = info.duration
    for segment in segments:
        segments_out.append({
            "text": segment.text.strip(),
            "start": round(segment.start, 2),
            "end": round(segment.end, 2),
        })
        if progress_callback:
            progress_callback(
                segment.end / total_duration if total_duration > 0 else 0.0
            )

    return {
        "language": info.language,
        "duration": total_duration,
        "segments": segments_out,
    }


def estimate_tokens(transcript: Dict[str, Any]) -> int:
    """Roughly estimate LLM token count for the transcript text.

    Uses conservative estimates: ~1.5 chars per Chinese token,
    ~4 chars per English token. Falls back to 1.5 for mixed text.

    Args:
        transcript: Transcript dict as returned by :func:`transcribe`.

    Returns:
        Estimated token count.
    """
    full_text = "\n".join(s["text"] for s in transcript["segments"])
    char_count = len(full_text)
    return int(char_count / 1.5)


def to_srt(transcript: Dict[str, Any]) -> str:
    """Convert transcript to SRT subtitle format.

    Args:
        transcript: Transcript dict as returned by :func:`transcribe`.

    Returns:
        SRT-formatted string.
    """
    lines: list[str] = []
    for i, seg in enumerate(transcript["segments"], 1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        lines.append(str(i))
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def _format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp ``HH:MM:SS,mmm``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")
