"""Tests for extractor/transcribe.py"""
import os
import sys

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.extractor.transcribe import estimate_tokens, to_srt, _format_timestamp  # noqa: E402


class TestTokenEstimation:
    def test_estimate_chinese(self):
        transcript = {"segments": [{"text": "这是一段中文测试文本"}]}
        tokens = estimate_tokens(transcript)
        assert tokens > 0
        assert tokens <= 20

    def test_estimate_empty(self):
        transcript = {"segments": []}
        tokens = estimate_tokens(transcript)
        assert tokens == 0

    def test_estimate_multiple_segments(self):
        transcript = {
            "segments": [
                {"text": "第一段内容"},
                {"text": "第二段内容"},
                {"text": "第三段内容"},
            ]
        }
        tokens = estimate_tokens(transcript)
        assert tokens > 0
        assert tokens <= 15

    def test_estimate_english(self):
        transcript = {
            "segments": [
                {"text": "This is a test transcript with English text."}
            ]
        }
        tokens = estimate_tokens(transcript)
        assert tokens > 0


class TestSRTGeneration:
    def test_to_srt(self):
        transcript = {
            "segments": [
                {"text": "你好世界", "start": 0.0, "end": 2.5},
                {"text": "这是测试", "start": 2.5, "end": 5.0},
            ]
        }
        srt = to_srt(transcript)
        assert "00:00:00,000 --> 00:00:02,500" in srt
        assert "你好世界" in srt
        assert "这是测试" in srt

    def test_to_srt_numbering(self):
        transcript = {
            "segments": [
                {"text": "A", "start": 0.0, "end": 1.0},
                {"text": "B", "start": 1.0, "end": 2.0},
                {"text": "C", "start": 2.0, "end": 3.0},
            ]
        }
        srt = to_srt(transcript)
        lines = srt.split("\n")
        assert lines[0] == "1"
        assert lines[4] == "2"
        assert lines[8] == "3"

    def test_to_srt_empty_segments(self):
        transcript = {"segments": []}
        srt = to_srt(transcript)
        assert srt == ""

    def test_to_srt_ends_with_newline_pattern(self):
        transcript = {
            "segments": [
                {"text": "Hello", "start": 0.0, "end": 1.0},
            ]
        }
        srt = to_srt(transcript)
        assert srt.endswith("\n")

    def test_timestamp_format_under_one_hour(self):
        assert _format_timestamp(65.5) == "00:01:05,500"
        assert _format_timestamp(0.0) == "00:00:00,000"

    def test_timestamp_format_over_one_hour(self):
        assert _format_timestamp(3661.0) == "01:01:01,000"
        assert _format_timestamp(7322.75) == "02:02:02,750"

    def test_timestamp_format_milliseconds(self):
        assert _format_timestamp(5.001) == "00:00:05,001"
        assert _format_timestamp(5.999) == "00:00:05,999"


class TestTranscribeFunction:
    """Tests for the transcribe() function with mocked WhisperModel."""

    @pytest.fixture(autouse=True)
    def _mock_faster_whisper(self):
        """Pre-patch faster_whisper in sys.modules to avoid slow real import."""
        mock_module = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], MagicMock(language="zh", duration=0.0))
        mock_module.WhisperModel = MagicMock(return_value=mock_model)
        with patch.dict(sys.modules, {"faster_whisper": mock_module}):
            yield

    def test_transcribe_basic(self):
        """Mock WhisperModel and verify output structure."""
        from video_splitter.extractor.transcribe import transcribe
        from video_splitter.config import SplitConfig

        fake_info = MagicMock()
        fake_info.language = "zh"
        fake_info.duration = 10.0

        fake_segment = MagicMock()
        fake_segment.text = "测试文本"
        fake_segment.start = 0.0
        fake_segment.end = 2.5

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)
        sys.modules["faster_whisper"].WhisperModel.return_value = mock_model

        config = SplitConfig()
        result = transcribe("/fake/audio.wav", config)

        assert result["language"] == "zh"
        assert result["duration"] == 10.0
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "测试文本"
        assert result["segments"][0]["start"] == 0.0
        assert result["segments"][0]["end"] == 2.5

    def test_transcribe_progress_callback(self):
        """Progress callback receives values in [0, 1]."""
        from video_splitter.extractor.transcribe import transcribe
        from video_splitter.config import SplitConfig

        fake_segment = MagicMock()
        fake_segment.text = "hello"
        fake_segment.start = 0.0
        fake_segment.end = 5.0

        fake_info = MagicMock()
        fake_info.language = "en"
        fake_info.duration = 5.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)
        sys.modules["faster_whisper"].WhisperModel.return_value = mock_model

        progress_values = []
        config = SplitConfig()
        transcribe("/fake/audio.wav", config, progress_callback=lambda v: progress_values.append(v))

        assert len(progress_values) >= 1
        assert all(0.0 <= v <= 1.0 for v in progress_values)

    def test_transcribe_empty_segments(self):
        """Zero-duration video produces empty segments."""
        from video_splitter.extractor.transcribe import transcribe
        from video_splitter.config import SplitConfig

        fake_info = MagicMock()
        fake_info.language = "zh"
        fake_info.duration = 0.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([], fake_info)
        sys.modules["faster_whisper"].WhisperModel.return_value = mock_model

        config = SplitConfig()
        result = transcribe("/fake/audio.wav", config)

        assert result["language"] == "zh"
        assert result["duration"] == 0.0
        assert result["segments"] == []

    def test_transcribe_no_progress_callback(self):
        """transcribe works fine when no progress_callback is provided."""
        from video_splitter.extractor.transcribe import transcribe
        from video_splitter.config import SplitConfig

        fake_segment = MagicMock()
        fake_segment.text = "text"
        fake_segment.start = 0.0
        fake_segment.end = 1.0

        fake_info = MagicMock()
        fake_info.language = "zh"
        fake_info.duration = 1.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_segment], fake_info)
        sys.modules["faster_whisper"].WhisperModel.return_value = mock_model

        config = SplitConfig()
        result = transcribe("/fake/audio.wav", config, progress_callback=None)

        assert len(result["segments"]) == 1

    def test_transcribe_multiple_segments(self):
        """Multiple segments are all collected."""
        from video_splitter.extractor.transcribe import transcribe
        from video_splitter.config import SplitConfig

        fake_seg1 = MagicMock()
        fake_seg1.text = "first"
        fake_seg1.start = 0.0
        fake_seg1.end = 5.0
        fake_seg2 = MagicMock()
        fake_seg2.text = "second"
        fake_seg2.start = 5.0
        fake_seg2.end = 10.0

        fake_info = MagicMock()
        fake_info.language = "en"
        fake_info.duration = 10.0

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([fake_seg1, fake_seg2], fake_info)
        sys.modules["faster_whisper"].WhisperModel.return_value = mock_model

        config = SplitConfig()
        result = transcribe("/fake/audio.wav", config)

        assert len(result["segments"]) == 2
        assert result["segments"][0]["text"] == "first"
        assert result["segments"][1]["text"] == "second"
