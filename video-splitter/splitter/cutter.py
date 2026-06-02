"""Video cutting using FFmpegSkill with keyframe-aware precision."""
from __future__ import annotations

import os
import subprocess
import importlib
import sys
from pathlib import Path
from typing import Callable, List, Optional


def _get_ffmpeg_skill():
    base = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(base))
    mod = importlib.import_module("ffmpeg-skill")
    return mod.FFmpegSkill, mod.FFmpegError


FFmpegSkill, FFmpegError = _get_ffmpeg_skill()


class VideoCutter:
    """Cuts video into segments using FFmpegSkill."""

    def __init__(self, config, progress_callback: Optional[Callable[[float], None]] = None):
        self.config = config
        self.ffmpeg = FFmpegSkill()
        self.progress_callback = progress_callback

    def cut(self, video_path: str, chapters: list, output_dir: str) -> List[str]:
        os.makedirs(output_dir, exist_ok=True)
        base_name = Path(video_path).stem
        output_files = []

        for i, ch in enumerate(chapters, 1):
            title = ch.title if hasattr(ch, "title") else ch.get("title", f"{i:02d}_片段{i}")
            start = ch.start_seconds if hasattr(ch, "start_seconds") else ch["start_seconds"]
            end = ch.end_seconds if hasattr(ch, "end_seconds") else ch["end_seconds"]

            out_name = f"{base_name}_{title}.mp4"
            out_path = os.path.join(output_dir, out_name)

            if self.config.cut_mode == "precise":
                self._cut_precise(video_path, out_path, start, end)
            else:
                self._cut_fast(video_path, out_path, start, end)

            output_files.append(out_path)

            if self.progress_callback:
                self.progress_callback(i / len(chapters))

        return output_files

    def _cut_fast(self, video_path: str, out_path: str, start: float, end: float):
        duration = end - start

        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-i", video_path,
            "-to", str(duration), "-c", "copy", "-avoid_negative_ts", "make_zero",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            self._cut_precise(video_path, out_path, start, end)
            return

        actual_dur = self._get_duration(out_path)
        offset = abs(actual_dur - duration)
        if offset > self.config.keyframe_tolerance:
            self._cut_precise(video_path, out_path, start, end)

    def _cut_precise(self, video_path: str, out_path: str, start: float, end: float):
        duration = end - start
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-i", video_path,
            "-to", str(duration),
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-b:a", "128k",
            out_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise FFmpegError(f"FFmpeg precise cut failed: {result.stderr[-500:]}")

    def _get_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
