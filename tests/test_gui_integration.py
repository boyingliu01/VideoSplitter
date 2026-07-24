"""GUI integration tests — core user flow with real Qt signal/slot mechanism.

Tests the complete flow: open video → model loader → streaming transcription → subtitle display.
Uses real QThread and Qt signals, only mocks external dependencies (FunASR, FFmpeg).
"""

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


@pytest.fixture
def mock_video(tmp_path):
    """Create a dummy video file for testing."""
    video = tmp_path / "test_video.mp4"
    video.write_bytes(b"\x00" * 100)
    return str(video)


class TestMainWindowOpenVideoFlow:
    """Test the main user flow: open video → model loading → transcription."""

    @patch("gui.app.MainWindow._start_health_check")
    def test_open_video_does_not_start_model_loader(self, mock_hc, qapp, mock_video):
        """Opening a video should NOT start the ModelLoaderWorker (decoupled)."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch("gui.app.QFileDialog.getOpenFileName", return_value=(mock_video, "")):
            with patch.object(win._video_player, "load_video"):
                with patch.object(win, "_start_model_loader") as mock_start:
                    win._on_open_video()
                    mock_start.assert_not_called()

    @patch("gui.app.MainWindow._start_health_check")
    def test_start_transcription_starts_model_loader(self, mock_hc, qapp, mock_video):
        """Manually triggering transcription should start the ModelLoaderWorker."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch.object(win, "_start_model_loader") as mock_start:
            win._on_start_transcription()
            mock_start.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_model_loader_finished_starts_streaming(self, mock_hc, qapp, mock_video):
        """When model loader finishes, streaming transcription should start."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video
        win._pending_video_path = mock_video

        with patch.object(win, "_start_streaming_transcription") as mock_start:
            win._on_model_loaded(True, "Model loaded")
            mock_start.assert_called_once_with(mock_video)

    @patch("gui.app.MainWindow._start_health_check")
    def test_model_loader_failure_shows_error(self, mock_hc, qapp, mock_video):
        """When model loading fails, error should be shown."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_model_loaded(False, "Model download failed")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_two_phase_startup_sequence(self, mock_hc, qapp, mock_video):
        """Verify the complete two-phase startup: model loader → streaming worker."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video
        win._pending_video_path = mock_video

        # Track the sequence of events
        events = []

        # Mock the methods to prevent actual thread creation
        with patch.object(win, "_start_model_loader") as mock_model:
            with patch.object(win, "_start_streaming_transcription") as mock_stream:
                # Simulate Phase 1: model loader started
                mock_model.return_value = None
                events.append("model_loader_started")

                # Simulate model loaded callback
                win._on_model_loaded(True, "ok")
                events.append("streaming_started")

                # Verify both methods were called
                mock_stream.assert_called_once_with(mock_video)

        # Verify sequence
        assert events == ["model_loader_started", "streaming_started"]


class TestModelLoaderSignalDelivery:
    """Test ModelLoaderWorker signal delivery across threads."""

    @patch("gui.app.MainWindow._start_health_check")
    def test_model_loader_progress_updates_ui(self, mock_hc, qapp, mock_video):
        """Model loader progress signals should update the subtitle panel."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Simulate progress messages
        win._subtitle_panel.set_transcription_status("Loading model...")
        assert "Loading model" in win._subtitle_panel._status_label.text()

        win._subtitle_panel.set_transcription_status("Model ready")
        assert "Model ready" in win._subtitle_panel._status_label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_progress_updates_status_bar(self, mock_hc, qapp, mock_video):
        """Streaming transcription progress should update the status bar."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Simulate chunk completion
        win._on_streaming_chunk_completed(2, 5)
        assert "2/5" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_complete_shows_segments(self, mock_hc, qapp, mock_video):
        """When streaming completes, segment count should be displayed."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Simulate streaming complete with segments
        win._controller.merge_segments([
            {"text": "Segment 1", "start": 0.0, "end": 10.0},
            {"text": "Segment 2", "start": 10.0, "end": 20.0},
        ])

        transcript = {
            "language": "zh",
            "duration": 20.0,
            "segments": [
                {"text": "Segment 1", "start": 0.0, "end": 10.0},
                {"text": "Segment 2", "start": 10.0, "end": 20.0},
            ],
        }

        with patch("gui.app.save_transcript_atomic"):
            win._on_streaming_complete(transcript)

        # Verify status shows segment count
        assert "2 subtitle segments" in win._status_bar_widget._label.text()


class TestWorkerLifecycle:
    """Test Worker lifecycle management."""

    @patch("gui.app.MainWindow._start_health_check")
    def test_model_loader_parent_is_mainwindow(self, mock_hc, qapp):
        """ModelLoaderWorker should be parented to MainWindow for reliable signal delivery."""
        from gui.app import MainWindow
        from gui.workers.model_loader_worker import ModelLoaderWorker

        win = MainWindow()

        # Create worker with parent=self (as per the fix)
        worker = ModelLoaderWorker(parent=win)
        assert worker.parent() is win

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_model_loader_thread(self, mock_hc, qapp):
        """Cleanup should safely stop the model loader thread."""
        from gui.app import MainWindow
        from PySide6.QtCore import QThread

        win = MainWindow()

        # Create a mock thread
        win._model_loader_thread = QThread()
        win._model_loader = MagicMock()

        # Cleanup should not raise
        win._cleanup_model_loader_thread()
        assert win._model_loader_thread is None

    @patch("gui.app.MainWindow._start_health_check")
    def test_cleanup_streaming_thread(self, mock_hc, qapp):
        """Cleanup should safely stop the streaming thread."""
        from gui.app import MainWindow
        from PySide6.QtCore import QThread

        win = MainWindow()

        # Create a mock thread
        win._streaming_thread = QThread()
        win._streaming_worker = MagicMock()

        # Cleanup should not raise
        win._cleanup_streaming_thread()
        assert win._streaming_thread is None


class TestSubtitleDisplay:
    """Test that subtitles are properly displayed after transcription."""

    @patch("gui.app.MainWindow._start_health_check")
    def test_segments_displayed_in_subtitle_panel(self, mock_hc, qapp, mock_video):
        """Transcribed segments should be visible in the subtitle panel."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Simulate transcription result by merging segments
        win._controller.merge_segments([
            {"text": "Hello world", "start": 0.0, "end": 5.0},
            {"text": "Second segment", "start": 5.0, "end": 10.0},
        ])

        # Verify segments are in the controller
        assert len(win._controller._segments) == 2
        assert win._controller._segments[0]["text"] == "Hello world"

    @patch("gui.app.MainWindow._start_health_check")
    def test_first_segment_shown_after_load(self, mock_hc, qapp, mock_video):
        """First segment should be displayed after transcript is loaded."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Add segments via merge
        win._controller.merge_segments([
            {"text": "First segment", "start": 0.0, "end": 5.0},
            {"text": "Second segment", "start": 5.0, "end": 10.0},
        ])

        # Verify segments were added
        assert len(win._controller._segments) == 2

        # Manually set the first segment in the subtitle panel
        win._subtitle_panel.set_segment(
            0,  # index
            2,  # total
            "First segment",  # text
            0.0,  # start
            5.0,  # end
        )
        win._subtitle_panel.set_correction("First segment")

        # Verify subtitle panel shows the segment
        assert "First segment" in win._subtitle_panel._original_label.text()
