"""Tests for StreamingTranscribeWorker — incremental ASR transcription.

Covers the streaming pipeline: ffprobe → single FFmpeg PCM extraction →
in-memory numpy chunk slicing → per-chunk inference with live signals.
"""

from __future__ import annotations

import sys
import os
from collections import deque
from unittest.mock import MagicMock, patch

import numpy as np

# Ensure project root is on path
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from gui.workers.streaming_transcribe_worker import (
    BYTES_PER_SECOND,
    StreamingTranscribeWorker,
)


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


def _fake_audio():
    """A small fake PCM chunk as float32 numpy."""
    return np.zeros(16000, dtype=np.float32)


def _run_worker_with_mocks(
    worker,
    total_duration=65.0,
    chunk_segments=None,
):
    """Run worker with all external dependencies mocked.

    Args:
        worker: The worker instance (signals already mocked).
        total_duration: Simulated video duration.
        chunk_segments: Dict mapping call_idx -> list of segments returned
            by engine._extract_segments for that call.
    """
    if chunk_segments is None:
        n_chunks = max(1, -(-int(total_duration) // 30))
        chunk_segments = {
            i: [{"text": f"text_{i}", "start": 0.0, "end": 5.0}]
            for i in range(n_chunks)
        }

    mock_model = MagicMock()
    mock_engine = MagicMock()
    mock_model.generate.return_value = object()

    def fake_extract_segments(result):
        call_idx = fake_extract_segments._call_count
        fake_extract_segments._call_count += 1
        return chunk_segments.get(call_idx, [])

    fake_extract_segments._call_count = 0
    mock_engine._extract_segments.side_effect = fake_extract_segments

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0
    mock_proc.returncode = 0

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
        # PCM data is always fully available in tests
        patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._pcm_size",
            return_value=10**12,
        ),
        patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._read_pcm_chunk",
            side_effect=lambda path, start, dur: _fake_audio(),
        ),
        patch("gui.workers.streaming_transcribe_worker.os.unlink"),
        patch("gui.workers.streaming_transcribe_worker.gc.collect"),
    ]

    for p in patches:
        p.start()
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

        call_count = 0

        def cancel_after_first_chunk(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                worker._cancelled = True

        worker.chunk_completed.emit = MagicMock(side_effect=cancel_after_first_chunk)

        _run_worker_with_mocks(worker, total_duration=120.0)

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
        _run_worker_with_mocks(worker, total_duration=15.0)

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

        calls = worker.segments_ready.emit.call_args_list
        # Chunk 0: start_time=0, segments keep original timestamps
        assert calls[0][0][0][0]["start"] == 1.0
        assert calls[0][0][0][0]["end"] == 5.0
        # Chunk 1: offset by 30
        assert calls[1][0][0][0]["start"] == 32.0
        assert calls[1][0][0][0]["end"] == 38.0
        # Chunk 2: offset by 60
        assert calls[2][0][0][0]["start"] == 60.0
        assert calls[2][0][0][0]["end"] == 65.0

    def test_ffmpeg_failure_emits_error(self):
        """Worker emits error if FFmpeg audio extraction fails."""
        worker = _make_worker_with_mocks()

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exits with failure immediately
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
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._pcm_size",
            return_value=0,  # file never grows
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ):
            worker.run("/fake/video.mp4")

        worker.error.emit.assert_called_once()
        assert "FFmpeg" in worker.error.emit.call_args[0][0]

    def test_progress_includes_eta(self):
        """Progress messages include an ETA once chunks complete."""
        worker = _make_worker_with_mocks()
        _run_worker_with_mocks(worker, total_duration=120.0)  # 4 chunks

        messages = [
            c[0][1]
            for c in worker.transcription_progress.emit.call_args_list
            if len(c[0]) >= 2 and isinstance(c[0][1], str)
        ]
        # At least one progress message should mention ETA after first chunk
        assert any("ETA" in m for m in messages), messages


class TestStreamingWorkerPriority:
    """Test request_priority() behavior."""

    def test_request_priority_sets_chunk_index(self):
        """request_priority sets the priority chunk index."""
        worker = StreamingTranscribeWorker()
        worker._completed_chunks = {0, 1}

        worker.request_priority(75.0)  # 75s → chunk 2
        assert worker._priority_chunk_index == 2

    def test_request_priority_ignores_completed_chunks(self):
        """request_priority does not set priority for already-completed chunks."""
        worker = StreamingTranscribeWorker()
        worker._completed_chunks = {0, 1, 2}

        worker.request_priority(15.0)  # chunk 0 already done
        assert worker._priority_chunk_index == -1

    def test_cancel_sets_flag(self):
        """cancel() sets the _cancelled flag."""
        worker = StreamingTranscribeWorker()
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True

    def test_priority_reorder_in_run(self):
        """Priority request reorders chunk processing when data is available."""
        worker = _make_worker_with_mocks()
        total_duration = 90.0  # 3 chunks

        chunk_segments = {
            i: [{"text": f"t{i}", "start": 0.0, "end": 5.0}]
            for i in range(3)
        }

        mock_model = MagicMock()
        mock_engine = MagicMock()
        mock_model.generate.return_value = object()

        chunk_process_order = []

        def fake_read_pcm(path, start_time, duration):
            chunk_idx = int(start_time // 30)
            chunk_process_order.append(chunk_idx)
            return _fake_audio()

        def fake_extract_segments(result):
            idx = chunk_process_order[-1]
            return chunk_segments.get(idx, [])

        mock_engine._extract_segments.side_effect = fake_extract_segments

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0

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
            return_value=mock_proc,
        ), patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._pcm_size",
            return_value=10**12,  # all data available → priority allowed
        ), patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._read_pcm_chunk",
            side_effect=fake_read_pcm,
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ), patch(
            "gui.workers.streaming_transcribe_worker.gc.collect",
        ):
            worker.run("/fake/video.mp4")

        # With priority=2 pre-set, order should be: 2 (priority), 0, 1
        assert chunk_process_order == [2, 0, 1]

    def test_priority_skipped_when_data_not_yet_extracted(self):
        """Priority chunk is NOT jumped to when its bytes aren't written yet."""
        worker = _make_worker_with_mocks()

        mock_model = MagicMock()
        mock_engine = MagicMock()
        mock_model.generate.return_value = object()
        mock_engine._extract_segments.return_value = []

        mock_proc = MagicMock()
        # ffmpeg finishes quickly; chunks beyond the available prefix are
        # read in "eof" mode (clamped reads, mocked anyway)
        mock_proc.poll.return_value = 0
        mock_proc.wait.return_value = 0
        mock_proc.returncode = 0

        chunk_process_order = []

        def fake_read_pcm(path, start_time, duration):
            chunk_process_order.append(int(start_time // 30))
            return _fake_audio()

        # Only chunk 0's data is available when the loop starts
        available = 30 * BYTES_PER_SECOND

        worker._priority_chunk_index = 2  # wants chunk 2, not yet extracted

        with patch(
            "gui.workers.streaming_transcribe_worker._get_audio_duration_ffprobe",
            return_value=90.0,
        ), patch(
            "gui.workers.streaming_transcribe_worker.load_funasr_model",
            return_value=mock_model,
        ), patch(
            "gui.workers.streaming_transcribe_worker.FunASREngine",
            return_value=mock_engine,
        ), patch(
            "gui.workers.streaming_transcribe_worker.subprocess.Popen",
            return_value=mock_proc,
        ), patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._pcm_size",
            return_value=available,
        ), patch(
            "gui.workers.streaming_transcribe_worker."
            "StreamingTranscribeWorker._read_pcm_chunk",
            side_effect=fake_read_pcm,
        ), patch(
            "gui.workers.streaming_transcribe_worker.os.unlink",
        ), patch(
            "gui.workers.streaming_transcribe_worker.gc.collect",
        ):
            worker.run("/fake/video.mp4")

        # Chunk 0 must come first; chunk 2 must not jump the queue
        assert chunk_process_order[0] == 0
        assert chunk_process_order == [0, 1, 2]


class TestPcmHelpers:
    """Unit tests for the raw-PCM read/wait helpers."""

    def test_read_pcm_chunk_reads_correct_range(self, tmp_path):
        """_read_pcm_chunk slices bytes at the right offset."""
        pcm = tmp_path / "test.pcm"
        # 3 seconds of 16kHz s16le: sample value = second index
        samples = np.concatenate([
            np.full(16000, 1, dtype=np.int16),
            np.full(16000, 2, dtype=np.int16),
            np.full(16000, 3, dtype=np.int16),
        ])
        pcm.write_bytes(samples.tobytes())

        chunk = StreamingTranscribeWorker._read_pcm_chunk(
            str(pcm), start_seconds=1.0, duration_seconds=1.0
        )
        assert chunk.dtype == np.float32
        assert chunk.size == 16000
        assert np.all(chunk == 2.0)

    def test_read_pcm_chunk_clamps_short_read(self, tmp_path):
        """Final chunk reads fewer bytes than requested without error."""
        pcm = tmp_path / "test.pcm"
        samples = np.full(16000, 7, dtype=np.int16)  # only 1s of data
        pcm.write_bytes(samples.tobytes())

        chunk = StreamingTranscribeWorker._read_pcm_chunk(
            str(pcm), start_seconds=0.0, duration_seconds=30.0
        )
        assert chunk.size == 16000  # clamped to available bytes

    def test_wait_for_data_ready(self, tmp_path):
        """_wait_for_data returns ready when file is big enough."""
        pcm = tmp_path / "test.pcm"
        pcm.write_bytes(b"\x00" * 100)
        worker = StreamingTranscribeWorker()
        proc = MagicMock()
        status, eof = worker._wait_for_data(str(pcm), 50, proc, False)
        assert status == "ready"
        assert eof is False

    def test_wait_for_data_failed(self, tmp_path):
        """_wait_for_data returns failed on non-zero ffmpeg exit."""
        pcm = tmp_path / "test.pcm"
        pcm.write_bytes(b"\x00" * 10)
        worker = StreamingTranscribeWorker()
        proc = MagicMock()
        proc.poll.return_value = 1
        status, eof = worker._wait_for_data(str(pcm), 10**6, proc, False)
        assert status == "failed"
        assert eof is True

    def test_wait_for_data_cancelled(self, tmp_path):
        """_wait_for_data returns cancelled when cancel flag is set."""
        pcm = tmp_path / "test.pcm"
        pcm.write_bytes(b"\x00" * 10)
        worker = StreamingTranscribeWorker()
        worker._cancelled = True
        proc = MagicMock()
        status, _ = worker._wait_for_data(str(pcm), 10**6, proc, False)
        assert status == "cancelled"

    def test_eta_string_empty_when_no_history(self):
        worker = StreamingTranscribeWorker()
        assert worker._eta_string(deque(), 5) == ""

    def test_eta_string_formats_seconds_and_minutes(self):
        assert StreamingTranscribeWorker._eta_string(
            deque([2.0, 2.0]), 5
        ) == ", ETA ~10s"
        assert StreamingTranscribeWorker._eta_string(
            deque([10.0]), 30
        ) == ", ETA ~5 min"


class TestStreamingWorkerDedup:
    """Test _deduplicate_segments() logic."""

    def test_no_existing_segments(self):
        worker = StreamingTranscribeWorker()
        worker._all_segments = []
        new_segs = [
            {"text": "a", "start": 0.0, "end": 5.0},
            {"text": "b", "start": 6.0, "end": 10.0},
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 2

    def test_overlapping_segment_skipped(self):
        worker = StreamingTranscribeWorker()
        worker._all_segments = [
            {"text": "prev", "start": 0.0, "end": 30.0},
        ]
        new_segs = [
            {"text": "overlap", "start": 29.0, "end": 35.0},
            {"text": "new", "start": 31.0, "end": 40.0},
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 1
        assert result[0]["text"] == "new"

    def test_non_overlapping_passes_through(self):
        worker = StreamingTranscribeWorker()
        worker._all_segments = [
            {"text": "prev", "start": 0.0, "end": 28.0},
        ]
        new_segs = [
            {"text": "next", "start": 30.0, "end": 40.0},
        ]
        result = worker._deduplicate_segments(new_segs)
        assert len(result) == 1
