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


@pytest.fixture
def mock_extractor():
    """Patch AudioExtractor.extract to return the input path unchanged."""
    with patch("gui.workers.transcribe_worker.AudioExtractor") as mock_cls:
        instance = MagicMock()
        instance.extract.side_effect = lambda path: path
        mock_cls.return_value = instance
        yield instance


class TestTranscribeWorker:
    """Tests for TranscribeWorker signal emissions and error handling."""

    def test_run_emits_finished_with_valid_transcript(self, mock_engine, mock_extractor):
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            worker.run("test_video.mp4")

        worker.finished.emit.assert_called_once()
        worker.error.emit.assert_not_called()
        call_arg = worker.finished.emit.call_args[0][0]
        assert call_arg["language"] == "zh"
        assert call_arg["duration"] == 10.0
        assert len(call_arg["segments"]) == 1

    def test_run_emits_progress_during_transcription(self, mock_engine, mock_extractor):
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
            worker.run("test_video.mp4")

        assert worker.progress.emit.call_count == 3
        worker.finished.emit.assert_called_once()
        worker.error.emit.assert_not_called()

    def test_run_emits_error_on_exception(self, mock_extractor):
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        engine = MagicMock()
        engine.transcribe.side_effect = RuntimeError("Model load failed")

        with patch("gui.workers.transcribe_worker.create_engine", return_value=engine):
            worker.run("test_video.mp4")

        worker.error.emit.assert_called_once()
        worker.finished.emit.assert_not_called()
        assert "Model load failed" in worker.error.emit.call_args[0][0]

    def test_run_extracts_audio_before_transcribe(self, mock_engine, mock_extractor):
        """Worker must call AudioExtractor.extract() with the video path."""
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            worker.run("my_video.mp4")

        mock_extractor.extract.assert_called_once_with("my_video.mp4")

    def test_run_cleans_up_extracted_wav(self, mock_engine, mock_extractor):
        """Worker should delete the temporary WAV after transcription."""
        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        # Override side_effect so extract() returns a distinct path
        mock_extractor.extract.side_effect = None
        mock_extractor.extract.return_value = "/tmp/extracted_audio.wav"

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            with patch("gui.workers.transcribe_worker.os.unlink") as mock_unlink:
                worker.run("test_video.mp4")
                mock_unlink.assert_called_once_with("/tmp/extracted_audio.wav")

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

    def test_worker_custom_engine(self, mock_extractor):
        engine = MagicMock()
        worker = TranscribeWorker(engine_name="whisper")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch("gui.workers.transcribe_worker.create_engine") as mock_create:
            mock_create.return_value = engine
            worker.run("test_video.mp4")
            mock_create.assert_called_once_with("whisper", worker._config)


class TestTranscribeWorkerWithQThread:
    """Integration tests: TranscribeWorker running in an actual QThread."""

    def test_worker_in_qthread_emits_finished(self, mock_engine, mock_extractor):
        """Worker moved to QThread emits finished signal correctly."""
        from PySide6.QtCore import QThread, QCoreApplication

        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication([])

        worker = TranscribeWorker(engine_name="funasr")
        thread = QThread()
        worker.moveToThread(thread)

        result = {"triggered": False}

        def _on_finished(transcript):
            result["triggered"] = True

        worker.finished.connect(_on_finished)
        thread.finished.connect(thread.quit)

        # Patch directly on the module so it's visible from the worker thread
        import gui.workers.transcribe_worker as tw
        original_create_engine = tw.create_engine
        tw.create_engine = lambda *a, **kw: mock_engine

        try:
            thread.started.connect(lambda: worker.run("test_video.mp4"))
            thread.start()
            # Process events until the worker thread finishes
            import time
            deadline = time.monotonic() + 5
            while thread.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)
        finally:
            if thread.isRunning():
                thread.quit()
                thread.wait(1000)
            tw.create_engine = original_create_engine

        assert result["triggered"], "finished signal was not emitted"
