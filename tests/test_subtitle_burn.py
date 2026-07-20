"""Tests for subtitle burning functionality."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from video_splitter.splitter.subtitle_burner import (
    SubtitleBurner,
    _format_srt_time,
    generate_chapter_srt,
)


# ── _format_srt_time ─────────────────────────────────────────────────


class TestFormatSrtTime:
    def test_zero(self):
        assert _format_srt_time(0.0) == "00:00:00,000"

    def test_seconds(self):
        assert _format_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _format_srt_time(125.0) == "00:02:05,000"

    def test_hours(self):
        assert _format_srt_time(3661.123) == "01:01:01,123"


# ── generate_chapter_srt ─────────────────────────────────────────────


class TestGenerateChapterSrt:
    SEGMENTS = [
        {"text": "第一段", "start": 0.0, "end": 10.0},
        {"text": "第二段", "start": 10.0, "end": 20.0},
        {"text": "第三段", "start": 20.0, "end": 30.0},
        {"text": "第四段", "start": 30.0, "end": 40.0},
    ]

    def test_full_chapter(self):
        """Chapter covering segments 1-2 exactly."""
        srt = generate_chapter_srt(self.SEGMENTS, 0.0, 20.0)
        assert "第一段" in srt
        assert "第二段" in srt
        assert "第三段" not in srt
        assert "第四段" not in srt

    def test_partial_chapter(self):
        """Chapter starts mid-segment."""
        srt = generate_chapter_srt(self.SEGMENTS, 5.0, 25.0)
        assert "第一段" in srt
        assert "第二段" in srt
        assert "第三段" in srt
        assert "第四段" not in srt

    def test_time_shift(self):
        """Timestamps should be relative to chapter start."""
        srt = generate_chapter_srt(self.SEGMENTS, 10.0, 30.0)
        # "第二段" starts at 10s absolute → 0s local
        assert "00:00:00,000" in srt
        # "第三段" starts at 20s absolute → 10s local
        assert "00:00:10,000" in srt

    def test_empty_chapter(self):
        """No segments in range → empty SRT."""
        srt = generate_chapter_srt(self.SEGMENTS, 50.0, 60.0)
        assert srt.strip() == ""

    def test_single_segment_overlap(self):
        """Chapter boundary cuts through a segment."""
        srt = generate_chapter_srt(self.SEGMENTS, 8.0, 12.0)
        assert "第一段" in srt
        assert "第二段" in srt
        # Local times: 8→0, 10→2, 12→4
        assert "00:00:00,000" in srt
        assert "00:00:02,000" in srt
        assert "00:00:04,000" in srt

    def test_empty_segments(self):
        srt = generate_chapter_srt([], 0.0, 10.0)
        assert srt.strip() == ""


# ── SubtitleBurner ───────────────────────────────────────────────────


class TestSubtitleBurner:
    def test_mismatch_raises(self):
        """segment_files and chapters must have same length."""
        burner = SubtitleBurner()
        with pytest.raises(ValueError, match="Mismatch"):
            burner.burn(["a.mp4"], [], [])

    @patch.object(SubtitleBurner, "_burn_subtitles")
    def test_burn_generates_srt_and_calls_ffmpeg(self, mock_burn):
        """burn() writes SRT file and calls _burn_subtitles."""
        burner = SubtitleBurner()
        segments = [{"text": "测试", "start": 0.0, "end": 5.0}]
        chapters = [
            {"title": "ch1", "start_seconds": 0.0, "end_seconds": 10.0},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            seg_path = os.path.join(tmpdir, "seg1.mp4")
            # Create dummy segment file
            with open(seg_path, "w") as f:
                f.write("dummy")

            result = burner.burn([seg_path], chapters, segments)

            assert len(result) == 1
            assert result[0].endswith("_subtitled.mp4")
            mock_burn.assert_called_once()

            # Check SRT file was created
            srt_path = os.path.join(tmpdir, "seg1.srt")
            assert os.path.exists(srt_path)
            with open(srt_path, encoding="utf-8") as f:
                content = f.read()
            assert "测试" in content

    @patch.object(SubtitleBurner, "_burn_subtitles")
    def test_burn_skips_empty_chapter(self, mock_burn):
        """If no subtitles for a chapter, skip FFmpeg call."""
        burner = SubtitleBurner()
        segments = [{"text": "测试", "start": 0.0, "end": 5.0}]
        chapters = [
            {"title": "ch1", "start_seconds": 50.0, "end_seconds": 60.0},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            seg_path = os.path.join(tmpdir, "seg1.mp4")
            with open(seg_path, "w") as f:
                f.write("dummy")

            result = burner.burn([seg_path], chapters, segments)

            # No subtitles → original file returned, no FFmpeg call
            assert result == [seg_path]
            mock_burn.assert_not_called()

    @patch.object(SubtitleBurner, "_burn_subtitles")
    def test_progress_callback(self, mock_burn):
        """Progress callback receives values in [0, 1]."""
        progress_values = []
        burner = SubtitleBurner(
            progress_callback=lambda f: progress_values.append(f)
        )
        segments = [{"text": "A", "start": 0.0, "end": 1.0}]
        chapters = [
            {"title": "ch1", "start_seconds": 0.0, "end_seconds": 5.0},
            {"title": "ch2", "start_seconds": 5.0, "end_seconds": 10.0},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            seg1 = os.path.join(tmpdir, "seg1.mp4")
            seg2 = os.path.join(tmpdir, "seg2.mp4")
            for p in [seg1, seg2]:
                with open(p, "w") as f:
                    f.write("dummy")

            burner.burn([seg1, seg2], chapters, segments)

            assert len(progress_values) == 2
            assert progress_values[-1] == 1.0

    @patch("subprocess.run")
    def test_burn_subtitles_ffmpeg_error(self, mock_run):
        """Non-zero return code raises RuntimeError."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error msg")
        burner = SubtitleBurner()
        with pytest.raises(RuntimeError, match="FFmpeg subtitle burn failed"):
            burner._burn_subtitles("in.mp4", "sub.srt", "out.mp4")


# ── BurnWorker ───────────────────────────────────────────────────────


class TestBurnWorker:
    def test_cancel_before_run(self):
        """Cancelling before run emits error."""
        from gui.workers.burn_worker import BurnWorker

        worker = BurnWorker()
        worker.cancel()

        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        worker.run(["seg.mp4"], [{"start_seconds": 0, "end_seconds": 10}], [])
        assert len(errors) == 1
        assert "Cancelled" in errors[0]

    @patch("gui.workers.burn_worker.SubtitleBurner")
    def test_run_calls_burner(self, MockBurner):
        """Worker delegates to SubtitleBurner.burn()."""
        from gui.workers.burn_worker import BurnWorker

        mock_instance = MockBurner.return_value
        mock_instance.burn.return_value = ["out_subtitled.mp4"]

        worker = BurnWorker()
        finished_results = []
        worker.finished.connect(lambda files: finished_results.extend(files))

        chapters = [{"start_seconds": 0, "end_seconds": 10}]
        segments = [{"text": "测试", "start": 0.0, "end": 5.0}]

        worker.run(["seg.mp4"], chapters, segments)

        mock_instance.burn.assert_called_once()
        assert len(finished_results) == 1

    @patch("gui.workers.burn_worker.SubtitleBurner")
    def test_run_error(self, MockBurner):
        """Exception in burner emits error signal."""
        from gui.workers.burn_worker import BurnWorker

        mock_instance = MockBurner.return_value
        mock_instance.burn.side_effect = RuntimeError("FFmpeg failed")

        worker = BurnWorker()
        errors = []
        worker.error.connect(lambda msg: errors.append(msg))

        chapters = [{"start_seconds": 0, "end_seconds": 10}]
        worker.run(["seg.mp4"], chapters, [])

        assert len(errors) == 1
        assert "FFmpeg failed" in errors[0]

    @patch("gui.workers.burn_worker.SubtitleBurner")
    def test_run_cancelled_midway(self, MockBurner):
        """Cancel between segments stops processing."""
        from gui.workers.burn_worker import BurnWorker

        mock_instance = MockBurner.return_value
        call_count = [0]

        def fake_burn(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                worker.cancel()
            return ["out.mp4"]

        mock_instance.burn.side_effect = fake_burn

        worker = BurnWorker()
        finished_results = []
        worker.finished.connect(lambda files: finished_results.extend(files))

        chapters = [
            {"start_seconds": 0, "end_seconds": 10},
            {"start_seconds": 10, "end_seconds": 20},
            {"start_seconds": 20, "end_seconds": 30},
        ]
        worker.run(["s1.mp4", "s2.mp4", "s3.mp4"], chapters, [])
        # Should have stopped after first segment
        assert len(finished_results) <= 2
