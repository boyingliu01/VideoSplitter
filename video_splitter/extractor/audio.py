"""FFmpeg audio extraction and quality pre-check."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional, Tuple


class AudioExtractor:
    """Extracts audio from video and performs quality pre-checks."""

    VIDEO_DURATION_LIMIT_HOURS: float = 2.0

    def __init__(self, progress_callback: Optional[Callable[[float], None]] = None):
        self.progress_callback = progress_callback
        try:
            import librosa  # noqa: F401
            import numpy  # noqa: F401
            self.has_librosa = True
        except ImportError:
            self.has_librosa = False

    def precheck(self, video_path: str) -> Tuple[bool, str]:
        """Check audio quality of a video file.

        Args:
            video_path: Path to the video file.

        Returns:
            Tuple of (is_ok, message). is_ok is False only for hard failures;
            warnings are returned with is_ok=True.
        """
        if not os.path.exists(video_path):
            return False, f"Video not found: {video_path}"
        if not self.has_librosa:
            return True, "librosa not available, skipping audio pre-check"

        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True, text=True, timeout=10,
            )
            duration = float(result.stdout.strip())
            sample_dur = min(30.0, duration)

            import librosa
            import numpy as np

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", video_path,
                    "-t", str(sample_dur),
                    "-vn", "-acodec", "pcm_s16le",
                    "-ar", "16000", "-ac", "1",
                    tmp_path,
                ],
                capture_output=True, timeout=30,
            )

            y, sr = librosa.load(tmp_path, sr=16000, mono=True)
            os.unlink(tmp_path)

            rms = float(np.sqrt(np.mean(y**2)))
            if rms < 0.001:
                return False, "No detectable speech in audio (RMS < 0.001)"

            frame_len = int(sr * 0.1)
            n_frames = len(y) // frame_len
            silent_frames = 0
            for i in range(n_frames):
                frame = y[i * frame_len : (i + 1) * frame_len]
                if np.sqrt(np.mean(frame**2)) < rms * 0.1:
                    silent_frames += 1

            silence_ratio = silent_frames / max(n_frames, 1)
            if silence_ratio > 0.9:
                return (
                    True,
                    f"Warning: high silence ratio ({silence_ratio:.0%}), "
                    f"ASR may be inaccurate",
                )

            return (
                True,
                f"Audio quality OK (RMS={rms:.4f}, silence={silence_ratio:.0%})",
            )
        except Exception as e:
            return True, f"Pre-check skipped: {e}"

    def get_duration(self, video_path: str) -> float:
        """Get video duration in seconds via ffprobe.

        Args:
            video_path: Path to the video file.

        Returns:
            Duration in seconds as a float.

        Raises:
            FileNotFoundError: If video_path does not exist.
            RuntimeError: If ffprobe fails.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr[-500:]}")
        return float(result.stdout.strip())

    def extract(self, video_path: str, output_path: Optional[str] = None) -> str:
        """Extract 16kHz mono WAV audio from a video file.

        Args:
            video_path: Path to the input video.
            output_path: Optional path for the output WAV file. Defaults to
                the input path with ``.wav`` extension.

        Returns:
            Path to the extracted audio file.

        Raises:
            RuntimeError: If FFmpeg extraction fails.
        """
        if output_path is None:
            output_path = str(Path(video_path).with_suffix(".wav"))

        duration = self.get_duration(video_path)

        if duration / 3600 > self.VIDEO_DURATION_LIMIT_HOURS:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                output_path,
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le",
                "-ar", "16000", "-ac", "1",
                "-f", "wav", output_path,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg audio extraction failed: {result.stderr[-500:]}"
            )

        return output_path
