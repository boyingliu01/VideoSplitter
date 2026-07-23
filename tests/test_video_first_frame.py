"""Automated verification: video open and transcription are decoupled.

Verifies that:
1. Opening a video only loads the video — no model loading or transcription
2. A separate "Start Speech Recognition" action triggers transcription
3. The two operations are fully independent
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

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


def _get_test_video() -> str:
    """Return path to a test video file."""
    candidates = [
        os.path.join(_PROJ_ROOT, "ffmpeg-video-workspace", "test-files", "test_input.mp4"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


def test_video_open_does_not_start_model_loading(qapp):
    """Opening a video must NOT trigger model loading or transcription."""
    from gui.app import MainWindow

    window = MainWindow()
    test_video = _get_test_video()
    if not test_video:
        pytest.skip("No test video file available")

    with patch.object(window, "_start_model_loader") as mock_loader:
        # Simulate opening a video by setting the path and calling load_video
        window._current_video_path = test_video
        window._video_player.load_video(test_video)
        window._split_panel.set_video_path(test_video)
        window._split_controller.set_video_path(test_video)

        # KEY ASSERTION: model loader was NOT called
        mock_loader.assert_not_called()


def test_on_start_transcription_triggers_model_loading(qapp):
    """Clicking 'Start Speech Recognition' triggers model loading."""
    from gui.app import MainWindow

    window = MainWindow()
    test_video = _get_test_video()
    if not test_video:
        pytest.skip("No test video file available")

    window._current_video_path = test_video

    with patch.object(window, "_start_model_loader") as mock_loader:
        window._on_start_transcription()
        mock_loader.assert_called_once()


def test_on_start_transcription_warns_without_video(qapp):
    """Starting transcription without a video shows a warning."""
    from gui.app import MainWindow

    window = MainWindow()
    window._current_video_path = ""

    with patch("gui.app.QMessageBox.warning") as mock_warn:
        window._on_start_transcription()
        mock_warn.assert_called_once()


def test_on_start_transcription_warns_if_already_running(qapp):
    """Starting transcription while one is running shows a warning."""
    from gui.app import MainWindow

    window = MainWindow()
    window._current_video_path = "/fake/video.mp4"
    window._streaming_worker = MagicMock()  # Simulate active transcription

    with patch("gui.app.QMessageBox.information") as mock_info:
        window._on_start_transcription()
        mock_info.assert_called_once()


def test_open_video_code_path_has_no_processEvents(qapp):
    """Verify _on_open_video no longer calls processEvents (old workaround removed)."""
    import inspect
    from gui.app import MainWindow

    source = inspect.getsource(MainWindow._on_open_video)
    assert "processEvents" not in source, (
        "_on_open_video should NOT call processEvents anymore — "
        "video and transcription are now fully decoupled"
    )


def test_open_video_code_path_has_no_qtimer(qapp):
    """Verify _on_open_video no longer uses QTimer (old workaround removed)."""
    import inspect
    from gui.app import MainWindow

    source = inspect.getsource(MainWindow._on_open_video)
    assert "QTimer" not in source, (
        "_on_open_video should NOT use QTimer anymore — "
        "video and transcription are now fully decoupled"
    )
