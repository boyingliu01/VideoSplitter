"""Fast-batch VAD transcription worker for GUI.

Refactored pipeline (fast-batch VAD mode):
1. ffprobe probe → audio_ready
2. Extract full audio (AudioExtractor) to WAV
3. Load ASR engine via create_engine("auto") — auto-selects GPU/CPU
4. model.generate(input=wav_path) — VAD auto-segments internally
5. Convert result to standard segments
6. Emit ALL segments at once via segments_ready
7. Completed signal with full transcript

Compared with the previous chunk-based streaming design:
- Removed: PCM chunk loop, FUNASR_CHUNK_SECONDS, per-chunk FFmpeg spawning
- Removed: _deduplicate_segments(), _merge_short_segments()
- Removed: request_priority(), _priority_chunk_index
- Added: 3-phase progress (Extracting → Transcribing → Processing)
- VAD handles natural sentence segmentation internally
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
from video_splitter.extractor.audio import AudioExtractor
from video_splitter.extractor.engines import (
    _get_audio_duration_ffprobe,
    create_engine,
    _extract_segments_from_sentence_info,
    _extract_segments_from_timestamps,
    _postprocess_sensevoice_text,
)

logger = logging.getLogger(__name__)


class StreamingTranscribeWorker(QObject):
    """Fast-batch ASR transcription worker running in a background QThread.

    Extracts full audio, transcribes with VAD auto-segmentation,
    and emits all segments at once.

    Signals:
        model_loading_progress: (str) human-readable status
        audio_ready: (float) total video duration in seconds
        segments_ready: (list) ALL segments at once (fast-batch)
        chunk_completed: (int, int) — (1, 1) at 100% (compat signal)
        transcription_complete: (dict) full transcript
        transcription_progress: (float, str) — progress + description
        error: (str)
        cancelled: ()
    """

    # Signals
    model_loading_progress = Signal(str)
    audio_ready = Signal(float)
    segments_ready = Signal(list)
    chunk_completed = Signal(int, int)
    transcription_complete = Signal(dict)
    transcription_progress = Signal(float, str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        engine_name: str = "auto",
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
        hotword: str = "",
    ) -> None:
        super().__init__(parent)
        self._engine_name = engine_name
        self._config = config if config is not None else SplitConfig()
        self._hotword = hotword

        # State
        self._cancelled: bool = False
        self._all_segments: List[Dict[str, Any]] = []

    @Slot(str)
    def run(self, video_path: str) -> None:
        """Main entry point — called from QThread."""
        try:
            self._run_fast_batch(video_path)
        except Exception as exc:
            logger.exception("Fast-batch transcription failed")
            self.error.emit(str(exc))

    # -- fast-batch VAD pipeline --------------------------------------------

    def _run_fast_batch(self, video_path: str) -> None:
        """Fast-batch VAD mode: extract audio, transcribe with VAD, emit all."""
        # ---- Phase 0: duration probe ----
        self.transcription_progress.emit(0.0, "Preparing...")
        self.model_loading_progress.emit("Probing video duration...")

        if self._cancelled:
            self.cancelled.emit()
            return

        try:
            total_duration = _get_audio_duration_ffprobe(video_path)
        except Exception as exc:
            self.error.emit(f"Cannot get video duration: {exc}")
            return

        if total_duration <= 0:
            self.error.emit("Video duration is 0 or invalid")
            return

        self.audio_ready.emit(total_duration)

        # ---- Phase 1: Extract audio ----
        self.transcription_progress.emit(10, "Extracting audio…")
        self.model_loading_progress.emit("Extracting audio…")

        if self._cancelled:
            self.cancelled.emit()
            return

        extractor = AudioExtractor()
        try:
            wav_path = extractor.extract(video_path)
        except Exception as exc:
            self.error.emit(f"Audio extraction failed: {exc}")
            return

        try:
            # ---- Phase 2: Load engine ----
            self.transcription_progress.emit(30, "Loading speech recognition model…")
            self.model_loading_progress.emit("Loading speech recognition model…")

            if self._cancelled:
                self.cancelled.emit()
                return

            engine = create_engine("auto", self._config)

            # ---- Phase 3: Transcribe with VAD ----
            self.transcription_progress.emit(50, "Transcribing with VAD…")
            self.model_loading_progress.emit("Transcribing with VAD…")

            if self._cancelled:
                self.cancelled.emit()
                return

            # Initialize engine (loads model) and run generate
            if hasattr(engine, "initialize"):
                engine.initialize()

            result = engine._model.generate(input=wav_path)

            # ---- Phase 4: Process results ----
            self.transcription_progress.emit(90, "Processing results…")
            self.model_loading_progress.emit("Processing results…")

            segments = self._extract_segments_from_result(result)

            # ---- Phase 5: Emit all segments & complete ----
            self._all_segments = segments
            if segments:
                self.segments_ready.emit(segments)

            # chunk_completed: emit once for compatibility (completed=1, total=1 = 100%)
            self.chunk_completed.emit(1, 1)

            self.transcription_progress.emit(1.0, "Transcription complete")

            transcript: dict = {
                "language": "zh",
                "duration": total_duration,
                "segments": segments,
            }
            self.transcription_complete.emit(transcript)

        finally:
            # Clean up extracted WAV
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _extract_segments_from_result(result: Any) -> list[dict]:
        """Extract standard segment format from engine generate() result.

        Handles both SenseVoice (sentence_info) and FunASR-Nano (timestamp) formats.

        Args:
            result: model.generate() return value.

        Returns:
            List of segment dicts with ``text``, ``start``, ``end`` (float seconds).
        """
        if not isinstance(result, list) or len(result) == 0:
            logger.warning("Empty result from model.generate()")
            return []

        first = result[0] if isinstance(result[0], dict) else {}

        # SenseVoice path: sentence_info
        sentence_info = first.get("sentence_info")
        if sentence_info:
            segments = _extract_segments_from_sentence_info(sentence_info)
            # Post-process SenseVoice text (strip emotion/event tags)
            for seg in segments:
                seg["text"] = _postprocess_sensevoice_text(seg["text"])
            logger.info("Extracted %d segments from sentence_info (SenseVoice)", len(segments))
            return segments

        # FunASR-Nano path: timestamp
        text = first.get("text", "")
        timestamps = first.get("timestamp", [])
        if text and timestamps:
            segments = _extract_segments_from_timestamps(text, timestamps)
            logger.info("Extracted %d segments from timestamp (FunASR-Nano)", len(segments))
            return segments

        # Fallback: text only, no timestamps
        if text:
            logger.warning("No timestamps in result, returning as single segment")
            return [{"text": text, "start": 0.0, "end": 0.0}]

        logger.warning("No recognizable format in model.generate() result")
        return []

    # -- public slots -------------------------------------------------------

    @Slot()
    def cancel(self) -> None:
        """Request cancellation. Checked at phase boundaries."""
        self._cancelled = True

    @Slot(str)
    def set_hotword(self, hotword: str) -> None:
        """Update the hotword string."""
        self._hotword = hotword
