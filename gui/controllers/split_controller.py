"""Split state machine: chapter detection, editing, validation, and cutting coordination."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from video_splitter.analyzer.chapter import Chapter
from video_splitter.analyzer.validator import ChapterValidator
from video_splitter.config import SplitConfig

logger = logging.getLogger(__name__)


class SplitController(QObject):
    """Central data source for chapter splitting workflow.

    Widgets (ChapterList, Timeline) emit edit signals to this controller,
    which broadcasts updates back via ``chapters_updated`` to prevent
    circular signal loops.  Widgets MUST use ``blockSignals(True)`` when
    applying updates from ``chapters_updated``.
    """

    chapters_detected = Signal(list)   # list[dict] — after LLM detection
    chapters_updated = Signal(list)    # list[dict] — after any edit
    chapters_exported = Signal(str)    # path — after export
    error = Signal(str)

    def __init__(
        self,
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or SplitConfig.from_env()
        self._chapters: List[Dict[str, Any]] = []
        self._transcript: Optional[Dict[str, Any]] = None
        self._video_path: str = ""

    # -- Properties --------------------------------------------------------

    @property
    def chapters(self) -> List[Dict[str, Any]]:
        """Return a deep copy of the current chapter list."""
        return [dict(ch) for ch in self._chapters]

    @property
    def chapter_count(self) -> int:
        return len(self._chapters)

    # -- Transcript & video path ------------------------------------------

    def set_transcript(self, transcript: Dict[str, Any]) -> None:
        """Store the (corrected) transcript from ReviewController."""
        self._transcript = transcript

    def set_video_path(self, path: str) -> None:
        """Store the current video file path."""
        self._video_path = path

    # -- Chapter detection (called after DetectChaptersWorker finishes) ---

    def receive_chapters(self, raw_chapters: List[Dict[str, Any]]) -> None:
        """Receive detected chapters, validate, and broadcast.

        Called by MainWindow after DetectChaptersWorker emits
        ``chapters_detected``.

        Args:
            raw_chapters: List of chapter dicts with ``title``,
                ``start_seconds``, ``end_seconds`` keys.
        """
        if not self._transcript:
            self.error.emit("No transcript available for validation")
            return

        try:
            chapters = [
                Chapter(
                    title=ch.get("title", f"{i+1:02d}_片段{i+1}"),
                    start_seconds=ch.get("start_seconds", 0),
                    end_seconds=ch.get("end_seconds", 0),
                )
                for i, ch in enumerate(raw_chapters)
            ]
            validator = ChapterValidator(self._config)
            segments = self._transcript.get("segments", [])
            base = Path(self._video_path).stem if self._video_path else "video"
            validated = validator.validate(chapters, segments, base)

            self._chapters = [
                {
                    "title": ch.title,
                    "start_seconds": ch.start_seconds,
                    "end_seconds": ch.end_seconds,
                }
                for ch in validated
            ]
            self.chapters_detected.emit(list(self._chapters))
            self.chapters_updated.emit(list(self._chapters))
        except Exception as exc:
            self.error.emit(f"Validation failed: {exc}")

    # -- Chapter editing ---------------------------------------------------

    def update_chapter(
        self,
        index: int,
        title: Optional[str] = None,
        start: Optional[float] = None,
        end: Optional[float] = None,
    ) -> bool:
        """Update a single chapter's properties.

        Args:
            index: Chapter index in the list.
            title: New title (or ``None`` to keep current).
            start: New start time in seconds (or ``None``).
            end: New end time in seconds (or ``None``).

        Returns:
            ``True`` if update succeeded, ``False`` if validation failed.
        """
        if index < 0 or index >= len(self._chapters):
            self.error.emit(f"Invalid chapter index: {index}")
            return False

        ch = dict(self._chapters[index])

        if title is not None:
            ch["title"] = title.strip() or ch["title"]

        if start is not None:
            ch["start_seconds"] = start

        if end is not None:
            ch["end_seconds"] = end

        # Boundary validation
        if ch["start_seconds"] >= ch["end_seconds"]:
            self.error.emit(
                f"Invalid range: start ({ch['start_seconds']:.1f}s) "
                f">= end ({ch['end_seconds']:.1f}s)"
            )
            return False

        duration = ch["end_seconds"] - ch["start_seconds"]
        if duration < 5.0:
            self.error.emit(
                f"Chapter too short: {duration:.1f}s (minimum 5s)"
            )
            return False

        # Range validation against neighbors
        if index > 0 and ch["start_seconds"] < self._chapters[index - 1]["end_seconds"]:
            self.error.emit("Start time overlaps with previous chapter")
            return False

        if index < len(self._chapters) - 1 and ch["end_seconds"] > self._chapters[index + 1]["start_seconds"]:
            self.error.emit("End time overlaps with next chapter")
            return False

        self._chapters[index] = ch
        self.chapters_updated.emit(list(self._chapters))
        return True

    def update_boundary(self, boundary_index: int, new_time: float) -> bool:
        """Atomically update a boundary between two adjacent chapters.

        Updates chapter[boundary_index].end and
        chapter[boundary_index+1].start to ``new_time`` in a single
        operation, avoiding transient invalid states.

        Args:
            boundary_index: Index of the left chapter (0-based).
            new_time: New boundary time in seconds.

        Returns:
            ``True`` if update succeeded, ``False`` otherwise.
        """
        if boundary_index < 0 or boundary_index >= len(self._chapters) - 1:
            self.error.emit(f"Invalid boundary index: {boundary_index}")
            return False

        left = dict(self._chapters[boundary_index])
        right = dict(self._chapters[boundary_index + 1])

        left["end_seconds"] = new_time
        right["start_seconds"] = new_time

        # Validate left chapter
        if left["start_seconds"] >= left["end_seconds"]:
            self.error.emit("Boundary move makes left chapter invalid")
            return False
        if left["end_seconds"] - left["start_seconds"] < 5.0:
            self.error.emit("Left chapter too short (<5s)")
            return False

        # Validate right chapter
        if right["start_seconds"] >= right["end_seconds"]:
            self.error.emit("Boundary move makes right chapter invalid")
            return False
        if right["end_seconds"] - right["start_seconds"] < 5.0:
            self.error.emit("Right chapter too short (<5s)")
            return False

        self._chapters[boundary_index] = left
        self._chapters[boundary_index + 1] = right
        self.chapters_updated.emit(list(self._chapters))
        return True

    def remove_chapter(self, index: int) -> bool:
        """Remove a chapter and merge its range with a neighbor.

        Args:
            index: Chapter index to remove.

        Returns:
            ``True`` if removal succeeded.
        """
        if index < 0 or index >= len(self._chapters):
            self.error.emit(f"Invalid chapter index: {index}")
            return False

        if len(self._chapters) <= 1:
            self.error.emit("Cannot remove the last chapter")
            return False

        removed = self._chapters.pop(index)

        # Extend neighbor to fill the gap
        if index > 0:
            self._chapters[index - 1]["end_seconds"] = removed["end_seconds"]
        elif index < len(self._chapters):
            self._chapters[index]["start_seconds"] = removed["start_seconds"]

        self.chapters_updated.emit(list(self._chapters))
        return True

    def merge_chapters(self, index: int) -> bool:
        """Merge chapter at ``index`` with the next one.

        Args:
            index: First chapter to merge.

        Returns:
            ``True`` if merge succeeded.
        """
        if index < 0 or index + 1 >= len(self._chapters):
            self.error.emit(f"Cannot merge: invalid index {index}")
            return False

        current = self._chapters[index]
        next_ch = self._chapters[index + 1]

        merged = {
            "title": f"{current['title']}+{next_ch['title']}",
            "start_seconds": current["start_seconds"],
            "end_seconds": next_ch["end_seconds"],
        }
        self._chapters[index] = merged
        self._chapters.pop(index + 1)

        self.chapters_updated.emit(list(self._chapters))
        return True

    # -- Revalidation ------------------------------------------------------

    def revalidate(self) -> None:
        """Re-run ChapterValidator on current chapters.

        Useful after manual edits to re-align boundaries to transcript
        segments and merge undersized chapters.
        """
        if not self._chapters or not self._transcript:
            self.error.emit("No chapters or transcript to revalidate")
            return

        try:
            chapters = [
                Chapter(
                    title=ch["title"],
                    start_seconds=ch["start_seconds"],
                    end_seconds=ch["end_seconds"],
                )
                for ch in self._chapters
            ]
            validator = ChapterValidator(self._config)
            segments = self._transcript.get("segments", [])
            base = Path(self._video_path).stem if self._video_path else "video"
            validated = validator.validate(chapters, segments, base)

            self._chapters = [
                {
                    "title": ch.title,
                    "start_seconds": ch.start_seconds,
                    "end_seconds": ch.end_seconds,
                }
                for ch in validated
            ]
            self.chapters_updated.emit(list(self._chapters))
        except Exception as exc:
            self.error.emit(f"Revalidation failed: {exc}")

    # -- Export ------------------------------------------------------------

    def export_chapters(self, output_path: Optional[str] = None) -> str:
        """Save chapters as JSON.

        Args:
            output_path: Target file path.  Auto-derived from
                ``_video_path`` if omitted.

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If no video path is set.
        """
        if not self._video_path:
            raise ValueError("No video path set")

        if output_path is None:
            output_path = str(
                Path(self._video_path).with_suffix(".chapters.json")
            )

        data = {
            "video": self._video_path,
            "chapters": self._chapters,
        }
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.chapters_exported.emit(output_path)
        return output_path

    # -- Helpers -----------------------------------------------------------

    def get_chapters_for_cutter(self) -> List[Chapter]:
        """Convert internal chapter dicts to Chapter objects for VideoCutter.

        Returns:
            List of :class:`Chapter` objects.
        """
        return [
            Chapter(
                title=ch["title"],
                start_seconds=ch["start_seconds"],
                end_seconds=ch["end_seconds"],
            )
            for ch in self._chapters
        ]

    def clear(self) -> None:
        """Reset all state."""
        self._chapters.clear()
        self._transcript = None
        self._video_path = ""
