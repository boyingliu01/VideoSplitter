"""Unit tests for TranscribeWorker — signal emissions, error handling, engine mocking."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from gui.workers.transcribe_worker import TranscribeWorker  # noqa: E402


@pytest.fixture
def mock_engine():
    """Create a mock engine that returns a valid transcript."""
    engine = MagicMock()
    engine.transcribe.return_value = {
        "language": "zh",
        "duration": 10.0,
        "segments": [{"text": "hello", "start": 0.0, "end": 1.0}],
    }
    engine.health_check.return_value = (True, "ok")
    return engine


class TestTranscribeWorker:
    """Tests for TranscribeWorker signal emissions and error handling."""

    def test_run_emits_finished_with_valid_transcript(self, mock_engine):
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            worker.run("test_audio.wav")

        worker.finished.emit.assert_called_once()
        worker.error.emit.assert_not_called()
        call_arg = worker.finished.emit.call_args[0][0]
        assert call_arg["language"] == "zh"
        assert call_arg["duration"] == 10.0
        assert len(call_arg["segments"]) == 1

    def test_run_emits_progress_during_transcription(self, mock_engine):
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        def _fake_transcribe(audio_path, config, progress_callback=None):
            if progress_callback:
                progress_callback(0.3, "Loading model...")
                progress_callback(0.7, "Processing...")
                progress_callback(1.0, "Done")
            return {"language": "zh", "duration": 10.0, "segments": []}

        mock_engine.transcribe.side_effect = _fake_transcribe

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            worker.run("test_audio.wav")

        assert worker.progress.emit.call_count == 3
        worker.finished.emit.assert_called_once()
        worker.error.emit.assert_not_called()

    def test_run_emits_error_on_exception(self):
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        engine = MagicMock()
        engine.transcribe.side_effect = RuntimeError("Model load failed")

        with patch("gui.workers.transcribe_worker.create_engine", return_value=engine):
            worker.run("test_audio.wav")

        worker.error.emit.assert_called_once()
        worker.finished.emit.assert_not_called()
        assert "Model load failed" in worker.error.emit.call_args[0][0]

    def test_default_engine_is_funasr(self):
        worker = TranscribeWorker()
        assert worker._engine_name == "funasr"

    def test_custom_engine_whisper(self):
        worker = TranscribeWorker(engine_name="whisper")
        assert worker._engine_name == "whisper"

    def test_config_is_stored(self):
        from video_splitter.config import SplitConfig

        config = SplitConfig(transcription_engine="whisper")
        worker = TranscribeWorker(config=config)
        assert worker._config is config

    def test_worker_default_config(self):
        worker = TranscribeWorker()
        assert worker._config is not None
        from video_splitter.config import SplitConfig
        assert isinstance(worker._config, SplitConfig)

    def test_worker_custom_engine(self):
        engine = MagicMock()
        worker = TranscribeWorker(engine_name="whisper")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch("gui.workers.transcribe_worker.create_engine") as mock_create:
            mock_create.return_value = engine
            worker.run("test_audio.wav")
            mock_create.assert_called_once_with("whisper", worker._config)
