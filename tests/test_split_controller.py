"""Unit tests for SplitController — chapter state management, editing, export."""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _PROJ_ROOT)

from gui.controllers.split_controller import SplitController  # noqa: E402


def _make_chapters(n: int = 3) -> list[dict]:
    """Generate sample chapter dicts."""
    return [
        {
            "title": f"{i+1:02d}_Chapter{i+1}",
            "start_seconds": float(i * 60),
            "end_seconds": float((i + 1) * 60),
        }
        for i in range(n)
    ]


def _make_transcript(n_segments: int = 10, duration: float = 600.0) -> dict:
    """Generate a sample transcript dict."""
    return {
        "duration": duration,
        "language": "zh",
        "segments": [
            {
                "text": f"Segment {i}",
                "start": float(i * (duration / n_segments)),
                "end": float((i + 1) * (duration / n_segments)),
            }
            for i in range(n_segments)
        ],
    }


class TestSplitControllerInit:
    def test_initial_state_empty(self):
        ctrl = SplitController()
        assert ctrl.chapters == []
        assert ctrl.chapter_count == 0

    def test_set_transcript(self):
        ctrl = SplitController()
        transcript = _make_transcript()
        ctrl.set_transcript(transcript)
        assert ctrl._transcript == transcript

    def test_set_video_path(self):
        ctrl = SplitController()
        ctrl.set_video_path("/tmp/test.mp4")
        assert ctrl._video_path == "/tmp/test.mp4"


class TestReceiveChapters:
    def test_receive_validates_and_emits(self):
        ctrl = SplitController()
        ctrl.error = MagicMock()
        ctrl.chapters_detected = MagicMock()
        ctrl.chapters_updated = MagicMock()
        ctrl.set_transcript(_make_transcript())
        ctrl.set_video_path("/tmp/test.mp4")

        raw = _make_chapters(3)
        ctrl.receive_chapters(raw)

        assert ctrl.chapter_count == 3
        ctrl.chapters_detected.emit.assert_called_once()
        ctrl.chapters_updated.emit.assert_called_once()
        ctrl.error.emit.assert_not_called()

    def test_receive_without_transcript_errors(self):
        ctrl = SplitController()
        ctrl.error = MagicMock()
        ctrl.receive_chapters(_make_chapters())
        ctrl.error.emit.assert_called_once()

    def test_receive_empty_chapters(self):
        ctrl = SplitController()
        ctrl.error = MagicMock()
        ctrl.chapters_detected = MagicMock()
        ctrl.set_transcript(_make_transcript())
        ctrl.set_video_path("/tmp/test.mp4")
        ctrl.receive_chapters([])
        assert ctrl.chapter_count == 0


class TestUpdateChapter:
    def test_update_title(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.update_chapter(0, title="New Title")
        assert result is True
        assert ctrl._chapters[0]["title"] == "New Title"
        ctrl.chapters_updated.emit.assert_called_once()

    def test_update_start_time(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.update_chapter(1, start=70.0)
        assert result is True
        assert ctrl._chapters[1]["start_seconds"] == 70.0

    def test_update_end_time(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.update_chapter(0, end=50.0)
        assert result is True
        assert ctrl._chapters[0]["end_seconds"] == 50.0

    def test_invalid_index(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        result = ctrl.update_chapter(-1, title="Bad")
        assert result is False
        ctrl.error.emit.assert_called_once()

    def test_start_ge_end_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        result = ctrl.update_chapter(0, start=60.0, end=50.0)
        assert result is False

    def test_too_short_chapter_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        result = ctrl.update_chapter(0, start=0.0, end=3.0)
        assert result is False
        assert "too short" in ctrl.error.emit.call_args[0][0].lower()

    def test_overlap_with_previous_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        # Chapter 1 starts at 60s; try to set its start before chapter 0's end
        result = ctrl.update_chapter(1, start=30.0)
        assert result is False
        assert "overlap" in ctrl.error.emit.call_args[0][0].lower()

    def test_overlap_with_next_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        # Chapter 0 ends at 60s; try to extend it past chapter 1's start
        result = ctrl.update_chapter(0, end=80.0)
        assert result is False

    def test_empty_title_keeps_original(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(1)
        ctrl.chapters_updated = MagicMock()
        original_title = ctrl._chapters[0]["title"]

        result = ctrl.update_chapter(0, title="   ")
        assert result is True
        assert ctrl._chapters[0]["title"] == original_title


class TestRemoveChapter:
    def test_remove_middle_chapter(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.remove_chapter(1)
        assert result is True
        assert ctrl.chapter_count == 2
        # Chapter 0 should now extend to cover chapter 1's end
        assert ctrl._chapters[0]["end_seconds"] == 120.0

    def test_remove_first_chapter(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.remove_chapter(0)
        assert result is True
        assert ctrl.chapter_count == 2
        # New chapter 0 should start from removed chapter's start
        assert ctrl._chapters[0]["start_seconds"] == 0.0

    def test_remove_last_chapter_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(1)
        ctrl.error = MagicMock()

        result = ctrl.remove_chapter(0)
        assert result is False

    def test_remove_invalid_index(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        result = ctrl.remove_chapter(5)
        assert result is False


class TestMergeChapters:
    def test_merge_adjacent(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        result = ctrl.merge_chapters(0)
        assert result is True
        assert ctrl.chapter_count == 2
        assert ctrl._chapters[0]["start_seconds"] == 0.0
        assert ctrl._chapters[0]["end_seconds"] == 120.0
        assert "+" in ctrl._chapters[0]["title"]

    def test_merge_last_chapter_fails(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(2)
        ctrl.error = MagicMock()

        result = ctrl.merge_chapters(1)
        assert result is False


class TestUpdateBoundary:
    def test_update_boundary_success(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        # Move boundary between chapter 0 and 1 from 60s to 90s
        result = ctrl.update_boundary(0, 90.0)
        assert result is True
        assert ctrl._chapters[0]["end_seconds"] == 90.0
        assert ctrl._chapters[1]["start_seconds"] == 90.0
        ctrl.chapters_updated.emit.assert_called_once()

    def test_update_boundary_left_too_short(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        # Move boundary to 2s — left chapter would be 2s (<5s)
        result = ctrl.update_boundary(0, 2.0)
        assert result is False
        ctrl.error.emit.assert_called_once()

    def test_update_boundary_right_too_short(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        # Move boundary to 178s — right chapter would be 178-180 = 2s (<5s)
        result = ctrl.update_boundary(1, 178.0)
        assert result is False

    def test_update_boundary_invalid_index(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.error = MagicMock()

        result = ctrl.update_boundary(2, 150.0)
        assert result is False

    def test_update_boundary_atomic_no_intermediate_state(self):
        """Both chapters must be updated before signal fires."""
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl.chapters_updated = MagicMock()

        ctrl.update_boundary(0, 90.0)

        # When signal fires, both chapters should already be consistent
        chapters = ctrl.chapters
        assert chapters[0]["end_seconds"] == 90.0
        assert chapters[1]["start_seconds"] == 90.0


class TestRevalidate:
    @patch("gui.controllers.split_controller.ChapterValidator")
    def test_revalidate_calls_validator(self, MockValidator):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl._transcript = _make_transcript()
        ctrl._video_path = "/tmp/test.mp4"
        ctrl.chapters_updated = MagicMock()

        mock_instance = MockValidator.return_value
        from video_splitter.analyzer.chapter import Chapter
        mock_instance.validate.return_value = [
            Chapter("01_A", 0, 60),
            Chapter("02_B", 60, 120),
        ]

        ctrl.revalidate()
        mock_instance.validate.assert_called_once()
        ctrl.chapters_updated.emit.assert_called_once()
        assert ctrl.chapter_count == 2

    def test_revalidate_no_chapters_errors(self):
        ctrl = SplitController()
        ctrl.error = MagicMock()
        ctrl.revalidate()
        ctrl.error.emit.assert_called_once()


class TestExportChapters:
    def test_export_to_json(self, tmp_path):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl._video_path = str(tmp_path / "test.mp4")
        ctrl.chapters_exported = MagicMock()

        output_path = ctrl.export_chapters()
        assert os.path.exists(output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data["chapters"]) == 3
        ctrl.chapters_exported.emit.assert_called_once_with(output_path)

    def test_export_custom_path(self, tmp_path):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(2)
        ctrl._video_path = str(tmp_path / "test.mp4")
        ctrl.chapters_exported = MagicMock()

        custom = str(tmp_path / "custom.json")
        result = ctrl.export_chapters(custom)
        assert result == custom
        assert os.path.exists(custom)

    def test_export_no_video_path_raises(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(1)
        with pytest.raises(ValueError, match="No video path"):
            ctrl.export_chapters()


class TestGetChaptersForCutter:
    def test_converts_to_chapter_objects(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)

        result = ctrl.get_chapters_for_cutter()
        assert len(result) == 3
        assert hasattr(result[0], "title")
        assert hasattr(result[0], "start_seconds")

    def test_clear_resets_state(self):
        ctrl = SplitController()
        ctrl._chapters = _make_chapters(3)
        ctrl._transcript = _make_transcript()
        ctrl._video_path = "/tmp/test.mp4"

        ctrl.clear()
        assert ctrl.chapters == []
        assert ctrl._transcript is None
        assert ctrl._video_path == ""
