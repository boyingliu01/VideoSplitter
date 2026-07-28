"""Unit tests for PostprocessWorker — signal emissions, error handling."""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from gui.workers.postprocess_worker import PostprocessWorker  # noqa: E402


@pytest.fixture
def sample_segments():
    return [
        {"text": "今天啊我们呃来讨论一下", "start": 0.0, "end": 3.5, "id": 0},
        {"text": "嗯这个项目的那个实施方案", "start": 4.0, "end": 7.2, "id": 1},
        {"text": "就是说首先呢我们要明确", "start": 8.0, "end": 11.0, "id": 2},
    ]


class TestPostprocessWorker:
    """Tests for PostprocessWorker signal emissions and error handling."""

    def test_run_emits_complete_with_cleaned_segments(self, sample_segments):
        """Worker calls LLM and emits cleaned segments."""
        worker = PostprocessWorker()
        worker.postprocess_complete = MagicMock()
        worker.postprocess_warning = MagicMock()
        worker.error = MagicMock()

        mock_response = (
            "[SEG_0] 今天我们来讨论一下\n"
            "[SEG_1] 这个项目的实施方案\n"
            "[SEG_2] 首先我们要明确"
        )

        with patch.object(worker, "_make_llm_fn") as mock_make_fn:
            mock_llm_fn = MagicMock(return_value=mock_response)
            mock_make_fn.return_value = mock_llm_fn
            worker.run(sample_segments)

        worker.postprocess_complete.emit.assert_called_once()
        worker.error.emit.assert_not_called()
        cleaned = worker.postprocess_complete.emit.call_args[0][0]
        assert len(cleaned) == 3
        assert cleaned[0]["text"] == "今天我们来讨论一下"

    def test_run_emits_warning_on_revert(self, sample_segments):
        """When LLM returns garbage, warning is emitted and originals returned."""
        worker = PostprocessWorker()
        worker.postprocess_complete = MagicMock()
        worker.postprocess_warning = MagicMock()
        worker.error = MagicMock()

        # Garbled response with wrong segment count → full revert
        mock_response = "[SEG_0] just one segment"

        with patch.object(worker, "_make_llm_fn") as mock_make_fn:
            mock_llm_fn = MagicMock(return_value=mock_response)
            mock_make_fn.return_value = mock_llm_fn
            worker.run(sample_segments)

        # Warning should be emitted
        assert worker.postprocess_warning.emit.call_count >= 1
        # Complete should still be emitted with original segments
        worker.postprocess_complete.emit.assert_called_once()
        reverted = worker.postprocess_complete.emit.call_args[0][0]
        assert len(reverted) == 3
        assert reverted[0]["text"] == sample_segments[0]["text"]

    def test_run_empty_segments(self):
        """Empty segments list emits immediately with empty list."""
        worker = PostprocessWorker()
        worker.postprocess_complete = MagicMock()
        worker.postprocess_warning = MagicMock()
        worker.error = MagicMock()

        worker.run([])

        worker.postprocess_complete.emit.assert_called_once()
        worker.error.emit.assert_not_called()
        assert worker.postprocess_complete.emit.call_args[0][0] == []

    def test_run_disabled_by_env(self, sample_segments):
        """When VIDEO_SPLITTER_POSTPROCESS_ENABLED=0, segments pass through unchanged."""
        worker = PostprocessWorker()
        worker.postprocess_complete = MagicMock()
        worker.postprocess_warning = MagicMock()
        worker.error = MagicMock()

        with patch.dict(os.environ, {"VIDEO_SPLITTER_POSTPROCESS_ENABLED": "0"}):
            worker.run(sample_segments)

        worker.postprocess_complete.emit.assert_called_once()
        worker.error.emit.assert_not_called()
        assert worker.postprocess_complete.emit.call_args[0][0] == sample_segments

    def test_run_no_api_key_skips(self, sample_segments):
        """When no API key is configured, ImportError is caught, segments pass through."""
        worker = PostprocessWorker()
        worker.postprocess_complete = MagicMock()
        worker.postprocess_warning = MagicMock()
        worker.error = MagicMock()

        with patch.object(worker, "_make_llm_fn", side_effect=ImportError("no openai")):
            worker.run(sample_segments)

        worker.postprocess_complete.emit.assert_called_once()
        assert worker.postprocess_complete.emit.call_args[0][0] == sample_segments

    def test_default_config(self):
        """Worker creates default SplitConfig if none provided."""
        worker = PostprocessWorker()
        from video_splitter.config import SplitConfig
        assert isinstance(worker._config, SplitConfig)

    def test_custom_config(self):
        """Worker stores custom SplitConfig."""
        from video_splitter.config import SplitConfig
        config = SplitConfig(llm_model="gpt-4")
        worker = PostprocessWorker(config=config)
        assert worker._config is config


class TestPostprocessWorkerWithQThread:
    """Integration tests: PostprocessWorker running in an actual QThread."""

    def test_worker_in_qthread_emits_complete(self, sample_segments):
        """Worker moved to QThread emits complete signal correctly."""
        from PySide6.QtCore import QThread, QCoreApplication

        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication([])

        worker = PostprocessWorker()
        thread = QThread()
        worker.moveToThread(thread)

        result = {"cleaned": None}

        def _on_complete(segments):
            result["cleaned"] = segments

        worker.postprocess_complete.connect(_on_complete)
        thread.finished.connect(thread.quit)

        mock_response = (
            "[SEG_0] 今天我们来讨论一下\n"
            "[SEG_1] 这个项目的实施方案\n"
            "[SEG_2] 首先我们要明确"
        )

        with patch.object(worker, "_make_llm_fn") as mock_make_fn:
            mock_llm_fn = MagicMock(return_value=mock_response)
            mock_make_fn.return_value = mock_llm_fn

            thread.started.connect(lambda: worker.run(sample_segments))
            thread.start()

            import time
            deadline = time.monotonic() + 5
            while thread.isRunning() and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(0.01)

            if thread.isRunning():
                thread.quit()
                thread.wait(1000)

        assert result["cleaned"] is not None
        assert len(result["cleaned"]) == 3
        assert result["cleaned"][0]["text"] == "今天我们来讨论一下"
