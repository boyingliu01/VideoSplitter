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

    def test_set_transcription_status(self, qapp):
        """set_transcription_status shows status text."""
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_transcription_status("正在识别第 3/10 段...")
        assert panel._status_label.text() == "正在识别第 3/10 段..."
        assert not panel._status_label.isHidden()

    def test_clear_transcription_status(self, qapp):
        """clear_transcription_status hides the status label."""
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_transcription_status("识别中...")
        panel.clear_transcription_status()
        assert panel._status_label.isHidden()

    def test_transcription_status_initially_hidden(self, qapp):
        """Status label is hidden by default."""
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        assert panel._status_label.isHidden()


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

    def test_play_changes_button_text(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        player = VideoPlayerWidget()
        player.play()
        assert player._play_pause_btn.text() == "\u23f8"

    def test_pause_changes_button_text(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        player = VideoPlayerWidget()
        player.play()
        player.pause()
        assert player._play_pause_btn.text() == "\u25b6"

    def test_seek_to_calls_set_position(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        from unittest.mock import MagicMock
        player = VideoPlayerWidget()
        player._player.setPosition = MagicMock()
        player.seek_to(5000)
        player._player.setPosition.assert_called_once_with(5000)

    def test_load_video_sets_source(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        from unittest.mock import MagicMock
        player = VideoPlayerWidget()
        player._player.setSource = MagicMock()
        player.load_video("C:/test/video.mp4")
        player._player.setSource.assert_called_once()

    def test_seeked_signal_emitted_on_slider_move(self, qapp):
        """Moving the seek slider emits seeked(int) signal."""
        from gui.widgets.video_player import VideoPlayerWidget
        from unittest.mock import MagicMock
        player = VideoPlayerWidget()
        player.seeked = MagicMock()
        # Simulate slider move
        player._seek_slider.setValue(5000)
        player._seek_slider.sliderMoved.emit(5000)
        player.seeked.emit.assert_called_once_with(5000)

    def test_seeked_signal_has_correct_signature(self, qapp):
        """seeked signal accepts int argument (position in ms)."""
        from gui.widgets.video_player import VideoPlayerWidget
        player = VideoPlayerWidget()
        assert hasattr(player, 'seeked')
        # Verify it's a Signal
        assert hasattr(player.seeked, 'emit')


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
