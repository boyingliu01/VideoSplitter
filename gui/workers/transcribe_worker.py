"""Worker object: ASR transcription in background thread"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
from video_splitter.extractor.audio import AudioExtractor
from video_splitter.extractor.engines import create_engine

if TYPE_CHECKING:
    pass


class TranscribeWorker(QObject):
    """ASR transcription worker running in a background QThread."""

    progress = Signal(float, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        engine_name: str = "funasr",
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine_name = engine_name
        self._config = config if config is not None else SplitConfig()

    @Slot(str)
    def run(self, video_path: str) -> None:
        try:
            # Phase 1: Extract audio from video → WAV (0-10%)
            self.progress.emit(0.0, "Extracting audio from video...")
            extractor = AudioExtractor()
            audio_path = extractor.extract(video_path)
            self.progress.emit(0.10, "Audio extraction complete")

            # Phase 2: Transcribe the extracted WAV (10-100%)
            engine = create_engine(self._engine_name, self._config)

            def _on_progress(frac: float, desc: str) -> None:
                # Map engine progress (0-1) to overall progress (0.1-1.0)
                overall = 0.1 + frac * 0.9
                self.progress.emit(overall, desc)

            transcript = engine.transcribe(
                audio_path,
                self._config,
                progress_callback=_on_progress,
            )

            # Clean up extracted WAV
            try:
                os.unlink(audio_path)
            except OSError:
                pass

            self.finished.emit(transcript)
        except Exception as exc:
            self.error.emit(str(exc))
