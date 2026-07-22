"""Pluggable transcription engines for video_splitter."""

from __future__ import annotations

import gc
import json
import logging
import os
import subprocess
import tempfile
import wave
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from video_splitter.config import SplitConfig

logger = logging.getLogger(__name__)

# FunASR model identifier.  FunASR ≥ 1.2 uses registered class names
# (e.g. "Paraformer") rather than full ModelScope IDs.
# Override via VIDEO_SPLITTER_FUNASR_MODEL_DIR env var (local path or ModelScope ID).
FUNASR_MODEL = "Paraformer"

# Fallback model keys to try if the primary key is not registered.
# This handles version differences across FunASR releases.
FUNASR_MODEL_FALLBACKS = [
    "paraformer-zh",
    "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
]

# Maximum audio length per FunASR generate() call (seconds).
# Override via VIDEO_SPLITTER_FUNASR_CHUNK_SECONDS env var.
# 30 s keeps per-chunk processing memory ~200 MB on top of the ~900 MB model.
FUNASR_CHUNK_SECONDS: int = int(
    os.environ.get("VIDEO_SPLITTER_FUNASR_CHUNK_SECONDS", "30")
)


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


def _read_wav_chunks(
    audio_path: str, chunk_seconds: int
) -> List[tuple[str, float, float]]:
    """Split a WAV file into temporal chunks written to temp files.

    Args:
        audio_path: Path to the source WAV file (must be PCM).
        chunk_seconds: Maximum duration of each chunk in seconds.

    Returns:
        List of ``(temp_wav_path, offset_seconds, duration_seconds)``
        tuples.  Caller is responsible for deleting the temp files.

    Raises:
        RuntimeError: If the WAV file cannot be read.
    """
    import numpy as np

    with wave.open(audio_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    # Convert raw bytes to numpy array (mono, float32)
    if sampwidth == 2:
        dtype = np.int16
    elif sampwidth == 4:
        dtype = np.int32
    else:
        dtype = np.uint8
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # If stereo, take only the first channel
    if n_channels > 1:
        samples = samples[::n_channels]

    # Sanitize: replace NaN / Inf with 0 (can occur with malformed WAV)
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)

    chunk_frames = chunk_seconds * framerate
    total_frames = len(samples)
    chunks: List[tuple[str, float, float]] = []

    for start_frame in range(0, total_frames, chunk_frames):
        end_frame = min(start_frame + chunk_frames, total_frames)
        chunk_samples = samples[start_frame:end_frame]
        offset = start_frame / framerate
        duration = len(chunk_samples) / framerate

        # Normalize to int16 for WAV writing
        chunk_int16 = np.clip(chunk_samples, -32768, 32767).astype(np.int16)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()

        with wave.open(tmp_path, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(framerate)
            wf_out.writeframes(chunk_int16.tobytes())

        chunks.append((tmp_path, offset, duration))

    return chunks


def _cleanup_chunk_files(chunks: List[tuple[str, float, float]]) -> None:
    """Remove temporary chunk WAV files."""
    for path, _, _ in chunks:
        try:
            os.unlink(path)
        except OSError:
            pass


def _extract_audio_range(
    video_path: str,
    start_seconds: float,
    duration_seconds: float,
    output_path: str | None = None,
) -> str:
    """Extract a time range of audio from video as 16kHz mono WAV.

    Uses FFmpeg with -ss before -i for fast seek (decode mode).

    Args:
        video_path: Input video/audio file path.
        start_seconds: Start time in seconds.
        duration_seconds: Duration to extract in seconds.
        output_path: Optional output WAV path. Defaults to temp file.

    Returns:
        Path to the extracted WAV file.

    Raises:
        RuntimeError: If FFmpeg extraction fails.
    """
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        output_path = tmp.name
        tmp.close()

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start_seconds:.3f}",
        "-i", video_path,
        "-t", f"{duration_seconds:.3f}",
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg audio range extraction failed: {result.stderr[-500:]}"
        )
    return output_path


# Module-level model cache (singleton per process)
_cached_funasr_model = None


def load_funasr_model(use_cache: bool = True):
    """Load FunASR AutoModel (public API for streaming worker).

    Uses a module-level singleton cache so the model is only loaded once
    per process. Subsequent calls return the cached instance immediately.

    Args:
        use_cache: If True (default), return cached model if available.
            Set to False to force reload (useful for testing).

    Returns:
        Loaded FunASR AutoModel instance.

    Raises:
        RuntimeError: If all model keys fail to load.
    """
    global _cached_funasr_model
    if use_cache and _cached_funasr_model is not None:
        logger.info("Returning cached FunASR model (skip reload)")
        return _cached_funasr_model
    model = _load_funasr_model()
    _cached_funasr_model = model
    return model


def clear_funasr_model_cache():
    """Clear the cached FunASR model, freeing memory.

    Next call to load_funasr_model() will reload from disk/network.
    """
    global _cached_funasr_model
    _cached_funasr_model = None
    gc.collect()


FUNASR_PUNC_MODEL = os.environ.get(
    "VIDEO_SPLITTER_FUNASR_PUNC_MODEL",
    "iic/punc_ct-transformer_cn-en-common-vocab471067-large",
)


def _load_funasr_model():
    """Load FunASR AutoModel with fallback model keys.

    Tries the primary model key first, then falls back to alternatives
    if the primary key is not registered (handles FunASR version differences).

    Returns:
        Loaded FunASR AutoModel instance.

    Raises:
        RuntimeError: If all model keys fail to load.
    """
    from funasr import AutoModel

    model_dir = os.environ.get("VIDEO_SPLITTER_FUNASR_MODEL_DIR", FUNASR_MODEL)
    candidates = [model_dir] + FUNASR_MODEL_FALLBACKS

    # Punctuation model (CT-Transformer) — adds punctuation to ASR output
    punc_model = os.environ.get("VIDEO_SPLITTER_FUNASR_PUNC_MODEL", FUNASR_PUNC_MODEL)
    # Allow disabling punctuation model via empty env var
    if punc_model in ("", "0", "false", "none"):
        punc_model = None

    last_error = None
    for key in candidates:
        try:
            logger.info("Trying FunASR model key: %s", key)
            kwargs: dict = {"model": key}
            if punc_model:
                kwargs["punc_model"] = punc_model
            model = AutoModel(**kwargs)
            return model
        except Exception as exc:
            logger.warning("Model key '%s' failed: %s", key, exc)
            last_error = exc

    raise RuntimeError(
        f"Failed to load FunASR model with any key. "
        f"Tried: {candidates}. Last error: {last_error}"
    )


class FunASREngine(TranscriptionEngine):
    """FunASR-based Chinese ASR transcription engine."""

    def transcribe(
        self,
        audio_path: str,
        config: SplitConfig,
        progress_callback: Optional[Callable[[float, str], None]] = None,
    ) -> Dict[str, Any]:
        """Transcribe audio using FunASR Chinese ASR model.

        For audio longer than ``FUNASR_CHUNK_SECONDS``, the file is
        automatically split into chunks to avoid OOM errors.  Each chunk
        is processed independently and results are merged with correct
        timestamp offsets.

        Args:
            audio_path: Path to the WAV audio file.
            config: SplitConfig instance (unused; kept for interface compatibility).
            progress_callback: Optional callback receiving ``(0.0-1.0, description)``.

        Returns:
            Dict with ``language``, ``duration``, ``segments``.
        """
        if progress_callback:
            progress_callback(0.0, "Loading speech recognition model (first time may take minutes)...")

        model = _load_funasr_model()

        if progress_callback:
            progress_callback(0.05, "Model loaded, preparing transcription...")

        # Determine total duration for progress reporting and chunking
        # decision.  Gracefully fall back to single-call mode if ffprobe
        # fails (e.g. in tests with non-existent paths).
        try:
            total_duration = _get_audio_duration_ffprobe(audio_path)
        except Exception:
            total_duration = 0.0

        # Decide whether to chunk
        if total_duration <= FUNASR_CHUNK_SECONDS:
            return self._transcribe_single(
                model, audio_path, total_duration, progress_callback
            )

        return self._transcribe_chunked(
            model, audio_path, total_duration, progress_callback
        )

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _extract_segments(result: Any) -> List[Dict[str, Any]]:
        """Extract segment list from a FunASR generate() result.

        Handles multiple FunASR result formats:
        - Format A: sentence_info list (some model versions)
        - Format B: text + timestamp (Paraformer in FunASR 1.3.x)
          text is space-separated words, timestamp is [[start_ms, end_ms], ...]
        """
        if not isinstance(result, list) or len(result) == 0:
            logger.warning("FunASR result is empty or not a list")
            return []

        first = result[0] if isinstance(result[0], dict) else {}

        segments: List[Dict[str, Any]] = []

        # Format A: sentence_info (some model versions)
        sentence_info = first.get("sentence_info")
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
            return segments

        # Format B: text + timestamp (FunASR 1.3.x Paraformer)
        text = first.get("text", "").strip()
        timestamps = first.get("timestamp", [])

        if not text:
            logger.warning("FunASR result has no text content")
            return []

        if not timestamps:
            # No timestamps — return as single segment
            return [{"text": text, "start": 0.0, "end": 0.0}]

        # Split text into words and merge into sentence-level segments.
        # Words are space-separated (Chinese char groups from Paraformer).
        # We merge consecutive words with gaps < SENTENCE_GAP_MS into
        # sentence-level segments for better readability.
        words = text.split()
        SENTENCE_GAP_MS = 800  # gap threshold to split sentences
        MIN_SEGMENT_DURATION_MS = 500

        # Build raw word-level entries
        word_entries: List[Dict[str, float]] = []
        for i, word in enumerate(words):
            if i < len(timestamps):
                start_ms = timestamps[i][0]
                end_ms = timestamps[i][1]
            else:
                # More words than timestamps — skip extras
                break
            word_entries.append({"text": word, "start": start_ms, "end": end_ms})

        if not word_entries:
            return []

        # Merge words into sentence-level segments based on gaps
        current_text = word_entries[0]["text"]
        seg_start = word_entries[0]["start"]
        seg_end = word_entries[0]["end"]

        for j in range(1, len(word_entries)):
            gap = word_entries[j]["start"] - seg_end
            if gap > SENTENCE_GAP_MS:
                # End current segment, start new one
                segments.append({
                    "text": current_text,
                    "start": round(seg_start / 1000.0, 2),
                    "end": round(seg_end / 1000.0, 2),
                })
                current_text = word_entries[j]["text"]
                seg_start = word_entries[j]["start"]
                seg_end = word_entries[j]["end"]
            else:
                # Continue current segment
                current_text += word_entries[j]["text"]
                seg_end = word_entries[j]["end"]

        # Don't forget the last segment
        segments.append({
            "text": current_text,
            "start": round(seg_start / 1000.0, 2),
            "end": round(seg_end / 1000.0, 2),
        })

        # Post-process: merge very short segments (< MIN_SEGMENT_DURATION_MS)
        # with the next segment to avoid tiny fragments
        merged: List[Dict[str, float]] = []
        for seg in segments:
            dur_ms = (seg["end"] - seg["start"]) * 1000
            if merged and dur_ms < MIN_SEGMENT_DURATION_MS:
                # Merge with previous segment
                merged[-1]["text"] += seg["text"]
                merged[-1]["end"] = seg["end"]
            else:
                merged.append(seg)

        logger.info(
            "Extracted %d segments from text+timestamp (%d words, %d timestamps)",
            len(merged), len(words), len(timestamps),
        )
        return merged

    def _transcribe_single(
        self,
        model: Any,
        audio_path: str,
        total_duration: float,
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> Dict[str, Any]:
        """Transcribe a short audio file in a single generate() call."""
        if progress_callback:
            progress_callback(0.1, "Running speech recognition...")

        result = model.generate(input=audio_path)

        if progress_callback:
            progress_callback(0.8, "Processing recognition results...")

        segments = self._extract_segments(result)
        # Use last segment's end time if available, otherwise use total_duration
        last_end = segments[-1]["end"] if segments else 0.0
        duration = last_end if last_end > 0 else total_duration

        if progress_callback:
            progress_callback(1.0, "Done")

        return {"language": "zh", "duration": duration, "segments": segments}

    def _transcribe_chunked(
        self,
        model: Any,
        audio_path: str,
        total_duration: float,
        progress_callback: Optional[Callable[[float, str], None]],
    ) -> Dict[str, Any]:
        """Transcribe a long audio file by processing fixed-size chunks."""
        n_chunks = max(1, int(total_duration // FUNASR_CHUNK_SECONDS) + 1)
        logger.info(
            "Audio %.0fs exceeds %ds limit — splitting into %d chunks",
            total_duration, FUNASR_CHUNK_SECONDS, n_chunks,
        )

        if progress_callback:
            progress_callback(0.05, f"Splitting audio into {n_chunks} segments for processing...")

        chunks = _read_wav_chunks(audio_path, FUNASR_CHUNK_SECONDS)
        all_segments: List[Dict[str, Any]] = []

        try:
            for i, (chunk_path, offset, _dur) in enumerate(chunks):
                frac = 0.1 + 0.7 * (i / len(chunks))
                elapsed_min = f"{i}/{len(chunks)}"
                if progress_callback:
                    progress_callback(
                        frac,
                        f"Recognizing speech: segment {i + 1}/{len(chunks)} ({elapsed_min})...",
                    )

                result = model.generate(input=chunk_path)
                segs = self._extract_segments(result)

                # Shift timestamps by chunk offset and deduplicate
                for seg in segs:
                    seg["start"] = round(seg["start"] + offset, 2)
                    seg["end"] = round(seg["end"] + offset, 2)

                    # Skip segments that overlap with the tail of the
                    # previous chunk (FunASR may repeat boundary text)
                    if (
                        all_segments
                        and seg["start"] < all_segments[-1]["end"] - 0.5
                    ):
                        continue
                    all_segments.append(seg)

                # Release per-chunk activations before next iteration
                del result, segs
                gc.collect()
        finally:
            _cleanup_chunk_files(chunks)

        if progress_callback:
            progress_callback(0.9, "Finalizing transcription results...")

        duration = all_segments[-1]["end"] if all_segments else total_duration

        if progress_callback:
            progress_callback(1.0, "Done")

        return {"language": "zh", "duration": duration, "segments": all_segments}

    def health_check(self) -> tuple[bool, str]:
        """Check FunASR dependency availability.

        Returns:
            ``(True, "ok")`` or ``(False, error_message)``.
        """
        try:
            import numpy as np

            model = _load_funasr_model()
            dummy_wav = np.zeros(16000, dtype=np.float32)
            model.generate(input=dummy_wav)
            return True, "ok"
        except ImportError:
            return False, "FunASR not installed. Install: pip install funasr"
        except Exception as e:
            return False, str(e)

    def transcribe_file_chunk(
        self,
        model: Any,
        video_path: str,
        start_seconds: float,
        duration_seconds: float,
    ) -> List[Dict[str, Any]]:
        """Transcribe a time range from a video file using an already-loaded model.

        Extracts audio for the given range via FFmpeg, runs FunASR generate(),
        and returns segments with timestamps offset to global timeline.

        Args:
            model: Already-loaded FunASR AutoModel instance.
            video_path: Path to the video/audio file.
            start_seconds: Start time of the chunk in seconds.
            duration_seconds: Duration of the chunk in seconds.

        Returns:
            List of segment dicts with ``text``, ``start``, ``end`` (global time).
        """
        chunk_wav = _extract_audio_range(video_path, start_seconds, duration_seconds)
        try:
            result = model.generate(input=chunk_wav)
            segments = self._extract_segments(result)

            # Offset timestamps to global timeline
            for seg in segments:
                seg["start"] = round(seg["start"] + start_seconds, 2)
                seg["end"] = round(seg["end"] + start_seconds, 2)

            return segments
        finally:
            try:
                os.unlink(chunk_wav)
            except OSError:
                pass


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
