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


class TestSubtitlePanelStreamingUI:
    """Tests for SubtitlePanel streaming-transcription UI additions:
    start button, recognized-segments scrolling list, click-to-jump."""

    def test_transcribe_button_emits_start_signal(self, qapp):
        from unittest.mock import MagicMock
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        spy = MagicMock()
        panel.start_transcription_requested.connect(spy)
        panel._transcribe_btn.click()
        spy.assert_called_once_with()

    def test_set_transcribing_toggles_button_state(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_transcribing(True)
        assert not panel._transcribe_btn.isEnabled()
        assert panel._transcribe_btn.text() == "识别中…"
        panel.set_transcribing(False)
        assert panel._transcribe_btn.isEnabled()
        assert panel._transcribe_btn.text() == "开始语音识别"

    def test_segment_list_view_initially_hidden(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        assert panel._segment_list_view.isHidden()

    def test_append_recognized_segments_populates_list(self, qapp):
        from PySide6.QtCore import Qt
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "第一句", "start": 65.0, "end": 70.0},
            {"text": "第二句", "start": 130.5, "end": 135.0},
        ])
        assert not panel._segment_list_view.isHidden()
        assert panel._segment_model.rowCount() == 2
        item0 = panel._segment_model.item(0, 0)
        assert item0 is not None
        assert item0.text() == "[01:05] 第一句"
        assert item0.data(Qt.ItemDataRole.UserRole + 1) == 65.0
        item1 = panel._segment_model.item(1, 0)
        assert item1 is not None
        assert item1.text() == "[02:10] 第二句"
        assert item1.data(Qt.ItemDataRole.UserRole + 1) == 130.5

    def test_append_empty_segments_keeps_list_hidden(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([])
        assert panel._segment_list_view.isHidden()
        assert panel._segment_model.rowCount() == 0

    def test_clear_recognized_segments(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "x", "start": 1.0, "end": 2.0},
        ])
        panel.clear_recognized_segments()
        assert panel._segment_model.rowCount() == 0
        assert panel._segment_list_view.isHidden()

    def test_segment_item_click_emits_segment_activated(self, qapp):
        from unittest.mock import MagicMock
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "第一句", "start": 65.0, "end": 70.0},
        ])
        spy = MagicMock()
        panel.segment_activated.connect(spy)
        # Simulate clicking the first row's QModelIndex
        idx = panel._segment_model.index(0, 0)
        panel._segment_list_view.clicked.emit(idx)
        spy.assert_called_once_with(65.0)

    # -- QListView highlight sync tests (Module 3) --------------------------

    def test_sync_highlight_sets_delegate_row(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "a", "start": 0.0, "end": 5.0},
            {"text": "b", "start": 5.0, "end": 10.0},
            {"text": "c", "start": 10.0, "end": 15.0},
        ])
        assert len(panel._segment_starts) == 3
        panel._pending_position = 6.0
        panel._do_sync_highlight()
        assert panel._segment_delegate._highlight_row == 1  # b is at 5.0–10.0

    def test_sync_highlight_before_first_segment(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "a", "start": 3.0, "end": 6.0},
        ])
        panel._pending_position = 1.0
        panel._do_sync_highlight()
        assert panel._segment_delegate._highlight_row == 0

    def test_sync_highlight_after_last_segment(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "a", "start": 1.0, "end": 4.0},
            {"text": "b", "start": 4.0, "end": 8.0},
        ])
        panel._pending_position = 10.0
        panel._do_sync_highlight()
        assert panel._segment_delegate._highlight_row == 1  # last row

    def test_sync_highlight_no_segments_no_crash(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel._pending_position = 5.0
        panel._do_sync_highlight()  # should not raise

    def test_sync_highlight_public_slot_starts_timer(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "x", "start": 0.0, "end": 5.0},
        ])
        panel.sync_highlight(2.5)
        assert panel._sync_timer.isActive()
        # Let the timer fire
        from PySide6.QtCore import QTimer
        QTimer.singleShot(300, lambda: None)  # dummy — just verify no crash
        # Actually drive the timer
        panel._do_sync_highlight()
        assert not panel._sync_timer.isActive()

    def test_delegate_highlight_row_triggers_viewport_update(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        from unittest.mock import MagicMock
        panel = SubtitlePanel()
        panel._segment_list_view.viewport = MagicMock()
        panel._segment_delegate.set_highlight_row(2)
        panel._segment_list_view.viewport().update.assert_called_once()

    def test_set_segment_updates_list_highlight(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "first", "start": 0.0, "end": 5.0},
            {"text": "second", "start": 5.0, "end": 10.0},
            {"text": "third", "start": 10.0, "end": 15.0},
        ])
        panel.set_segment(index=1, total=3, text="second", start_time=5.0, end_time=10.0)
        assert panel._segment_delegate._highlight_row == 1

    def test_model_row_count_matches_segment_starts(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.append_recognized_segments([
            {"text": "a", "start": 0.0, "end": 2.0},
            {"text": "b", "start": 2.0, "end": 4.0},
            {"text": "c", "start": 4.0, "end": 6.0},
            {"text": "d", "start": 6.0, "end": 8.0},
        ])
        assert panel._segment_model.rowCount() == 4
        assert len(panel._segment_starts) == 4
        assert panel._segment_starts == [0.0, 2.0, 4.0, 6.0]
