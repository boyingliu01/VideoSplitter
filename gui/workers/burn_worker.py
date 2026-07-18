"""Worker object: subtitle burning in background thread."""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.splitter.subtitle_burner import SubtitleBurner


class BurnWorker(QObject):
    """Subtitle burning worker running in a background QThread.

    Managed by MainWindow (same lifecycle pattern as SplitWorker).
    Bridges SubtitleBurner's ``progress_callback`` to Qt signals.

    Thread safety:
        ``_cancelled`` is written from the main thread via ``cancel()``
        and read from the worker thread in ``run()``.  Under CPython the
        GIL makes simple bool assignment effectively atomic.
    """

    progress = Signal(float, str)   # (0-1 fraction, description)
    finished = Signal(list)         # list[str] — output file paths
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation (takes effect between segments)."""
        self._cancelled = True

    @Slot(list, list, list)
    def run(
        self,
        segment_files: List[str],
        chapters: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
    ) -> None:
        """Execute subtitle burning.

        Args:
            segment_files: Paths to split video segment files.
            chapters: Chapter dicts with ``start_seconds``, ``end_seconds``.
            transcript_segments: Corrected transcript segments.
        """
        if self._cancelled:
            self.error.emit("Cancelled before burning started")
            return

        try:
            total = len(segment_files)

            def _on_progress(frac: float) -> None:
                self.progress.emit(frac, f"Burning subtitles... ({frac:.0%})")

            burner = SubtitleBurner(progress_callback=_on_progress)

            # Process segments one by one for cancellation support
            output_files: List[str] = []

            for i, (seg_path, chapter) in enumerate(
                zip(segment_files, chapters)
            ):
                if self._cancelled:
                    self.progress.emit(
                        i / total,
                        f"Cancelled after {i}/{total} segments",
                    )
                    break

                self.progress.emit(
                    i / total,
                    f"Burning segment {i + 1}/{total}",
                )

                result = burner.burn(
                    [seg_path],
                    [chapter],
                    transcript_segments,
                )
                output_files.extend(result)

            if self._cancelled:
                self.finished.emit(output_files)
            else:
                self.progress.emit(1.0, f"Complete: {len(output_files)} segments")
                self.finished.emit(output_files)

        except Exception as exc:
            self.error.emit(f"Subtitle burning failed: {exc}")
