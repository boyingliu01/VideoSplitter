"""Review tab: transcript display + edit area + navigation"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
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
    save_next_requested = Signal()
    skip_all_requested = Signal()
    jump_requested = Signal(int)
    save_requested = Signal()
    editing_started = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._segment_label = QLabel("Segment 0/0", self)
        self._segment_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._timestamp_label = QLabel("[00:00:00.000]", self)
        self._timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        self._prev_btn = QPushButton("\u25c0 上一段", self)
        self._prev_btn.clicked.connect(self.prev_requested.emit)

        self._save_next_btn = QPushButton("保存并继续 \u25b6", self)
        self._save_next_btn.clicked.connect(self.save_next_requested.emit)

        self._skip_all_btn = QPushButton("全部跳过", self)
        self._skip_all_btn.clicked.connect(self.skip_all_requested.emit)

        self._jump_spin = QSpinBox(self)
        self._jump_spin.setPrefix("跳到... ")
        self._jump_spin.setValue(1)
        self._jump_spin.editingFinished.connect(
            lambda: self.jump_requested.emit(self._jump_spin.value())
        )

        self._save_btn = QPushButton("保存", self)
        self._save_btn.clicked.connect(self.save_requested.emit)

        header_layout = QVBoxLayout()
        header_layout.addWidget(self._segment_label)
        header_layout.addWidget(self._timestamp_label)

        nav_layout = QHBoxLayout()
        nav_layout.addWidget(self._prev_btn)
        nav_layout.addWidget(self._save_next_btn)
        nav_layout.addWidget(self._skip_all_btn)
        nav_layout.addWidget(self._jump_spin)
        nav_layout.addWidget(self._save_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(header_layout)
        layout.addSpacing(8)
        layout.addWidget(QLabel("原文:", self))
        layout.addWidget(self._original_label)
        layout.addSpacing(4)
        layout.addWidget(QLabel("修正:", self))
        layout.addWidget(self._correction_edit)
        layout.addSpacing(8)
        layout.addLayout(nav_layout)

    def _on_text_changed(self) -> None:
        self.editing_started.emit()

    def set_segment(
        self,
        index: int,
        total: int,
        text: str,
        start_time: float,
        end_time: float,
    ) -> None:
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
