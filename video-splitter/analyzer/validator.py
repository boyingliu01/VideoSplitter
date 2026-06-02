"""Chapter validation, duration constraints, boundary alignment, naming."""
from __future__ import annotations

import re
from typing import Any, List

from .chapter import Chapter


class ChapterValidator:
    """Validates and adjusts chapters to meet duration constraints.

    Applies three phases: boundary alignment to transcript segments,
    undersized segment merging, and oversized segment splitting.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.max_dur = config.max_segment_duration * 60  # seconds
        self.min_dur = config.min_segment_duration * 60  # seconds

    def validate(
        self,
        chapters: List[Chapter],
        transcript_segments: List[dict],
        base_name: str,
    ) -> List[Chapter]:
        """Validate, align, and name chapters.

        Args:
            chapters: Raw chapters from :class:`ChapterDetector`.
            transcript_segments: Transcript segment list (each with
                ``start`` and ``end`` keys in seconds).
            base_name: Base name for segment filename generation.

        Returns:
            Validated and adjusted chapter list.
        """
        aligned = [
            self._align_to_segments(ch, transcript_segments) for ch in chapters
        ]

        merged = self._merge_undersized(aligned)

        final = self._split_oversized(merged)

        for i, ch in enumerate(final, 1):
            sanitized_title = re.sub(r'[/:*?"<>|]', "", ch.title)
            if not sanitized_title.startswith(f"{i:02d}_"):
                sanitized_title = f"{i:02d}_{sanitized_title}"
            ch.title = sanitized_title

        return final

    def _align_to_segments(
        self, chapter: Chapter, segments: List[dict]
    ) -> Chapter:
        """Align chapter boundary to nearest transcript segment boundary."""
        if not segments:
            return chapter

        best_end = chapter.end_seconds
        min_dist = float("inf")
        for seg in segments:
            dist = abs(seg["end"] - chapter.end_seconds)
            if dist < min_dist:
                min_dist = dist
                best_end = seg["end"]

        return Chapter(
            title=chapter.title,
            start_seconds=chapter.start_seconds,
            end_seconds=best_end,
        )

    def _merge_undersized(self, chapters: List[Chapter]) -> List[Chapter]:
        """Merge segments shorter than minimum duration into neighbors."""
        if len(chapters) <= 1:
            return chapters

        merged: List[Chapter] = []
        i = 0
        while i < len(chapters):
            ch = chapters[i]
            dur = ch.end_seconds - ch.start_seconds

            if dur < self.min_dur and i + 1 < len(chapters):
                next_ch = chapters[i + 1]
                merged.append(
                    Chapter(
                        title=ch.title,
                        start_seconds=ch.start_seconds,
                        end_seconds=next_ch.end_seconds,
                    )
                )
                i += 2
            elif dur < self.min_dur and merged:
                merged[-1] = Chapter(
                    title=merged[-1].title,
                    start_seconds=merged[-1].start_seconds,
                    end_seconds=ch.end_seconds,
                )
                i += 1
            else:
                merged.append(ch)
                i += 1

        return merged

    def _split_oversized(self, chapters: List[Chapter]) -> List[Chapter]:
        """Recursively split chapters exceeding maximum duration."""
        result: List[Chapter] = []
        for ch in chapters:
            dur = ch.end_seconds - ch.start_seconds
            if dur <= self.max_dur:
                result.append(ch)
            else:
                n_parts = int(dur / self.max_dur) + 1
                part_dur = dur / n_parts
                for i in range(n_parts):
                    result.append(
                        Chapter(
                            title=f"{ch.title}_part{i + 1}",
                            start_seconds=ch.start_seconds + i * part_dur,
                            end_seconds=(
                                ch.start_seconds + (i + 1) * part_dur
                                if i < n_parts - 1
                                else ch.end_seconds
                            ),
                        )
                    )
        return result


def generate_segment_filename(
    base_name: str, template: str, seq: int, title: str
) -> str:
    """Generate output filename from a template.

    Args:
        base_name: Source file basename (without extension).
        template: Naming template with ``{basename}``, ``{seq}``, ``{title}``.
        seq: 1-based sequence number.
        title: Sanitized chapter title.

    Returns:
        Generated filename string.
    """
    name = template.format(basename=base_name, seq=seq, title=title)
    name = re.sub(r'[/:*?"<>|]', "", name)
    return name
