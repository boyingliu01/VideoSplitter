"""Progress/status display with progress bar"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class StatusBarWidget(QWidget):
    """Progress/status display with a text label and progress bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Ready", self)
        self._label.setStyleSheet("font-size: 13px; font-weight: bold; padding: 2px;")

        self._progress_bar = QProgressBar(self)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(22)
        self._progress_bar.hide()  # Hidden by default

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(self._label)
        layout.addWidget(self._progress_bar)

    def set_status(self, text: str) -> None:
        """Set the status bar text."""
        self._label.setText(text)

    def set_progress(self, fraction: float, description: str = "") -> None:
        """Set progress with percentage and description."""
        pct = int(fraction * 100)
        self._progress_bar.setValue(pct)
        self._progress_bar.setFormat(f"{pct}%")
        self._progress_bar.show()
        if description:
            self._label.setText(f"{description}  [{pct}%]")
        else:
            self._label.setText(f"{pct}%")

    def show_progress(self, description: str = "") -> None:
        """Show progress bar (indeterminate mode)."""
        self._progress_bar.setRange(0, 0)  # Indeterminate
        self._progress_bar.show()
        if description:
            self._label.setText(description)

    def hide_progress(self) -> None:
        """Hide progress bar and reset."""
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.hide()
