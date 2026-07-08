"""FunASR paraformer-zh transcription with VAD and punctuation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

if TYPE_CHECKING:
    from video_splitter.config import SplitConfig

logger = logging.getLogger(__name__)

_MODEL_CACHE: Dict[str, Any] = {}


def _resolve_device(config: SplitConfig) -> str:
    """Map config.device to FunASR AutoModel device parameter."""
    if config.device == "auto":
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    return config.device


def transcribe(
    audio_path: str,
    config: SplitConfig,
    progress_callback: Optional[Callable[[float], None]] = None,
    hotwords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """Transcribe audio using FunASR paraformer-zh with VAD + punctuation.

    The VAD model handles arbitrary-length audio — no manual chunking needed.
    First call downloads models from ModelScope (~2 GB total, cached afterwards):

    - paraformer-zh (~1 GB ASR model)
    - fsmn-vad (~2 MB voice activity detection)
    - ct-punc (~1.1 GB punctuation restoration)

    Args:
        audio_path: Path to 16kHz mono WAV audio file.
        config: SplitConfig instance (uses model_size, device).
        progress_callback: Optional callback receiving a float in [0, 1].
        hotwords: Optional list of hotword strings for ASR biasing.
            Passed to model.generate() as a space-separated string.

    Returns:
        Dict with keys ``language``, ``duration``, ``segments``.
        Each segment is a dict with ``text``, ``start``, ``end``.
    """
    from funasr import AutoModel

    if config.language and config.language != "zh":
        logger.warning(
            "config.language=%r but paraformer-zh only supports Chinese; "
            "output will be Chinese regardless",
            config.language,
        )

    if progress_callback:
        progress_callback(0.0)

    model_name = config.model_size
    if model_name not in _MODEL_CACHE:
        _MODEL_CACHE[model_name] = AutoModel(
            model="iic/speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 60000},
            punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
            device=_resolve_device(config),
            disable_update=True,
            log_level="error",
        )

    model = _MODEL_CACHE[model_name]

    logger.info("Transcribing with FunASR (VAD+punc pipeline)...")

    gen_kwargs = {
        "input": audio_path,
        "batch_size_s": 300,
        "batch_size_threshold_s": 60,
    }
    if hotwords:
        hotword_str = " ".join(hotwords)
        gen_kwargs["hotword"] = hotword_str
        logger.info(
            "Using %d hotwords for ASR biasing: %s",
            len(hotwords),
            hotword_str[:100],
        )

    res = model.generate(**gen_kwargs)
    result = res[0]

    # VAD+punc pipeline: prefer sentence_info with sentence-level timestamps.
    # When not available (e.g. ASR+VAD+punc without sentence-level output),
    # fall back to raw text + character-level timestamps.
    sentence_info = result.get("sentence_info", [])
    if sentence_info:
        segments_out = []
        for seg in sentence_info:
            segments_out.append({
                "text": seg["text"].strip(),
                "start": round(seg["start"] / 1000, 2),
                "end": round(seg["end"] / 1000, 2),
            })
        total_duration = round(sentence_info[-1]["end"] / 1000, 2)
    else:
        # Fallback: char-level timestamps with gap-based segmentation.
        # VAD has already filtered silence regions, so timestamps are denser.
        # Use a smaller gap threshold (300ms) to produce natural sentence breaks.
        raw_text = result.get("text", "")
        timestamps = result.get("timestamp", [])
        raw_text = raw_text.replace(" ", "")

        segments = []
        current_text = ""
        gap_start = 0.0
        GAP_THRESHOLD_MS = 300

        for i, (ch, ts) in enumerate(zip(raw_text, timestamps)):
            if not current_text:
                current_text = ch
                gap_start = ts[0]
            else:
                gap = ts[0] - timestamps[i - 1][1]
                if gap > GAP_THRESHOLD_MS:
                    segments.append({
                        "text": current_text,
                        "start": round(gap_start / 1000, 2),
                        "end": round(timestamps[i - 1][1] / 1000, 2),
                    })
                    current_text = ch
                    gap_start = ts[0]
                else:
                    current_text += ch

        if current_text and timestamps:
            segments.append({
                "text": current_text,
                "start": round(gap_start / 1000, 2),
                "end": round(timestamps[-1][1] / 1000, 2),
            })

        segments_out = [{"text": s["text"], "start": s["start"], "end": s["end"]} for s in segments]
        total_duration = round(timestamps[-1][1] / 1000, 2) if timestamps else 0.0

    if progress_callback:
        progress_callback(1.0)

    logger.info(
        "Transcription complete: %d segments, %.1fs audio",
        len(segments_out),
        total_duration,
    )

    return {
        "language": "zh",
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
