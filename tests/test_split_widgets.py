"""Unit tests for Split-related widgets and workers."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _PROJ_ROOT)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


from gui.widgets.chapter_list import ChapterListWidget  # noqa: E402
from gui.widgets.timeline import TimelineWidget  # noqa: E402
from gui.widgets.split_panel import SplitPanel  # noqa: E402
from gui.workers.detect_worker import DetectChaptersWorker  # noqa: E402
from gui.workers.split_worker import SplitWorker  # noqa: E402
from gui.controllers.review_controller import ReviewController  # noqa: E402


def _make_chapters(n: int = 3) -> list[dict]:
    return [
        {
            "title": f"{i+1:02d}_Chapter{i+1}",
            "start_seconds": float(i * 60),
            "end_seconds": float((i + 1) * 60),
        }
        for i in range(n)
    ]


# =============================================================================
# ChapterListWidget tests
# =============================================================================

class TestChapterListWidget:
    def test_set_chapters_populates_table(self, qapp):
        widget = ChapterListWidget()
        chapters = _make_chapters(3)
        widget.set_chapters(chapters)
        assert widget._table.rowCount() == 3

    def test_set_chapters_displays_titles(self, qapp):
        widget = ChapterListWidget()
        widget.set_chapters(_make_chapters(2))
        assert widget._table.item(0, 1).text() == "01_Chapter1"
        assert widget._table.item(1, 1).text() == "02_Chapter2"

    def test_set_chapters_displays_timestamps(self, qapp):
        widget = ChapterListWidget()
        widget.set_chapters(_make_chapters(2))
        # Start time for chapter 0
        start_text = widget._table.item(0, 2).text()
        assert "00:00" in start_text

    def test_set_chapters_blocks_signals(self, qapp):
        widget = ChapterListWidget()
        widget.chapter_edited = MagicMock()
        widget.set_chapters(_make_chapters(3))
        # cellChanged should NOT have emitted chapter_edited during set_chapters
        widget.chapter_edited.emit.assert_not_called()

    def test_set_chapters_empty(self, qapp):
        widget = ChapterListWidget()
        widget.set_chapters([])
        assert widget._table.rowCount() == 0

    def test_set_chapters_duration_column(self, qapp):
        widget = ChapterListWidget()
        widget.set_chapters(_make_chapters(2))
        # Duration for chapter 0: 60s
        dur_text = widget._table.item(0, 4).text()
        assert "60" in dur_text

    def test_selected_index_no_selection(self, qapp):
        widget = ChapterListWidget()
        widget.set_chapters(_make_chapters(2))
        assert widget.selected_index() == -1

    def test_parse_timestamp_display_hms(self):
        result = ChapterListWidget._parse_timestamp_display("01:30:45.000")
        assert abs(result - 5445.0) < 0.01

    def test_parse_timestamp_display_ms(self):
        result = ChapterListWidget._parse_timestamp_display("02:30.000")
        assert abs(result - 150.0) < 0.01

    def test_parse_timestamp_display_invalid(self):
        result = ChapterListWidget._parse_timestamp_display("invalid")
        assert result == 0.0


# =============================================================================
# TimelineWidget tests
# =============================================================================

class TestTimelineWidget:
    def test_initial_state(self, qapp):
        widget = TimelineWidget()
        assert widget._duration == 0.0
        assert widget._chapters == []

    def test_set_duration(self, qapp):
        widget = TimelineWidget()
        widget.set_duration(600.0)
        assert widget._duration == 600.0

    def test_set_duration_negative_clamped(self, qapp):
        widget = TimelineWidget()
        widget.set_duration(-10.0)
        assert widget._duration == 0.0

    def test_set_chapters(self, qapp):
        widget = TimelineWidget()
        chapters = _make_chapters(3)
        widget.set_chapters(chapters)
        assert len(widget._chapters) == 3

    def test_set_current_position(self, qapp):
        widget = TimelineWidget()
        widget.set_current_position(120.5)
        assert widget._current_position == 120.5

    def test_hit_test_boundary_found(self, qapp):
        widget = TimelineWidget()
        widget._duration = 180.0
        widget._chapters = _make_chapters(3)
        widget.resize(200, 50)

        # Boundary at 60s = 60/180 * bar_width + margin_left
        bar_width = 200 - 10 - 10  # 180px
        boundary_x = 10 + int((60 / 180) * bar_width)

        result = widget._hit_test_boundary(boundary_x, 10, bar_width)
        assert result == 0  # First boundary

    def test_hit_test_boundary_not_found(self, qapp):
        widget = TimelineWidget()
        widget._duration = 180.0
        widget._chapters = _make_chapters(3)

        result = widget._hit_test_boundary(5.0, 10, 180)
        assert result == -1

    def test_x_to_time(self, qapp):
        widget = TimelineWidget()
        # With duration=0, result is always 0
        result = widget._x_to_time(100.0, 10, 180)
        expected = ((100.0 - 10) / 180) * 0.0
        assert abs(result - expected) < 0.01

    def test_x_to_time_with_duration(self, qapp):
        widget = TimelineWidget()
        widget._duration = 600.0
        result = widget._x_to_time(100.0, 10, 180)
        expected = ((100.0 - 10) / 180) * 600.0
        assert abs(result - expected) < 0.01

    def test_format_time_short(self):
        assert TimelineWidget._format_time_short(0) == "00:00"
        assert TimelineWidget._format_time_short(65) == "01:05"
        assert TimelineWidget._format_time_short(3661) == "1:01:01"

    def test_hit_test_no_chapters(self, qapp):
        widget = TimelineWidget()
        widget._duration = 180.0
        widget._chapters = []
        result = widget._hit_test_boundary(50.0, 10, 180)
        assert result == -1


# =============================================================================
# SplitPanel tests
# =============================================================================

class TestSplitPanel:
    def test_initial_state(self, qapp):
        panel = SplitPanel()
        assert panel._detect_btn.isEnabled()
        assert not panel._validate_btn.isEnabled()
        assert not panel._split_btn.isEnabled()
        assert not panel._cancel_btn.isEnabled()

    def test_set_chapters_enables_buttons(self, qapp):
        panel = SplitPanel()
        panel.set_chapters(_make_chapters(2))
        assert panel._validate_btn.isEnabled()
        assert panel._split_btn.isEnabled()

    def test_set_chapters_empty_disables_buttons(self, qapp):
        panel = SplitPanel()
        panel.set_chapters(_make_chapters(2))
        panel.set_chapters([])
        assert not panel._validate_btn.isEnabled()
        assert not panel._split_btn.isEnabled()

    def test_set_detecting_toggles_ui(self, qapp):
        panel = SplitPanel()
        panel.set_detecting(True)
        assert not panel._detect_btn.isEnabled()
        assert panel._cancel_btn.isEnabled()
        assert "Detecting" in panel._detect_btn.text()

        panel.set_detecting(False)
        assert panel._detect_btn.isEnabled()
        assert "Detect Chapters" in panel._detect_btn.text()

    def test_set_splitting_toggles_ui(self, qapp):
        panel = SplitPanel()
        panel.set_chapters(_make_chapters(1))
        panel.set_splitting(True)
        assert not panel._split_btn.isEnabled()
        assert panel._cancel_btn.isEnabled()
        assert "Splitting" in panel._split_btn.text()

        panel.set_splitting(False)
        assert panel._split_btn.isEnabled()
        assert "Start Split" in panel._split_btn.text()

    def test_set_video_path_updates_output(self, qapp):
        panel = SplitPanel()
        panel.set_video_path("/tmp/myvideo.mp4")
        assert "myvideo_segments" in panel.output_dir()

    def test_output_dir_empty_default(self, qapp):
        panel = SplitPanel()
        assert panel.output_dir() == ""

    def test_default_output_dir(self):
        result = SplitPanel._default_output_dir("/videos/test.mp4")
        assert result.endswith("test_segments")

    def test_default_output_dir_empty(self):
        result = SplitPanel._default_output_dir("")
        assert result == ""


# =============================================================================
# DetectChaptersWorker tests
# =============================================================================

class TestDetectChaptersWorker:
    def test_initial_state(self):
        worker = DetectChaptersWorker()
        assert worker._cancelled is False

    def test_cancel(self):
        worker = DetectChaptersWorker()
        worker.cancel()
        assert worker._cancelled is True

    @patch("gui.workers.detect_worker.ChapterDetector")
    def test_run_success(self, MockDetector):
        worker = DetectChaptersWorker()
        worker.chapters_detected = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        from video_splitter.analyzer.chapter import Chapter
        mock_detector = MockDetector.return_value
        mock_detector.detect.return_value = [
            Chapter("01_A", 0, 60),
            Chapter("02_B", 60, 120),
        ]

        transcript = {"duration": 120.0, "segments": []}
        worker.run(transcript)

        worker.chapters_detected.emit.assert_called_once()
        chapters = worker.chapters_detected.emit.call_args[0][0]
        assert len(chapters) == 2
        assert chapters[0]["title"] == "01_A"

    @patch("gui.workers.detect_worker.ChapterDetector")
    def test_run_error(self, MockDetector):
        worker = DetectChaptersWorker()
        worker.chapters_detected = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        mock_detector = MockDetector.return_value
        mock_detector.detect.side_effect = RuntimeError("LLM failed")

        transcript = {"duration": 120.0, "segments": []}
        worker.run(transcript)

        worker.error.emit.assert_called_once()
        assert "LLM failed" in worker.error.emit.call_args[0][0]

    def test_run_cancelled_before_start(self):
        worker = DetectChaptersWorker()
        worker.chapters_detected = MagicMock()
        worker.error = MagicMock()
        worker.cancel()

        worker.run({"duration": 60.0, "segments": []})
        worker.error.emit.assert_called_once()
        worker.chapters_detected.emit.assert_not_called()


# =============================================================================
# SplitWorker tests
# =============================================================================

class TestSplitWorker:
    def test_initial_state(self):
        worker = SplitWorker()
        assert worker._cancelled is False

    def test_cancel(self):
        worker = SplitWorker()
        worker.cancel()
        assert worker._cancelled is True

    @patch("gui.workers.split_worker.VideoCutter")
    def test_run_success(self, MockCutter, tmp_path):
        worker = SplitWorker()
        worker.progress = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()

        mock_cutter = MockCutter.return_value
        mock_cutter.cut_single = MagicMock()

        chapters = _make_chapters(2)
        video_path = str(tmp_path / "test.mp4")
        output_dir = str(tmp_path / "output")

        worker.run(video_path, chapters, output_dir)

        worker.finished.emit.assert_called_once()
        output_files = worker.finished.emit.call_args[0][0]
        assert len(output_files) == 2

    @patch("gui.workers.split_worker.VideoCutter")
    def test_run_cancelled_before_start(self, MockCutter, tmp_path):
        worker = SplitWorker()
        worker.progress = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()
        worker.cancel()

        worker.run(str(tmp_path / "test.mp4"), _make_chapters(), str(tmp_path / "out"))
        worker.error.emit.assert_called_once()

    @patch("gui.workers.split_worker.VideoCutter")
    def test_run_cancelled_midway(self, MockCutter, tmp_path):
        worker = SplitWorker()
        worker.progress = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()

        mock_cutter = MockCutter.return_value
        mock_cutter.cut_single = MagicMock()

        chapters = _make_chapters(3)
        video_path = str(tmp_path / "test.mp4")
        output_dir = str(tmp_path / "output")

        # Cancel after first segment
        call_count = [0]

        def fake_cut(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                worker.cancel()

        mock_cutter.cut_single.side_effect = fake_cut
        worker.run(video_path, chapters, output_dir)

        # Should have finished with partial results
        worker.finished.emit.assert_called_once()
        output_files = worker.finished.emit.call_args[0][0]
        assert len(output_files) == 1  # Only first segment completed

    @patch("gui.workers.split_worker.VideoCutter")
    def test_run_error(self, MockCutter, tmp_path):
        worker = SplitWorker()
        worker.progress = MagicMock()
        worker.finished = MagicMock()
        worker.error = MagicMock()

        mock_cutter = MockCutter.return_value
        mock_cutter.cut_single.side_effect = RuntimeError("FFmpeg failed")

        worker.run(str(tmp_path / "test.mp4"), _make_chapters(1), str(tmp_path / "out"))
        worker.error.emit.assert_called_once()


# =============================================================================
# ReviewController enhancement tests (get_transcript, set_duration)
# =============================================================================

class TestReviewControllerEnhancement:
    def test_set_duration(self):
        ctrl = ReviewController()
        ctrl.set_duration(600.0)
        assert ctrl._duration == 600.0

    def test_get_transcript_returns_duration_and_segments(self):
        ctrl = ReviewController()
        ctrl._duration = 300.0
        ctrl._language = "zh"
        ctrl._segments = [
            {"text": "Hello", "start": 0, "end": 5},
            {"text": "World", "start": 5, "end": 10},
        ]

        result = ctrl.get_transcript()
        assert result["duration"] == 300.0
        assert result["language"] == "zh"
        assert len(result["segments"]) == 2

    def test_get_transcript_returns_copy(self):
        ctrl = ReviewController()
        ctrl._segments = [{"text": "A", "start": 0, "end": 1}]
        result = ctrl.get_transcript()
        result["segments"].append({"text": "B", "start": 1, "end": 2})
        # Original should not be modified
        assert len(ctrl._segments) == 1

    def test_load_transcript_stores_duration(self):
        ctrl = ReviewController()
        ctrl.progress_loaded = MagicMock()
        segments = [{"text": "test", "start": 0, "end": 5}]
        transcript = {"segments": segments, "duration": 600.0, "language": "en"}

        with (
            patch("gui.controllers.review_controller.load_transcript", return_value=transcript),
            patch("gui.controllers.review_controller.load_progress", return_value=None),
        ):
            ctrl.load_transcript("test.json")

        assert ctrl._duration == 600.0
        assert ctrl._language == "en"
