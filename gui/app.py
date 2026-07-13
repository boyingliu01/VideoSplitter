"""MainWindow + application entry point for GUI subtitle review"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
)

from gui.controllers.review_controller import ReviewController
from gui.widgets.status_bar import StatusBarWidget
from gui.widgets.subtitle_panel import SubtitlePanel
from gui.widgets.video_player import VideoPlayerWidget
from gui.workers.transcribe_worker import TranscribeWorker
from video_splitter.extractor.engines import FunASREngine


class MainWindow(QMainWindow):
    """Main application window with menu, video player, review tab, and status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoSplitter - Subtitle Review")
        self.resize(1280, 720)

        self._controller = ReviewController(self)
        self._worker: TranscribeWorker | None = None
        self._worker_thread: QThread | None = None

        self._build_menu()
        self._build_central()
        self._build_status()
        self._connect_signals()
        self._setup_shortcuts()
        self._run_health_check()

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        open_video_action = QAction("&Open Video...", self)
        open_video_action.triggered.connect(self._on_open_video)
        file_menu.addAction(open_video_action)

        open_transcript_action = QAction("Open &Transcript...", self)
        open_transcript_action.triggered.connect(self._on_open_transcript)
        file_menu.addAction(open_transcript_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence("Alt+F4"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = menu_bar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _build_central(self) -> None:
        self._video_player = VideoPlayerWidget(self)

        self._tab_widget = QTabWidget(self)
        self._subtitle_panel = SubtitlePanel(self)
        self._tab_widget.addTab(self._subtitle_panel, "Review")

        split_tab = QLabel("Split functionality coming in Phase B")
        split_tab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._tab_widget.addTab(split_tab, "Split")
        self._tab_widget.setTabEnabled(1, False)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._video_player)
        splitter.addWidget(self._tab_widget)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        self.setCentralWidget(splitter)

    def _build_status(self) -> None:
        self._status_bar_widget = StatusBarWidget()
        self.statusBar().addWidget(self._status_bar_widget, stretch=1)
        self._status_bar_widget._label = QLabel("Ready", self._status_bar_widget)
        layout = QVBoxLayout(self._status_bar_widget)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(self._status_bar_widget._label)

    def _connect_signals(self) -> None:
        sp = self._subtitle_panel
        ctrl = self._controller
        vp = self._video_player

        vp.position_changed.connect(self._on_position_changed)

        sp.prev_requested.connect(ctrl.prev)
        sp.save_next_requested.connect(self._on_save_next)
        sp.jump_requested.connect(lambda n: ctrl.jump_to(n - 1))
        sp.save_requested.connect(self._on_save_current)
        sp.editing_started.connect(vp.pause)

        ctrl.segment_changed.connect(self._on_segment_changed)
        ctrl.error.connect(self._on_controller_error)

    def _setup_shortcuts(self) -> None:
        self._space_action = QAction(self)
        self._space_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self._space_action.triggered.connect(self._video_player._toggle_play_pause)
        self.addAction(self._space_action)

        save_next_action = QAction(self)
        save_next_action.setShortcut(QKeySequence("Ctrl+Return"))
        save_next_action.triggered.connect(self._on_save_next)
        self.addAction(save_next_action)

        prev_action = QAction(self)
        prev_action.setShortcut(QKeySequence("Ctrl+Left"))
        prev_action.triggered.connect(self._controller.prev)
        self.addAction(prev_action)

        next_action = QAction(self)
        next_action.setShortcut(QKeySequence("Ctrl+Right"))
        next_action.triggered.connect(self._on_next_skip)
        self.addAction(next_action)

        jump_action = QAction(self)
        jump_action.setShortcut(QKeySequence("Ctrl+G"))
        jump_action.triggered.connect(self._subtitle_panel._jump_spin.setFocus)
        self.addAction(jump_action)

        save_action = QAction(self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._on_save_current)
        self.addAction(save_action)

    def _run_health_check(self) -> None:
        try:
            ok, msg = FunASREngine().health_check()
            self._status_bar_widget._label.setText(f"Engine: {'OK' if ok else msg}")
            if not ok:
                QMessageBox.warning(
                    self,
                    "Engine Health Check",
                    f"Transcription engine not ready:\n{msg}\n\n"
                    "You can still work with existing transcripts.",
                )
        except Exception as exc:
            self._status_bar_widget._label.setText(f"Engine: error - {exc}")

    def _on_open_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)",
        )
        if not path:
            return
        self._video_player.load_video(path)

        self._worker = TranscribeWorker("funasr", parent=None)
        self._worker_thread = QThread(self)
        self._worker.moveToThread(self._worker_thread)

        self._worker.progress.connect(self._on_transcribe_progress)
        self._worker.finished.connect(self._on_transcribe_finished)
        self._worker.error.connect(self._on_transcribe_error)
        thread: QThread = self._worker_thread
        thread.started.connect(lambda: self._worker.run(path))  # type: ignore[union-attr]
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_open_transcript(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Transcript",
            "",
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not path:
            return
        try:
            self._controller.load_transcript(path)
        except Exception as exc:
            QMessageBox.warning(self, "Error", f"Failed to load transcript:\n{exc}")

    def _on_save_next(self) -> None:
        seg = self._controller.current_segment()
        if seg:
            text = self._subtitle_panel.get_correction()
            self._controller.save_correction(text, seg["index"])
        result = self._controller.next()
        if result is None:
            self._status_bar_widget._label.setText("Review complete — all segments reviewed")

    def _on_save_current(self) -> None:
        seg = self._controller.current_segment()
        if seg:
            text = self._subtitle_panel.get_correction()
            self._controller.save_correction(text, seg["index"])
            self._status_bar_widget._label.setText("Saved")

    def _on_next_skip(self) -> None:
        result = self._controller.next()
        if result is None:
            self._status_bar_widget._label.setText("Review complete — all segments reviewed")

    def _on_position_changed(self, position_ms: int) -> None:
        secs = position_ms / 1000.0
        t = f"{int(secs // 60):02d}:{int(secs % 60):02d}"
        self._status_bar_widget._label.setText(f"Position: {t}")

    def _on_segment_changed(self, data: dict) -> None:
        self._subtitle_panel.set_segment(
            data["index"],
            data["total"],
            data["text"],
            data["start"],
            data["end"],
        )
        self._subtitle_panel.set_correction(data["text"])
        self._subtitle_panel.set_modified(data.get("modified", False))
        self._video_player.seek_to(int(data["start"] * 1000))

    def _on_controller_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Error", msg)

    def _on_transcribe_progress(self, frac: float, desc: str) -> None:
        self._status_bar_widget._label.setText(f"Transcribing: {desc} ({frac:.0%})")

    def _on_transcribe_finished(self, transcript: dict) -> None:
        self._status_bar_widget._label.setText("Transcription complete")
        self._cleanup_thread()

    def _on_transcribe_error(self, msg: str) -> None:
        QMessageBox.warning(self, "Transcription Error", msg)
        self._status_bar_widget._label.setText("Transcription failed")
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About VideoSplitter",
            "VideoSplitter — Subtitle Review Tool\n\n"
            "Phase A: ASR transcription + manual subtitle correction.",
        )


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
