"""Split tab main panel: chapter list + timeline + action buttons."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.chapter_list import ChapterListWidget
from gui.widgets.timeline import TimelineWidget


class SplitPanel(QWidget):
    """Split tab main panel combining chapter list, timeline, and controls.

    Layout::

        [Detect Chapters] [Validate] [Cancel]     -- action buttons
        +--------------------------------------+
        | Chapter List (ChapterListWidget)     |  -- upper half
        +--------------------------------------+
        | Timeline (TimelineWidget)            |  -- lower half
        +--------------------------------------+
        [Output: ...] [Browse] [Start Split]   -- bottom action row

    Signals:
        detect_requested: User clicked "Detect Chapters".
        validate_requested: User clicked "Validate".
        split_requested: User clicked "Start Split".
            Args: (output_dir,)
        cancel_requested: User clicked "Cancel".
        chapter_title_edited: Chapter title changed in the list.
            Args: (index, new_title, start, end)
        chapter_remove_requested: Delete chapter from context menu.
            Args: (index,)
        chapter_merge_requested: Merge chapter with next.
            Args: (index,)
        boundary_moved: Timeline boundary dragged.
            Args: (boundary_index, new_time_seconds)
        position_clicked: Timeline bar clicked.
            Args: (time_seconds,)
    """

    detect_requested = Signal()
    validate_requested = Signal()
    split_requested = Signal(str)
    burn_requested = Signal()
    cancel_requested = Signal()
    chapter_title_edited = Signal(int, str, float, float)
    chapter_remove_requested = Signal(int)
    chapter_merge_requested = Signal(int)
    boundary_moved = Signal(int, float)
    position_clicked = Signal(float)

    def __init__(
        self,
        video_path: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._video_path = video_path
        self._output_dir = self._default_output_dir(video_path)

        self._build_ui()
        self._connect_internal_signals()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        # -- Top action buttons --
        self._detect_btn = QPushButton("Detect Chapters", self)
        self._detect_btn.setToolTip(
            "Run LLM chapter detection on the current transcript"
        )
        self._detect_btn.clicked.connect(self.detect_requested.emit)

        self._validate_btn = QPushButton("Validate", self)
        self._validate_btn.setToolTip(
            "Re-run ChapterValidator to re-align boundaries and merge short chapters"
        )
        self._validate_btn.clicked.connect(self.validate_requested.emit)
        self._validate_btn.setEnabled(False)

        self._cancel_btn = QPushButton("Cancel", self)
        self._cancel_btn.setToolTip("Cancel the current operation")
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)

        top_btn_layout = QHBoxLayout()
        top_btn_layout.addWidget(self._detect_btn)
        top_btn_layout.addWidget(self._validate_btn)
        top_btn_layout.addStretch()
        top_btn_layout.addWidget(self._cancel_btn)

        # -- Chapter list + Timeline (vertical splitter) --
        self._chapter_list = ChapterListWidget(self)
        self._timeline = TimelineWidget(self)

        content_splitter = QSplitter(Qt.Orientation.Vertical, self)
        content_splitter.addWidget(self._chapter_list)
        content_splitter.addWidget(self._timeline)
        content_splitter.setStretchFactor(0, 7)
        content_splitter.setStretchFactor(1, 3)

        # -- Bottom action row --
        self._output_label = QLabel("Output:", self)
        self._output_edit = QLineEdit(self._output_dir, self)
        self._output_edit.setPlaceholderText("Output directory...")

        self._browse_btn = QPushButton("Browse...", self)
        self._browse_btn.setFixedWidth(70)
        self._browse_btn.clicked.connect(self._on_browse_output)

        self._split_btn = QPushButton("Start Split", self)
        self._split_btn.setToolTip("Cut video into chapters using FFmpeg")
        self._split_btn.setEnabled(False)
        self._split_btn.clicked.connect(self._on_start_split)

        self._burn_btn = QPushButton("Burn Subtitles", self)
        self._burn_btn.setToolTip(
            "Burn corrected subtitles into the split video segments"
        )
        self._burn_btn.setEnabled(False)
        self._burn_btn.clicked.connect(self.burn_requested.emit)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self._output_label)
        bottom_layout.addWidget(self._output_edit, stretch=1)
        bottom_layout.addWidget(self._browse_btn)
        bottom_layout.addWidget(self._split_btn)
        bottom_layout.addWidget(self._burn_btn)

        # -- Main layout --
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(top_btn_layout)
        main_layout.addWidget(content_splitter, stretch=1)
        main_layout.addLayout(bottom_layout)

    def _connect_internal_signals(self) -> None:
        """Wire chapter list and timeline signals to panel-level signals."""
        cl = self._chapter_list
        cl.chapter_edited.connect(self.chapter_title_edited)
        cl.chapter_remove_requested.connect(self.chapter_remove_requested)
        cl.chapter_merge_requested.connect(self.chapter_merge_requested)

        tl = self._timeline
        tl.boundary_moved.connect(self.boundary_moved)
        tl.position_clicked.connect(self.position_clicked)

    # -- Public API --------------------------------------------------------

    def set_chapters(self, chapters: List[Dict[str, Any]]) -> None:
        """Update both chapter list and timeline with new data."""
        self._chapter_list.set_chapters(chapters)
        self._timeline.set_chapters(chapters)

        has_chapters = len(chapters) > 0
        self._validate_btn.setEnabled(has_chapters)
        self._split_btn.setEnabled(has_chapters)

    def set_duration(self, duration: float) -> None:
        """Set timeline total duration."""
        self._timeline.set_duration(duration)

    def set_current_position(self, position_seconds: float) -> None:
        """Update timeline playback position indicator."""
        self._timeline.set_current_position(position_seconds)

    def set_video_path(self, path: str) -> None:
        """Update video path and recalculate default output dir."""
        self._video_path = path
        self._output_dir = self._default_output_dir(path)
        self._output_edit.setText(self._output_dir)

    def set_detecting(self, active: bool) -> None:
        """Toggle UI state during chapter detection."""
        self._detect_btn.setEnabled(not active)
        self._cancel_btn.setEnabled(active)
        if active:
            self._detect_btn.setText("Detecting...")
        else:
            self._detect_btn.setText("Detect Chapters")

    def set_splitting(self, active: bool) -> None:
        """Toggle UI state during video splitting."""
        self._split_btn.setEnabled(not active)
        self._detect_btn.setEnabled(not active)
        self._burn_btn.setEnabled(not active)
        self._cancel_btn.setEnabled(active)
        if active:
            self._split_btn.setText("Splitting...")
        else:
            self._split_btn.setText("Start Split")

    def set_burning(self, active: bool) -> None:
        """Toggle UI state during subtitle burning."""
        self._burn_btn.setEnabled(not active)
        self._split_btn.setEnabled(not active)
        self._detect_btn.setEnabled(not active)
        self._cancel_btn.setEnabled(active)
        if active:
            self._burn_btn.setText("Burning...")
        else:
            self._burn_btn.setText("Burn Subtitles")

    def set_split_complete(self, segment_files: list) -> None:
        """Enable burn button after successful split."""
        self._split_btn.setEnabled(True)
        self._burn_btn.setEnabled(len(segment_files) > 0)
        self._detect_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)

    def set_progress(self, frac: float, desc: str) -> None:
        """Update progress display (reuses status bar via parent)."""
        # Progress is shown in the status bar, managed by MainWindow.
        # This method is a hook for future inline progress bar.
        pass

    def output_dir(self) -> str:
        """Return the current output directory path."""
        return self._output_edit.text().strip()

    # -- Private slots -----------------------------------------------------

    def _on_browse_output(self) -> None:
        """Open directory picker for output location."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Directory", self._output_dir
        )
        if path:
            self._output_edit.setText(path)
            self._output_dir = path

    def _on_start_split(self) -> None:
        """Emit split_requested with the current output directory."""
        out = self.output_dir()
        if out:
            self.split_requested.emit(out)

    # -- Helpers -----------------------------------------------------------

    @staticmethod
    def _default_output_dir(video_path: str) -> str:
        """Derive default output directory from video path."""
        if not video_path:
            return ""
        p = Path(video_path)
        return str(p.parent / (p.stem + "_segments"))
