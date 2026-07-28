"""Review tab: transcript display + edit area + navigation"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from video_splitter.review import format_timestamp


class SubtitlePanel(QWidget):
    """Review tab: transcript display + edit area + navigation."""

    prev_requested = Signal()
    next_requested = Signal()
    save_next_requested = Signal()
    skip_all_requested = Signal()
    jump_requested = Signal(int)
    save_requested = Signal()
    editing_started = Signal()
    start_transcription_requested = Signal()
    segment_activated = Signal(float)  # start-time in seconds of clicked row

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editing_triggered: bool = False

        # Prominent speech-recognition starter (top of panel)
        self._transcribe_btn = QPushButton("开始语音识别", self)
        self._transcribe_btn.setMinimumHeight(32)
        self._transcribe_btn.setStyleSheet("font-weight: bold;")
        self._transcribe_btn.clicked.connect(
            self.start_transcription_requested.emit
        )

        self._segment_label = QLabel("Segment 0/0", self)
        self._segment_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._timestamp_label = QLabel("[00:00:00.000]", self)
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Scrolling list of segments recognized so far (streaming view).
        # Hidden until the first segments arrive; rows are click-to-jump.
        self._segment_list = QListWidget(self)
        self._segment_list.setMaximumHeight(140)
        self._segment_list.setVisible(False)
        self._segment_list.itemClicked.connect(self._on_segment_item_clicked)

        self._original_label = QLabel("", self)
        self._original_label.setWordWrap(True)
        self._original_label.setMaximumHeight(60)
        self._original_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self._correction_edit = QTextEdit(self)
        self._correction_edit.setMinimumHeight(80)
        self._correction_edit.setPlaceholderText("输入修正...")
        self._correction_edit.textChanged.connect(self._on_text_changed)

        self._prev_btn = QPushButton("\u25c0 上一段 (Ctrl+Shift+\u2190)", self)
        self._prev_btn.clicked.connect(self.prev_requested.emit)

        self._next_btn = QPushButton("下一段 \u25b6 (Ctrl+Shift+\u2192)", self)
        self._next_btn.clicked.connect(self.next_requested.emit)

        self._save_next_btn = QPushButton("保存并继续 \u25b6 (Ctrl+Enter)", self)
        self._save_next_btn.clicked.connect(self.save_next_requested.emit)

        self._skip_all_btn = QPushButton("全部跳过", self)
        self._skip_all_btn.clicked.connect(self.skip_all_requested.emit)

        self._jump_spin = QSpinBox(self)
        self._jump_spin.setPrefix("跳到... ")
        self._jump_spin.setValue(1)
        self._jump_spin.lineEdit().returnPressed.connect(
            lambda: self.jump_requested.emit(self._jump_spin.value())
        )

        self._save_btn = QPushButton("保存 (Ctrl+S)", self)
        self._save_btn.clicked.connect(self.save_requested.emit)

        self._status_label = QLabel("", self)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setVisible(False)
        self._status_label.setStyleSheet("color: #666; font-style: italic;")

        header_layout = QVBoxLayout()
        header_layout.addWidget(self._segment_label)
        header_layout.addWidget(self._timestamp_label)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._next_btn)
        nav_layout.addWidget(self._save_next_btn)
        nav_layout.addWidget(self._skip_all_btn)
        nav_layout.addWidget(self._jump_spin)
        nav_layout.addWidget(self._save_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self._transcribe_btn)
        layout.addLayout(header_layout)
        layout.addSpacing(4)
        layout.addWidget(self._segment_list)
        layout.addSpacing(4)
        layout.addWidget(QLabel("原文:", self))
        layout.addWidget(self._original_label)
        layout.addSpacing(4)
        layout.addWidget(QLabel("修正:", self))
        layout.addWidget(self._correction_edit)
        layout.addSpacing(8)
        layout.addWidget(self._status_label)
        layout.addLayout(nav_layout)

    def _on_text_changed(self) -> None:
        if not self._editing_triggered:
            self._editing_triggered = True
            self.editing_started.emit()

    def set_segment(
        self,
        index: int,
        total: int,
        text: str,
        start_time: float,
        end_time: float,
    ) -> None:
        self._editing_triggered = False
        self._segment_label.setText(f"Segment {index + 1}/{total}")
        self._timestamp_label.setText(
            f"[{format_timestamp(start_time)}]"
        )
        self._original_label.setText(text)
        self._jump_spin.setRange(1, total)
        self._jump_spin.blockSignals(True)
        self._jump_spin.setValue(index + 1)
        self._jump_spin.blockSignals(False)

    def set_correction(self, text: str) -> None:
        self._correction_edit.blockSignals(True)
        self._correction_edit.setPlainText(text)
        self._correction_edit.blockSignals(False)

    def get_correction(self) -> str:
        return self._correction_edit.toPlainText()

    def set_modified(self, modified: bool) -> None:
        font = self._segment_label.font()
        font.setBold(modified)
        self._segment_label.setFont(font)

    def clear(self) -> None:
        self._segment_label.setText("Segment 0/0")
        self._timestamp_label.setText("[00:00:00.000]")
        self._original_label.setText("")
        self._correction_edit.clear()
        self.set_modified(False)
        self.clear_transcription_status()

    def set_transcription_status(self, text: str) -> None:
        """Show a transcription status message (e.g. '正在识别第 3/10 段...')."""
        self._status_label.setText(text)
        self._status_label.setVisible(True)

    def clear_transcription_status(self) -> None:
        """Hide the transcription status message."""
        self._status_label.setVisible(False)

    # -- streaming transcription UI -----------------------------------------

    def set_transcribing(self, active: bool) -> None:
        """Toggle the transcribe button between idle and busy states."""
        if active:
            self._transcribe_btn.setEnabled(False)
            self._transcribe_btn.setText("识别中…")
        else:
            self._transcribe_btn.setEnabled(True)
            self._transcribe_btn.setText("开始语音识别")

    def append_recognized_segments(self, segments: list[dict]) -> None:
        """Append newly recognized segments to the scrolling list.

        Each row shows ``[mm:ss] text`` and stores the segment start time
        (seconds, float) in ``Qt.UserRole`` for click-to-jump.
        """
        if not segments:
            return
        if not self._segment_list.isVisible():
            self._segment_list.setVisible(True)
        for seg in segments:
            start = float(seg.get("start", 0.0))
            m, s = divmod(int(start), 60)
            text = seg.get("text", "")
            item = QListWidgetItem(f"[{m:02d}:{s:02d}] {text}")
            item.setData(Qt.ItemDataRole.UserRole, start)
            item.setToolTip(text)
            self._segment_list.addItem(item)
        self._segment_list.scrollToBottom()

    def clear_recognized_segments(self) -> None:
        """Clear and hide the recognized-segments list."""
        self._segment_list.clear()
        self._segment_list.setVisible(False)

    def _on_segment_item_clicked(self, item: QListWidgetItem) -> None:
        """Forward a row click as a segment_activated(start_seconds) signal."""
        start = item.data(Qt.ItemDataRole.UserRole)
        if start is not None:
            self.segment_activated.emit(float(start))
