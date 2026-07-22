"""ModelLoaderWorker integration tests — cross-thread signal delivery and lifecycle."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJ_ROOT)

from PySide6.QtCore import QThread, QObject
from PySide6.QtWidgets import QApplication

from gui.workers.model_loader_worker import ModelLoaderWorker


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestModelLoaderLifecycle:
    """Test ModelLoaderWorker lifecycle management."""

    def test_worker_with_parent_none(self, qapp):
        """Worker can be created without parent (legacy behavior)."""
        worker = ModelLoaderWorker(parent=None)
        assert worker.parent() is None

    def test_worker_with_parent(self, qapp):
        """Worker can be created with parent for reliable signal delivery."""
        parent = QObject()
        worker = ModelLoaderWorker(parent=parent)
        assert worker.parent() is parent

    def test_worker_parented_to_mainwindow(self, qapp):
        """Worker parented to MainWindow survives thread operations."""
        from gui.app import MainWindow

        with patch("gui.app.MainWindow._start_health_check"):
            win = MainWindow()

        worker = ModelLoaderWorker(parent=win)
        assert worker.parent() is win

    def test_thread_cleanup_with_timeout(self, qapp):
        """Thread cleanup should wait with timeout for signal delivery."""
        worker = ModelLoaderWorker()
        thread = QThread()
        worker.moveToThread(thread)
        thread.start()

        # Simulate cleanup with timeout
        thread.quit()
        finished = thread.wait(5000)  # 5s timeout

        # Thread should have finished
        assert finished is True

    def test_worker_signals_exist(self, qapp):
        """Worker should have progress and finished signals."""
        worker = ModelLoaderWorker()
        assert hasattr(worker, "progress")
        assert hasattr(worker, "finished")
