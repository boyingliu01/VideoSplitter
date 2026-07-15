"""Editable chapter list widget for the Split tab."""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from video_splitter.review import format_timestamp


class ChapterListWidget(QWidget):
    """Editable chapter list based on QTableWidget.

    Columns: #, Title (editable), Start, End, Duration.
    Double-click title to edit.  Right-click for context menu
    (delete / merge with next).

    Signals:
        chapter_edited: Emitted when a chapter title is changed via the UI.
            Args: (index, new_title, start_seconds, end_seconds)
        chapter_remove_requested: Emitted on context-menu "Delete".
            Args: (index,)
        chapter_merge_requested: Emitted on context-menu "Merge with next".
            Args: (index,)
    """

    chapter_edited = Signal(int, str, float, float)
    chapter_remove_requested = Signal(int)
    chapter_merge_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._table = QTableWidget(self)
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(
            ["#", "Title", "Start", "End", "Duration"]
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.cellChanged.connect(self._on_cell_changed)

        header = self._table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(2, 90)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(4, 70)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._table)

    def set_chapters(self, chapters: List[Dict[str, Any]]) -> None:
        """Populate the table with chapter data.

        Uses ``blockSignals(True)`` to prevent ``cellChanged`` from
        firing during programmatic updates (prevents circular signals
        with the controller).

        Args:
            chapters: List of chapter dicts with ``title``,
                ``start_seconds``, ``end_seconds``.
        """
        self._table.blockSignals(True)
        try:
            self._table.setRowCount(len(chapters))
            for row, ch in enumerate(chapters):
                # # column (read-only)
                num_item = QTableWidgetItem(str(row + 1))
                num_item.setFlags(
                    num_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 0, num_item)

                # Title column (editable)
                title_item = QTableWidgetItem(ch.get("title", ""))
                self._table.setItem(row, 1, title_item)

                # Start column (read-only display)
                start = ch.get("start_seconds", 0.0)
                start_item = QTableWidgetItem(format_timestamp(start))
                start_item.setFlags(
                    start_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                self._table.setItem(row, 2, start_item)

                # End column (read-only display)
                end = ch.get("end_seconds", 0.0)
                end_item = QTableWidgetItem(format_timestamp(end))
                end_item.setFlags(
                    end_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                self._table.setItem(row, 3, end_item)

                # Duration column (read-only, computed)
                dur = end - start
                dur_item = QTableWidgetItem(f"{dur:.1f}s")
                dur_item.setFlags(
                    dur_item.flags() & ~Qt.ItemFlag.ItemIsEditable
                )
                dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, 4, dur_item)
        finally:
            self._table.blockSignals(False)

    def selected_index(self) -> int:
        """Return the currently selected row index, or -1."""
        rows = self._table.selectionModel().selectedRows()
        if rows:
            return rows[0].row()
        return -1

    # -- Private slots -----------------------------------------------------

    def _on_cell_changed(self, row: int, column: int) -> None:
        """Handle cell edits — only title column (1) is editable."""
        if column != 1:
            return

        item = self._table.item(row, 1)
        if item is None:
            return

        # Read start/end from the table to emit full data
        start_item = self._table.item(row, 2)
        end_item = self._table.item(row, 3)
        if start_item is None or end_item is None:
            return

        # Parse timestamps back to seconds
        start = self._parse_timestamp_display(start_item.text())
        end = self._parse_timestamp_display(end_item.text())

        self.chapter_edited.emit(row, item.text(), start, end)

    def _on_context_menu(self, pos) -> None:
        """Show right-click context menu."""
        index = self._table.rowAt(pos.y())
        if index < 0:
            return

        menu = QMenu(self)

        delete_action = menu.addAction("Delete chapter")
        delete_action.triggered.connect(
            lambda: self.chapter_remove_requested.emit(index)
        )

        # Only show merge if not the last row
        if index < self._table.rowCount() - 1:
            merge_action = menu.addAction("Merge with next")
            merge_action.triggered.connect(
                lambda: self.chapter_merge_requested.emit(index)
            )

        menu.exec(self._table.viewport().mapToGlobal(pos))

    @staticmethod
    def _parse_timestamp_display(text: str) -> float:
        """Parse display timestamp (HH:MM:SS.mmm) back to seconds."""
        try:
            parts = text.strip().split(":")
            if len(parts) == 3:
                h, m, s = parts
                return float(h) * 3600 + float(m) * 60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return float(m) * 60 + float(s)
        except (ValueError, IndexError):
            pass
        return 0.0
