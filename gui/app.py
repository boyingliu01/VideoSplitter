"""MainWindow + application entry point for GUI subtitle review and video splitting."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl, QObject, Signal, Slot
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
)

from gui.controllers.review_controller import ReviewController
from gui.controllers.split_controller import SplitController
from gui.widgets.status_bar import StatusBarWidget
from gui.widgets.subtitle_panel import SubtitlePanel
from gui.widgets.split_panel import SplitPanel
from gui.widgets.video_player import VideoPlayerWidget
from gui.workers.burn_worker import BurnWorker
from gui.workers.detect_worker import DetectChaptersWorker
from gui.workers.split_worker import SplitWorker
from gui.workers.transcribe_worker import TranscribeWorker
from gui.workers.streaming_transcribe_worker import StreamingTranscribeWorker
from gui.workers.model_loader_worker import ModelLoaderWorker
from video_splitter.review import save_transcript_atomic

logger = logging.getLogger(__name__)


class _HealthCheckWorker(QObject):
    """Run FunASR health check in a background thread.

    Uses load_funasr_model(use_cache=True) so the loaded model is cached
    for later use by ModelLoaderWorker / StreamingTranscribeWorker.
    This avoids loading the model twice at startup.
    """

    finished = Signal(bool, str)

    @Slot()
    def run(self) -> None:
        try:
            from video_splitter.extractor.engines import load_funasr_model
            model = load_funasr_model(use_cache=True)
            # Quick sanity check with dummy audio
            import numpy as np
            dummy_wav = np.zeros(16000, dtype=np.float32)
            model.generate(input=dummy_wav)
            self.finished.emit(True, "ok")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class MainWindow(QMainWindow):
    """Main application window with menu, video player, review tab, and status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoSplitter - Subtitle Review & Split")
        self.resize(1280, 720)

        self._current_video_path: str = ""

        self._controller = ReviewController(self)
        self._split_controller = SplitController(parent=self)

        # TranscribeWorker lifecycle (legacy batch worker)
        self._worker: TranscribeWorker | None = None
        self._worker_thread: QThread | None = None

        # StreamingTranscribeWorker lifecycle (streaming ASR)
        self._streaming_worker: StreamingTranscribeWorker | None = None
        self._streaming_thread: QThread | None = None

        # ModelLoaderWorker lifecycle (pre-load ASR model)
        self._model_loader: ModelLoaderWorker | None = None
        self._model_loader_thread: QThread | None = None
        self._pending_video_path: str = ""  # Video path waiting for model

        # DetectChaptersWorker lifecycle
        self._detect_worker: DetectChaptersWorker | None = None
        self._detect_thread: QThread | None = None

        # SplitWorker lifecycle
        self._split_worker: SplitWorker | None = None
        self._split_thread: QThread | None = None

        # BurnWorker lifecycle
        self._burn_worker: BurnWorker | None = None
        self._burn_thread: QThread | None = None

        # Health check worker
        self._hc_worker: _HealthCheckWorker | None = None
        self._hc_thread: QThread | None = None

        # Track split output for subtitle burning
        self._split_output_files: list[str] = []

        # Hotword string for ASR enhancement (loaded from document)
        self._hotword: str = ""
        self._hotword_file_path: str = ""

        self._build_menu()
        self._build_central()
        self._build_status()
        self._connect_signals()
        self._setup_shortcuts()
        self._start_health_check()

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

        export_chapters_action = QAction("Export &Chapters...", self)
        export_chapters_action.triggered.connect(self._on_export_chapters)
        file_menu.addAction(export_chapters_action)

        file_menu.addSeparator()

        open_hotword_action = QAction("Open Hot&word Document...", self)
        open_hotword_action.triggered.connect(self._on_open_hotword)
        file_menu.addAction(open_hotword_action)

        file_menu.addSeparator()

        transcribe_action = QAction("Start &Speech Recognition", self)
        transcribe_action.triggered.connect(self._on_start_transcription)
        file_menu.addAction(transcribe_action)

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

        self._split_panel = SplitPanel(parent=self)
        self._tab_widget.addTab(self._split_panel, "Split")

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._video_player)
        splitter.addWidget(self._tab_widget)
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        self.setCentralWidget(splitter)

    def _build_status(self) -> None:
        self._status_bar_widget = StatusBarWidget()
        self.statusBar().addWidget(self._status_bar_widget, stretch=1)

    def _connect_signals(self) -> None:
        sp = self._subtitle_panel
        ctrl = self._controller
        vp = self._video_player

        vp.position_changed.connect(self._on_position_changed)

        # Seek → streaming worker priority request
        vp.seeked.connect(self._on_video_seeked)

        sp.prev_requested.connect(ctrl.prev)
        sp.save_next_requested.connect(self._on_save_next)
        sp.jump_requested.connect(lambda n: ctrl.jump_to(n - 1))
        sp.save_requested.connect(self._on_save_current)
        sp.editing_started.connect(vp.pause)

        ctrl.segment_changed.connect(self._on_segment_changed)
        ctrl.error.connect(self._on_controller_error)

        # Video player duration → ReviewController
        vp.duration_changed.connect(
            lambda ms: self._controller.set_duration(ms / 1000.0)
        )

        # Split panel signals
        sp = self._split_panel
        sp.detect_requested.connect(self._on_detect_chapters)
        sp.validate_requested.connect(self._split_controller.revalidate)
        sp.split_requested.connect(self._on_start_split)
        sp.burn_requested.connect(self._on_burn_subtitles)
        sp.cancel_requested.connect(self._on_cancel_operation)
        sp.chapter_title_edited.connect(
            lambda idx, title, s, e: self._split_controller.update_chapter(
                idx, title=title
            )
        )
        sp.chapter_remove_requested.connect(self._split_controller.remove_chapter)
        sp.chapter_merge_requested.connect(self._split_controller.merge_chapters)
        sp.boundary_moved.connect(self._on_boundary_moved)
        sp.position_clicked.connect(
            lambda t: self._video_player.seek_to(int(t * 1000))
        )

        # Split controller signals
        sc = self._split_controller
        sc.chapters_updated.connect(self._split_panel.set_chapters)
        sc.chapters_exported.connect(
            lambda p: self._status_bar_widget.set_status(f"Chapters exported: {p}")
        )
        sc.error.connect(self._on_split_error)

    def _setup_shortcuts(self) -> None:
        # Use QShortcut with ApplicationShortcut context so space works
        # even when focus is in QTextEdit (subtitle correction editor)
        space_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Space), self)
        space_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        space_shortcut.activated.connect(self._video_player._toggle_play_pause)

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

    def _start_health_check(self) -> None:
        """Run FunASR health check in background thread (non-blocking)."""
        self._status_bar_widget.set_status("Checking engine...")
        self._hc_worker = _HealthCheckWorker()
        self._hc_thread = QThread(self)
        self._hc_worker.moveToThread(self._hc_thread)
        self._hc_worker.finished.connect(self._on_health_check_done)
        self._hc_thread.started.connect(self._hc_worker.run)
        self._hc_thread.finished.connect(self._hc_thread.deleteLater)
        self._hc_thread.start()

    def _on_health_check_done(self, ok: bool, msg: str) -> None:
        """Handle health check result from background thread."""
        self._status_bar_widget.set_status(f"Engine: {'OK' if ok else msg}")
        if not ok:
            QMessageBox.warning(
                self,
                "Engine Health Check",
                f"Transcription engine not ready:\n{msg}\n\n"
                "You can still work with existing transcripts.",
            )
        # Cleanup worker
        if self._hc_thread is not None:
            self._hc_thread.quit()
            self._hc_thread = None
            self._hc_worker = None

    def _on_open_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            "",
            "Video Files (*.mp4 *.avi *.mkv *.mov);;All Files (*.*)",
        )
        if not path:
            return
        self._current_video_path = path

        self._video_player.load_video(path)

        self._split_panel.set_video_path(path)
        self._split_controller.set_video_path(path)

        self._status_bar_widget.set_status(f"Video loaded: {os.path.basename(path)}")
        self._subtitle_panel.set_transcription_status(
            "Click File → Start Speech Recognition to begin transcription."
        )

    def _on_start_transcription(self) -> None:
        """Start streaming speech recognition for the current video."""
        if not self._current_video_path:
            QMessageBox.warning(
                self, "No Video",
                "Please open a video file first.",
            )
            return

        if self._streaming_worker is not None:
            QMessageBox.information(
                self, "Already Running",
                "Speech recognition is already in progress.",
            )
            return

        self._status_bar_widget.show_progress("Loading speech recognition model...")
        self._subtitle_panel.set_transcription_status("Initializing speech recognition...")

        self._pending_video_path = self._current_video_path
        self._start_model_loader()

    def _start_model_loader(self) -> None:
        """Start ModelLoaderWorker to pre-load FunASR model."""
        # Clean up any previous model loader
        self._cleanup_model_loader_thread()

        # Parent = self (MainWindow) so worker survives thread deletion
        # and its finished signal is reliably delivered to the main thread.
        self._model_loader = ModelLoaderWorker(parent=self)
        self._model_loader_thread = QThread(self)
        self._model_loader.moveToThread(self._model_loader_thread)

        self._model_loader.progress.connect(
            lambda msg: self._subtitle_panel.set_transcription_status(msg)
        )
        self._model_loader.finished.connect(self._on_model_loaded)

        thread: QThread = self._model_loader_thread
        thread.started.connect(self._model_loader.run)  # type: ignore[union-attr]
        # Do NOT deleteLater on thread.finished — worker (parent=self) manages
        # its own lifetime. We clean up the thread reference in _on_model_loaded.
        thread.start()

    def _on_model_loaded(self, success: bool, message: str) -> None:
        """Model loaded — now start streaming transcription."""
        self._cleanup_model_loader_thread()

        if not success:
            self._on_streaming_error(message)
            return

        # Phase 2: Start streaming transcription (model is now cached)
        self._status_bar_widget.set_progress(0.0, "Starting streaming transcription...")
        self._start_streaming_transcription(self._pending_video_path)

    def _start_streaming_transcription(self, path: str) -> None:
        """Start the StreamingTranscribeWorker (model already cached)."""
        # Also try loading hotwords from environment if not already set via GUI
        if not self._hotword:
            from video_splitter.extractor.hotwords import load_hotwords_from_env
            self._hotword = load_hotwords_from_env()

        self._streaming_worker = StreamingTranscribeWorker(
            "funasr", parent=None, hotword=self._hotword
        )
        self._streaming_thread = QThread(self)
        self._streaming_worker.moveToThread(self._streaming_thread)

        self._streaming_worker.audio_ready.connect(self._on_streaming_audio_ready)
        self._streaming_worker.segments_ready.connect(self._on_streaming_segments_ready)
        self._streaming_worker.chunk_completed.connect(self._on_streaming_chunk_completed)
        self._streaming_worker.transcription_complete.connect(self._on_streaming_complete)
        self._streaming_worker.transcription_progress.connect(self._on_streaming_progress)
        self._streaming_worker.model_loading_progress.connect(
            lambda msg: self._subtitle_panel.set_transcription_status(msg)
        )
        self._streaming_worker.error.connect(self._on_streaming_error)
        self._streaming_worker.cancelled.connect(self._on_streaming_cancelled)

        thread: QThread = self._streaming_thread
        thread.started.connect(lambda: self._streaming_worker.run(path))  # type: ignore[union-attr]
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
            return

        # Show the first segment in the subtitle panel
        seg = self._controller.current_segment()
        if seg:
            self._on_segment_changed({
                "index": seg["index"],
                "total": len(self._controller._segments),
                "text": seg["text"],
                "start": seg["start"],
                "end": seg["end"],
                "modified": False,
            })

        # Pass transcript to split controller for chapter detection
        self._split_controller.set_transcript(self._controller.get_transcript())
        self._status_bar_widget.set_status(f"Loaded transcript: {path}")

    def _on_open_hotword(self) -> None:
        """Open a hotword document to improve ASR accuracy."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Hotword Document",
            "",
            "Text Files (*.txt);;Word Documents (*.docx);;PDF Files (*.pdf);;All Files (*.*)",
        )
        if not path:
            return

        from video_splitter.extractor.hotwords import load_hotwords_from_file

        try:
            hotwords = load_hotwords_from_file(path)
            if not hotwords:
                QMessageBox.warning(
                    self, "Warning",
                    "No hotwords extracted from the document.\n"
                    "Check the file format and content."
                )
                return

            self._hotword = hotwords
            self._hotword_file_path = path
            word_count = len(hotwords.split())
            self._status_bar_widget.set_status(
                f"Loaded {word_count} hotwords from: {os.path.basename(path)}"
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Error",
                f"Failed to load hotword document:\n{exc}"
            )

    def _on_save_next(self) -> None:
        seg = self._controller.current_segment()
        if seg:
            text = self._subtitle_panel.get_correction()
            self._controller.save_correction(text, seg["index"])
        result = self._controller.next()
        if result is None:
            self._status_bar_widget.set_status("Review complete — all segments reviewed")

    def _on_save_current(self) -> None:
        seg = self._controller.current_segment()
        if seg:
            text = self._subtitle_panel.get_correction()
            self._controller.save_correction(text, seg["index"])
            self._status_bar_widget.set_status("Saved")

    def _on_next_skip(self) -> None:
        result = self._controller.next()
        if result is None:
            self._status_bar_widget.set_status("Review complete — all segments reviewed")

    def _on_position_changed(self, position_ms: int) -> None:
        secs = position_ms / 1000.0
        t = f"{int(secs // 60):02d}:{int(secs % 60):02d}"
        self._status_bar_widget.set_status(f"Position: {t}")
        # Sync timeline position indicator
        self._split_panel.set_current_position(secs)

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
        self._status_bar_widget.set_progress(frac, desc)

    def _on_transcribe_finished(self, transcript: dict) -> None:
        n_segs = len(transcript.get("segments", []))
        logger.info("Transcription complete: %d segments", n_segs)
        self._status_bar_widget.hide_progress()
        self._status_bar_widget.set_status(f"Ready - {n_segs} subtitle segments loaded")
        self._cleanup_thread()

        # Save transcript to disk next to the video file
        transcript_path = str(
            Path(self._current_video_path).with_suffix(".transcript.json")
        )
        try:
            save_transcript_atomic(transcript_path, transcript)
        except Exception as exc:
            logger.error("Failed to save transcript: %s", exc)
            QMessageBox.warning(
                self, "Error", f"Failed to save transcript:\n{exc}"
            )
            return

        # Load transcript into ReviewController so subtitle panel is populated
        try:
            self._controller.load_transcript(transcript_path)
        except Exception as exc:
            logger.error("Failed to load transcript for review: %s", exc)
            QMessageBox.warning(
                self, "Error", f"Failed to load transcript for review:\n{exc}"
            )
            return

        # Show the first segment in the subtitle panel
        seg = self._controller.current_segment()
        if seg:
            self._on_segment_changed({
                "index": seg["index"],
                "total": len(self._controller._segments),
                "text": seg["text"],
                "start": seg["start"],
                "end": seg["end"],
                "modified": False,
            })
        else:
            logger.warning("No segments to display after transcription")

        # Pass transcript to split controller for chapter detection
        self._split_controller.set_transcript(transcript)
        self._split_panel.set_duration(transcript.get("duration", 0.0))

    def _on_transcribe_error(self, msg: str) -> None:
        logger.error("Transcription error: %s", msg)
        self._status_bar_widget.hide_progress()
        QMessageBox.warning(self, "Transcription Error", msg)
        self._status_bar_widget.set_status("Transcription failed - see error for details")
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        if self._worker_thread is not None:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None

    def _cleanup_streaming_thread(self) -> None:
        if self._streaming_thread is not None:
            self._streaming_thread.quit()
            self._streaming_thread.wait()
            self._streaming_thread = None
            self._streaming_worker = None

    def _cleanup_model_loader_thread(self) -> None:
        """Safely stop and clean up the model loader thread."""
        if self._model_loader_thread is not None:
            self._model_loader_thread.quit()
            self._model_loader_thread.wait(5000)  # 5s timeout for signal delivery
            self._model_loader_thread = None
        # Worker is parented to self, no need to delete

    def _on_video_seeked(self, position_ms: int) -> None:
        """Forward video seek position to streaming worker for priority transcription."""
        if self._streaming_worker is not None:
            self._streaming_worker.request_priority(position_ms / 1000.0)

    def _on_streaming_audio_ready(self, total_duration: float) -> None:
        """Audio extraction complete — update UI."""
        self._controller.set_duration(total_duration)
        self._split_panel.set_duration(total_duration)
        self._status_bar_widget.set_progress(
            0.05, f"Audio ready ({total_duration:.0f}s), loading model..."
        )

    def _on_streaming_segments_ready(self, segments: list) -> None:
        """New segments from a completed chunk — merge into ReviewController."""
        self._controller.merge_segments(segments)
        n_total = len(self._controller._segments)

        # Always show the first segment for review (once)
        if n_total > 0 and self._controller._current_index == 0:
            seg = self._controller.current_segment()
            if seg:
                self._on_segment_changed({
                    "index": seg["index"],
                    "total": n_total,
                    "text": seg["text"],
                    "start": seg["start"],
                    "end": seg["end"],
                    "modified": False,
                })

        # Always update the status with the latest recognized text
        # so the user can see progress during streaming
        if segments:
            latest_text = segments[-1].get("text", "")
            start = segments[-1].get("start", 0)
            m, s = divmod(int(start), 60)
            self._subtitle_panel.set_transcription_status(
                f"[{m:02d}:{s:02d}] {latest_text}"
            )

    def _on_streaming_chunk_completed(self, completed: int, total: int) -> None:
        """A chunk finished — update progress."""
        frac = 0.1 + 0.85 * (completed / total)
        self._status_bar_widget.set_progress(
            frac, f"Recognizing segment {completed}/{total}..."
        )

    def _on_streaming_complete(self, transcript: dict) -> None:
        """All chunks transcribed — finalize.

        Uses the in-memory segments from ReviewController (which already
        received all chunks via merge_segments and preserves any user
        corrections made during streaming) instead of reloading from disk.
        """
        n_segs = len(self._controller._segments)
        logger.info("Streaming transcription complete: %d segments", n_segs)
        self._status_bar_widget.hide_progress()
        self._status_bar_widget.set_status(
            f"Ready - {n_segs} subtitle segments loaded"
        )
        self._subtitle_panel.clear_transcription_status()
        self._cleanup_streaming_thread()

        # Save the in-memory transcript to disk (preserves user corrections
        # made during streaming, unlike reloading from worker's raw output)
        transcript_path = str(
            Path(self._current_video_path).with_suffix(".transcript.json")
        )
        memory_transcript = self._controller.get_transcript()
        try:
            save_transcript_atomic(transcript_path, memory_transcript)
        except Exception as exc:
            logger.error("Failed to save transcript: %s", exc)
            QMessageBox.warning(
                self, "Error", f"Failed to save transcript:\n{exc}"
            )
            return

        # Ensure transcript_path is set so future save_correction calls work
        self._controller._transcript_path = transcript_path

        # Show the first segment (or current if user was already reviewing)
        seg = self._controller.current_segment()
        if seg:
            self._on_segment_changed({
                "index": seg["index"],
                "total": n_segs,
                "text": seg["text"],
                "start": seg["start"],
                "end": seg["end"],
                "modified": seg["index"] in self._controller._modified_indices,
            })

        # Pass transcript to split controller for chapter detection
        self._split_controller.set_transcript(memory_transcript)

    def _on_streaming_progress(self, frac: float, desc: str) -> None:
        """Progress update from streaming worker."""
        if frac >= 0:
            self._status_bar_widget.set_progress(frac, desc)
        else:
            # Negative frac = indeterminate
            self._status_bar_widget.set_status(desc)

    def _on_streaming_error(self, msg: str) -> None:
        """Streaming transcription error."""
        logger.error("Streaming transcription error: %s", msg)
        self._status_bar_widget.hide_progress()
        self._subtitle_panel.clear_transcription_status()
        QMessageBox.warning(self, "Transcription Error", msg)
        self._status_bar_widget.set_status("Transcription failed - see error for details")
        self._cleanup_streaming_thread()

    def _on_streaming_cancelled(self) -> None:
        """Streaming transcription was cancelled."""
        logger.info("Streaming transcription cancelled")
        self._status_bar_widget.hide_progress()
        self._subtitle_panel.clear_transcription_status()
        self._status_bar_widget.set_status("Transcription cancelled")
        self._cleanup_streaming_thread()

    # -- Split workflow handlers -----------------------------------------------

    def _on_detect_chapters(self) -> None:
        """Start LLM chapter detection in a background thread."""
        transcript = self._controller.get_transcript()
        if not transcript.get("segments"):
            QMessageBox.warning(
                self, "No Transcript",
                "Please load or transcribe a video first.",
            )
            return

        self._split_controller.set_transcript(transcript)
        self._split_panel.set_detecting(True)

        self._detect_worker = DetectChaptersWorker(parent=None)
        self._detect_thread = QThread(self)
        self._detect_worker.moveToThread(self._detect_thread)

        self._detect_worker.chapters_detected.connect(
            self._on_chapters_detected
        )
        self._detect_worker.progress.connect(self._on_detect_progress)
        self._detect_worker.error.connect(self._on_detect_error)

        thread = self._detect_thread
        thread.started.connect(
            lambda: self._detect_worker.run(transcript)  # type: ignore[union-attr]
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_chapters_detected(self, chapters: list) -> None:
        """Receive detected chapters from worker and pass to controller."""
        self._split_panel.set_detecting(False)
        self._split_controller.receive_chapters(chapters)
        self._status_bar_widget.set_status(
            f"Detected {len(chapters)} chapters"
        )
        self._cleanup_detect_thread()

    def _on_detect_progress(self, frac: float, desc: str) -> None:
        self._status_bar_widget.set_status(f"Detecting: {desc} ({frac:.0%})")

    def _on_detect_error(self, msg: str) -> None:
        self._split_panel.set_detecting(False)
        self._status_bar_widget.set_status(f"Detection failed: {msg}")
        QMessageBox.warning(self, "Chapter Detection Error", msg)
        self._cleanup_detect_thread()

    def _cleanup_detect_thread(self) -> None:
        if self._detect_thread is not None:
            self._detect_thread.quit()
            self._detect_thread.wait()
            self._detect_thread = None
            self._detect_worker = None

    def _on_start_split(self, output_dir: str) -> None:
        """Start FFmpeg video cutting in a background thread."""
        if not self._current_video_path:
            QMessageBox.warning(
                self, "No Video",
                "Please open a video file first.",
            )
            return

        chapters = self._split_controller.chapters
        if not chapters:
            QMessageBox.warning(
                self, "No Chapters",
                "Please detect or create chapters first.",
            )
            return

        self._split_panel.set_splitting(True)

        self._split_worker = SplitWorker(parent=None)
        self._split_thread = QThread(self)
        self._split_worker.moveToThread(self._split_thread)

        self._split_worker.progress.connect(self._on_split_progress)
        self._split_worker.finished.connect(self._on_split_finished)
        self._split_worker.error.connect(self._on_split_error)

        thread = self._split_thread
        thread.started.connect(
            lambda: self._split_worker.run(  # type: ignore[union-attr]
                self._current_video_path, chapters, output_dir
            )
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_split_progress(self, frac: float, desc: str) -> None:
        self._status_bar_widget.set_status(f"Splitting: {desc} ({frac:.0%})")

    def _on_split_finished(self, output_files: list) -> None:
        self._split_output_files = output_files
        self._split_panel.set_split_complete(output_files)
        self._status_bar_widget.set_status(
            f"Split complete: {len(output_files)} segments"
        )
        self._cleanup_split_thread()

        if output_files:
            output_dir = str(Path(output_files[0]).parent)
            result = QMessageBox.information(
                self, "Split Complete",
                f"Successfully created {len(output_files)} segments.\n\n"
                f"Output: {output_dir}\n\n"
                "Open output folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))

    def _on_split_error(self, msg: str) -> None:
        """Handle errors from detect or split workers."""
        # Only reset the UI state for the operation that actually failed
        if self._split_worker is not None:
            self._split_panel.set_splitting(False)
            self._cleanup_split_thread()
        if self._detect_worker is not None:
            self._split_panel.set_detecting(False)
            self._cleanup_detect_thread()
        self._status_bar_widget.set_status(f"Error: {msg}")
        QMessageBox.warning(self, "Error", msg)

    # -- Subtitle burn workflow handlers ---------------------------------------

    def _on_burn_subtitles(self) -> None:
        """Start subtitle burning in a background thread."""
        if not self._split_output_files:
            QMessageBox.warning(
                self, "No Segments",
                "Please split the video first.",
            )
            return

        transcript = self._controller.get_transcript()
        if not transcript.get("segments"):
            QMessageBox.warning(
                self, "No Transcript",
                "Please load or transcribe a video first.",
            )
            return

        self._split_panel.set_burning(True)

        self._burn_worker = BurnWorker(parent=None)
        self._burn_thread = QThread(self)
        self._burn_worker.moveToThread(self._burn_thread)

        self._burn_worker.progress.connect(self._on_burn_progress)
        self._burn_worker.finished.connect(self._on_burn_finished)
        self._burn_worker.error.connect(self._on_burn_error)

        thread = self._burn_thread
        thread.started.connect(
            lambda: self._burn_worker.run(  # type: ignore[union-attr]
                self._split_output_files,
                self._split_controller.chapters,
                transcript["segments"],
            )
        )
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_burn_progress(self, frac: float, desc: str) -> None:
        self._status_bar_widget.set_status(f"Burning: {desc} ({frac:.0%})")

    def _on_burn_finished(self, output_files: list) -> None:
        self._split_panel.set_burning(False)
        self._status_bar_widget.set_status(
            f"Subtitle burn complete: {len(output_files)} segments"
        )
        self._cleanup_burn_thread()

        if output_files:
            output_dir = str(Path(output_files[0]).parent)
            result = QMessageBox.information(
                self, "Burn Complete",
                f"Successfully burned subtitles into {len(output_files)} segments.\n\n"
                f"Output: {output_dir}\n\n"
                "Open output folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if result == QMessageBox.StandardButton.Yes:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))

    def _on_burn_error(self, msg: str) -> None:
        self._split_panel.set_burning(False)
        self._status_bar_widget.set_status(f"Burn error: {msg}")
        QMessageBox.warning(self, "Burn Error", msg)
        self._cleanup_burn_thread()

    def _cleanup_burn_thread(self) -> None:
        if self._burn_thread is not None:
            self._burn_thread.quit()
            self._burn_thread.wait()
            self._burn_thread = None
            self._burn_worker = None

    def _cleanup_split_thread(self) -> None:
        if self._split_thread is not None:
            self._split_thread.quit()
            self._split_thread.wait()
            self._split_thread = None
            self._split_worker = None

    def _on_cancel_operation(self) -> None:
        """Cancel the current background operation."""
        if self._streaming_worker is not None:
            self._streaming_worker.cancel()
            self._status_bar_widget.set_status("Cancelling transcription...")
        if self._detect_worker is not None:
            self._detect_worker.cancel()
            self._status_bar_widget.set_status("Cancelling detection...")
        if self._split_worker is not None:
            self._split_worker.cancel()
            self._status_bar_widget.set_status("Cancelling split...")
        if self._burn_worker is not None:
            self._burn_worker.cancel()
            self._status_bar_widget.set_status("Cancelling burn...")

    def _on_boundary_moved(self, boundary_index: int, new_time: float) -> None:
        """Handle timeline boundary drag — atomically update both adjacent chapters."""
        self._split_controller.update_boundary(boundary_index, new_time)

    def _on_export_chapters(self) -> None:
        """Export chapters to JSON file."""
        try:
            path = self._split_controller.export_chapters()
            self._status_bar_widget.set_status(f"Chapters exported: {path}")
        except ValueError as exc:
            QMessageBox.warning(self, "Export Error", str(exc))

    def _on_about(self) -> None:
        QMessageBox.about(
            self,
            "About VideoSplitter",
            "VideoSplitter — Subtitle Review & Split Tool\n\n"
            "Phase A: ASR transcription + manual subtitle correction.\n"
            "Phase B: LLM chapter detection + interactive splitting.",
        )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
