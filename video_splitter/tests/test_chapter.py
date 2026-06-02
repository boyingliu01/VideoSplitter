"""Tests for analyzer/chapter.py"""
import sys
import importlib
import pytest

sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')


def _get_modules():
        chapter_mod = importlib.import_module('video_splitter.analyzer.chapter')
        config_mod = importlib.import_module('video_splitter.config')
        return chapter_mod, config_mod


class TestTimestampParsing:
    def test_parse_mm_ss(self):
        chapter_mod, _ = _get_modules()
        assert chapter_mod._parse_timestamp("05:30") == 330.0

    def test_parse_hh_mm_ss(self):
        chapter_mod, _ = _get_modules()
        assert chapter_mod._parse_timestamp("01:02:03") == 3723.0

    def test_parse_timestamp_comma_separator(self):
        chapter_mod, _ = _get_modules()
        result = chapter_mod._parse_timestamp("01:02:03,5")
        assert abs(result - 3723.5) < 0.01

    def test_parse_timestamp_invalid(self):
        chapter_mod, _ = _get_modules()
        with pytest.raises(ValueError, match="Invalid timestamp"):
            chapter_mod._parse_timestamp("not-a-timestamp")

    def test_format_seconds_to_timestamp(self):
        chapter_mod, _ = _get_modules()
        assert chapter_mod._seconds_to_timestamp(65.0) == "01:05.000"
        assert chapter_mod._seconds_to_timestamp(3661.5) == "01:01:01.500"

    def test_format_zero_seconds(self):
        chapter_mod, _ = _get_modules()
        assert chapter_mod._seconds_to_timestamp(0.0) == "00:00.000"

    def test_format_milliseconds_precision(self):
        chapter_mod, _ = _get_modules()
        assert chapter_mod._seconds_to_timestamp(5.123) == "00:05.123"


class TestUniformSplit:
    def test_single_segment_short_video(self):
        chapter_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        detector = chapter_mod.ChapterDetector(config)
        chapters = detector._uniform_split(600)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert chapters[0].end_seconds == 600.0

    def test_multi_segment(self):
        chapter_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        detector = chapter_mod.ChapterDetector(config)
        chapters = detector._uniform_split(3600)
        assert len(chapters) == 4
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 900 + 1

    def test_edge_case_boundary(self):
        chapter_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        detector = chapter_mod.ChapterDetector(config)
        chapters = detector._uniform_split(900)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert abs(chapters[0].end_seconds - 900.0) < 0.01

    def test_very_long_video(self):
        chapter_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=10)
        detector = chapter_mod.ChapterDetector(config)
        chapters = detector._uniform_split(7200)
        assert len(chapters) == 12
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 600 + 1

    def test_chapter_titles_increment(self):
        chapter_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        detector = chapter_mod.ChapterDetector(config)
        chapters = detector._uniform_split(3600)
        for i, ch in enumerate(chapters):
            assert ch.title.startswith(f"{i + 1:02d}_")


class TestChapterModel:
    def test_to_dict(self):
        chapter_mod, _ = _get_modules()
        ch = chapter_mod.Chapter(title="01_测试", start_seconds=0.0, end_seconds=300.0)
        d = ch.to_dict()
        assert d["title"] == "01_测试"
        assert d["start"] == "00:00.000"
        assert d["end"] == "05:00.000"
        assert d["start_seconds"] == 0.0
        assert d["end_seconds"] == 300.0

    def test_to_dict_hours(self):
        chapter_mod, _ = _get_modules()
        ch = chapter_mod.Chapter(title="03_高级", start_seconds=7200.0, end_seconds=10800.0)
        d = ch.to_dict()
        assert d["start"] == "02:00:00.000"
        assert d["end"] == "03:00:00.000"

    def test_repr(self):
        chapter_mod, _ = _get_modules()
        ch = chapter_mod.Chapter(title="01_概述", start_seconds=0.0, end_seconds=300.0)
        r = repr(ch)
        assert "01_概述" in r
        assert "00:00.000" in r
        assert "05:00.000" in r
