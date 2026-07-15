"""Tests for pipeline.py — Pipeline.run() orchestration with mocked sub-stages."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import json
from unittest.mock import MagicMock, patch

import pytest

from video_splitter.config import SplitConfig  # noqa: E402
from video_splitter.pipeline import Pipeline  # noqa: E402


@pytest.fixture
def config():
    return SplitConfig(resume=False)


@pytest.fixture
def mock_components():
    """Returns mocks dict for all Pipeline sub-components."""
    return {
        "precheck": (True, "OK"),
        "audio_path": "/tmp/test.wav",
        "transcript": {
            "language": "zh",
            "duration": 300.0,
            "segments": [
                {"text": "你好", "start": 0.0, "end": 150.0},
                {"text": "世界", "start": 150.0, "end": 300.0},
            ],
        },
        "srt": "1\n00:00:00,000 --> 00:02:30,000\n你好\n\n2\n00:02:30,000 --> 00:05:00,000\n世界\n\n",
        "chapters": [],
    }


def _make_chapter(title, start, end):
    """Create a Chapter-like object with title, start_seconds, end_seconds, to_dict()."""
    return type("Ch", (), {
        "title": title,
        "start_seconds": start,
        "end_seconds": end,
        "to_dict": lambda self, t=title, s=start, e=end: {"title": t, "start_seconds": s, "end_seconds": e},
    })()


class TestPipelineRun:
    """Tests for Pipeline.run() with all sub-stages mocked."""

    def test_full_pipeline_success(self, config, mock_components, tmp_path):
        """Happy path: all stages complete successfully."""
        video_path = str(tmp_path / "test.mp4")
        chapters = [_make_chapter("01_简介", 0.0, 150.0), _make_chapter("02_正文", 150.0, 300.0)]
        output_files = [str(tmp_path / "output" / "01.mp4"), str(tmp_path / "output" / "02.mp4")]

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.audio.extract = MagicMock(return_value=mock_components["audio_path"])
        pipeline.chapter_detector.detect = MagicMock(return_value=chapters)
        pipeline.validator.validate = MagicMock(return_value=chapters)
        pipeline.cutter.cut = MagicMock(return_value=output_files)

        with (
            patch("video_splitter.pipeline.transcribe", return_value=mock_components["transcript"]),
            patch("video_splitter.pipeline.estimate_tokens", return_value=50),
            patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]),
        ):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        assert result["steps_completed"] == ["precheck", "transcribe", "chapter", "validate", "cut"]
        assert len(result["output_files"]) == 2
        assert "elapsed_seconds" in result

    def test_pipeline_precheck_failure(self, config, tmp_path):
        """Precheck failure should raise RuntimeError."""
        video_path = str(tmp_path / "test.mp4")

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(False, "No audio detected"))

        with pytest.raises(RuntimeError, match="No audio detected"):
            pipeline.run(video_path)

    def test_pipeline_resume_transcript(self, config, mock_components, tmp_path):
        """Resume mode: existing transcript is loaded, not re-transcribed."""
        config.resume = True
        video_path = str(tmp_path / "test.mp4")
        chapters = [_make_chapter("01_简介", 0.0, 300.0)]
        output_files = [str(tmp_path / "output" / "01.mp4")]

        # Pre-create transcript file for resume
        transcript_path = str(tmp_path / "test.transcript.json")
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(mock_components["transcript"], f)

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.chapter_detector.detect = MagicMock(return_value=chapters)
        pipeline.validator.validate = MagicMock(return_value=chapters)
        pipeline.cutter.cut = MagicMock(return_value=output_files)

        with (
            patch("video_splitter.pipeline.transcribe") as mock_transcribe,
            patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]),
        ):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        # transcribe should NOT be called (resumed from file)
        mock_transcribe.assert_not_called()

    def test_pipeline_resume_chapters(self, config, mock_components, tmp_path):
        """Resume mode: existing chapters JSON is loaded, LLM skipped."""
        config.resume = True
        video_path = str(tmp_path / "test.mp4")
        chapters = [_make_chapter("01_X", 0.0, 300.0)]
        output_files = [str(tmp_path / "output" / "01.mp4")]

        # Pre-create transcript file
        transcript_path = str(tmp_path / "test.transcript.json")
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(mock_components["transcript"], f)

        # Pre-create chapters file (Chapter model: title, start_seconds, end_seconds)
        chapters_path = str(tmp_path / "test.chapters.json")
        chapters_data = [{"title": "01_X", "start_seconds": 0.0, "end_seconds": 300.0}]
        with open(chapters_path, "w", encoding="utf-8") as f:
            json.dump(chapters_data, f)

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.chapter_detector.detect = MagicMock()
        pipeline.validator.validate = MagicMock(return_value=chapters)
        pipeline.cutter.cut = MagicMock(return_value=output_files)

        with patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        # chapter_detector.detect should NOT be called
        pipeline.chapter_detector.detect.assert_not_called()


class TestPipelineDryRun:
    """Tests for Pipeline.dry_run() — cost estimation without full pipeline."""

    def test_dry_run_precheck_failure(self, config, tmp_path):
        """Precheck failure returns error status."""
        video_path = str(tmp_path / "test.mp4")
        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(False, "No audio detected"))

        result = pipeline.dry_run(video_path)
        assert result["status"] == "error"
        assert "No audio detected" in result["message"]

    def test_dry_run_success(self, config, tmp_path):
        """Happy path: estimate tokens and cost."""
        video_path = str(tmp_path / "test.mp4")
        transcript = {
            "language": "zh",
            "duration": 600.0,
            "segments": [{"text": "test", "start": 0.0, "end": 10.0}],
        }

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(True, "OK"))
        pipeline.audio.extract = MagicMock(return_value="/tmp/test.wav")

        with (
            patch("video_splitter.pipeline.transcribe", return_value=transcript),
            patch("video_splitter.pipeline.estimate_tokens", return_value=5000),
        ):
            result = pipeline.dry_run(video_path)

        assert result["status"] == "ok"
        assert result["duration_minutes"] == 10.0
        assert result["estimated_tokens"] == 5000
        assert "llm_calls" in result

    def test_dry_run_chunked_when_over_budget(self, config, tmp_path):
        """When tokens exceed budget, llm_calls shows 'multiple (chunked)'."""
        video_path = str(tmp_path / "test.mp4")
        transcript = {
            "language": "zh",
            "duration": 3600.0,
            "segments": [{"text": "long transcript", "start": 0.0, "end": 3600.0}],
        }

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(True, "OK"))
        pipeline.audio.extract = MagicMock(return_value="/tmp/test.wav")

        # Token count > llm_token_budget (default 60000) triggers chunked
        with (
            patch("video_splitter.pipeline.transcribe", return_value=transcript),
            patch("video_splitter.pipeline.estimate_tokens", return_value=100000),
        ):
            result = pipeline.dry_run(video_path)

        assert result["llm_calls"] == "multiple (chunked)"

    def test_dry_run_single_call_within_budget(self, config, tmp_path):
        """When tokens within budget, llm_calls is 1."""
        video_path = str(tmp_path / "test.mp4")
        transcript = {
            "language": "zh",
            "duration": 300.0,
            "segments": [],
        }

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(True, "OK"))
        pipeline.audio.extract = MagicMock(return_value="/tmp/test.wav")

        with (
            patch("video_splitter.pipeline.transcribe", return_value=transcript),
            patch("video_splitter.pipeline.estimate_tokens", return_value=1000),
        ):
            result = pipeline.dry_run(video_path)

        assert result["llm_calls"] == 1
