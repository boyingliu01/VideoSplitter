"""Tests for gui/workers/model_loader_worker.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

from gui.workers.model_loader_worker import ModelLoaderWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestModelLoaderWorker:
    """Tests for ModelLoaderWorker."""

    def test_emits_finished_on_success(self, qapp):
        """Worker emits finished(True, ...) when model loads."""
        worker = ModelLoaderWorker()
        results = {}

        def on_finished(success, message):
            results["success"] = success
            results["message"] = message

        worker.finished.connect(on_finished)

        mock_model = MagicMock()
        with patch(
            "video_splitter.extractor.engines.load_funasr_model",
            return_value=mock_model,
        ):
            worker.run()

        assert results.get("success") is True

    def test_emits_finished_on_failure(self, qapp):
        """Worker emits finished(False, ...) when model loading fails."""
        worker = ModelLoaderWorker()
        results = {}

        def on_finished(success, message):
            results["success"] = success
            results["message"] = message

        worker.finished.connect(on_finished)

        with patch(
            "video_splitter.extractor.engines.load_funasr_model",
            side_effect=RuntimeError("Model download failed"),
        ):
            worker.run()

        assert results.get("success") is False
        assert "Model download failed" in results.get("message", "")

    def test_returns_cached_model_immediately(self, qapp):
        """If model is cached, worker returns without force-loading."""
        from video_splitter.extractor.engines import clear_funasr_model_cache

        clear_funasr_model_cache()
        worker = ModelLoaderWorker()
        progress_messages = []

        def on_progress(msg):
            progress_messages.append(msg)

        worker.progress.connect(on_progress)

        mock_model = MagicMock()

        def mock_load(use_cache=True):
            # Simulate cache hit: always return model
            return mock_model

        with patch(
            "video_splitter.extractor.engines.load_funasr_model",
            side_effect=mock_load,
        ):
            worker.run()

        assert any("cached" in msg.lower() for msg in progress_messages)
