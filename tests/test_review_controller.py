"""Unit tests for ReviewController — review state machine, transcript IO, and progress."""
from __future__ import annotations

import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _PROJ_ROOT)

from gui.controllers.review_controller import ReviewController  # noqa: E402


def _make_segments(n: int = 3) -> list[dict]:
    return [
        {"text": f"Segment {i}", "start": float(i * 5), "end": float(i * 5 + 4)}
        for i in range(n)
    ]


class TestLoadTranscript:
    def test_loads_segments_and_emits_progress(self):
        ctrl = ReviewController()
        ctrl.progress_loaded = MagicMock()
        segments = _make_segments(5)
        with (
            patch("gui.controllers.review_controller.load_transcript", return_value={"segments": segments}),
            patch("video_splitter.review.filter_segments", return_value=segments),
            patch("gui.controllers.review_controller.load_progress", return_value=None),
        ):
            result = ctrl.load_transcript("test_transcript.json")
        assert len(result) == 5
        assert ctrl._current_index == 0
        ctrl.progress_loaded.emit.assert_called_once()

    def test_resumes_from_progress(self):
        ctrl = ReviewController()
        ctrl.progress_loaded = MagicMock()
        segments = _make_segments(5)
        with (
            patch("gui.controllers.review_controller.load_transcript", return_value={"segments": segments}),
            patch("video_splitter.review.filter_segments", return_value=segments),
            patch("gui.controllers.review_controller.load_progress", return_value={"current_index": 3, "modified_count": 1}),
        ):
            result = ctrl.load_transcript("test_transcript.json")
        assert len(result) == 5
        assert ctrl._current_index == 3


class TestNavigation:
    def test_next_advances_and_emits(self):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._current_index = 0
        with patch("gui.controllers.review_controller.save_progress"):
            result = ctrl.next()
        assert result is not None
        assert ctrl._current_index == 1
        ctrl.segment_changed.emit.assert_called_once()

    def test_next_at_end_returns_none(self):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._current_index = 2
        result = ctrl.next()
        assert result is None
        assert ctrl._current_index == 2

    def test_prev_moves_backward(self):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._current_index = 1
        with patch("gui.controllers.review_controller.save_progress"):
            result = ctrl.prev()
        assert result is not None
        assert ctrl._current_index == 0

    def test_prev_at_beginning_returns_none(self):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._current_index = 0
        result = ctrl.prev()
        assert result is None
        assert ctrl._current_index == 0

    def test_jump_to_in_range(self):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(5)
        ctrl._current_index = 0
        with patch("gui.controllers.review_controller.save_progress"):
            result = ctrl.jump_to(3)
        assert result is not None
        assert ctrl._current_index == 3
        ctrl.segment_changed.emit.assert_called_once()

    def test_jump_to_out_of_range_returns_none(self):
        ctrl = ReviewController()
        ctrl._segments = _make_segments(3)
        result = ctrl.jump_to(99)
        assert result is None

    def test_current_segment_out_of_range(self):
        ctrl = ReviewController()
        ctrl._segments = []
        result = ctrl.current_segment()
        assert result is None


class TestSaveCorrection:
    def test_saves_valid_correction(self, tmp_path):
        ctrl = ReviewController()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        with (
            patch("gui.controllers.review_controller.sanitize_text", return_value="corrected text"),
            patch("gui.controllers.review_controller.save_transcript_atomic"),
            patch("gui.controllers.review_controller.save_progress"),
        ):
            ctrl.save_correction("corrected text", 0)
        assert ctrl._segments[0]["text"] == "corrected text"
        assert 0 in ctrl._modified_indices

    def test_save_invalid_index_emits_error(self):
        ctrl = ReviewController()
        ctrl.error = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl.save_correction("text", 99)
        ctrl.error.emit.assert_called_once()

    def test_save_empty_after_sanitize_emits_error(self):
        ctrl = ReviewController()
        ctrl.error = MagicMock()
        ctrl._segments = _make_segments(3)
        with patch("gui.controllers.review_controller.sanitize_text", return_value=""):
            ctrl.save_correction("   ", 0)
        ctrl.error.emit.assert_called_once()


class TestEmitSegment:
    def test_includes_modified_flag(self, tmp_path):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(5)
        ctrl._transcript_path = str(tmp_path / "test.json")
        ctrl._current_index = 1
        ctrl._modified_indices = {2}  # current_index becomes 2 after next()
        with patch("gui.controllers.review_controller.save_progress"):
            ctrl.next()
        call_arg = ctrl.segment_changed.emit.call_args[0][0]
        assert call_arg["modified"] is True

    def test_unmodified_segment(self, tmp_path):
        ctrl = ReviewController()
        ctrl.segment_changed = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test.json")
        ctrl._modified_indices = set()
        ctrl._current_index = 0
        with patch("gui.controllers.review_controller.save_progress"):
            ctrl.next()
        call_arg = ctrl.segment_changed.emit.call_args[0][0]
        assert call_arg["modified"] is False


class TestProgressPersistence:
    def test_save_progress_contains_keys(self, tmp_path):
        ctrl = ReviewController()
        ctrl._segments = _make_segments(5)
        ctrl._current_index = 2
        ctrl._modified_indices = {0, 2}
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        with patch("gui.controllers.review_controller.save_progress") as mock_save:
            ctrl._save_progress()
        mock_save.assert_called_once()
        call_data = mock_save.call_args[0][1]
        assert call_data["current_index"] == 2
        assert len(call_data["modified_indices"]) == 2


class TestExportSrt:
    def test_writes_srt_file(self, tmp_path):
        ctrl = ReviewController()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        expected_srt = str(tmp_path / "test_transcript.srt")
        with (
            patch("gui.controllers.review_controller.to_srt") as mock_to_srt,
            patch("gui.controllers.review_controller.export_srt_path", return_value=expected_srt),
            patch("tempfile.mkstemp") as mock_mkstemp,
            patch("gui.controllers.review_controller.os.fdopen") as mock_fdopen,
            patch("gui.controllers.review_controller.os.replace"),
            patch("gui.controllers.review_controller.os.unlink"),
        ):
            mock_mkstemp.return_value = (99, str(tmp_path / "tmp_export.srt"))
            mock_f = MagicMock()
            mock_fdopen.return_value.__enter__.return_value = mock_f
            result = ctrl.export_srt()
        assert result == expected_srt
        mock_to_srt.assert_called_once()
