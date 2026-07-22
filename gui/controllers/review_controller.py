"""Review state machine + transcript IO + progress persistence"""

from __future__ import annotations

import os

from PySide6.QtCore import QObject, Signal

from video_splitter.review import (
    export_srt_path,
    load_progress,
    load_transcript,
    sanitize_text,
    save_progress,
    save_transcript_atomic,
)
from video_splitter.extractor.transcribe import to_srt


class ReviewController(QObject):
    """Review state machine + transcript IO + progress persistence."""

    segment_changed = Signal(dict)
    progress_loaded = Signal(dict)
    transcript_saved = Signal()
    segments_merged = Signal(int)  # number of new segments added
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._segments: list[dict] = []
        self._duration: float = 0.0
        self._language: str = ""
        self._current_index: int = 0
        self._modified_indices: set[int] = set()
        self._transcript_path: str = ""
        self._progress_path: str = ""

    def load_transcript(self, path: str) -> list[dict]:
        self._transcript_path = path

        transcript = load_transcript(path)
        self._segments = transcript["segments"]
        self._duration = transcript.get("duration", 0.0)
        self._language = transcript.get("language", "")

        progress = load_progress(path) or {}
        self._current_index = progress.get("current_index", 0)
        self._modified_indices = set(progress.get("modified_indices", []))
        total = len(self._segments)

        self.progress_loaded.emit({
            "current_index": self._current_index,
            "modified_indices": list(self._modified_indices),
            "total": total,
        })
        return self._segments

    def current_segment(self) -> dict | None:
        if 0 <= self._current_index < len(self._segments):
            seg = self._segments[self._current_index]
            return {
                "text": seg["text"],
                "start": seg["start"],
                "end": seg["end"],
                "index": self._current_index,
            }
        return None

    def save_correction(self, text: str, index: int) -> None:
        if index < 0 or index >= len(self._segments):
            self.error.emit(f"Invalid segment index: {index}")
            return

        sanitized = sanitize_text(text)
        if not sanitized:
            self.error.emit("Text is empty after sanitization")
            return

        self._segments[index]["text"] = sanitized
        self._modified_indices.add(index)

        transcript = {
            "segments": self._segments,
            "duration": self._duration,
            "language": self._language,
        }
        try:
            save_transcript_atomic(self._transcript_path, transcript)
            self._save_progress()
        except Exception as e:
            self.error.emit(str(e))

    def next(self) -> dict | None:
        if self._current_index + 1 >= len(self._segments):
            return None
        self._current_index += 1
        return self._emit_segment()

    def prev(self) -> dict | None:
        if self._current_index <= 0:
            return None
        self._current_index -= 1
        return self._emit_segment()

    def jump_to(self, n: int) -> dict | None:
        if n < 0 or n >= len(self._segments):
            return None
        self._current_index = n
        return self._emit_segment()

    def export_srt(self) -> str:
        """Export segments as SRT file (atomic write via tempfile).
        
        Returns:
            Path to the saved SRT file.
        
        Raises:
            OSError: If the file cannot be written.
        """
        transcript = {"segments": self._segments}
        srt_content = to_srt(transcript)
        srt_path = export_srt_path(self._transcript_path)
        import tempfile
        fd, tmp_path = tempfile.mkstemp(
            suffix=".srt", prefix="vs_export_", dir=os.path.dirname(srt_path) or "."
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(srt_content)
            os.replace(tmp_path, srt_path)
        except Exception:
            os.unlink(tmp_path)
            raise
        return srt_path

    def _emit_segment(self) -> dict:
        seg = self._segments[self._current_index]
        data = {
            "index": self._current_index,
            "total": len(self._segments),
            "text": seg["text"],
            "start": seg["start"],
            "end": seg["end"],
            "modified": self._current_index in self._modified_indices,
        }
        self._save_progress()
        self.segment_changed.emit(data)
        return data

    def set_duration(self, duration: float) -> None:
        """Set the transcript duration (from VideoPlayerWidget).

        Args:
            duration: Total duration in seconds.
        """
        self._duration = duration

    def get_transcript(self) -> dict:
        """Return the in-memory corrected transcript with duration + segments.

        Used by SplitController to get the user-corrected transcript
        for chapter detection, without re-reading from disk.

        Returns:
            Dict with ``duration``, ``segments``, and ``language`` keys.
        """
        return {
            "duration": self._duration,
            "language": self._language,
            "segments": list(self._segments),
        }

    def _save_progress(self) -> None:
        save_progress(self._transcript_path, {
            "current_index": self._current_index,
            "total": len(self._segments),
            "modified_count": len(self._modified_indices),
            "modified_indices": list(self._modified_indices),
        })

    def merge_segments(self, new_segments: list[dict]) -> None:
        """Merge new segments from streaming ASR into existing segments.

        Inserts new segments in start-time order, deduplicating against
        the existing tail. Does not change _current_index.

        Args:
            new_segments: List of segment dicts with 'text', 'start', 'end'.
        """
        if not new_segments:
            return

        added = 0
        for seg in new_segments:
            # Deduplicate: skip if overlapping with existing tail
            if self._segments:
                last_end = self._segments[-1]["end"]
                if seg["start"] < last_end - 0.5:
                    continue

            # Insert in sorted order by start time
            insert_pos = len(self._segments)
            for i, existing in enumerate(self._segments):
                if seg["start"] < existing["start"]:
                    insert_pos = i
                    break

            self._segments.insert(insert_pos, seg)

            # Adjust current_index if insertion is before it
            if insert_pos <= self._current_index:
                self._current_index += 1

            added += 1

        if added > 0:
            self.segments_merged.emit(added)
