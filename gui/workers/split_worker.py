"""Worker object: FFmpeg video cutting in background thread."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.analyzer.chapter import Chapter
from video_splitter.config import SplitConfig
from video_splitter.splitter.cutter import VideoCutter


class SplitWorker(QObject):
    """Video cutting worker running in a background QThread.

    Managed by MainWindow (same lifecycle pattern as TranscribeWorker).
    Bridges VideoCutter's ``progress_callback`` to Qt signals.

    Note:
        Cancel is checked between segments.  Once an FFmpeg subprocess
        is running for a single segment, it cannot be interrupted.
        The current segment will finish before cancellation takes effect.

    Thread safety:
        ``_cancelled`` is written from the main thread via ``cancel()``
        and read from the worker thread in ``run()``.  Under CPython the
        GIL makes simple bool assignment effectively atomic, so this is
        safe in practice.  For stricter guarantees consider using
        ``threading.Event``.
    """

    progress = Signal(float, str)   # (0-1 fraction, description)
    finished = Signal(list)         # list[str] — output file paths
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
        """Request cancellation (takes effect between segments)."""
        self._cancelled = True

    @Slot(str, list, str)
    def run(
        self,
        video_path: str,
        chapters: List[Dict[str, Any]],
        output_dir: str,
    ) -> None:
        """Execute video cutting.

        Args:
            video_path: Path to the source video file.
            chapters: List of chapter dicts with ``title``,
                ``start_seconds``, ``end_seconds``.
            output_dir: Directory to write output segments.
        """
        if self._cancelled:
            self.error.emit("Cancelled before cutting started")
            return

        try:
            # Convert dicts to Chapter objects
            chapter_objects = [
                Chapter(
                    title=ch["title"],
                    start_seconds=ch["start_seconds"],
                    end_seconds=ch["end_seconds"],
                )
                for ch in chapters
            ]

            total = len(chapter_objects)
            output_files: List[str] = []

            def _on_progress(frac: float) -> None:
                """Bridge VideoCutter callback to Qt signal."""
                self.progress.emit(frac, f"Cutting segments... ({frac:.0%})")

            cutter = VideoCutter(self._config, progress_callback=_on_progress)

            # Custom loop to support per-segment cancellation
            os.makedirs(output_dir, exist_ok=True)
            base_name = Path(video_path).stem

            for i, ch in enumerate(chapter_objects):
                if self._cancelled:
                    self.progress.emit(
                        i / total,
                        f"Cancelled after {i}/{total} segments",
                    )
                    break

                self.progress.emit(
                    i / total,
                    f"Cutting segment {i + 1}/{total}: {ch.title}",
                )

                out_name = f"{base_name}_{ch.title}.mp4"
                out_path = os.path.join(output_dir, out_name)

                cutter.cut_single(
                    video_path, out_path,
                    ch.start_seconds, ch.end_seconds,
                )

                output_files.append(out_path)

                if cutter.progress_callback:
                    cutter.progress_callback((i + 1) / total)

            if self._cancelled:
                self.finished.emit(output_files)
            else:
                self.progress.emit(1.0, f"Complete: {len(output_files)} segments")
                self.finished.emit(output_files)

        except Exception as exc:
            self.error.emit(f"Video cutting failed: {exc}")
