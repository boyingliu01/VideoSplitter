"""Tests for splitter/cutter.py — VideoCutter with mocked subprocess."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.config import SplitConfig  # noqa: E402
from video_splitter.analyzer.chapter import Chapter  # noqa: E402


class TestVideoCutter:
    """Tests for VideoCutter.cut() with mocked FFmpeg subprocess calls."""

    @pytest.fixture(autouse=True)
    def mock_ffmpeg_skill(self):
        """Mock FFmpegSkill constructor to avoid real FFmpeg dependency."""
        with patch("video_splitter.splitter.cutter.FFmpegSkill") as mock_skill:
            mock_skill.return_value = MagicMock()
            yield mock_skill

    def test_cut_fast_mode_success(self, tmp_path):
        """Fast mode: successful ffmpeg + duration check within tolerance."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)
        chapters = [
            Chapter("01_简介", 0.0, 30.0),
            Chapter("02_正文", 30.0, 60.0),
        ]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config)
        cutter._cut_fast = MagicMock()
        cutter._get_duration = MagicMock(return_value=30.0)

        result = cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert len(result) == 2
        assert os.path.exists(output_dir)
        assert cutter._cut_fast.call_count == 2

    def test_cut_fast_falls_back_to_precise(self, tmp_path):
        """Fast mode: when ffmpeg returns non-zero, fall back to precise."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)
        cutter = VideoCutter(config)
        cutter._cut_precise = MagicMock()

        # Simulate _cut_fast failing: subprocess returns non-zero
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            cutter._cut_fast(str(tmp_path / "test.mp4"), str(tmp_path / "output" / "file.mp4"), 0.0, 30.0)

        cutter._cut_precise.assert_called_once()

    def test_cut_precise_mode_direct(self, tmp_path):
        """Precise mode: calls _cut_precise directly without _cut_fast."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="precise", keyframe_tolerance=0.5)
        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config)
        cutter._cut_precise = MagicMock()
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        cutter._cut_precise.assert_called_once()
        cutter._cut_fast.assert_not_called()

    def test_cut_precise_success(self, tmp_path):
        """Precise mode: successful ffmpeg re-encode."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="precise", keyframe_tolerance=0.5)
        cutter = VideoCutter(config)
        mock_result = MagicMock()
        mock_result.returncode = 0

        out_path = str(tmp_path / "output" / "file.mp4")
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            cutter._cut_precise(str(tmp_path / "test.mp4"), out_path, 0.0, 30.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-c:v" in cmd
        assert "libx264" in cmd

    def test_cut_precise_failure(self, tmp_path):
        """Precise mode: non-zero exit raises FFmpegError."""
        from video_splitter.splitter.cutter import VideoCutter, FFmpegError

        config = SplitConfig(cut_mode="precise", keyframe_tolerance=0.5)
        cutter = VideoCutter(config)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error"

        out_path = str(tmp_path / "output" / "file.mp4")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(FFmpegError, match="FFmpeg precise cut failed"):
                cutter._cut_precise(str(tmp_path / "test.mp4"), out_path, 0.0, 30.0)

    def test_cut_creates_output_dir(self, tmp_path):
        """Output directory is created if it doesn't exist."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)
        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "nested" / "output")

        cutter = VideoCutter(config)
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert os.path.exists(output_dir)

    def test_cut_progress_callback(self, tmp_path):
        """Progress callback is called with fraction values."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)
        chapters = [
            Chapter("01_a", 0.0, 30.0),
            Chapter("02_b", 30.0, 60.0),
            Chapter("03_c", 60.0, 90.0),
        ]
        output_dir = str(tmp_path / "output")
        progress_values = []

        cutter = VideoCutter(config, progress_callback=lambda v: progress_values.append(v))
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert len(progress_values) == 3
        assert progress_values == [1/3, 2/3, 3/3]

    def test_get_duration(self, tmp_path):
        """_get_duration parses ffprobe output correctly."""
        from video_splitter.splitter.cutter import VideoCutter

        config = SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)
        cutter = VideoCutter(config)
        mock_result = MagicMock()
        mock_result.stdout = "45.678\n"
        with patch("subprocess.run", return_value=mock_result):
            duration = cutter._get_duration("/some/video.mp4")
        assert duration == 45.678
