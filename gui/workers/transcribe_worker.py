"""Worker object: ASR transcription in background thread"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
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
    def run(self, audio_path: str) -> None:
        try:
            engine = create_engine(self._engine_name, self._config)

            def _on_progress(frac: float, desc: str) -> None:
                self.progress.emit(frac, desc)

            transcript = engine.transcribe(
                audio_path,
                self._config,
                progress_callback=_on_progress,
            )
            self.finished.emit(transcript)
        except Exception as exc:
            self.error.emit(str(exc))
