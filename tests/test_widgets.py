"""Smoke tests for GUI widgets — verify instantiation without crash, signal wiring."""
from __future__ import annotations

import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestSubtitlePanel:
    """Smoke tests for SubtitlePanel widget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        assert panel is not None

    def test_set_segment_no_crash(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_segment(index=0, total=5, text="测试文本", start_time=0.0, end_time=5.0)
        assert panel._segment_label.text() == "Segment 1/5"
        assert "00:00.000" in panel._timestamp_label.text()

    def test_set_correction_get_correction(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_correction("修正后的文本")
        assert panel.get_correction() == "修正后的文本"

    def test_set_modified_toggles_bold(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_modified(True)
        assert panel._segment_label.font().bold() is True
        panel.set_modified(False)
        assert panel._segment_label.font().bold() is False

    def test_clear_resets_all(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_segment(index=0, total=3, text="text", start_time=1.0, end_time=2.0)
        panel.set_correction("corrected")
        panel.clear()
        assert panel._segment_label.text() == "Segment 0/0"
        assert panel._correction_edit.toPlainText() == ""


class TestVideoPlayerWidget:
    """Smoke tests for VideoPlayerWidget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        player = VideoPlayerWidget()
        assert player is not None

    def test_initial_state(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        from PySide6.QtMultimedia import QMediaPlayer
        player = VideoPlayerWidget()
        assert player._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState


class TestStatusBarWidget:
    """Smoke tests for StatusBarWidget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        assert bar is not None

    def test_set_status(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_status("Processing...")
        assert bar._label.text() == "Processing..."

    def test_set_progress(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_progress(0.5, "Transcribing")
        assert "50%" in bar._label.text()
        assert "Transcribing" in bar._label.text()

    def test_set_progress_no_description(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_progress(0.75)
        assert "75%" in bar._label.text()
