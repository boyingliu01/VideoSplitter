"""QMediaPlayer + QVideoWidget wrapper for video playback"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class VideoPlayerWidget(QWidget):
    """QMediaPlayer + QVideoWidget wrapper for video playback."""

    position_changed = Signal(int)
    duration_changed = Signal(int)
    seeked = Signal(int)  # Emitted when user drags seek slider (position in ms)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._video_widget = QVideoWidget(self)

        self._play_pause_btn = QPushButton("\u25b6", self)
        self._play_pause_btn.setFixedWidth(40)
        self._play_pause_btn.clicked.connect(self._toggle_play_pause)

        self._seek_slider = QSlider(Qt.Orientation.Horizontal, self)
        self._seek_slider.setRange(0, 0)

        controls_layout = QHBoxLayout()
        controls_layout.addWidget(self._play_pause_btn)
        controls_layout.addWidget(self._seek_slider)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._video_widget, stretch=1)
        layout.addLayout(controls_layout)

        self._player.setVideoOutput(self._video_widget)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.errorOccurred.connect(self._on_error)
        self._seek_slider.sliderMoved.connect(self._player.setPosition)
        self._seek_slider.sliderMoved.connect(self._on_slider_moved)

    def load_video(self, path: str) -> None:
        self._player.setSource(QUrl.fromLocalFile(path))

    def seek_to(self, position_ms: int) -> None:
        self._player.setPosition(position_ms)

    def play(self) -> None:
        self._player.play()
        self._play_pause_btn.setText("\u23f8")

    def pause(self) -> None:
        self._player.pause()
        self._play_pause_btn.setText("\u25b6")

    def _toggle_play_pause(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.pause()
        else:
            self.play()

    def _on_position_changed(self, position: int) -> None:
        self._seek_slider.setValue(position)
        self.position_changed.emit(position)

    def _on_duration_changed(self, duration: int) -> None:
        self._seek_slider.setRange(0, duration)
        self.duration_changed.emit(duration)

    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        QMessageBox.warning(
            self,
            "Playback Error",
            "This video codec is not supported by the built-in player. "
            "Please pre-convert to H.264 MP4 using FFmpeg.",
        )

    def _on_slider_moved(self, position: int) -> None:
        """Emit seeked signal when user drags the seek slider."""
        self.seeked.emit(position)
