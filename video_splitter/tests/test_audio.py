"""Tests for extractor/audio.py — AudioExtractor with mocked subprocess."""
import os
import sys
import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.extractor.audio import AudioExtractor  # noqa: E402


class TestAudioExtractorInit:
    """Tests for AudioExtractor.__init__ — librosa detection."""

    def test_librosa_available(self):
        """When librosa is installed, has_librosa is True."""
        extractor = AudioExtractor()
        assert extractor.has_librosa is True

    def test_librosa_not_available(self):
        """When librosa import fails, has_librosa is False."""
        import builtins
        orig_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "librosa":
                raise ImportError("No module named 'librosa'")
            return orig_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            extractor = AudioExtractor()
            assert extractor.has_librosa is False


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


class TestPrecheckAudioAnalysis:
    """Tests for the librosa-based audio analysis path in precheck()."""

    def test_precheck_low_rms_returns_false(self, tmp_path):
        """RMS < 0.001 returns (False, ...)."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        extractor.has_librosa = True

        fake_y = np.zeros(16000, dtype=np.float32)  # silent → RMS ~0
        ffprobe_result = MagicMock()
        ffprobe_result.stdout = "1.0\n"

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            with patch("librosa.load", return_value=(fake_y, 16000)):
                ok, msg = extractor.precheck(video_path)
        assert ok is False
        assert "RMS" in msg

    def test_precheck_good_audio(self, tmp_path):
        """Normal audio returns (True, OK message)."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        extractor.has_librosa = True

        # Generate audio with amplitude 0.5 → RMS ~0.35
        rng = np.random.default_rng(42)
        fake_y = (rng.random(48000, dtype=np.float32) - 0.5) * 0.5

        ffprobe_result = MagicMock()
        ffprobe_result.stdout = "3.0\n"

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            with patch("librosa.load", return_value=(fake_y, 16000)):
                ok, msg = extractor.precheck(video_path)
        assert ok is True

    def test_precheck_high_silence_warning(self, tmp_path):
        """>90% silence returns (True, warning)."""
        video_path = str(tmp_path / "test.mp4")
        (tmp_path / "test.mp4").write_text("dummy")
        extractor = AudioExtractor()
        extractor.has_librosa = True

        # 99% silence: one burst then all zeros
        fake_y = np.zeros(48000, dtype=np.float32)
        fake_y[:1000] = 0.5  # first 1000 samples loud, rest silent
        # Normalize to have low enough RMS for silence ratio to trigger
        # rms of full signal is low, but most frames near zero → silence ratio > 0.9

        ffprobe_result = MagicMock()
        ffprobe_result.stdout = "3.0\n"

        def fake_run(cmd, **kwargs):
            if "ffprobe" in cmd[0]:
                return ffprobe_result
            return MagicMock(returncode=0)

        with patch("subprocess.run", side_effect=fake_run):
            with patch("librosa.load", return_value=(fake_y, 16000)):
                ok, msg = extractor.precheck(video_path)
        assert ok is True
        assert "silence" in msg.lower()


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
