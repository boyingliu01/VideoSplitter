"""Burn subtitles into video segments using FFmpeg."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _format_srt_time(seconds: float) -> str:
    """Format seconds to SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_chapter_srt(
    segments: List[Dict[str, Any]],
    chapter_start: float,
    chapter_end: float,
) -> str:
    """Generate SRT content for a single chapter.

    Filters transcript segments that overlap with the chapter time range
    and shifts timestamps relative to chapter start.

    Args:
        segments: Transcript segments with ``text``, ``start``, ``end``.
        chapter_start: Chapter start time in seconds (absolute).
        chapter_end: Chapter end time in seconds (absolute).

    Returns:
        SRT-formatted string with time-shifted subtitles.
    """
    lines: list[str] = []
    idx = 0

    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]

        # Skip segments completely outside the chapter
        if seg_end <= chapter_start or seg_start >= chapter_end:
            continue

        # Clamp to chapter boundaries and shift to local time
        local_start = max(seg_start, chapter_start) - chapter_start
        local_end = min(seg_end, chapter_end) - chapter_start

        if local_end <= local_start:
            continue

        idx += 1
        lines.append(str(idx))
        lines.append(f"{_format_srt_time(local_start)} --> {_format_srt_time(local_end)}")
        lines.append(seg["text"])
        lines.append("")

    return "\n".join(lines)


class SubtitleBurner:
    """Burns subtitles into video segments using FFmpeg.

    Uses the ``subtitles`` video filter to hard-burn SRT subtitles
    into each video segment.  Requires re-encoding (libx264 + aac).
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.progress_callback = progress_callback

    def burn(
        self,
        segment_files: List[str],
        chapters: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
        output_dir: Optional[str] = None,
    ) -> List[str]:
        """Burn subtitles into a list of video segments.

        For each segment, an SRT file is generated from the transcript
        segments that fall within the chapter's time range, then burned
        into the video using FFmpeg's ``subtitles`` filter.

        Args:
            segment_files: Paths to the split video segment files.
            chapters: Chapter dicts with ``start_seconds``, ``end_seconds``.
            transcript_segments: Corrected transcript segments.
            output_dir: Directory for output files.  Defaults to the
                same directory as the input segments.

        Returns:
            List of output file paths with burned subtitles.

        Raises:
            RuntimeError: If FFmpeg subtitle burning fails.
        """
        if len(segment_files) != len(chapters):
            raise ValueError(
                f"Mismatch: {len(segment_files)} segment files "
                f"but {len(chapters)} chapters"
            )

        output_files: list[str] = []
        total = len(segment_files)

        for i, (seg_path, chapter) in enumerate(zip(segment_files, chapters)):
            ch_start = chapter["start_seconds"]
            ch_end = chapter["end_seconds"]

            # Generate SRT for this chapter
            srt_content = generate_chapter_srt(
                transcript_segments, ch_start, ch_end
            )

            # If no subtitles for this chapter, just copy the file
            if not srt_content.strip():
                output_files.append(seg_path)
                if self.progress_callback:
                    self.progress_callback((i + 1) / total)
                continue

            # Write SRT to temp file
            seg_dir = output_dir or str(Path(seg_path).parent)
            srt_path = os.path.join(
                seg_dir,
                Path(seg_path).stem + ".srt",
            )
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)

            # Build output path
            out_name = Path(seg_path).stem + "_subtitled.mp4"
            out_path = os.path.join(seg_dir, out_name)

            # Burn subtitles using FFmpeg
            self._burn_subtitles(seg_path, srt_path, out_path)

            output_files.append(out_path)

            if self.progress_callback:
                self.progress_callback((i + 1) / total)

        return output_files

    def _burn_subtitles(
        self, video_path: str, srt_path: str, out_path: str
    ) -> None:
        """Burn a single SRT file into a video segment.

        Args:
            video_path: Input video file.
            srt_path: Input SRT subtitle file.
            out_path: Output video file with burned subtitles.

        Raises:
            RuntimeError: If FFmpeg exits with non-zero return code.
        """
        # On Windows, backslashes and colons in the path must be escaped
        # for the FFmpeg subtitles filter.
        escaped_srt = srt_path.replace("\\", "/").replace(":", "\\:")

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"subtitles='{escaped_srt}':force_style='FontSize=24,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,MarginV=30'",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg subtitle burn failed for {video_path}: "
                f"{result.stderr[-500:]}"
            )
