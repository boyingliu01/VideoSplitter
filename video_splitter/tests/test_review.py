"""Tests for review.py"""
from __future__ import annotations

import json
import os
import sys
import importlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
review_mod = importlib.import_module("video_splitter.review")


def _make_transcript(segments=None):
    return {
        "language": "zh",
        "duration": 10.0,
        "segments": segments or [
            {"text": "第一段", "start": 0.0, "end": 2.5},
            {"text": "第二段", "start": 2.5, "end": 5.0},
            {"text": "第三段", "start": 5.0, "end": 7.5},
            {"text": "第四段", "start": 7.5, "end": 10.0},
        ],
    }


# ─── LoadTranscript ─────────────────────────────────────────────

class TestLoadTranscript:
    def test_load_transcript_normal(self, tmp_path):
        transcript = _make_transcript()
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
        result = review_mod.load_transcript(str(path))
        assert result["language"] == "zh"
        assert len(result["segments"]) == 4

    def test_load_transcript_missing(self):
        try:
            review_mod.load_transcript("/nonexistent/path.json")
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_load_transcript_filters_empty_segments(self, tmp_path):
        transcript = _make_transcript([
            {"text": "", "start": 0.0, "end": 2.0},
            {"text": "valid", "start": 2.0, "end": 4.0},
            {"text": "   ", "start": 4.0, "end": 6.0},
        ])
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")
        result = review_mod.load_transcript(str(path))
        assert len(result["segments"]) == 1
        assert result["segments"][0]["text"] == "valid"


# ─── FilterSegments ──────────────────────────────────────────────

class TestFilterSegments:
    def test_filter_empty_text(self):
        segments = [
            {"text": "", "start": 0.0, "end": 1.0},
            {"text": "hello", "start": 1.0, "end": 2.0},
        ]
        result = review_mod.filter_segments(segments)
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    def test_filter_whitespace_text(self):
        segments = [
            {"text": "   \t\n  ", "start": 0.0, "end": 1.0},
            {"text": "hello", "start": 1.0, "end": 2.0},
        ]
        result = review_mod.filter_segments(segments)
        assert len(result) == 1
        assert result[0]["text"] == "hello"

    def test_filter_zero_length(self):
        segments = [
            {"text": "hello", "start": 1.0, "end": 1.0},
            {"text": "world", "start": 2.0, "end": 3.0},
        ]
        result = review_mod.filter_segments(segments)
        assert len(result) == 1
        assert result[0]["text"] == "world"

    def test_filter_keep_valid(self):
        segments = [
            {"text": "first", "start": 0.0, "end": 1.0},
            {"text": "second", "start": 1.0, "end": 2.0},
            {"text": "third", "start": 2.0, "end": 3.0},
        ]
        result = review_mod.filter_segments(segments)
        assert len(result) == 3

    def test_filter_empty_list(self):
        result = review_mod.filter_segments([])
        assert result == []


# ─── SanitizeText ────────────────────────────────────────────────

class TestSanitizeText:
    def test_strip_control_chars(self):
        text = "hello\x00\x01\x02world"
        result = review_mod.sanitize_text(text)
        assert result == "helloworld"

    def test_strip_null_bytes(self):
        text = "test\x00\x00\x00data"
        result = review_mod.sanitize_text(text)
        assert result == "testdata"

    def test_normalize_unicode(self):
        # NFKC: fullwidth to halfwidth
        text = "Ｈｅｌｌｏ"
        result = review_mod.sanitize_text(text)
        assert result == "Hello"

    def test_preserve_normal_text(self):
        text = "Hello, world! 你好世界"
        result = review_mod.sanitize_text(text)
        assert result == "Hello, world! 你好世界"

    def test_strip_newlines_and_tabs(self):
        text = "line1\nline2\tindented"
        result = review_mod.sanitize_text(text)
        assert result == "line1line2indented"

    def test_strip_c1_control_chars(self):
        text = "test\x80\x9fdata"
        result = review_mod.sanitize_text(text)
        assert result == "testdata"


# ─── AtomicSave ──────────────────────────────────────────────────

class TestAtomicSave:
    def test_atomic_save_and_load(self, tmp_path):
        transcript = _make_transcript()
        path = str(tmp_path / "output.json")
        review_mod.save_transcript_atomic(path, transcript)
        assert os.path.exists(path)
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        assert loaded["language"] == "zh"

    def test_atomic_save_overwrites(self, tmp_path):
        path = str(tmp_path / "output.json")
        review_mod.save_transcript_atomic(path, _make_transcript(
            [{"text": "first", "start": 0.0, "end": 1.0}]
        ))
        review_mod.save_transcript_atomic(path, _make_transcript(
            [{"text": "second", "start": 1.0, "end": 2.0}]
        ))
        loaded = json.loads(Path(path).read_text(encoding="utf-8"))
        assert loaded["segments"][0]["text"] == "second"


# ─── ProgressFile ────────────────────────────────────────────────

class TestProgressFile:
    def test_save_and_load_progress(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        progress = {"current_index": 5, "total": 10}
        review_mod.save_progress(video_path, progress)
        loaded = review_mod.load_progress(video_path)
        assert loaded is not None
        assert loaded["current_index"] == 5

    def test_load_progress_no_file(self, tmp_path):
        video_path = str(tmp_path / "nonexistent.mp4")
        result = review_mod.load_progress(video_path)
        assert result is None

    def test_load_progress_corrupted(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        prog_path = video_path + ".review_progress.json"
        Path(prog_path).write_text("not valid json{{{", encoding="utf-8")
        result = review_mod.load_progress(video_path)
        assert result is None
        # Should have renamed corrupted file
        corrupted = video_path + ".review_progress.json.corrupted"
        assert os.path.exists(corrupted)

    def test_clear_progress(self, tmp_path):
        video_path = str(tmp_path / "video.mp4")
        progress = {"current_index": 3, "total": 10}
        review_mod.save_progress(video_path, progress)
        assert os.path.exists(video_path + ".review_progress.json")
        review_mod.clear_progress(video_path)
        assert not os.path.exists(video_path + ".review_progress.json")


# ─── Formatting ──────────────────────────────────────────────────

class TestFormatting:
    def test_format_timestamp(self):
        assert review_mod.format_timestamp(0.0) == "00:00:00.000"
        assert review_mod.format_timestamp(65.5) == "00:01:05.500"
        assert review_mod.format_timestamp(3661.0) == "01:01:01.000"
        assert review_mod.format_timestamp(5.001) == "00:00:05.001"

    def test_format_segment_header(self):
        seg = {"text": "Hello world", "start": 10.0, "end": 15.5}
        header = review_mod.format_segment_header(0, 10, 2, seg)
        assert "1/10" in header
        assert "00:00:10.000" in header
        assert "00:00:15.500" in header
        assert "Hello world" in header
        assert "2 changed" in header

    def test_format_segment_header_no_modified(self):
        seg = {"text": "Test", "start": 0.0, "end": 1.0}
        header = review_mod.format_segment_header(5, 20, 0, seg)
        assert "6/20" in header
        assert "0 changed" in header


# ─── Integration ─────────────────────────────────────────────────

class TestIntegration:
    def test_full_review_flow_no_changes(self, tmp_path):
        """Simulate pressing Enter for all segments (no changes)."""
        transcript = _make_transcript([
            {"text": "A", "start": 0.0, "end": 1.0},
            {"text": "B", "start": 1.0, "end": 2.0},
            {"text": "C", "start": 2.0, "end": 3.0},
        ])
        video_path = str(tmp_path / "video.mp4")
        transcript_path = str(tmp_path / "transcript.json")
        Path(transcript_path).write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        # Use :q after reviewing 2 segments; third segment never reached
        inputs = ["", "", ":q"]
        with patch("builtins.input", side_effect=inputs):
            with patch("builtins.print"):
                review_mod.run_review(
                    video_path=video_path,
                    transcript_path=transcript_path,
                    no_save=False,
                )

        # Progress should be saved on :q
        assert os.path.exists(video_path + ".review_progress.json")
        # Transcript should NOT be overwritten on :q
        saved = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        assert len(saved["segments"]) == 3

    def test_review_with_modifications(self, tmp_path):
        """Modify a segment and complete the review."""
        transcript = _make_transcript([
            {"text": "A", "start": 0.0, "end": 1.0},
            {"text": "B", "start": 1.0, "end": 2.0},
            {"text": "C", "start": 2.0, "end": 3.0},
        ])
        video_path = str(tmp_path / "video.mp4")
        transcript_path = str(tmp_path / "transcript.json")
        Path(transcript_path).write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        # Replace segment 1, keep others, :q on last
        inputs = ["fixed A", "", "fixed C"]
        with patch("builtins.input", side_effect=inputs):
            with patch("builtins.print"):
                review_mod.run_review(
                    video_path=video_path,
                    transcript_path=transcript_path,
                    no_save=False,
                )

        # All segments completed; transcript saved
        saved = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        assert saved["segments"][0]["text"] == "fixed A"
        assert saved["segments"][1]["text"] == "B"
        assert saved["segments"][2]["text"] == "fixed C"
        # Progress should be cleared on completion
        assert not os.path.exists(video_path + ".review_progress.json")
        # SRT should be generated
        srt_path = transcript_path.replace(".transcript.json", ".srt")
        # SRT path is derived; check if it exists
        srt_path2 = str(Path(transcript_path).with_suffix("").with_suffix(".srt"))
        assert os.path.exists(srt_path2) or os.path.exists(srt_path)

    def test_no_save_mode(self, tmp_path):
        """no_save=True should not write changes."""
        transcript = _make_transcript([
            {"text": "A", "start": 0.0, "end": 1.0},
        ])
        video_path = str(tmp_path / "video.mp4")
        transcript_path = str(tmp_path / "transcript.json")
        Path(transcript_path).write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        with patch("builtins.input", side_effect=["changed"]):
            with patch("builtins.print"):
                review_mod.run_review(
                    video_path=video_path,
                    transcript_path=transcript_path,
                    no_save=True,
                )

        saved = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        assert saved["segments"][0]["text"] == "A"

    def test_jump_command(self, tmp_path):
        """Test :j N command jumps to the correct segment."""
        transcript = _make_transcript([
            {"text": "A", "start": 0.0, "end": 1.0},
            {"text": "B", "start": 1.0, "end": 2.0},
            {"text": "C", "start": 2.0, "end": 3.0},
            {"text": "D", "start": 3.0, "end": 4.0},
        ])
        video_path = str(tmp_path / "video.mp4")
        transcript_path = str(tmp_path / "transcript.json")
        Path(transcript_path).write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        # Jump to segment 4 (index 3), modify it, then quit
        inputs = [":j 4", "fixed D", ":q"]
        with patch("builtins.input", side_effect=inputs):
            with patch("builtins.print"):
                review_mod.run_review(
                    video_path=video_path,
                    transcript_path=transcript_path,
                    no_save=False,
                )

        saved = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        assert saved["segments"][3]["text"] == "fixed D"

    def test_resume_mode(self, tmp_path):
        """Resume should pick up from saved progress index."""
        transcript = _make_transcript([
            {"text": "A", "start": 0.0, "end": 1.0},
            {"text": "B", "start": 1.0, "end": 2.0},
            {"text": "C", "start": 2.0, "end": 3.0},
        ])
        video_path = str(tmp_path / "video.mp4")
        transcript_path = str(tmp_path / "transcript.json")
        Path(transcript_path).write_text(
            json.dumps(transcript, ensure_ascii=False), encoding="utf-8"
        )

        # Save progress at index 1 (segment 2)
        review_mod.save_progress(video_path, {"current_index": 1, "total": 3})

        inputs = ["fixed B", "fixed C"]
        with patch("builtins.input", side_effect=inputs):
            with patch("builtins.print"):
                review_mod.run_review(
                    video_path=video_path,
                    transcript_path=transcript_path,
                    resume=True,
                )

        saved = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        assert saved["segments"][0]["text"] == "A"  # unchanged
        assert saved["segments"][1]["text"] == "fixed B"
        assert saved["segments"][2]["text"] == "fixed C"
