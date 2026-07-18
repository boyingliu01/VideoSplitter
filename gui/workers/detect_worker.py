"""Worker object: LLM chapter detection in background thread."""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.analyzer.chapter import ChapterDetector
from video_splitter.config import SplitConfig


class DetectChaptersWorker(QObject):
    """Chapter detection worker running in a background QThread.

    Managed by MainWindow (same lifecycle pattern as TranscribeWorker).
    Emits ``chapters_detected`` on success or ``error`` on failure.

    Note:
        Cancel is checked before the LLM call begins.  Once the HTTP
        request is in-flight, it cannot be interrupted.

    Thread safety:
        ``_cancelled`` is written from the main thread via ``cancel()``
        and read from the worker thread in ``run()``.  Under CPython the
        GIL makes simple bool assignment effectively atomic, so this is
        safe in practice.  For stricter guarantees consider using
        ``threading.Event``.
    """

    chapters_detected = Signal(list)  # list[dict]
    progress = Signal(float, str)
    error = Signal(str)

    def __init__(
        self,
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or SplitConfig.from_env()
        self._cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation (takes effect before LLM call starts)."""
        self._cancelled = True

    @Slot(dict)
    def run(self, transcript: Dict[str, Any]) -> None:
        """Execute chapter detection on the given transcript.

        Args:
            transcript: Dict with ``duration`` and ``segments`` keys.
        """
        if self._cancelled:
            self.error.emit("Cancelled before detection started")
            return

        try:
            self.progress.emit(0.0, "Initializing chapter detector...")
            detector = ChapterDetector(self._config)

            if self._cancelled:
                self.error.emit("Cancelled before LLM call")
                return

            self.progress.emit(0.1, "Detecting chapters via LLM...")
            chapters = detector.detect(transcript)

            if self._cancelled:
                self.error.emit("Cancelled after detection")
                return

            self.progress.emit(1.0, f"Detected {len(chapters)} chapters")

            # Convert to serializable dicts
            result = [
                {
                    "title": ch.title,
                    "start_seconds": ch.start_seconds,
                    "end_seconds": ch.end_seconds,
                }
                for ch in chapters
            ]
            self.chapters_detected.emit(result)

        except Exception as exc:
            self.error.emit(f"Chapter detection failed: {exc}")
