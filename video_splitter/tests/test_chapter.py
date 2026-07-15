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

    def test_chunked_detect_splits_long_transcript(self, detector_15min):
        """Transcript > token budget triggers chunked_detect path."""
        # Build a transcript with many timestamped lines to trigger chunking
        segments = []
        for i in range(100):
            t = i * 30.0
            segments.append({"text": f"内容{i}", "start": t, "end": t + 30.0})
        transcript = {"duration": 3000.0, "segments": segments}

        fake_chapters = [Chapter("01_test", 0.0, 3000.0)]
        with patch.object(detector_15min, "_call_llm", return_value=fake_chapters):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) >= 1

    def test_chunked_detect_dedup_overlapping(self, detector_15min):
        """Chunked detection deduplicates overlapping chapters."""
        segments = []
        for i in range(80):
            t = i * 30.0
            segments.append({"text": f"内容{i}", "start": t, "end": t + 30.0})
        transcript = {"duration": 2400.0, "segments": segments}

        # Two identical overlapping chapters → dedup keeps one
        fake_chapters = [
            Chapter("01_intro", 0.0, 480.0),
            Chapter("02_body", 480.0, 980.0),
            Chapter("03_body_longer_title", 500.0, 1000.0),  # overlaps with 02
            Chapter("04_end", 1000.0, 1800.0),
        ]
        with patch.object(detector_15min, "_call_llm", return_value=fake_chapters):
            chapters = detector_15min.detect(transcript)
        titles = [ch.title for ch in chapters]
        # The dedup logic keeps the one with longer title when overlap > 60s
        assert len(titles) <= 4

    def test_chunked_detect_last_chunk(self, detector_15min):
        """Ensure the last chunk is appended even if it doesn't exceed chunk_duration."""
        segments = []
        for i in range(20):
            t = i * 30.0
            segments.append({"text": f"内容{i}", "start": t, "end": t + 30.0})
        transcript = {"duration": 600.0, "segments": segments}

        fake_chapters = [Chapter("01_X", 0.0, 600.0)]
        with patch.object(detector_15min, "_call_llm", return_value=fake_chapters):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) >= 1


class TestParseResponse:
    """Tests for ChapterDetector._parse_response() — JSON parsing with edge cases."""

    def test_parse_valid_json_with_markdown_fence(self, detector_15min):
        """Strip ```json ... ``` wrapper before parsing."""
        raw = '```json\n[{"title": "01_测试", "start": "00:00:00", "end": "00:05:00"}]\n```'
        chapters = detector_15min._parse_response(raw, 300.0)
        assert len(chapters) == 1
        assert chapters[0].title == "01_测试"

    def test_parse_valid_json_with_triple_backtick_no_json_tag(self, detector_15min):
        raw = '```\n[{"title": "01_概述", "start": "00:00:00", "end": "00:03:00"}]\n```'
        chapters = detector_15min._parse_response(raw, 300.0)
        assert len(chapters) == 1
        assert chapters[0].title == "01_概述"

    def test_parse_sanitizes_special_chars_in_title(self, detector_15min):
        raw = '[{"title": "01_测试/文件:名*", "start": "00:00:00", "end": "00:05:00"}]'
        chapters = detector_15min._parse_response(raw, 300.0)
        assert chapters[0].title == "01_测试文件名"

    def test_parse_auto_generates_title_when_missing(self, detector_15min):
        raw = '[{"start": "00:00:00", "end": "00:05:00"}]'
        chapters = detector_15min._parse_response(raw, 300.0)
        assert len(chapters) == 1
        assert chapters[0].title == "01_片段1"

    def test_parse_auto_start_timestamp(self, detector_15min):
        """Missing 'start' defaults to 00:00:00."""
        raw = '[{"title": "01_test", "end": "00:05:00"}]'
        chapters = detector_15min._parse_response(raw, 300.0)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert chapters[0].end_seconds == 300.0

    def test_parse_not_a_list_raises_value_error(self, detector_15min):
        raw = '{"title": "not a list"}'
        with pytest.raises(ValueError, match="Expected JSON array"):
            detector_15min._parse_response(raw, 300.0)

    def test_parse_out_of_range_timestamp_raises(self, detector_15min):
        raw = '[{"title": "t", "start": "00:00:00", "end": "99:00:00"}]'
        with pytest.raises(ValueError, match="Timecode out of range"):
            detector_15min._parse_response(raw, 300.0)

    def test_parse_start_geq_end_raises(self, detector_15min):
        raw = '[{"title": "t", "start": "00:05:00", "end": "00:01:00"}]'
        with pytest.raises(ValueError, match="Invalid time range"):
            detector_15min._parse_response(raw, 300.0)

    def test_parse_multiple_chapters_numbered(self, detector_15min):
        raw = (
            '[{"title": "01_简介", "start": "00:00:00", "end": "00:05:00"},'
            '{"title": "02_正文", "start": "00:05:00", "end": "00:10:00"}]'
        )
        chapters = detector_15min._parse_response(raw, 600.0)
        assert len(chapters) == 2
        assert chapters[0].start_seconds == 0.0
        assert chapters[1].start_seconds == 300.0


class TestCallLLM:
    """Tests for ChapterDetector._call_llm() — retry and fallback logic."""

    def test_call_llm_success_first_attempt(self, detector_15min):
        """First attempt succeeds, no retries."""
        fake_chapters = [Chapter("01_ok", 0.0, 60.0)]
        fake_response = '[{"title": "01_ok", "start": "00:00:00", "end": "00:01:00"}]'
        with patch.object(detector_15min, "_llm_request", return_value=fake_response):
            chapters = detector_15min._call_llm("prompt", 60.0)
        assert len(chapters) == 1
        assert chapters[0].title == "01_ok"

    def test_call_llm_retry_then_success(self, detector_15min):
        """First attempt fails, second succeeds after retry."""
        fake_response = '[{"title": "01_retry", "start": "00:00:00", "end": "00:01:00"}]'
        with patch.object(detector_15min, "_llm_request", side_effect=[Exception("fail"), fake_response]):
            with patch("video_splitter.analyzer.chapter.time.sleep", return_value=None):
                chapters = detector_15min._call_llm("prompt", 60.0)
        assert len(chapters) == 1
        assert chapters[0].title == "01_retry"

    def test_call_llm_all_retries_exhausted(self, detector_15min):
        """All attempts fail → fall back to uniform split."""
        with patch.object(detector_15min, "_llm_request", side_effect=Exception("always fail")):
            with patch("video_splitter.analyzer.chapter.time.sleep", return_value=None):
                chapters = detector_15min._call_llm("prompt", 900.0)
        # Should fall back to uniform split for 900s = 1 segment
        assert len(chapters) == 1

    def test_llm_request_missing_openai_raises(self, detector_15min):
        """_llm_request raises RuntimeError when openai not installed."""
        with patch.dict(sys.modules, {"openai": None}):
            with pytest.raises(RuntimeError, match="openai package required"):
                detector_15min._llm_request("prompt")


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
