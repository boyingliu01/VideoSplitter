"""GUI Signal Wiring Integration Tests.

These tests verify that the signal/slot connections in MainWindow are correctly
wired. They catch bugs where components work individually but the "plumbing"
between them is broken (e.g., transcript not passed to subtitle panel after
transcription completes).

These tests do NOT mock internal signals - they verify the actual data flow
from user action to UI state change.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJ_ROOT)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_transcript(n_segments=5, duration=50.0):
    """Create a realistic transcript with multiple segments."""
    return {
        "duration": duration,
        "language": "zh",
        "segments": [
            {
                "text": f"这是第{i+1}段测试文本",
                "start": float(i * 10),
                "end": float((i + 1) * 10),
            }
            for i in range(n_segments)
        ],
    }


class TestTranscriptionToSubtitleFlow:
    """Verify: transcription complete → subtitle panel shows content.

    This is the critical user-facing flow: after waiting for transcription,
    the user must see the transcribed text in the subtitle panel.
    """

    @patch("gui.app.FunASREngine")
    def test_transcription_populates_subtitle_panel(self, MockEngine, qapp, tmp_path):
        """After transcription, subtitle panel must show the first segment."""
        MockEngine.return_value.health_check.return_value = (True, "OK")
        from gui.app import MainWindow

        win = MainWindow()
        win._cleanup_thread = lambda: None

        # Set up a video path (required for saving transcript)
        fake_video = str(tmp_path / "video.mp4")
        with open(fake_video, "wb"):
            pass
        win._current_video_path = fake_video

        transcript = _make_transcript()
        win._on_transcribe_finished(transcript)

        # ASSERTION 1: Subtitle panel shows segment counter
        label_text = win._subtitle_panel._segment_label.text()
        assert "Segment 1/5" in label_text, (
            f"Expected 'Segment 1/5' in label, got '{label_text}'"
        )

        # ASSERTION 2: Subtitle panel shows the first segment text
        original_text = win._subtitle_panel._original_label.text()
        assert original_text == "这是第1段测试文本", (
            f"Expected first segment text, got '{original_text}'"
        )

        # ASSERTION 3: Correction edit shows the same text
        correction = win._subtitle_panel._correction_edit.toPlainText()
        assert correction == "这是第1段测试文本"

        # ASSERTION 4: Timestamp is displayed
        timestamp = win._subtitle_panel._timestamp_label.text()
        assert "00:00" in timestamp or "00:10" in timestamp

    @patch("gui.app.FunASREngine")
    def test_transcription_enables_navigation(self, MockEngine, qapp, tmp_path):
        """After transcription, user must be able to navigate between segments."""
        MockEngine.return_value.health_check.return_value = (True, "OK")
        from gui.app import MainWindow

        win = MainWindow()
        win._cleanup_thread = lambda: None

        fake_video = str(tmp_path / "video.mp4")
        with open(fake_video, "wb"):
            pass
        win._current_video_path = fake_video

        transcript = _make_transcript(n_segments=3)
        win._on_transcribe_finished(transcript)

        # Navigate to next segment
        result = win._controller.next()
        assert result is not None, "next() should return a segment"
        assert result["text"] == "这是第2段测试文本"

        # Navigate back
        result = win._controller.prev()
        assert result is not None
        assert result["text"] == "这是第1段测试文本"

        # Jump to specific segment
        result = win._controller.jump_to(2)
        assert result is not None
        assert result["text"] == "这是第3段测试文本"

    @patch("gui.app.FunASREngine")
    def test_transcription_saves_file_for_review(self, MockEngine, qapp, tmp_path):
        """Transcript must be saved to disk so review can be resumed later."""
        MockEngine.return_value.health_check.return_value = (True, "OK")
        from gui.app import MainWindow

        win = MainWindow()
        win._cleanup_thread = lambda: None

        fake_video = str(tmp_path / "my_video.mp4")
        with open(fake_video, "wb"):
            pass
        win._current_video_path = fake_video

        transcript = _make_transcript()
        win._on_transcribe_finished(transcript)

        # Verify transcript file was created
        transcript_path = str(tmp_path / "my_video.transcript.json")
        assert os.path.exists(transcript_path), (
            f"Transcript file not found at {transcript_path}"
        )

        # Verify it can be loaded back
        import json
        with open(transcript_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert len(loaded["segments"]) == 5
        assert loaded["segments"][0]["text"] == "这是第1段测试文本"

    @patch("gui.app.FunASREngine")
    def test_transcription_also_feeds_split_controller(self, MockEngine, qapp, tmp_path):
        """Split controller must also receive transcript for chapter detection."""
        MockEngine.return_value.health_check.return_value = (True, "OK")
        from gui.app import MainWindow

        win = MainWindow()
        win._cleanup_thread = lambda: None

        fake_video = str(tmp_path / "video.mp4")
        with open(fake_video, "wb"):
            pass
        win._current_video_path = fake_video

        transcript = _make_transcript()
        win._on_transcribe_finished(transcript)

        # Split controller should have the transcript
        assert win._split_controller._transcript is not None
        assert len(win._split_controller._transcript["segments"]) == 5


class TestOpenTranscriptFlow:
    """Verify: open existing transcript → subtitle panel shows content.

    Users should be able to resume work on a previously saved transcript.
    """

    @patch("gui.app.FunASREngine")
    def test_open_transcript_populates_panel(self, MockEngine, qapp, tmp_path):
        """Loading an existing transcript must populate the subtitle panel AND feed split controller."""
        MockEngine.return_value.health_check.return_value = (True, "OK")
        from gui.app import MainWindow
        import json

        win = MainWindow()

        # Create a transcript file
        transcript = _make_transcript(n_segments=4)
        transcript_path = str(tmp_path / "existing.transcript.json")
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False)

        # Mock the file dialog to return our transcript path
        with patch("gui.app.QFileDialog") as MockDialog:
            MockDialog.getOpenFileName.return_value = (transcript_path, "")
            win._on_open_transcript()

        # ASSERTION 1: Controller has the segments
        assert len(win._controller._segments) == 4
        assert win._controller._segments[0]["text"] == "这是第1段测试文本"

        # ASSERTION 2: Subtitle panel actually displays the first segment
        label_text = win._subtitle_panel._segment_label.text()
        assert "Segment 1/4" in label_text, (
            f"Expected 'Segment 1/4' in label, got '{label_text}'"
        )
        assert win._subtitle_panel._original_label.text() == "这是第1段测试文本"

        # ASSERTION 3: Split controller received the transcript for chapter detection
        assert win._split_controller._transcript is not None
        assert len(win._split_controller._transcript["segments"]) == 4
