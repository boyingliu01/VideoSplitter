"""E2E tests for review, export, and transcript persistence.

These tests verify the full review workflow:
- Save/load transcript round-trip
- Export SRT from real transcript
- Progress file save/load/corruption recovery
- Chinese character handling in SRT export
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.review import (  # noqa: E402
    clear_progress,
    export_srt_path,
    filter_segments,
    format_segment_header,
    format_timestamp,
    load_progress,
    load_transcript,
    sanitize_text,
    save_progress,
    save_transcript_atomic,
)


@pytest.fixture
def sample_transcript():
    """Realistic transcript dict with Chinese text."""
    return {
        "language": "zh",
        "duration": 60.0,
        "segments": [
            {"text": "大家好，欢迎收看本期视频", "start": 0.5, "end": 5.2},
            {"text": "今天我们要讨论一个非常重要的话题", "start": 5.5, "end": 12.8},
            {"text": "首先让我们来看一下背景资料", "start": 13.0, "end": 20.1},
            {"text": "", "start": 20.1, "end": 20.1},  # empty — should be filtered
            {"text": "接下来进入正题", "start": 25.0, "end": 30.0},
        ],
    }


class TestTranscriptRoundTrip:
    """Save → load transcript preserves all data."""

    def test_save_load_round_trip(self, tmp_path, sample_transcript):
        """Atomic save then load should produce identical transcript."""
        path = str(tmp_path / "transcript.json")
        save_transcript_atomic(path, sample_transcript)

        loaded = load_transcript(path)
        assert loaded["language"] == "zh"
        assert loaded["duration"] == 60.0
        # Empty segments are filtered by load_transcript
        assert len(loaded["segments"]) == 4
        assert loaded["segments"][0]["text"] == "大家好，欢迎收看本期视频"
        assert loaded["segments"][0]["start"] == 0.5

    def test_atomic_save_creates_valid_json(self, tmp_path, sample_transcript):
        """Saved file should be valid, readable JSON."""
        path = str(tmp_path / "atomic.json")
        save_transcript_atomic(path, sample_transcript)

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["language"] == "zh"
        assert len(data["segments"]) == 5  # raw save, no filtering

    def test_load_nonexistent_raises(self):
        """Loading nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_transcript("/nonexistent/path.json")

    def test_chinese_text_preserved(self, tmp_path):
        """Chinese characters should survive JSON round-trip."""
        transcript = {
            "language": "zh",
            "duration": 10.0,
            "segments": [
                {"text": "这是一个中文测试句子", "start": 0.0, "end": 5.0},
            ],
        }
        path = str(tmp_path / "chinese.json")
        save_transcript_atomic(path, transcript)
        loaded = load_transcript(path)
        assert loaded["segments"][0]["text"] == "这是一个中文测试句子"


class TestSRTExport:
    """Export transcript to SRT subtitle format."""

    def test_export_srt_path_generation(self, tmp_path):
        """SRT path should be derived from transcript path."""
        transcript_path = str(tmp_path / "video.transcript.json")
        srt_path = export_srt_path(transcript_path)
        assert srt_path.endswith(".srt")
        # .with_suffix("").with_suffix(".srt") strips .json then .transcript
        # so video.transcript.json → video.srt
        assert "video" in srt_path

    def test_to_srt_with_chinese_text(self, sample_transcript):
        """SRT output should contain properly formatted Chinese subtitles."""
        from video_splitter.extractor.transcribe import to_srt

        srt = to_srt(sample_transcript)
        assert "大家好，欢迎收看本期视频" in srt
        assert "今天我们要讨论一个非常重要的话题" in srt
        # SRT format: number, timestamp, text, blank line
        assert "1\n" in srt
        assert "00:00:00,500" in srt

    def test_to_srt_empty_segments_included(self):
        """to_srt includes all segments (filtering is caller's responsibility)."""
        from video_splitter.extractor.transcribe import to_srt

        transcript = {
            "language": "zh",
            "duration": 10.0,
            "segments": [
                {"text": "有效文本", "start": 0.0, "end": 5.0},
                {"text": "", "start": 5.0, "end": 5.0},
                {"text": "   ", "start": 5.0, "end": 10.0},
            ],
        }
        srt = to_srt(transcript)
        assert "有效文本" in srt
        # to_srt includes ALL segments (even empty ones)
        # Filtering should be done before calling to_srt
        blocks = [line for line in srt.strip().split("\n") if line.strip().isdigit()]
        assert len(blocks) == 3  # all 3 segments included


class TestProgressFile:
    """Review progress save/load/clear cycle."""

    def test_save_and_load_progress(self, tmp_path):
        """Progress file round-trip should preserve data."""
        video_path = str(tmp_path / "test.mp4")
        # Create dummy video file
        with open(video_path, "w") as f:
            f.write("dummy")

        progress = {
            "current_index": 5,
            "modified_count": 2,
            "segments": [{"text": "modified", "start": 0.0, "end": 1.0}],
        }
        save_progress(video_path, progress)
        loaded = load_progress(video_path)

        assert loaded is not None
        assert loaded["current_index"] == 5
        assert loaded["modified_count"] == 2
        assert len(loaded["segments"]) == 1

    def test_load_progress_no_file(self, tmp_path):
        """No progress file returns None."""
        video_path = str(tmp_path / "no_progress.mp4")
        assert load_progress(video_path) is None

    def test_load_progress_corrupted_file(self, tmp_path):
        """Corrupted progress file returns None and renames file."""
        video_path = str(tmp_path / "corrupt.mp4")
        with open(video_path, "w") as f:
            f.write("dummy")

        prog_path = video_path + ".review_progress.json"
        with open(prog_path, "w") as f:
            f.write("not valid json{{{")

        result = load_progress(video_path)
        assert result is None
        # Corrupted file should be renamed
        assert os.path.exists(prog_path + ".corrupted")

    def test_clear_progress(self, tmp_path):
        """clear_progress should delete the progress file."""
        video_path = str(tmp_path / "clear.mp4")
        with open(video_path, "w") as f:
            f.write("dummy")

        prog_path = video_path + ".review_progress.json"
        with open(prog_path, "w") as f:
            json.dump({"index": 0}, f)

        assert os.path.exists(prog_path)
        clear_progress(video_path)
        assert not os.path.exists(prog_path)


class TestSanitizeText:
    """Text sanitization for transcript content."""

    def test_strip_control_chars(self):
        """Control characters should be removed."""
        assert sanitize_text("hello\x00world") == "helloworld"
        assert sanitize_text("test\x1fdata") == "testdata"

    def test_preserve_chinese(self):
        """Chinese characters should be preserved."""
        assert sanitize_text("你好世界") == "你好世界"
        assert sanitize_text("测试\t文本") == "测试文本"

    def test_unicode_normalization(self):
        """Unicode should be NFKC normalized."""
        # Full-width → half-width
        result = sanitize_text("\uff21\uff22\uff23")  # ＡＢＣ
        assert result == "ABC"

    def test_strip_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        assert sanitize_text("  hello  ") == "hello"


class TestFilterSegments:
    """Segment filtering logic."""

    def test_filter_empty_text(self):
        """Empty and whitespace-only segments are removed."""
        segments = [
            {"text": "valid", "start": 0.0, "end": 1.0},
            {"text": "", "start": 1.0, "end": 2.0},
            {"text": "   ", "start": 2.0, "end": 3.0},
        ]
        result = filter_segments(segments)
        assert len(result) == 1
        assert result[0]["text"] == "valid"

    def test_filter_zero_length(self):
        """Zero-length segments are removed."""
        segments = [
            {"text": "valid", "start": 0.0, "end": 5.0},
            {"text": "zero", "start": 5.0, "end": 5.0},
        ]
        result = filter_segments(segments)
        assert len(result) == 1


class TestFormatTimestamp:
    """Timestamp formatting."""

    def test_zero(self):
        assert format_timestamp(0.0) == "00:00:00.000"

    def test_minutes(self):
        assert format_timestamp(125.5) == "00:02:05.500"

    def test_hours(self):
        assert format_timestamp(3661.0) == "01:01:01.000"

    def test_segment_header(self):
        seg = {"text": "测试文本", "start": 10.0, "end": 20.5}
        header = format_segment_header(0, 5, 0, seg)
        assert "Segment 1/5" in header
        assert "00:00:10.000" in header
        assert "00:00:20.500" in header
        assert "测试文本" in header
