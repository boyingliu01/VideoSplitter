"""Tests for analyzer/validator.py"""
import os
import sys

import pytest

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.analyzer.chapter import Chapter  # noqa: E402
from video_splitter.analyzer.validator import ChapterValidator, generate_segment_filename  # noqa: E402
from video_splitter.config import SplitConfig  # noqa: E402


@pytest.fixture
def validator_15min():
    """ChapterValidator with 15-min max, 1-min min."""
    return ChapterValidator(SplitConfig(max_segment_duration=15, min_segment_duration=1))


@pytest.fixture
def validator_default():
    """ChapterValidator with default config."""
    return ChapterValidator(SplitConfig())


@pytest.fixture
def validator_0min_60max():
    """ChapterValidator with min_segment=0, max_segment=60."""
    return ChapterValidator(SplitConfig(min_segment_duration=0, max_segment_duration=60))


class TestMergeUndersized:
    def test_merge_short_segment_with_next(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 330),
            Chapter("03", 330, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2

    def test_no_merge_when_all_valid(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2
        assert result[0].end_seconds == 300.0
        assert result[1].end_seconds == 600.0

    def test_single_chapter_unchanged(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [Chapter("01", 0, 30)]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1

    def test_merge_short_with_prev_when_no_next(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 330),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 330.0


class TestSplitOversized:
    def test_split_long_segment(self, validator_15min):
        chapters = [Chapter("01", 0, 2000)]
        result = validator_15min._split_oversized(chapters)
        assert len(result) == 3
        for ch in result:
            assert ch.end_seconds - ch.start_seconds <= 900 + 5

    def test_no_split_when_valid(self, validator_15min):
        chapters = [
            Chapter("01", 0, 600),
            Chapter("02", 600, 900),
        ]
        result = validator_15min._split_oversized(chapters)
        assert len(result) == 2

    def test_split_parts_have_unique_titles(self, validator_15min):
        chapters = [Chapter("05_深度学习", 0, 2000)]
        result = validator_15min._split_oversized(chapters)
        titles = [ch.title for ch in result]
        assert "05_深度学习_part1" in titles
        assert "05_深度学习_part3" in titles
        assert len(set(titles)) == len(titles)


class TestFilenameGeneration:
    def test_basic_template(self):
        name = generate_segment_filename("lesson", "{basename}_{seq:02d}_{title}", 1, "简介")
        assert name == "lesson_01_简介"

    def test_illegal_chars_removed(self):
        name = generate_segment_filename("test", "{basename}_{seq:02d}_{title}", 1, "架构/概述:核心")
        assert "/" not in name
        assert ":" not in name

    def test_custom_template(self):
        name = generate_segment_filename("video", "{seq:03d}-{title}", 5, "部署方案")
        assert name == "005-部署方案"

    def test_illegal_chars_removed_from_title_only(self):
        name = generate_segment_filename("abc", "{basename}_{seq:02d}_{title}", 1, 'test?"<>|')
        assert '"' not in name
        assert "?" not in name
        assert "<" not in name
        assert ">" not in name
        assert "|" not in name
        assert "abc_01_test" == name


class TestBoundaryAlignment:
    def test_align_to_segment(self, validator_default):
        chapters = [Chapter("01", 0, 310)]
        segments = [
            {"start": 0, "end": 305},
            {"start": 305, "end": 610},
        ]
        result = validator_default._align_to_segments(chapters[0], segments)
        assert result.end_seconds == 305.0

    def test_align_empty_segments_no_change(self, validator_default):
        ch = Chapter("01", 0, 300)
        result = validator_default._align_to_segments(ch, [])
        assert result.end_seconds == 300.0

    def test_align_to_closer_boundary(self, validator_default):
        ch = Chapter("01", 0, 308)
        segments = [
            {"start": 0, "end": 300},
            {"start": 300, "end": 310},
            {"start": 310, "end": 600},
        ]
        result = validator_default._align_to_segments(ch, segments)
        assert result.end_seconds == 310.0


class TestValidatePipeline:
    def test_validate_adds_sequence_prefix(self, validator_0min_60max):
        chapters = [
            Chapter("系统架构", 0, 300),
            Chapter("部署方案", 300, 600),
        ]
        result = validator_0min_60max.validate(chapters, [], "video")
        assert result[0].title == "01_系统架构"
        assert result[1].title == "02_部署方案"

    def test_validate_strips_illegal_chars_in_title(self, validator_0min_60max):
        chapters = [Chapter("核心:架构/概述", 0, 300)]
        result = validator_0min_60max.validate(chapters, [], "video")
        assert ":" not in result[0].title
        assert "/" not in result[0].title
        assert result[0].title.startswith("01_")
