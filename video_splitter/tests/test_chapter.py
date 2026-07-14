"""Tests for analyzer/chapter.py"""
import os
import sys

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
