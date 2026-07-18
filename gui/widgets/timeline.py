"""Self-drawn timeline widget with draggable chapter boundaries."""

from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPolygon,
)
from PySide6.QtWidgets import QWidget


# Color palette for chapter segments (cycled if more than 8)
_CHAPTER_COLORS = [
    QColor(70, 130, 180),   # Steel blue
    QColor(60, 179, 113),   # Medium sea green
    QColor(255, 165, 0),    # Orange
    QColor(186, 85, 211),   # Medium purple
    QColor(220, 20, 60),    # Crimson
    QColor(0, 191, 255),    # Deep sky blue
    QColor(255, 215, 0),    # Gold
    QColor(127, 255, 0),    # Spring green
]

_HIT_TEST_PX = 6   # pixels tolerance for hit-testing a boundary line
_MIN_CHAPTER_SECONDS = 5.0
_BAR_HEIGHT = 30    # pixels for the main timeline bar
_MARGIN_LEFT = 10
_MARGIN_RIGHT = 10
_MARGIN_TOP = 20
_MARGIN_BOTTOM = 25


class TimelineWidget(QWidget):
    """Horizontal timeline showing chapter boundaries with drag support.

    Draws a colored bar divided by chapter boundary lines.  Users can
    drag boundary lines to adjust chapter durations (minimum 5 seconds).
    Clicking on the bar seeks the video to that position.

    Signals:
        boundary_moved: Emitted when a boundary line is dragged.
            Args: (boundary_index, new_time_seconds).
            ``boundary_index`` is the index of the *end* boundary of
            chapter[i] (= the *start* boundary of chapter[i+1]).
        position_clicked: Emitted when the user clicks on the bar.
            Args: (time_seconds,).
    """

    boundary_moved = Signal(int, float)
    position_clicked = Signal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(_BAR_HEIGHT + _MARGIN_TOP + _MARGIN_BOTTOM + 20)

        self._duration: float = 0.0
        self._chapters: List[Dict[str, Any]] = []
        self._current_position: float = 0.0

        # Drag state
        self._dragging_boundary: int = -1  # -1 = not dragging
        self._drag_preview_time: float = 0.0

        self.setMouseTracking(True)

    # -- Public API --------------------------------------------------------

    def set_duration(self, duration: float) -> None:
        """Set total video duration in seconds."""
        self._duration = max(duration, 0.0)
        self.update()

    def set_chapters(self, chapters: List[Dict[str, Any]]) -> None:
        """Set chapter list for display.

        Uses no signals (pure display widget), so no blockSignals needed.
        """
        self._chapters = list(chapters)
        self.update()

    def set_current_position(self, position_seconds: float) -> None:
        """Update the playback position indicator."""
        self._current_position = position_seconds
        self.update()

    # -- Painting ----------------------------------------------------------

    def paintEvent(self, event) -> None:
        """Draw the timeline bar, chapter segments, and boundaries."""
        if self._duration <= 0:
            self._draw_empty()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bar_left = _MARGIN_LEFT
        bar_right = self.width() - _MARGIN_RIGHT
        bar_top = _MARGIN_TOP
        bar_bottom = bar_top + _BAR_HEIGHT
        bar_width = bar_right - bar_left

        # Background bar
        painter.fillRect(
            bar_left, bar_top, bar_width, _BAR_HEIGHT,
            QBrush(QColor(220, 220, 220)),
        )

        # Draw chapter segments (colored blocks)
        if self._chapters:
            for i, ch in enumerate(self._chapters):
                start = ch.get("start_seconds", 0.0)
                end = ch.get("end_seconds", 0.0)

                x1 = bar_left + int((start / self._duration) * bar_width)
                x2 = bar_left + int((end / self._duration) * bar_width)

                color = _CHAPTER_COLORS[i % len(_CHAPTER_COLORS)]
                painter.fillRect(x1, bar_top, x2 - x1, _BAR_HEIGHT, QBrush(color))

                # Chapter title (if space allows)
                seg_width = x2 - x1
                if seg_width > 40:
                    painter.setPen(QPen(QColor(255, 255, 255)))
                    font = QFont()
                    font.setPointSize(8)
                    painter.setFont(font)
                    title = ch.get("title", "")
                    if len(title) > seg_width // 7:
                        title = title[: seg_width // 7] + "…"
                    painter.drawText(
                        x1 + 4, bar_top + 4,
                        seg_width - 8, _BAR_HEIGHT - 8,
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        title,
                    )

            # Draw boundary lines between chapters
            painter.setPen(QPen(QColor(40, 40, 40), 2))
            for i in range(len(self._chapters) - 1):
                boundary_time = self._chapters[i].get("end_seconds", 0.0)
                x = bar_left + int((boundary_time / self._duration) * bar_width)
                painter.drawLine(x, bar_top, x, bar_bottom)

                # Boundary time label
                painter.setPen(QPen(QColor(60, 60, 60)))
                font = QFont()
                font.setPointSize(7)
                painter.setFont(font)
                ts = self._format_time_short(boundary_time)
                painter.drawText(
                    x - 30, bar_bottom + 2, 60, 15,
                    Qt.AlignmentFlag.AlignCenter,
                    ts,
                )
                painter.setPen(QPen(QColor(40, 40, 40), 2))

        # Drag preview line
        if self._dragging_boundary >= 0:
            preview_x = bar_left + int(
                (self._drag_preview_time / self._duration) * bar_width
            )
            painter.setPen(QPen(QColor(0, 120, 215), 3, Qt.PenStyle.DashLine))
            painter.drawLine(preview_x, bar_top - 5, preview_x, bar_bottom + 5)

            # Time label for preview
            painter.setPen(QPen(QColor(0, 120, 215)))
            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            ts = self._format_time_short(self._drag_preview_time)
            painter.drawText(
                preview_x - 30, bar_top - 15, 60, 14,
                Qt.AlignmentFlag.AlignCenter,
                ts,
            )

        # Current position indicator (thin red line)
        if self._current_position > 0:
            pos_x = bar_left + int(
                (self._current_position / self._duration) * bar_width
            )
            painter.setPen(QPen(QColor(220, 50, 50), 2))
            painter.drawLine(pos_x, bar_top - 3, pos_x, bar_bottom + 3)

            # Triangle indicator
            painter.setBrush(QBrush(QColor(220, 50, 50)))
            triangle_points = [
                (pos_x - 5, bar_top - 3),
                (pos_x + 5, bar_top - 3),
                (pos_x, bar_top + 3),
            ]
            polygon = QPolygon([QPoint(x, y) for x, y in triangle_points])
            painter.drawPolygon(polygon)

        # Start/end labels
        painter.setPen(QPen(QColor(60, 60, 60)))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            bar_left, bar_bottom + 5, 80, 15,
            Qt.AlignmentFlag.AlignLeft,
            "00:00",
        )
        end_ts = self._format_time_short(self._duration)
        painter.drawText(
            bar_right - 80, bar_bottom + 5, 80, 15,
            Qt.AlignmentFlag.AlignRight,
            end_ts,
        )

        painter.end()

    def _draw_empty(self) -> None:
        """Draw placeholder when no video is loaded."""
        painter = QPainter(self)
        painter.setPen(QPen(QColor(150, 150, 150)))
        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "No video loaded — open a video to see the timeline",
        )
        painter.end()

    # -- Mouse interaction -------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """Start drag if clicking near a boundary, otherwise emit position."""
        if self._duration <= 0 or not self._chapters:
            return

        bar_left = _MARGIN_LEFT
        bar_right = self.width() - _MARGIN_RIGHT
        bar_width = bar_right - bar_left
        mouse_x = event.position().x()

        # Hit-test boundaries
        boundary_index = self._hit_test_boundary(mouse_x, bar_left, bar_width)
        if boundary_index >= 0:
            self._dragging_boundary = boundary_index
            self._drag_preview_time = self._x_to_time(mouse_x, bar_left, bar_width)
            self.update()
        else:
            # Click to seek
            time = self._x_to_time(mouse_x, bar_left, bar_width)
            time = max(0.0, min(time, self._duration))
            self.position_clicked.emit(time)

    def mouseMoveEvent(self, event) -> None:
        """Update drag preview or change cursor near boundaries."""
        if self._duration <= 0:
            return

        bar_left = _MARGIN_LEFT
        bar_right = self.width() - _MARGIN_RIGHT
        bar_width = bar_right - bar_left
        mouse_x = event.position().x()

        if self._dragging_boundary >= 0:
            # Update preview
            new_time = self._x_to_time(mouse_x, bar_left, bar_width)
            new_time = max(0.0, min(new_time, self._duration))

            # Enforce minimum chapter duration
            idx = self._dragging_boundary
            min_time = (
                self._chapters[idx]["start_seconds"] + _MIN_CHAPTER_SECONDS
                if idx < len(self._chapters)
                else _MIN_CHAPTER_SECONDS
            )
            max_time = (
                self._chapters[idx + 1]["end_seconds"] - _MIN_CHAPTER_SECONDS
                if idx + 1 < len(self._chapters)
                else self._duration - _MIN_CHAPTER_SECONDS
            )
            new_time = max(min_time, min(new_time, max_time))

            self._drag_preview_time = new_time
            self.update()
        else:
            # Cursor feedback near boundaries
            boundary = self._hit_test_boundary(mouse_x, bar_left, bar_width)
            if boundary >= 0:
                self.setCursor(Qt.CursorShape.SplitHCursor)
            else:
                self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        """Commit the drag or ignore if not dragging."""
        if self._dragging_boundary >= 0:
            boundary_idx = self._dragging_boundary
            new_time = self._drag_preview_time
            self._dragging_boundary = -1
            self.boundary_moved.emit(boundary_idx, new_time)
            self.update()

    # -- Helpers -----------------------------------------------------------

    def _hit_test_boundary(
        self, mouse_x: float, bar_left: int, bar_width: int
    ) -> int:
        """Return boundary index if mouse is within ±_HIT_TEST_PX, else -1.

        A "boundary" is the dividing line between chapter[i] and chapter[i+1],
        i.e. there are ``len(chapters) - 1`` boundaries (indices 0..n-2).
        """
        for i in range(len(self._chapters) - 1):
            boundary_time = self._chapters[i].get("end_seconds", 0.0)
            bx = bar_left + int((boundary_time / self._duration) * bar_width)
            if abs(mouse_x - bx) <= _HIT_TEST_PX:
                return i
        return -1

    def _x_to_time(self, mouse_x: float, bar_left: int, bar_width: int) -> float:
        """Convert pixel X to time in seconds."""
        if bar_width <= 0:
            return 0.0
        fraction = (mouse_x - bar_left) / bar_width
        return fraction * self._duration

    @staticmethod
    def _format_time_short(seconds: float) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
