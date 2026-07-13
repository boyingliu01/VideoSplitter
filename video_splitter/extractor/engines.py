"""Pluggable transcription engines for video_splitter."""

from __future__ import annotations

import json
import os
import subprocess
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from video_splitter.config import SplitConfig

FUNASR_MODEL = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"


class TranscriptionEngine(ABC):
    """Abstract base class for transcription engines."""

    @abstractmethod
    def transcribe(
        self,
        audio_path: str,
        config: SplitConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio file to segments.

        Args:
            audio_path: Path to the WAV audio file.
            config: SplitConfig instance with model and language settings.
            progress_callback: Optional callback receiving ``(0.0-1.0, description)``.

        Returns:
            Dict with keys ``language``, ``duration``, ``segments``.
            Each segment has ``text``, ``start``, ``end`` (float seconds).
        """

    @abstractmethod
    def health_check(self) -> tuple[bool, str]:
        """Check whether the engine and its dependencies are available.

        Returns:
            Tuple of ``(ok, message)``.
        """


def _get_audio_duration_ffprobe(audio_path: str) -> float:
    """Get audio duration in seconds via ffprobe.

    Raises:
        RuntimeError: If ffprobe is not found, times out, or returns invalid output.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                audio_path,
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found. Install FFmpeg and ensure it is on PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe timed out on: {audio_path}")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed on {audio_path}: {e.stderr.strip()}")

    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"ffprobe returned non-JSON output for: {audio_path}")
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError):
        raise RuntimeError(f"Cannot parse duration from ffprobe output for: {audio_path}")


class FunASREngine(TranscriptionEngine):
    """FunASR-based Chinese ASR transcription engine."""

    def transcribe(
        self,
        audio_path: str,
        config: SplitConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio using FunASR Chinese ASR model.

        Args:
            audio_path: Path to the WAV audio file.
            config: SplitConfig instance (unused; kept for interface compatibility).
            progress_callback: Optional callback receiving ``(0.0-1.0, description)``.

        Returns:
            Dict with ``language``, ``duration``, ``segments``.
        """
        from funasr import AutoModel

        if progress_callback:
            progress_callback(0.0, "Loading FunASR model...")

        model_dir = os.environ.get("VIDEO_SPLITTER_FUNASR_MODEL_DIR", FUNASR_MODEL)
        model = AutoModel(model=model_dir)

        if progress_callback:
            progress_callback(0.1, "Transcribing...")

        result = model.generate(input=audio_path)

        if progress_callback:
            progress_callback(0.8, "Processing results...")

        if isinstance(result, list) and len(result) > 0:
            first = result[0] if isinstance(result[0], dict) else {}
        else:
            first = {}

        sentence_info = first.get("sentence_info")

        segments: list[Dict[str, Any]] = []
        if sentence_info:
            for item in sentence_info:
                text = item.get("text", "")
                if not text:
                    continue
                segments.append({
                    "text": text,
                    "start": round(item.get("start", 0) / 1000.0, 2),
                    "end": round(item.get("end", 0) / 1000.0, 2),
                })
            if segments:
                duration = segments[-1]["end"]
            else:
                duration = _get_audio_duration_ffprobe(audio_path)
        else:
            duration = _get_audio_duration_ffprobe(audio_path)

        if progress_callback:
            progress_callback(1.0, "Done")

        return {
            "language": "zh",
            "duration": duration,
            "segments": segments,
        }

    def health_check(self) -> tuple[bool, str]:
        """Check FunASR dependency availability.

        Returns:
            ``(True, "ok")`` or ``(False, error_message)``.
        """
        try:
            from funasr import AutoModel
            import numpy as np

            model_dir = os.environ.get("VIDEO_SPLITTER_FUNASR_MODEL_DIR", FUNASR_MODEL)
            model = AutoModel(model=model_dir)
            dummy_wav = np.zeros(16000, dtype=np.float32)
            model.generate(input=dummy_wav)
            return True, "ok"
        except ImportError:
            return False, "FunASR not installed. Install: pip install funasr"
        except Exception as e:
            return False, str(e)


class WhisperEngine(TranscriptionEngine):
    """faster-whisper based transcription engine."""

    def transcribe(
        self,
        audio_path: str,
        config: SplitConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio using faster-whisper.

        Args:
            audio_path: Path to the WAV audio file.
            config: SplitConfig instance with model and language settings.
            progress_callback: Optional callback receiving ``(0.0-1.0, description)``.

        Returns:
            Dict with ``language``, ``duration``, ``segments``.
        """
        from video_splitter.extractor.transcribe import transcribe as _whisper_transcribe

        def _progress(frac: float) -> None:
            if progress_callback:
                progress_callback(frac, "Transcribing...")

        result = _whisper_transcribe(audio_path, config, progress_callback=_progress)

        if progress_callback:
            progress_callback(1.0, "Done")

        return result

    def health_check(self) -> tuple[bool, str]:
        """Check faster-whisper dependency availability.

        Returns:
            ``(True, "ok")`` or ``(False, error_message)``.
        """
        try:
            import faster_whisper  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "faster-whisper not installed. Install: pip install faster-whisper"
        except Exception as e:
            return False, str(e)


_ENGINE_REGISTRY: Dict[str, type[TranscriptionEngine]] = {
    "funasr": FunASREngine,
    "whisper": WhisperEngine,
}


def create_engine(
    name: str = "funasr",
    config: Optional[SplitConfig] = None,
) -> TranscriptionEngine:
    """Factory to create a transcription engine by name.

    Args:
        name: Engine name (``"funasr"`` or ``"whisper"``). Defaults to ``"funasr"``.
        config: Optional SplitConfig (reserved for future use).

    Returns:
        Instance of :class:`TranscriptionEngine`.

    Raises:
        ValueError: If *name* is not a recognized engine.
    """
    cls = _ENGINE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown engine: {name!r}. Available: {list(_ENGINE_REGISTRY)}"
        )
    engine = cls()
    return engine
