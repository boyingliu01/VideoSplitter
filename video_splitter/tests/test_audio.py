"""Tests for extractor/audio.py — AudioExtractor with mocked subprocess."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.extractor.audio import AudioExtractor  # noqa: E402


class TestAudioPrecheck:
    """Tests for AudioExtractor.precheck()."""

    def test_precheck_file_not_found(self):
        extractor = AudioExtractor()
        ok, msg = extractor.precheck("/nonexistent/video.mp4")
        assert ok is False
        assert "not found" in msg

    def test_precheck_no_librosa(self, tmp_path):
        """When librosa is not available, skip pre-check with OK status."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        extractor.has_librosa = False
        ok, msg = extractor.precheck(video_path)
        assert ok is True
        assert "librosa" in msg

    def test_precheck_ffprobe_failure(self, tmp_path):
        """When ffprobe subprocess fails, pre-check is skipped (returns OK)."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        extractor.has_librosa = True
        with patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
            ok, msg = extractor.precheck(video_path)
        assert ok is True
        assert "skipped" in msg.lower()


class TestGetDuration:
    """Tests for AudioExtractor.get_duration()."""

    def test_get_duration_file_not_found(self):
        extractor = AudioExtractor()
        with pytest.raises(FileNotFoundError, match="not found"):
            extractor.get_duration("/nonexistent/video.mp4")

    def test_get_duration_success(self, tmp_path):
        """Valid ffprobe output returns float duration."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "123.456\n"
        with patch("subprocess.run", return_value=mock_result):
            duration = extractor.get_duration(video_path)
        assert duration == 123.456

    def test_get_duration_ffprobe_error(self, tmp_path):
        """Non-zero ffprobe exit raises RuntimeError."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error: invalid file"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                extractor.get_duration(video_path)


class TestExtract:
    """Tests for AudioExtractor.extract()."""

    def test_extract_success(self, tmp_path):
        """Successful FFmpeg extraction returns output path."""
        video_path = str(tmp_path / "test.mp4")
        # Create a dummy video file (just needs to exist for path handling)
        (tmp_path / "test.mp4").write_text("dummy")
        # Create a dummy wav so the path exists
        (tmp_path / "test.wav").write_text("dummy")

        extractor = AudioExtractor()
        # Mock get_duration to return short duration (triggers -f wav path)
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            output = extractor.extract(video_path)

        assert output == str(tmp_path / "test.wav")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-ar" in cmd
        assert "16000" in cmd

    def test_extract_custom_output_path(self, tmp_path):
        """Custom output_path is respected."""
        video_path = str(tmp_path / "test.mp4")
        custom_out = str(tmp_path / "custom.wav")
        (tmp_path / "test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            output = extractor.extract(video_path, output_path=custom_out)
        assert output == custom_out

    def test_extract_ffmpeg_failure(self, tmp_path):
        """FFmpeg non-zero exit raises RuntimeError."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "FFmpeg error: codec not supported"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="FFmpeg audio extraction failed"):
                extractor.extract(video_path)

    def test_extract_long_video_no_f_flag(self, tmp_path):
        """Video > 2 hours: omit -f wav flag from FFmpeg command."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=8000.0)  # > 2 hours

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            extractor.extract(video_path)

        cmd = mock_run.call_args[0][0]
        assert "-f" not in cmd
