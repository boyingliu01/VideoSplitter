"""Review tab: transcript display + edit area + navigation"""

from __future__ import annotations

import bisect

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSpinBox,
    QStyledItemDelegate,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from video_splitter.review import format_timestamp


class _SegmentHighlightDelegate(QStyledItemDelegate):
    """Custom delegate that draws a gold background on the highlighted row."""

    HIGHLIGHT_COLOR = QColor("#FFF3CD")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._highlight_row: int = -1

    def set_highlight_row(self, row: int) -> None:
        """Store the row to highlight and trigger a repaint of the viewport."""
        if row != self._highlight_row:
            self._highlight_row = row
            p = self.parent()
            if p is not None:
                p.viewport().update()

    def paint(self, painter, option, index) -> None:
        """Draw the item with a gold background if it's the highlighted row."""
        if index.row() == self._highlight_row:
            painter.save()
            painter.fillRect(option.rect, self.HIGHLIGHT_COLOR)
            painter.restore()
        super().paint(painter, option, index)


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

        # -- Playback-synced highlight state --
        self._segment_starts: list[float] = []
        self._pending_position: float = -1.0
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(250)
        self._sync_timer.timeout.connect(self._do_sync_highlight)

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

        # Scrollable full-subtitle list (QListView + QStandardItemModel)
        self._segment_model = QStandardItemModel(self)
        self._segment_list_view = QListView(self)
        self._segment_list_view.setModel(self._segment_model)
        self._segment_list_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._segment_list_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._segment_list_view.setMaximumHeight(140)
        self._segment_list_view.setVisible(False)

        self._segment_delegate = _SegmentHighlightDelegate(self._segment_list_view)
        self._segment_list_view.setItemDelegate(self._segment_delegate)

        self._segment_list_view.clicked.connect(self._on_list_row_clicked)

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
        layout.addWidget(self._segment_list_view)
        layout.addSpacing(4)
        layout.addWidget(QLabel("原文:", self))
        layout.addWidget(self._original_label)
        layout.addSpacing(4)
        layout.addWidget(QLabel("修正:", self))
        layout.addWidget(self._correction_edit)
        layout.addSpacing(8)
        layout.addWidget(self._status_label)
        layout.addLayout(nav_layout)

    # -- playback-synced highlight ------------------------------------------

    def sync_highlight(self, position_secs: float) -> None:
        """Schedule a highlight sync to the given playback position.

        Uses a 250 ms QTimer throttle to avoid excessive repaints.
        """
        self._pending_position = position_secs
        if not self._sync_timer.isActive():
            self._sync_timer.start()

    def _do_sync_highlight(self) -> None:
        """Find the segment whose window contains _pending_position and
        highlight its row in the QListView."""
        if not self._segment_starts or self._pending_position < 0:
            self._sync_timer.stop()
            return

        # bisect_right: find the first segment whose start > position,
        # then the current segment is the one before it (row-1).
        # If position is before the first segment start, row 0 is highlighted.
        idx = bisect.bisect_right(self._segment_starts, self._pending_position)
        row = max(0, idx - 1)
        row = min(row, self._segment_model.rowCount() - 1)

        self._segment_delegate.set_highlight_row(row)

        # Scroll so the highlighted row is visible at the top of the viewport
        model_idx = self._segment_model.index(row, 0)
        if model_idx.isValid():
            self._segment_list_view.scrollTo(
                model_idx, QAbstractItemView.ScrollHint.PositionAtTop
            )

        self._sync_timer.stop()

    # -- edit / correction ---------------------------------------------------

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

        # Update list highlight to the active segment
        if index < self._segment_model.rowCount():
            self._segment_delegate.set_highlight_row(index)
            model_idx = self._segment_model.index(index, 0)
            if model_idx.isValid():
                self._segment_list_view.scrollTo(
                    model_idx, QAbstractItemView.ScrollHint.PositionAtTop
                )

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
        (seconds, float) in ``Qt.UserRole + 1`` for click-to-jump.
        """
        if not segments:
            return
        if not self._segment_list_view.isVisible():
            self._segment_list_view.setVisible(True)

        for seg in segments:
            start = float(seg.get("start", 0.0))
            m, s = divmod(int(start), 60)
            text = seg.get("text", "")
            label = f"[{m:02d}:{s:02d}] {text}"

            item = QStandardItem(label)
            item.setData(start, Qt.ItemDataRole.UserRole + 1)
            item.setToolTip(text)
            self._segment_model.appendRow(item)

            self._segment_starts.append(start)

        self._segment_list_view.scrollToBottom()

    def clear_recognized_segments(self) -> None:
        """Clear and hide the recognized-segments list."""
        self._segment_model.clear()
        self._segment_starts.clear()
        self._segment_list_view.setVisible(False)

    def _on_list_row_clicked(self, index) -> None:
        """Forward a row click as a segment_activated(start_seconds) signal."""
        if not index.isValid():
            return
        item = self._segment_model.itemFromIndex(index)
        if item is None:
            return
        start = item.data(Qt.ItemDataRole.UserRole + 1)
        if start is not None:
            self.segment_activated.emit(float(start))
