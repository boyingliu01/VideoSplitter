"""StreamingTranscribeWorker integration tests — MainWindow signal chain."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
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


class TestStreamingWorkerWithMainWindow:
    """Test StreamingTranscribeWorker integration with MainWindow."""

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_worker_lifecycle_in_mainwindow(self, mock_hc, qapp, mock_video):
        """MainWindow should properly manage StreamingTranscribeWorker lifecycle."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Verify initial state
        assert win._streaming_worker is None
        assert win._streaming_thread is None

        # Start streaming transcription
        win._start_streaming_transcription(mock_video)

        # Verify worker and thread are created
        assert win._streaming_worker is not None
        assert win._streaming_thread is not None

        # Cleanup
        win._cleanup_streaming_thread()
        assert win._streaming_thread is None

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_worker_cleanup_idempotent(self, mock_hc, qapp, mock_video):
        """Cleanup should be safe to call multiple times."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Cleanup when nothing exists should not raise
        win._cleanup_streaming_thread()
        win._cleanup_streaming_thread()  # Second call should also be safe

    @patch("gui.app.MainWindow._start_health_check")
    def test_full_two_phase_flow_with_streaming(self, mock_hc, qapp, mock_video):
        """Test complete two-phase flow: model loader → streaming worker."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video
        win._pending_video_path = mock_video

        # Track the flow
        flow = []

        # Phase 1: Model loader
        with patch.object(win, "_start_model_loader"):
            flow.append("phase1_model_loader")

            # Simulate model loaded
            with patch.object(win, "_start_streaming_transcription") as mock_stream:
                win._on_model_loaded(True, "ok")
                flow.append("phase2_streaming")

                # Verify streaming was started
                mock_stream.assert_called_once_with(mock_video)

        assert flow == ["phase1_model_loader", "phase2_streaming"]

    @patch("gui.app.MainWindow._start_health_check")
    def test_model_loader_failure_prevents_streaming(self, mock_hc, qapp, mock_video):
        """When model loading fails, streaming should not start."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch.object(win, "_start_streaming_transcription") as mock_stream:
            with patch("gui.app.QMessageBox"):
                win._on_model_loaded(False, "Model download failed")

                # Verify streaming was NOT started
                mock_stream.assert_not_called()

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_complete_updates_ui(self, mock_hc, qapp, mock_video):
        """When streaming completes, UI should show segment count."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        # Add some segments
        win._controller.merge_segments([
            {"text": "Segment 1", "start": 0.0, "end": 10.0},
            {"text": "Segment 2", "start": 10.0, "end": 20.0},
            {"text": "Segment 3", "start": 20.0, "end": 30.0},
        ])

        transcript = {
            "language": "zh",
            "duration": 30.0,
            "segments": [
                {"text": "Segment 1", "start": 0.0, "end": 10.0},
                {"text": "Segment 2", "start": 10.0, "end": 20.0},
                {"text": "Segment 3", "start": 20.0, "end": 30.0},
            ],
        }

        with patch("gui.app.save_transcript_atomic"):
            win._on_streaming_complete(transcript)

        # Verify status shows segment count
        assert "3 subtitle segments" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_error_shows_dialog(self, mock_hc, qapp, mock_video):
        """When streaming fails, error dialog should be shown."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch("gui.app.QMessageBox") as MockMsg:
            win._on_streaming_error("Transcription failed")
            MockMsg.warning.assert_called_once()

    @patch("gui.app.MainWindow._start_health_check")
    def test_streaming_cancelled_updates_status(self, mock_hc, qapp, mock_video):
        """When streaming is cancelled, status should reflect cancellation."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        win._on_streaming_cancelled()

        assert "cancelled" in win._status_bar_widget._label.text().lower()

    @patch("gui.app.MainWindow._start_health_check")
    def test_chunk_completed_updates_progress(self, mock_hc, qapp, mock_video):
        """Chunk completion should update progress display."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        win._on_streaming_chunk_completed(3, 10)

        assert "3/10" in win._status_bar_widget._label.text()

    @patch("gui.app.MainWindow._start_health_check")
    def test_segments_ready_merges_into_controller(self, mock_hc, qapp, mock_video):
        """New segments from streaming should be merged into controller."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        new_segs = [
            {"text": "New segment", "start": 0.0, "end": 5.0},
        ]

        with patch.object(win._controller, "merge_segments") as mock_merge:
            win._on_streaming_segments_ready(new_segs)
            mock_merge.assert_called_once_with(new_segs)

    @patch("gui.app.MainWindow._start_health_check")
    def test_audio_ready_sets_duration(self, mock_hc, qapp, mock_video):
        """Audio ready signal should set duration in controller and split panel."""
        from gui.app import MainWindow

        win = MainWindow()
        win._current_video_path = mock_video

        with patch.object(win._split_panel, "set_duration") as mock_set_dur:
            win._on_streaming_audio_ready(120.0)

            assert win._controller._duration == 120.0
            mock_set_dur.assert_called_once_with(120.0)
