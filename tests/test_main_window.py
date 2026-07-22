"""Tests for gui/app.py — MainWindow event handlers and workflow orchestration."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJ_ROOT)


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_transcript(n_segments=3, duration=30.0):
    return {
        "duration": duration,
        "language": "zh",
        "segments": [
            {"text": f"seg{i}", "start": float(i * 10), "end": float((i + 1) * 10)}
            for i in range(n_segments)
        ],
    }


def _make_chapters(n=2):
    return [
        {
            "title": f"{i+1:02d}_Ch{i+1}",
            "start_seconds": float(i * 60),
            "end_seconds": float((i + 1) * 60),
        }
        for i in range(n)
    ]


# ── MainWindow construction ──────────────────────────────────────────────

class TestMainWindowInit:
    @patch("gui.app.MainWindow._start_health_check")
    def test_init_creates_controllers(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        assert win._controller is not None
        assert win._split_controller is not None
        assert win._worker is None
        assert win._burn_worker is None
        assert win._split_output_files == []

    @patch("gui.app.MainWindow._start_health_check")
    def test_init_builds_menu_and_central(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        assert win._video_player is not None
        assert win._subtitle_panel is not None
        assert win._split_panel is not None
        assert win._tab_widget is not None
        assert win._status_bar_widget is not None

    @patch("gui.app.MainWindow._start_health_check")
    def test_health_check_failure_shows_warning(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_health_check_done(False, "Model not found")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_health_check_ok_updates_status(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_health_check_done(True, "ok")
        assert "OK" in win._status_bar_widget._label.text()


# ── Position / segment / status handlers ─────────────────────────────────

class TestMainWindowHandlers:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_position_changed(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_position_changed(65000)  # 65 seconds
        status_text = win._status_bar_widget._label.text()
        assert "01:05" in status_text

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_segment_changed(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._video_player.seek_to = MagicMock()
        data = {
            "index": 1, "total": 10, "text": "Hello world",
            "start": 5.0, "end": 15.0, "modified": True,
        }
        win._on_segment_changed(data)
        win._video_player.seek_to.assert_called_once_with(5000)

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_controller_error(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_controller_error("Something went wrong")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_save_next_no_segment(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._controller.current_segment = MagicMock(return_value=None)
        win._controller.next = MagicMock(return_value=None)
        win._on_save_next()
        status = win._status_bar_widget._label.text()
        assert "complete" in status.lower() or "review" in status.lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_save_current_with_segment(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._controller.current_segment = MagicMock(
            return_value={"index": 0, "text": "test", "start": 0, "end": 5}
        )
        win._controller.save_correction = MagicMock()
        win._subtitle_panel.get_correction = MagicMock(return_value="corrected")
        win._on_save_current()
        win._controller.save_correction.assert_called_once_with("corrected", 0)
        assert "Saved" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_next_skip(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._controller.next = MagicMock(return_value=None)
        win._on_next_skip()
        assert "complete" in win._status_bar_widget._label.text().lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_boundary_moved(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._split_controller.update_boundary = MagicMock()
        win._on_boundary_moved(1, 120.5)
        win._split_controller.update_boundary.assert_called_once_with(1, 120.5)

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_about(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_about()
            MockMsg.about.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_export_chapters_no_chapters(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._split_controller.export_chapters = MagicMock(side_effect=ValueError("No chapters"))
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_export_chapters()
            MockMsg.warning.assert_called_once()


# ── Transcribe workflow ──────────────────────────────────────────────────

class TestTranscribeWorkflow:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_transcribe_progress(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_transcribe_progress(0.5, "Processing")
        assert "50%" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_transcribe_finished(self, mock_hc, qapp, tmp_path):
        """Transcription result must be visible in subtitle panel, not just split controller."""
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_thread = MagicMock()
        # Set a video path so transcript can be saved next to it
        fake_video = str(tmp_path / "test_video.mp4")
        # Create a dummy file so Path operations work
        with open(fake_video, "wb") as f:
            f.write(b"\x00")
        win._current_video_path = fake_video

        transcript = _make_transcript()
        win._on_transcribe_finished(transcript)

        # KEY ASSERTION: ReviewController must have the segments loaded
        segments = win._controller._segments
        assert len(segments) == 3, "Subtitle panel should have segments after transcription"
        assert segments[0]["text"] == "seg0"

        # KEY ASSERTION: Subtitle panel must display the first segment
        assert "Segment 1/3" in win._subtitle_panel._segment_label.text()
        assert win._subtitle_panel._original_label.text() == "seg0"

        # Split controller should also receive the transcript
        assert win._split_controller._transcript == transcript
        win._cleanup_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_transcribe_error(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_transcribe_error("Model failed")
            MockMsg.warning.assert_called_once()
        win._cleanup_thread.assert_called_once()
        assert "failed" in win._status_bar_widget._label.text().lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_thread_none(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        assert win._worker_thread is None
        win._cleanup_thread()  # should not raise


# ── Split workflow ───────────────────────────────────────────────────────

class TestSplitWorkflow:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_split_progress(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_split_progress(0.75, "Cutting segment 3")
        assert "75%" in win._status_bar_widget._label.text()

    @patch("gui.app.QDesktopServices")
    @patch("gui.app.QMessageBox")
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_split_finished(self, mock_hc, MockMsg, MockDesktop, qapp, tmp_path):
        MockMsg.information.return_value = MockMsg.StandardButton.No
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_split_thread = MagicMock()
        files = [str(tmp_path / f"seg{i}.mp4") for i in range(3)]
        win._on_split_finished(files)
        assert win._split_output_files == files
        win._cleanup_split_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_split_finished_empty(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_split_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_split_finished([])
            # No dialog for empty list
            MockMsg.information.assert_not_called()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_split_error_detect_mode(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._detect_worker = MagicMock()
        win._split_worker = None
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_split_error("Detection failed")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_detect_chapters_no_transcript(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._controller.get_transcript = MagicMock(
            return_value={"segments": [], "duration": 0}
        )
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_detect_chapters()
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_chapters_detected(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_detect_thread = MagicMock()
        win._split_controller.receive_chapters = MagicMock()
        chapters = _make_chapters(3)
        win._on_chapters_detected(chapters)
        win._split_controller.receive_chapters.assert_called_once_with(chapters)
        win._cleanup_detect_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_detect_progress(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_detect_progress(0.3, "Analyzing")
        assert "30%" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_detect_error(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_detect_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_detect_error("LLM timeout")
            MockMsg.warning.assert_called_once()
        win._cleanup_detect_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_detect_thread_none(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_detect_thread()  # should not raise


# ── Burn workflow ────────────────────────────────────────────────────────

class TestBurnWorkflow:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_burn_progress(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_burn_progress(0.6, "Burning segment 2")
        assert "60%" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_burn_finished(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_burn_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            MockMsg.information.return_value = MockMsg.StandardButton.No
            win._on_burn_finished(["a.mp4", "b.mp4"])
            assert "2 segments" in win._status_bar_widget._label.text()
        win._cleanup_burn_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_burn_error(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_burn_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_burn_error("FFmpeg crashed")
            MockMsg.warning.assert_called_once()
        win._cleanup_burn_thread.assert_called_once()
        assert "error" in win._status_bar_widget._label.text().lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_burn_subtitles_no_segments(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._split_output_files = []
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_burn_subtitles()
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_burn_subtitles_no_transcript(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._split_output_files = ["seg1.mp4"]
        win._controller.get_transcript = MagicMock(
            return_value={"segments": [], "duration": 0}
        )
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_burn_subtitles()
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_burn_thread_none(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_burn_thread()  # should not raise


# ── Cancel / cleanup ────────────────────────────────────────────────────

class TestCancelCleanup:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_cancel_detect(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        mock_worker = MagicMock()
        win._detect_worker = mock_worker
        win._on_cancel_operation()
        mock_worker.cancel.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_cancel_split(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        mock_worker = MagicMock()
        win._split_worker = mock_worker
        win._on_cancel_operation()
        mock_worker.cancel.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_cancel_burn(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        mock_worker = MagicMock()
        win._burn_worker = mock_worker
        win._on_cancel_operation()
        mock_worker.cancel.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_split_thread_none(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_split_thread()  # should not raise

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_start_split_no_video(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._current_video_path = ""
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_start_split("/tmp/out")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_start_split_no_chapters(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._current_video_path = "/tmp/video.mp4"
        win._split_controller._chapters = []
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_start_split("/tmp/out")
            MockMsg.warning.assert_called_once()


# ── Streaming transcription integration ───────────────────────────────────

class TestStreamingIntegration:
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_audio_ready(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._split_panel.set_duration = MagicMock()
        win._on_streaming_audio_ready(120.0)
        assert win._controller._duration == 120.0
        win._split_panel.set_duration.assert_called_once_with(120.0)

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_segments_ready_merges(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._controller.merge_segments = MagicMock()
        new_segs = [{"text": "hello", "start": 0.0, "end": 5.0}]
        win._on_streaming_segments_ready(new_segs)
        win._controller.merge_segments.assert_called_once_with(new_segs)

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_chunk_completed_updates_progress(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._on_streaming_chunk_completed(2, 5)
        assert "2/5" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_error(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_streaming_thread = MagicMock()
        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_streaming_error("Model crashed")
            MockMsg.warning.assert_called_once()
        win._cleanup_streaming_thread.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_cancelled(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_streaming_thread = MagicMock()
        win._on_streaming_cancelled()
        win._cleanup_streaming_thread.assert_called_once()
        assert "cancelled" in win._status_bar_widget._label.text().lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_video_seeked_forwards_priority(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        mock_worker = MagicMock()
        win._streaming_worker = mock_worker
        win._on_video_seeked(45000)  # 45 seconds
        mock_worker.request_priority.assert_called_once_with(45.0)

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_video_seeked_no_worker(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        assert win._streaming_worker is None
        win._on_video_seeked(45000)  # Should not raise

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_streaming_thread_none(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_streaming_thread()  # Should not raise

    @patch("gui.app.MainWindow._start_health_check")
    def test_on_cancel_streaming(self, mock_hc, qapp):
        from gui.app import MainWindow
        win = MainWindow()
        mock_worker = MagicMock()
        win._streaming_worker = mock_worker
        win._on_cancel_operation()
        mock_worker.cancel.assert_called_once()

    @patch("gui.app.save_transcript_atomic")
    @patch("gui.app.MainWindow._start_health_check")
    def test_on_streaming_complete_preserves_user_corrections(
        self, mock_hc, mock_save, qapp, tmp_path
    ):
        """User corrections made during streaming must survive completion."""
        from gui.app import MainWindow
        win = MainWindow()
        win._cleanup_streaming_thread = MagicMock()
        fake_video = str(tmp_path / "test.mp4")
        with open(fake_video, "wb") as f:
            f.write(b"\x00")
        win._current_video_path = fake_video

        # Simulate streaming: merge some segments
        win._controller.merge_segments([
            {"text": "original text", "start": 0.0, "end": 10.0},
            {"text": "second segment", "start": 10.0, "end": 20.0},
        ])

        # User corrects the first segment
        win._controller._transcript_path = str(tmp_path / "test.transcript.json")
        win._controller.save_correction("corrected text", 0)
        assert win._controller._segments[0]["text"] == "corrected text"
        assert 0 in win._controller._modified_indices

        # Streaming completes — should NOT reload from disk
        worker_transcript = {
            "language": "zh",
            "duration": 20.0,
            "segments": [
                {"text": "original text", "start": 0.0, "end": 10.0},
                {"text": "second segment", "start": 10.0, "end": 20.0},
            ],
        }
        win._on_streaming_complete(worker_transcript)

        # KEY ASSERTION: user correction is preserved
        assert win._controller._segments[0]["text"] == "corrected text"
        assert 0 in win._controller._modified_indices
        # Saved transcript should contain corrected text
        saved = mock_save.call_args[0][1]
        assert saved["segments"][0]["text"] == "corrected text"
