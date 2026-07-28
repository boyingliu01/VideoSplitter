"""Tests for StreamingTranscribeWorker — fast-batch VAD mode.

Covers the refactored pipeline:
1. ffprobe duration probe → audio_ready signal
2. Full audio extraction (AudioExtractor)
3. Engine loading via create_engine("auto")
4. model.generate(input=wav_path) → VAD auto-segmentation
5. ALL segments emitted at once via segments_ready
6. transcription_complete with full transcript
"""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root is on path
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from gui.workers.streaming_transcribe_worker import (
    StreamingTranscribeWorker,
)


def _make_worker_with_mocks():
    """Create a worker with mocked signals."""
    worker = StreamingTranscribeWorker(engine_name="auto")
    worker.audio_ready = MagicMock()
    worker.segments_ready = MagicMock()
    worker.chunk_completed = MagicMock()
    worker.transcription_complete = MagicMock()
    worker.transcription_progress = MagicMock()
    worker.model_loading_progress = MagicMock()
    worker.error = MagicMock()
    worker.cancelled = MagicMock()
    return worker


def _make_sensevoice_segments(n_total: int = 3, duration: float = 30.0):
    """Create fake SenseVoice sentence_info segments."""
    seg_duration = duration / n_total
    return [
        {"text": f"segment_{i}", "start": i * seg_duration * 1000, "end": (i + 1) * seg_duration * 1000}
        for i in range(n_total)
    ]


def _run_fast_batch_with_mocks(worker, total_duration=30.0, sentence_info=None, side_effect=None):
    """Run worker in fast-batch VAD mode with all external deps mocked.

    Args:
        worker: Worker with mocked signals.
        total_duration: Simulated video duration in seconds.
        sentence_info: List of dicts to return as model.generate() result[0]["sentence_info"].
        side_effect: If set, model.generate is replaced with this side_effect.
    """
    if sentence_info is None:
        sentence_info = _make_sensevoice_segments(n_total=5, duration=total_duration)
    if side_effect is None:
        side_effect = [{"sentence_info": sentence_info}]

    # Mock model
    mock_model = MagicMock()
    mock_model.generate.return_value = side_effect

    # Mock engine with _model attribute set
    mock_engine = MagicMock()
    mock_engine._model = mock_model
    mock_engine.initialize.return_value = None

    # Mock AudioExtractor
    mock_extractor_instance = MagicMock()
    mock_extractor_instance.get_duration.return_value = total_duration
    mock_extractor_instance.extract.return_value = "/tmp/fake.wav"

    patches = [
        patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=total_duration,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.create_engine",
            return_value=mock_engine,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.AudioExtractor",
            return_value=mock_extractor_instance,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ),
    ]

    for p in patches:
        p.start()
    try:
        worker.run("/fake/video.mp4")
    finally:
        for p in patches:
            p.stop()

    return mock_model, mock_engine, mock_extractor_instance


class TestStreamingTranscribeWorkerSignals:
    """Test fast-batch VAD mode signal emissions."""

    def test_emits_audio_ready(self):
        """Worker emits audio_ready with total duration."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(worker, total_duration=65.0)

        worker.audio_ready.emit.assert_called_once_with(65.0)

    def test_emits_segments_ready_once_with_all_segments(self):
        """Worker emits segments_ready exactly ONCE with all VAD segments."""
        worker = _make_worker_with_mocks()
        sentence_info = _make_sensevoice_segments(n_total=5, duration=50.0)
        _run_fast_batch_with_mocks(worker, total_duration=50.0, sentence_info=sentence_info)

        # segments_ready must be emitted EXACTLY once (fast-batch mode)
        assert worker.segments_ready.emit.call_count == 1, (
            f"Expected 1 segments_ready emit, got {worker.segments_ready.emit.call_count}"
        )

        # All 5 segments must be in that single emit
        segments = worker.segments_ready.emit.call_args[0][0]
        assert len(segments) == 5
        assert segments[0]["text"] == "segment_0"
        assert segments[4]["text"] == "segment_4"

    def test_emits_transcription_complete(self):
        """Worker emits transcription_complete with full transcript dict."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(worker, total_duration=30.0)

        worker.transcription_complete.emit.assert_called_once()
        transcript = worker.transcription_complete.emit.call_args[0][0]
        assert transcript["language"] == "zh"
        assert transcript["duration"] == 30.0
        assert "segments" in transcript

    def test_cancel_stops_transcription(self):
        """cancel() stops transcription before processing."""
        worker = _make_worker_with_mocks()

        # Setting cancelled BEFORE run starts means it exits immediately
        worker._cancelled = True

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=60.0,
        ):
            worker.run("/fake/video.mp4")

        worker.cancelled.emit.assert_called_once()
        # No segments or complete signal when cancelled
        worker.segments_ready.emit.assert_not_called()
        worker.transcription_complete.emit.assert_not_called()

    def test_error_on_duration_failure(self):
        """Worker emits error if ffprobe fails."""
        worker = _make_worker_with_mocks()

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            side_effect=RuntimeError("ffprobe failed"),
        ):
            worker.run("/fake/video.mp4")

        worker.error.emit.assert_called_once()
        assert "ffprobe" in worker.error.emit.call_args[0][0]

    def test_progress_has_three_phases(self):
        """Progress emits cover the 3-phase pipeline: Extracting, Transcribing, Processing."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(worker, total_duration=30.0)

        messages = [
            c[0][1]
            for c in worker.transcription_progress.emit.call_args_list
            if len(c[0]) >= 2 and isinstance(c[0][1], str)
        ]
        # Must have at least one progress message
        assert len(messages) > 0
        # Check for the 3-phase progress pattern
        all_text = " ".join(messages)
        assert "Extracting" in all_text, f"Missing 'Extracting' phase in: {messages}"
        assert "Transcribing" in all_text, f"Missing 'Transcribing' phase in: {messages}"

    def test_segments_from_sensevoice_sentence_info(self):
        """SenseVoice segments from sentence_info are properly formatted."""
        worker = _make_worker_with_mocks()
        sentence_info = [
            {"text": "<|zh|>hello world", "start": 0, "end": 1000},
            {"text": "<|zh|><|Speech|>second", "start": 1500, "end": 3000},
        ]
        _run_fast_batch_with_mocks(worker, total_duration=10.0, sentence_info=sentence_info)

        segments = worker.segments_ready.emit.call_args[0][0]
        assert len(segments) == 2
        # SenseVoice tags should be stripped
        assert "hello world" in segments[0]["text"]
        assert segments[0]["start"] == 0.0
        assert segments[0]["end"] == 1.0
        # second segment
        assert segments[1]["start"] == 1.5
        assert segments[1]["end"] == 3.0

    def test_segments_from_funasr_nano_timestamps(self):
        """FunASR-Nano segments from timestamp output are properly formatted."""
        worker = _make_worker_with_mocks()

        # FunASR-Nano returns text + timestamp (not sentence_info)
        mock_engine = MagicMock()
        mock_model = MagicMock()
        # Simulate FunASR-Nano output format: timestamp, no sentence_info
        mock_model.generate.return_value = [{
            "text": "你好世界",
            "timestamp": [[0, 3000], [3000, 5000]],
        }]
        mock_engine._model = mock_model
        mock_engine.initialize.return_value = None

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.get_duration.return_value = 5.0
        mock_extractor_instance.extract.return_value = "/tmp/fake.wav"

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=5.0,
        ), patch(
            "gui.workers.streaming_transcribe_worker.create_engine",
            return_value=mock_engine,
        ), patch(
            "gui.workers.streaming_transcribe_worker.AudioExtractor",
            return_value=mock_extractor_instance,
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ):
            worker.run("/fake/video.mp4")

        worker.segments_ready.emit.assert_called_once()
        segments = worker.segments_ready.emit.call_args[0][0]
        assert len(segments) > 0

    def test_model_loading_progress_emitted(self):
        """Worker emits model_loading_progress during engine initialization."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(worker)

        # Should have emitted loading progress
        assert worker.model_loading_progress.emit.call_count > 0

    def test_error_on_audio_extraction_failure(self):
        """Worker emits error if AudioExtractor.extract() raises."""
        worker = _make_worker_with_mocks()

        mock_extractor_instance = MagicMock()
        mock_extractor_instance.get_duration.return_value = 30.0
        mock_extractor_instance.extract.side_effect = RuntimeError("FFmpeg failed")

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=30.0,
        ), patch(
            "gui.workers.streaming_transcribe_worker.AudioExtractor",
            return_value=mock_extractor_instance,
        ):
            worker.run("/fake/video.mp4")

        worker.error.emit.assert_called_once()
        assert "FFmpeg" in worker.error.emit.call_args[0][0]


class TestStreamingWorkerHotword:
    """Test hotword handling in fast-batch mode."""

    def test_set_hotword_updates(self):
        """set_hotword() updates the internal hotword string."""
        worker = StreamingTranscribeWorker(engine_name="auto")
        worker.set_hotword("质量 红线")
        assert worker._hotword == "质量 红线"

    def test_cancel_sets_flag(self):
        """cancel() sets the _cancelled flag."""
        worker = StreamingTranscribeWorker(engine_name="auto")
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True

    def test_no_priority_method(self):
        """request_priority should NOT exist in the refactored worker."""
        worker = StreamingTranscribeWorker(engine_name="auto")
        assert not hasattr(worker, "request_priority"), \
            "request_priority must be removed from fast-batch worker"

    def test_no_deduplicate_method(self):
        """_deduplicate_segments should NOT exist in the refactored worker."""
        worker = StreamingTranscribeWorker(engine_name="auto")
        assert not hasattr(worker, "_deduplicate_segments"), \
            "_deduplicate_segments must be removed (VAD handles merging)"

    def test_no_chunk_seconds_attr(self):
        """_chunk_seconds attribute should NOT exist."""
        worker = StreamingTranscribeWorker(engine_name="auto")
        assert not hasattr(worker, "_chunk_seconds"), \
            "_chunk_seconds must be removed"

    def test_no_read_pcm_chunk(self):
        """_read_pcm_chunk static method should NOT exist."""
        assert not hasattr(StreamingTranscribeWorker, "_read_pcm_chunk"), \
            "_read_pcm_chunk must be removed"


class TestStreamingWorkerSegments:
    """Test segment extraction and formatting."""

    def test_empty_sentence_info_results_in_empty_segments(self):
        """Empty sentence_info should emit empty segment list."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(
            worker, total_duration=10.0,
            sentence_info=[],
        )

        # When no segments found, segments_ready is NOT emitted
        # (worker only emits when there are segments)
        worker.segments_ready.emit.assert_not_called()
        worker.transcription_complete.emit.assert_called_once()
        transcript = worker.transcription_complete.emit.call_args[0][0]
        assert transcript["segments"] == []

    def test_segments_preserve_original_order(self):
        """Segments must preserve the order from VAD output."""
        worker = _make_worker_with_mocks()
        sentence_info = [
            {"text": "first", "start": 0, "end": 10000},
            {"text": "second", "start": 11000, "end": 20000},
            {"text": "third", "start": 21000, "end": 30000},
        ]
        _run_fast_batch_with_mocks(worker, total_duration=30.0, sentence_info=sentence_info)

        segments = worker.segments_ready.emit.call_args[0][0]
        assert segments[0]["text"] == "first"
        assert segments[1]["text"] == "second"
        assert segments[2]["text"] == "third"

    def test_chunk_completed_emitted_once_at_end(self):
        """chunk_completed signal is emitted once with (1, 1) at the end."""
        worker = _make_worker_with_mocks()
        _run_fast_batch_with_mocks(worker, total_duration=30.0)

        # In fast-batch mode, chunk_completed is emitted once
        # with completed=1, total=1 to indicate 100%
        assert worker.chunk_completed.emit.call_count == 1
        completed, total = worker.chunk_completed.emit.call_args[0]
        assert completed == 1
        assert total == 1
