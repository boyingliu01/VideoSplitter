"""Tests for extractor/transcribe.py"""
import os
import sys

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

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
