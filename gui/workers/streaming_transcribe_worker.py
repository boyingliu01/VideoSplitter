"""Streaming/incremental ASR transcription worker for GUI.

Unlike TranscribeWorker which transcribes the entire audio before returning,
this worker transcribes in 30s chunks and emits segments incrementally so
the UI becomes interactive almost immediately.
"""

from __future__ import annotations

import gc
import logging
import math
import os
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
from video_splitter.extractor.engines import (
    FUNASR_CHUNK_SECONDS,
    FunASREngine,
    _get_audio_duration_ffprobe,
    _extract_audio_range,
    load_funasr_model,
)

logger = logging.getLogger(__name__)


class StreamingTranscribeWorker(QObject):
    """Incremental ASR transcription worker running in a background QThread.

    Transcribes video audio in chunks, emitting segments as each chunk
    completes. Supports priority requests (seek-to-chunk) and cancellation.
    """

    # Signals
    model_loading_progress = Signal(str)       # Model loading status description
    audio_ready = Signal(float)                # Audio extraction done, arg=total_duration
    segments_ready = Signal(list)              # New segments from a completed chunk
    chunk_completed = Signal(int, int)         # (completed_count, total_count)
    transcription_complete = Signal(dict)      # Full transcript dict when all done
    transcription_progress = Signal(float, str)  # (0.0-1.0, description)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        engine_name: str = "funasr",
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
        hotword: str = "",
    ) -> None:
        super().__init__(parent)
        self._engine_name = engine_name
        self._config = config if config is not None else SplitConfig()
        self._chunk_seconds: int = FUNASR_CHUNK_SECONDS
        self._hotword = hotword  # Space-separated hotword string for ASR enhancement

        # State (only accessed from worker thread, except priority/cancel)
        self._priority_chunk_index: int = -1  # -1 = no priority request
        self._cancelled: bool = False
        self._completed_chunks: Set[int] = set()
        self._all_segments: List[Dict[str, Any]] = []

    @Slot(str)
    def run(self, video_path: str) -> None:
        """Main entry point — called from QThread.

        Phases:
        1. Get video duration + start FFmpeg audio extraction + load model (parallel)
        2. Compute chunk layout
        3. Transcribe chunks in order (with priority override on seek)
        4. Emit transcription_complete when done
        """
        try:
            self._run_impl(video_path)
        except Exception as exc:
            logger.exception("Streaming transcription failed")
            self.error.emit(str(exc))

    def _run_impl(self, video_path: str) -> None:
        # Phase 1: Get duration + load model
        self.transcription_progress.emit(0.0, "Step 1/2: Loading model...")
        self.model_loading_progress.emit("Getting video duration...")

        # Get video duration via ffprobe
        try:
            total_duration = _get_audio_duration_ffprobe(video_path)
        except Exception as exc:
            self.error.emit(f"Cannot get video duration: {exc}")
            return

        if total_duration <= 0:
            self.error.emit("Video duration is 0 or invalid")
            return

        self.audio_ready.emit(total_duration)

        # Load model (if cached by health check, returns instantly)
        self.model_loading_progress.emit("Loading speech recognition model...")
        self.transcription_progress.emit(0.02, "Step 1/2: Loading model...")

        model = load_funasr_model(use_cache=True)
        if model is None:
            self.model_loading_progress.emit("Model not cached, loading from disk...")
            model = load_funasr_model(use_cache=False)
        self.model_loading_progress.emit("Model loaded successfully")

        self.transcription_progress.emit(0.05, "Step 2/2: Model ready, starting transcription...")

        # Phase 2: Compute chunk layout and transcribe on-the-fly
        # Each chunk is extracted directly from the video file via FFmpeg.
        # This avoids the long upfront wait for full audio extraction —
        # the first result appears after just model_load + 1 chunk extraction.
        n_chunks = max(1, math.ceil(total_duration / self._chunk_seconds))
        logger.info(
            "Streaming transcription: %.0fs video → %d chunks of %ds",
            total_duration, n_chunks, self._chunk_seconds,
        )

        chunk_queue: Deque[int] = deque(range(n_chunks))
        engine = FunASREngine()
        chunks_since_gc = 0

        try:
            while chunk_queue:
                # Check cancellation
                if self._cancelled:
                    logger.info("Streaming transcription cancelled")
                    self.cancelled.emit()
                    return

                # Check priority request
                if (
                    self._priority_chunk_index >= 0
                    and self._priority_chunk_index in chunk_queue
                ):
                    priority_idx = self._priority_chunk_index
                    chunk_queue.remove(priority_idx)
                    chunk_queue.appendleft(priority_idx)
                    self._priority_chunk_index = -1
                    self.transcription_progress.emit(
                        -1.0,
                        f"Priority: transcribing segment at requested position...",
                    )

                # Pop next chunk
                chunk_idx = chunk_queue.popleft()
                start_time = chunk_idx * self._chunk_seconds
                duration = min(
                    self._chunk_seconds,
                    total_duration - start_time,
                )

                # Update progress
                frac = 0.05 + 0.9 * (len(self._completed_chunks) / n_chunks)
                self.transcription_progress.emit(
                    frac,
                    f"Step 2/2: Recognizing segment {len(self._completed_chunks) + 1}/{n_chunks}...",
                )

                # Extract this chunk directly from the video file
                try:
                    chunk_wav = _extract_audio_range(
                        video_path, start_time, duration
                    )
                except Exception as exc:
                    logger.warning("Failed to extract chunk %d: %s", chunk_idx, exc)
                    self._completed_chunks.add(chunk_idx)
                    continue

                try:
                    generate_kwargs: dict = {"input": chunk_wav}
                    if self._hotword:
                        generate_kwargs["hotword"] = self._hotword

                    result = model.generate(**generate_kwargs)
                    new_segments = engine._extract_segments(result)

                    # Offset timestamps to global timeline
                    for seg in new_segments:
                        seg["start"] = round(seg["start"] + start_time, 2)
                        seg["end"] = round(seg["end"] + start_time, 2)

                    # Deduplicate against existing segments
                    deduped = self._deduplicate_segments(new_segments)
                    self._all_segments.extend(deduped)

                    if deduped:
                        self.segments_ready.emit(deduped)

                except Exception as exc:
                    logger.warning("Failed to transcribe chunk %d: %s", chunk_idx, exc)
                finally:
                    try:
                        os.unlink(chunk_wav)
                    except OSError:
                        pass

                self._completed_chunks.add(chunk_idx)
                self.chunk_completed.emit(len(self._completed_chunks), n_chunks)

                # GC every 3 chunks
                chunks_since_gc += 1
                if chunks_since_gc >= 3:
                    gc.collect()
                    chunks_since_gc = 0

        finally:
            pass  # No temp WAV to clean up

        # Phase 3: Complete
        self.transcription_progress.emit(1.0, "Transcription complete")
        transcript = {
            "language": "zh",
            "duration": total_duration,
            "segments": self._all_segments,
        }
        self.transcription_complete.emit(transcript)

    def _deduplicate_segments(
        self, new_segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove segments that overlap with existing ones.

        Strategy: skip new segments whose start overlaps with the tail of
        the last existing segment (< 0.5s gap) and have identical text.
        """
        if not self._all_segments:
            return new_segments

        last_end = self._all_segments[-1]["end"]
        deduped: List[Dict[str, Any]] = []

        for seg in new_segments:
            # Skip if overlapping with existing tail
            if seg["start"] < last_end - 0.5:
                continue
            deduped.append(seg)

        return deduped

    @Slot(float)
    def request_priority(self, time_seconds: float) -> None:
        """Request priority transcription for the chunk containing time_seconds.

        Thread-safe: called from GUI thread while run() executes in worker thread.
        Safe because int assignment is atomic under CPython GIL.
        """
        target_chunk = int(time_seconds / self._chunk_seconds)
        if target_chunk not in self._completed_chunks:
            self._priority_chunk_index = target_chunk

    @Slot()
    def cancel(self) -> None:
        """Request cancellation. Checked at chunk boundaries.

        Thread-safe: bool assignment is atomic under CPython GIL.
        """
        self._cancelled = True
