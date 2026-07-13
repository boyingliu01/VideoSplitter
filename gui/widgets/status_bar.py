"""Progress/status display"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StatusBarWidget(QWidget):
    """Progress/status display with a text label."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Ready", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(self._label)

    def set_status(self, text: str) -> None:
        """Set the status bar text."""
        self._label.setText(text)

    def set_progress(self, fraction: float, description: str = "") -> None:
        """Set progress text with percentage."""
        pct = int(fraction * 100)
        text = f"{description} ({pct}%)" if description else f"{pct}%"
        self._label.setText(text)
