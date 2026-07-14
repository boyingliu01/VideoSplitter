"""Tests for analyzer/chapter.py"""
import os
import sys
from unittest.mock import patch

import pytest

# Compute project root from this file's location (3 levels up: tests/ -> video_splitter/ -> E:\Private\VideoSplitter)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.analyzer.chapter import Chapter, ChapterDetector, _parse_timestamp, _seconds_to_timestamp  # noqa: E402
from video_splitter.config import SplitConfig  # noqa: E402


@pytest.fixture
def detector_15min():
    """ChapterDetector configured for 15-minute max segment."""
    return ChapterDetector(SplitConfig(max_segment_duration=15))


@pytest.fixture
def detector_10min():
    """ChapterDetector configured for 10-minute max segment."""
    return ChapterDetector(SplitConfig(max_segment_duration=10))


class TestTimestampParsing:
    def test_parse_mm_ss(self):
        assert _parse_timestamp("05:30") == 330.0

    def test_parse_hh_mm_ss(self):
        assert _parse_timestamp("01:02:03") == 3723.0

    def test_parse_timestamp_comma_separator(self):
        result = _parse_timestamp("01:02:03,5")
        assert abs(result - 3723.5) < 0.01

    def test_parse_timestamp_invalid(self):
        with pytest.raises(ValueError, match="Invalid timestamp"):
            _parse_timestamp("not-a-timestamp")

    def test_format_seconds_to_timestamp(self):
        assert _seconds_to_timestamp(65.0) == "01:05.000"
        assert _seconds_to_timestamp(3661.5) == "01:01:01.500"

    def test_format_zero_seconds(self):
        assert _seconds_to_timestamp(0.0) == "00:00.000"

    def test_format_milliseconds_precision(self):
        assert _seconds_to_timestamp(5.123) == "00:05.123"


class TestUniformSplit:
    def test_single_segment_short_video(self, detector_15min):
        chapters = detector_15min._uniform_split(600)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert chapters[0].end_seconds == 600.0

    def test_multi_segment(self, detector_15min):
        chapters = detector_15min._uniform_split(3600)
        assert len(chapters) == 4
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 900 + 1

    def test_edge_case_boundary(self, detector_15min):
        chapters = detector_15min._uniform_split(900)
        assert len(chapters) == 1
        assert abs(chapters[0].end_seconds - 900.0) < 0.01

    def test_very_long_video(self, detector_10min):
        chapters = detector_10min._uniform_split(7200)
        assert len(chapters) == 12
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 600 + 1

    def test_chapter_titles_increment(self, detector_15min):
        chapters = detector_15min._uniform_split(3600)
        for i, ch in enumerate(chapters):
            assert ch.title.startswith(f"{i + 1:02d}_")


class TestChapterModel:
    def test_to_dict(self):
        ch = Chapter(title="01_测试", start_seconds=0.0, end_seconds=300.0)
        d = ch.to_dict()
        assert d["title"] == "01_测试"
        assert d["start"] == "00:00.000"
        assert d["end"] == "05:00.000"
        assert d["start_seconds"] == 0.0
        assert d["end_seconds"] == 300.0

    def test_to_dict_hours(self):
        ch = Chapter(title="03_高级", start_seconds=7200.0, end_seconds=10800.0)
        d = ch.to_dict()
        assert d["start"] == "02:00:00.000"
        assert d["end"] == "03:00:00.000"

    def test_repr(self):
        ch = Chapter(title="01_概述", start_seconds=0.0, end_seconds=300.0)
        r = repr(ch)
        assert "01_概述" in r
        assert "00:00.000" in r
        assert "05:00.000" in r


class TestChapterDetection:
    """Tests for ChapterDetector.detect() — LLM integration with mocking."""

    def test_detect_single_call_short_transcript(self, detector_15min):
        """Single LLM call path: transcript within token budget."""
        transcript = {
            "duration": 300.0,
            "segments": [
                {"text": "第一段", "start": 0.0, "end": 150.0},
                {"text": "第二段", "start": 150.0, "end": 300.0},
            ],
        }
        fake_chapters = [
            Chapter("01_简介", 0.0, 150.0),
            Chapter("02_正文", 150.0, 300.0),
        ]
        with patch.object(detector_15min, "_single_detect", return_value=fake_chapters):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) == 2
        assert chapters[0].title == "01_简介"
        assert chapters[1].title == "02_正文"

    def test_detect_falls_back_to_uniform_on_llm_failure(self, detector_15min):
        """When all LLM retries fail, fall back to uniform split."""
        transcript = {
            "duration": 1800.0,
            "segments": [
                {"text": "短文本", "start": 0.0, "end": 10.0},
            ],
        }
        with patch.object(detector_15min, "_call_llm", side_effect=Exception("API down")):
            chapters = detector_15min.detect(transcript)
        # Should fall back to uniform split for 1800s video at 15min/segment = 2 segments
        assert len(chapters) == 2

    def test_build_transcript_text(self, detector_15min):
        """_build_transcript_text formats segments with timestamps."""
        transcript = {
            "duration": 120.0,
            "segments": [
                {"text": "你好", "start": 0.0, "end": 60.0},
                {"text": "世界", "start": 60.0, "end": 120.0},
            ],
        }
        result = detector_15min._build_transcript_text(transcript)
        assert "[00:00.000] 你好" in result
        assert "[01:00.000] 世界" in result

    def test_detect_empty_transcript(self, detector_15min):
        """Empty segments list should still work (uniform split fallback)."""
        transcript = {"duration": 600.0, "segments": []}
        with patch.object(detector_15min, "_call_llm", side_effect=Exception("API down")):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert abs(chapters[0].end_seconds - 600.0) < 0.01


class TestSplitConfig:
    """Tests for SplitConfig.from_env() environment variable parsing."""

    def test_from_env_defaults(self):
        """Default config when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            config = SplitConfig.from_env()
        assert config.max_segment_duration == 15
        assert config.resume is False
        assert config.transcription_engine == "funasr"

    def test_from_env_resume_true(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_RESUME": "1"}, clear=True):
            config = SplitConfig.from_env()
        assert config.resume is True

    def test_from_env_resume_yes(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_RESUME": "yes"}, clear=True):
            config = SplitConfig.from_env()
        assert config.resume is True

    def test_from_env_custom_engine(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_ENGINE": "whisper"}, clear=True):
            config = SplitConfig.from_env()
        assert config.transcription_engine == "whisper"

    def test_from_env_api_key_overrides(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "WHALECLOUD_API_KEY": "whale-test"}, clear=True):
            config = SplitConfig.from_env()
        # WHALECLOUD_API_KEY should override OPENAI_API_KEY
        assert config.llm_api_key == "whale-test"

    def test_from_env_device_override(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_DEVICE": "cpu"}, clear=True):
            config = SplitConfig.from_env()
        assert config.device == "cpu"
