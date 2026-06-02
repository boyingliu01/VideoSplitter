"""Tests for analyzer/validator.py"""
import sys
import importlib

sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')


def _get_modules():
    chapter_mod = importlib.import_module('video-splitter.analyzer.chapter')
    validator_mod = importlib.import_module('video-splitter.analyzer.validator')
    config_mod = importlib.import_module('video-splitter.config')
    return chapter_mod, validator_mod, config_mod


class TestMergeUndersized:
    def test_merge_short_segment_with_next(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=1)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 300),
            chapter_mod.Chapter("02", 300, 330),
            chapter_mod.Chapter("03", 330, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2

    def test_no_merge_when_all_valid(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=1)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 300),
            chapter_mod.Chapter("02", 300, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2
        assert result[0].end_seconds == 300.0
        assert result[1].end_seconds == 600.0

    def test_single_chapter_unchanged(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=1)
        validator = validator_mod.ChapterValidator(config)
        chapters = [chapter_mod.Chapter("01", 0, 30)]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1

    def test_merge_short_with_prev_when_no_next(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=1)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 300),
            chapter_mod.Chapter("02", 300, 330),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 330.0


class TestSplitOversized:
    def test_split_long_segment(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 2000)
        ]
        result = validator._split_oversized(chapters)
        assert len(result) == 3
        for ch in result:
            assert ch.end_seconds - ch.start_seconds <= 900 + 5

    def test_no_split_when_valid(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 600),
            chapter_mod.Chapter("02", 600, 900),
        ]
        result = validator._split_oversized(chapters)
        assert len(result) == 2

    def test_split_parts_have_unique_titles(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(max_segment_duration=15)
        validator = validator_mod.ChapterValidator(config)
        chapters = [chapter_mod.Chapter("05_深度学习", 0, 2000)]
        result = validator._split_oversized(chapters)
        titles = [ch.title for ch in result]
        assert "05_深度学习_part1" in titles
        assert "05_深度学习_part3" in titles
        assert len(set(titles)) == len(titles)


class TestFilenameGeneration:
    def test_basic_template(self):
        _, validator_mod, _ = _get_modules()
        name = validator_mod.generate_segment_filename("lesson", "{basename}_{seq:02d}_{title}", 1, "简介")
        assert name == "lesson_01_简介"

    def test_illegal_chars_removed(self):
        _, validator_mod, _ = _get_modules()
        name = validator_mod.generate_segment_filename("test", "{basename}_{seq:02d}_{title}", 1, "架构/概述:核心")
        assert "/" not in name
        assert ":" not in name

    def test_custom_template(self):
        _, validator_mod, _ = _get_modules()
        name = validator_mod.generate_segment_filename("video", "{seq:03d}-{title}", 5, "部署方案")
        assert name == "005-部署方案"

    def test_illegal_chars_removed_from_title_only(self):
        _, validator_mod, _ = _get_modules()
        name = validator_mod.generate_segment_filename("abc", "{basename}_{seq:02d}_{title}", 1, 'test?"<>|')
        assert '"' not in name
        assert "?" not in name
        assert "<" not in name
        assert ">" not in name
        assert "|" not in name
        assert "abc_01_test" == name


class TestBoundaryAlignment:
    def test_align_to_segment(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig()
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("01", 0, 310)
        ]
        segments = [
            {"start": 0, "end": 305},
            {"start": 305, "end": 610},
        ]
        result = validator._align_to_segments(chapters[0], segments)
        assert result.end_seconds == 305.0

    def test_align_empty_segments_no_change(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig()
        validator = validator_mod.ChapterValidator(config)
        ch = chapter_mod.Chapter("01", 0, 300)
        result = validator._align_to_segments(ch, [])
        assert result.end_seconds == 300.0

    def test_align_to_closer_boundary(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig()
        validator = validator_mod.ChapterValidator(config)
        ch = chapter_mod.Chapter("01", 0, 308)
        segments = [
            {"start": 0, "end": 300},
            {"start": 300, "end": 310},
            {"start": 310, "end": 600},
        ]
        result = validator._align_to_segments(ch, segments)
        assert result.end_seconds == 310.0


class TestValidatePipeline:
    def test_validate_adds_sequence_prefix(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=0, max_segment_duration=60)
        validator = validator_mod.ChapterValidator(config)
        chapters = [
            chapter_mod.Chapter("系统架构", 0, 300),
            chapter_mod.Chapter("部署方案", 300, 600),
        ]
        result = validator.validate(chapters, [], "video")
        assert result[0].title == "01_系统架构"
        assert result[1].title == "02_部署方案"

    def test_validate_strips_illegal_chars_in_title(self):
        chapter_mod, validator_mod, config_mod = _get_modules()
        config = config_mod.SplitConfig(min_segment_duration=0, max_segment_duration=60)
        validator = validator_mod.ChapterValidator(config)
        chapters = [chapter_mod.Chapter("核心:架构/概述", 0, 300)]
        result = validator.validate(chapters, [], "video")
        assert ":" not in result[0].title
        assert "/" not in result[0].title
        assert result[0].title.startswith("01_")
