"""Tests for StreamingTranscribeWorker — incremental ASR transcription."""

from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure project root is on path
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from gui.workers.streaming_transcribe_worker import StreamingTranscribeWorker


def _make_worker_with_mocks():
    """Create a worker with mocked signals."""
    worker = StreamingTranscribeWorker(engine_name="funasr")
    worker.audio_ready = MagicMock()
    worker.segments_ready = MagicMock()
    worker.chunk_completed = MagicMock()
    worker.transcription_complete = MagicMock()
    worker.transcription_progress = MagicMock()
    worker.model_loading_progress = MagicMock()
    worker.error = MagicMock()
    worker.cancelled = MagicMock()
    return worker


def _run_worker_with_mocks(
    worker,
    total_duration=65.0,
    chunk_segments=None,
    cancel_after_chunk=None,
):
    """Run worker with all dependencies mocked.

    Args:
        worker: The worker instance (signals already mocked).
        total_duration: Simulated video duration.
        chunk_segments: Dict mapping chunk_idx -> list of segments returned
                        by _extract_segments for that chunk.
                        Default: each chunk returns one segment.
        cancel_after_chunk: If set, cancel() after this chunk index completes.
    """
    if chunk_segments is None:
        n_chunks = max(1, -(-int(total_duration) // 30))
        chunk_segments = {
            i: [{"text": f"text_{i}", "start": 0.0, "end": 5.0}]
            for i in range(n_chunks)
        }

    mock_model = MagicMock()
    mock_engine = MagicMock()

    # model.generate() returns a fake result
    fake_result = object()
    mock_model.generate.return_value = fake_result

    # engine._extract_segments() returns per-chunk segments based on start_time
    def fake_extract_segments(result):
        # We figure out which chunk this is from by looking at call order
        # Instead, we use a simpler approach: track call count
        call_idx = fake_extract_segments._call_count
        fake_extract_segments._call_count += 1
        return chunk_segments.get(call_idx, [])

    fake_extract_segments._call_count = 0
    mock_engine._extract_segments.side_effect = fake_extract_segments

    # Mock FFmpeg subprocess
    mock_proc = MagicMock()
    mock_proc.wait.return_value = None
    mock_proc.returncode = 0
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read.return_value = b""

    patches = [
        patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=total_duration,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.load_funasr_model",
            return_value=mock_model,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.FunASREngine",
            return_value=mock_engine,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker.subprocess.Popen",
            return_value=mock_proc,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker._extract_audio_range",
            return_value="/tmp/fake_chunk.wav",
        ),
        patch("gui.workers.streaming_transcribe_worker.os.unlink"),
        patch("gui.workers.streaming_transcribe_worker.gc.collect"),
    ]

    # Apply all patches
    mocks = [p.start() for p in patches]

    try:
        worker.run("/fake/video.mp4")
    finally:
        for p in patches:
            p.stop()

    return mock_model, mock_engine


class TestStreamingTranscribeWorkerSignals:
    """Test that the worker emits correct signals during transcription."""

    def test_emits_audio_ready(self):
        """Worker emits audio_ready with total duration."""
        worker = _make_worker_with_mocks()
        _run_worker_with_mocks(worker, total_duration=65.0)

        worker.audio_ready.emit.assert_called_once_with(65.0)

    def test_emits_segments_per_chunk(self):
        """Worker emits segments_ready for each completed chunk."""
        worker = _make_worker_with_mocks()
        total_duration = 65.0  # 3 chunks: 0-30, 30-60, 60-65
        chunk_segments = {
            0: [{"text": "chunk0", "start": 0.0, "end": 10.0}],
            1: [{"text": "chunk1", "start": 0.0, "end": 10.0}],
            2: [{"text": "chunk2", "start": 0.0, "end": 5.0}],
        }
        _run_worker_with_mocks(worker, total_duration, chunk_segments)

        # segments_ready should be called for each chunk that has segments
        assert worker.segments_ready.emit.call_count == 3

    def test_emits_transcription_complete(self):
        """Worker emits transcription_complete with full transcript dict."""
        worker = _make_worker_with_mocks()
        _run_worker_with_mocks(worker, total_duration=30.0)

        worker.transcription_complete.emit.assert_called_once()
        transcript = worker.transcription_complete.emit.call_args[0][0]
        assert transcript["language"] == "zh"
        assert transcript["duration"] == 30.0
        assert "segments" in transcript

    def test_cancel_stops_transcription(self):
        """cancel() stops the transcription loop at next chunk boundary."""
        worker = _make_worker_with_mocks()
        # 4 chunks for 120s video
        chunk_segments = {
            i: [{"text": f"t{i}", "start": 0.0, "end": 5.0}]
            for i in range(4)
        }

        # We need to cancel after first chunk — use side_effect on chunk_completed.emit
        call_count = 0

        def cancel_after_first_chunk(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                worker._cancelled = True

        worker.chunk_completed.emit = MagicMock(side_effect=cancel_after_first_chunk)

        _run_worker_with_mocks(worker, total_duration=120.0, chunk_segments=chunk_segments)

        # Should have processed only 1 chunk before cancellation
        assert call_count == 1
        worker.cancelled.emit.assert_called_once()

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

    def test_short_video_single_chunk(self):
        """Video shorter than chunk_seconds produces exactly 1 chunk."""
        worker = _make_worker_with_mocks()
        _run_worker_with_mocks(worker, total_duration=15.0)  # < 30s = 1 chunk

        # Should complete with 1 chunk
        worker.chunk_completed.emit.assert_called()
        worker.transcription_complete.emit.assert_called_once()

    def test_segments_have_offset_timestamps(self):
        """Segments from each chunk have globally-offset timestamps."""
        worker = _make_worker_with_mocks()
        total_duration = 65.0  # 3 chunks
        chunk_segments = {
            0: [{"text": "a", "start": 1.0, "end": 5.0}],
            1: [{"text": "b", "start": 2.0, "end": 8.0}],
            2: [{"text": "c", "start": 0.0, "end": 5.0}],
        }
        _run_worker_with_mocks(worker, total_duration, chunk_segments)

        # Check that segments_ready was called with offset timestamps
        calls = worker.segments_ready.emit.call_args_list
        # Chunk 0: start_time=0, so segments keep original timestamps
        assert calls[0][0][0][0]["start"] == 1.0
        assert calls[0][0][0][0]["end"] == 5.0
        # Chunk 1: start_time=30, so offset by 30
        assert calls[1][0][0][0]["start"] == 32.0
        assert calls[1][0][0][0]["end"] == 38.0
        # Chunk 2: start_time=60, so offset by 60
        assert calls[2][0][0][0]["start"] == 60.0
        assert calls[2][0][0][0]["end"] == 65.0

    def test_ffmpeg_failure_emits_error(self):
        """Worker emits error if FFmpeg audio extraction fails."""
        worker = _make_worker_with_mocks()

        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mock_proc.returncode = 1
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = b"ffmpeg error details"

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=60.0,
        ), patch(
            "gui.workers.streaming_transcribe_worker.load_funasr_model",
            return_value=MagicMock(),
        ), patch(
            "gui.workers.streaming_transcribe_worker.subprocess.Popen",
            return_value=mock_proc,
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ):
            worker.run("/fake/video.mp4")

        worker.error.emit.assert_called_once()
        assert "FFmpeg" in worker.error.emit.call_args[0][0]


class TestStreamingWorkerPriority:
    """Test request_priority() behavior."""

    def test_request_priority_sets_chunk_index(self):
        """request_priority sets the priority chunk index."""
        worker = StreamingTranscribeWorker()
        worker._completed_chunks = {0, 1}  # chunks 0 and 1 already done

        worker.request_priority(75.0)  # 75s → chunk 2 (75//30=2)
        assert worker._priority_chunk_index == 2

    def test_request_priority_ignores_completed_chunks(self):
        """request_priority does not set priority for already-completed chunks."""
        worker = StreamingTranscribeWorker()
        worker._completed_chunks = {0, 1, 2}

        worker.request_priority(15.0)  # 15s → chunk 0 (already done)
        assert worker._priority_chunk_index == -1

    def test_cancel_sets_flag(self):
        """cancel() sets the _cancelled flag."""
        worker = StreamingTranscribeWorker()
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True

    def test_priority_reorder_in_run(self):
        """Priority request reorders chunk processing in run loop.

        We verify this by pre-setting _priority_chunk_index before run(),
        so chunk 2 is processed first, then 0, then 1.
        """
        worker = _make_worker_with_mocks()
        total_duration = 90.0  # 3 chunks: 0, 1, 2

        chunk_segments = {
            i: [{"text": f"t{i}", "start": 0.0, "end": 5.0}]
            for i in range(3)
        }

        mock_model = MagicMock()
        mock_engine = MagicMock()
        mock_model.generate.return_value = object()

        chunk_process_order = []

        def fake_extract_range(video_path, start_time, duration):
            chunk_idx = int(start_time // 30)
            chunk_process_order.append(chunk_idx)
            return "/tmp/fake_chunk.wav"

        def fake_extract_segments(result):
            # Return segments for whatever chunk was just processed
            idx = chunk_process_order[-1]
            return chunk_segments.get(idx, [])

        mock_engine._extract_segments.side_effect = fake_extract_segments

        # Pre-set priority for chunk 2 BEFORE running
        worker._priority_chunk_index = 2

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=total_duration,
        ), patch(
            "gui.workers.streaming_transcribe_worker.load_funasr_model",
            return_value=mock_model,
        ), patch(
            "gui.workers.streaming_transcribe_worker.FunASREngine",
            return_value=mock_engine,
        ), patch(
            "gui.workers.streaming_transcribe_worker.subprocess.Popen",
            return_value=MagicMock(returncode=0, wait=MagicMock(), stderr=MagicMock(read=MagicMock(return_value=b""))),
        ), patch(
            "gui.workers.streaming_transcribe_worker._extract_audio_range",
            side_effect=fake_extract_range,
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ), patch(
            "gui.workers.streaming_transcribe_worker.gc.collect",
        ):
            worker.run("/fake/video.mp4")

        # With priority=2 pre-set, order should be: 2 (priority), 0, 1
        assert chunk_process_order == [2, 0, 1]


class TestStreamingWorkerDedup:
    """Test _deduplicate_segments() logic."""

    def test_no_existing_segments(self):
        """When no existing segments, all new segments pass through."""
        worker = StreamingTranscribeWorker()
        worker._all_segments = []
        new_segs = [
            {"text": "a", "start": 0.0, "end": 5.0},
            {"text": "b", "start": 6.0, "end": 10.0},
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 2

    def test_overlapping_segment_skipped(self):
        """New segments overlapping with existing tail are skipped."""
        worker = StreamingTranscribeWorker()
        worker._all_segments = [
            {"text": "prev", "start": 0.0, "end": 30.0},
        ]
        new_segs = [
            {"text": "overlap", "start": 29.0, "end": 35.0},  # overlaps
            {"text": "new", "start": 31.0, "end": 40.0},       # no overlap
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 1
        assert result[0]["text"] == "new"

    def test_non_overlapping_passes_through(self):
        """New segments after existing tail pass through."""
        worker = StreamingTranscribeWorker()
        worker._all_segments = [
            {"text": "prev", "start": 0.0, "end": 28.0},
        ]
        new_segs = [
            {"text": "next", "start": 30.0, "end": 40.0},  # gap > 0.5s
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 1
