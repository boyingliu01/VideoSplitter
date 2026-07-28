"""Streaming/incremental ASR transcription worker for GUI.

True streaming pipeline:
1. ffprobe gets the video duration.
2. FFmpeg extracts audio to a raw PCM s16le file (16 kHz mono) on disk,
   with ``-nostats -v error`` so stderr stays tiny (avoids the classic
   pipe-buffer deadlock when a long video fills the 64 KB stderr pipe).
3. Transcription starts as soon as the first chunk's PCM bytes have been
   written — there is no wait for full extraction.  Chunks are sliced in
   memory (numpy) and fed directly to ``model.generate()``.
4. Priority seek is honoured for regions that FFmpeg has already written.

Compared with the previous design this eliminates:
- the 1-3 minute "extracting audio" wait before the first subtitle;
- N per-chunk FFmpeg process spawns and N temporary WAV files;
- the stderr pipe deadlock on long videos.
"""

from __future__ import annotations

import gc
import logging
import math
import os
import subprocess
import tempfile
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
from video_splitter.extractor.engines import (
    FUNASR_CHUNK_SECONDS,
    FunASREngine,
    _get_audio_duration_ffprobe,
    load_funasr_model,
)

logger = logging.getLogger(__name__)

# Raw PCM layout produced by FFmpeg: 16 kHz, mono, s16le.
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2
BYTES_PER_SECOND = SAMPLE_RATE * BYTES_PER_SAMPLE  # 32000

# How often to poll the growing PCM file while waiting for data.
_EXTRACT_POLL_INTERVAL = 0.2


class StreamingTranscribeWorker(QObject):
    """Incremental ASR transcription worker running in a background QThread.

    Transcribes video audio in chunks, emitting segments as each chunk
    completes.  Audio is extracted once by a single FFmpeg process into a
    raw PCM file; chunks are sliced from that file in memory as soon as
    the bytes are available (read-while-write streaming).

    Signals:
        model_loading_progress: (str) human-readable status
        audio_ready: (float) total video duration in seconds
        segments_ready: (list) new segments from a completed chunk
        chunk_completed: (completed_count, total_count)
        transcription_complete: (dict) full transcript when all done
        transcription_progress: (0.0-1.0, description) — negative frac = indeterminate
        error: (str)
        cancelled: ()
    """

    # Signals
    model_loading_progress = Signal(str)
    audio_ready = Signal(float)
    segments_ready = Signal(list)
    chunk_completed = Signal(int, int)
    transcription_complete = Signal(dict)
    transcription_progress = Signal(float, str)
    error = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        engine_name: str = "funasr",
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
        hotword: str = "",
    ) -> None:
        super().__init__(parent)
        self._engine_name = engine_name
        self._config = config if config is not None else SplitConfig()
        self._chunk_seconds: int = FUNASR_CHUNK_SECONDS
        self._hotword = hotword  # Space-separated hotword string for ASR enhancement
        self._hotword_lock = threading.Lock()

        # State (only accessed from worker thread, except priority/cancel)
        self._priority_chunk_index: int = -1  # -1 = no priority request
        self._cancelled: bool = False
        self._completed_chunks: Set[int] = set()
        self._all_segments: List[Dict[str, Any]] = []

    @Slot(str)
    def run(self, video_path: str) -> None:
        """Main entry point — called from QThread."""
        try:
            self._run_impl(video_path)
        except Exception as exc:
            logger.exception("Streaming transcription failed")
            self.error.emit(str(exc))

    # -- pipeline -----------------------------------------------------------

    def _run_impl(self, video_path: str) -> None:
        # Phase 1: duration probe
        self.transcription_progress.emit(0.0, "Step 1/3: Preparing...")
        self.model_loading_progress.emit("Getting video duration...")

        try:
            total_duration = _get_audio_duration_ffprobe(video_path)
        except Exception as exc:
            self.error.emit(f"Cannot get video duration: {exc}")
            return

        if total_duration <= 0:
            self.error.emit("Video duration is 0 or invalid")
            return

        self.audio_ready.emit(total_duration)

        # Phase 2: start FFmpeg extraction (raw PCM, quiet stderr).
        # -nostats -v error keeps stderr well below the pipe buffer, so
        # waiting on the process can never deadlock on a full pipe.
        self.model_loading_progress.emit("Extracting audio...")
        self.transcription_progress.emit(0.02, "Step 1/3: Extracting audio...")

        tmp_pcm = tempfile.NamedTemporaryFile(suffix=".pcm", delete=False)
        tmp_pcm_path = tmp_pcm.name
        tmp_pcm.close()

        ffmpeg_cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE), "-ac", "1",
            "-nostats", "-v", "error",
            "-f", "s16le", tmp_pcm_path,
        ]
        ffmpeg_proc = subprocess.Popen(
            ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

        try:
            # Phase 3: load the model while FFmpeg extracts (parallel).
            self.model_loading_progress.emit("Loading speech recognition model...")
            self._configure_torch_threads()
            model = load_funasr_model(use_cache=True)
            self.model_loading_progress.emit("Model loaded successfully")

            # Phase 4: transcribe chunks as their PCM data becomes available.
            self.transcription_progress.emit(
                0.08, "Step 2/3: Starting streaming transcription..."
            )
            self._transcribe_loop(ffmpeg_proc, tmp_pcm_path, total_duration, model)

        finally:
            # Reap ffmpeg and clean up the PCM file.
            try:
                if ffmpeg_proc.poll() is None:
                    ffmpeg_proc.wait(timeout=120)
            except Exception:
                pass
            try:
                os.unlink(tmp_pcm_path)
            except OSError:
                pass

    def _transcribe_loop(
        self,
        ffmpeg_proc: subprocess.Popen,
        pcm_path: str,
        total_duration: float,
        model: Any,
    ) -> None:
        """Transcribe chunks in order, reading PCM as FFmpeg writes it."""
        n_chunks = max(1, math.ceil(total_duration / self._chunk_seconds))
        logger.info(
            "Streaming transcription: %.0fs video -> %d chunks of %ds",
            total_duration, n_chunks, self._chunk_seconds,
        )

        chunk_queue: Deque[int] = deque(range(n_chunks))
        engine = FunASREngine()
        inference_times: Deque[float] = deque(maxlen=5)
        chunks_since_gc = 0
        ffmpeg_eof = False

        while chunk_queue:
            if self._cancelled:
                logger.info("Streaming transcription cancelled")
                self.cancelled.emit()
                return

            # Priority handling: only jump the queue if the requested
            # region has already been extracted (cannot read the future).
            # The request stays pending until honoured (or fulfilled by
            # normal in-order processing).
            if self._priority_chunk_index >= 0:
                p_idx = self._priority_chunk_index
                if p_idx not in chunk_queue:
                    # Already processed in normal order — fulfilled.
                    self._priority_chunk_index = -1
                else:
                    p_end = min(
                        (p_idx + 1) * self._chunk_seconds, total_duration
                    )
                    if ffmpeg_eof or self._pcm_size(pcm_path) >= int(
                        p_end * BYTES_PER_SECOND
                    ):
                        chunk_queue.remove(p_idx)
                        chunk_queue.appendleft(p_idx)
                        self._priority_chunk_index = -1
                        self.transcription_progress.emit(
                            -1.0, "Priority: transcribing requested position..."
                        )

            chunk_idx = chunk_queue.popleft()
            start_time = chunk_idx * self._chunk_seconds
            duration = min(self._chunk_seconds, total_duration - start_time)
            needed_bytes = int((start_time + duration) * BYTES_PER_SECOND)

            # Wait until this chunk's PCM bytes are on disk.
            if chunk_idx == 0 and not ffmpeg_eof:
                self.transcription_progress.emit(
                    -1.0, "Step 2/3: Extracting first audio segment..."
                )
            status, ffmpeg_eof = self._wait_for_data(
                pcm_path, needed_bytes, ffmpeg_proc, ffmpeg_eof
            )
            if status == "cancelled":
                self.cancelled.emit()
                return
            if status == "failed":
                self.error.emit(self._ffmpeg_error_message(ffmpeg_proc))
                return

            # Slice the chunk from the PCM file (in-memory, no ffmpeg spawn).
            audio = self._read_pcm_chunk(pcm_path, start_time, duration)
            if audio.size == 0:
                logger.warning("Chunk %d: no PCM data available, skipped", chunk_idx)
                self._completed_chunks.add(chunk_idx)
                continue

            # Inference.
            done = len(self._completed_chunks)
            frac = 0.1 + 0.85 * (done / n_chunks)
            eta_str = self._eta_string(inference_times, n_chunks - done)
            self.transcription_progress.emit(
                frac, f"Step 3/3: Recognizing {done + 1}/{n_chunks}{eta_str}..."
            )

            t0 = time.monotonic()
            result = None
            try:
                generate_kwargs: dict = {"input": audio}
                with self._hotword_lock:
                    current_hotword = self._hotword
                if current_hotword:
                    generate_kwargs["hotword"] = current_hotword

                result = model.generate(**generate_kwargs)
                new_segments = engine._extract_segments(result)

                for seg in new_segments:
                    seg["start"] = round(seg["start"] + start_time, 2)
                    seg["end"] = round(seg["end"] + start_time, 2)

                deduped = self._deduplicate_segments(new_segments)
                self._all_segments.extend(deduped)

                if deduped:
                    self.segments_ready.emit(deduped)

            except Exception as exc:
                logger.warning("Failed to transcribe chunk %d: %s", chunk_idx, exc)
            finally:
                inference_times.append(time.monotonic() - t0)
                del audio, result

            self._completed_chunks.add(chunk_idx)
            self.chunk_completed.emit(len(self._completed_chunks), n_chunks)

            chunks_since_gc += 1
            if chunks_since_gc >= 10:
                gc.collect()
                chunks_since_gc = 0

        # All chunks processed.  A non-zero ffmpeg exit at this point means
        # the tail of the audio may be missing — warn but keep the results.
        ret = ffmpeg_proc.poll()
        if ret is None:
            try:
                ret = ffmpeg_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                ret = -1
        if ret not in (0, None):
            logger.warning(
                "FFmpeg exited with code %s after all chunks were transcribed", ret
            )

        # Phase 5: complete
        self.transcription_progress.emit(1.0, "Transcription complete")
        transcript = {
            "language": "zh",
            "duration": total_duration,
            "segments": self._all_segments,
        }
        self.transcription_complete.emit(transcript)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _configure_torch_threads() -> None:
        """Use all CPU cores for torch CPU inference.

        PyTorch defaults to cores/2 on many builds; ASR encoder inference
        scales with threads up to the physical core count.  Override via
        VIDEO_SPLITTER_TORCH_THREADS.
        """
        try:
            import torch

            default = str(os.cpu_count() or 4)
            n = int(os.environ.get("VIDEO_SPLITTER_TORCH_THREADS", default))
            n = max(1, n)
            if torch.get_num_threads() != n:
                torch.set_num_threads(n)
                logger.info("torch num_threads set to %d", n)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Could not configure torch threads: %s", exc)

    @staticmethod
    def _pcm_size(path: str) -> int:
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    def _wait_for_data(
        self,
        pcm_path: str,
        needed_bytes: int,
        proc: subprocess.Popen,
        already_eof: bool,
    ) -> tuple[str, bool]:
        """Block until the PCM file covers ``needed_bytes``.

        Args:
            pcm_path: Path to the growing raw PCM file.
            needed_bytes: Byte count required for the next chunk.
            proc: The running FFmpeg process.
            already_eof: True once FFmpeg has exited successfully.

        Returns:
            ``(status, eof)`` where status is one of ``"ready"`` (full data
            available), ``"eof"`` (FFmpeg finished; read what exists),
            ``"failed"`` (FFmpeg exited non-zero), or ``"cancelled"``.
        """
        while True:
            if self._cancelled:
                return "cancelled", already_eof
            if self._pcm_size(pcm_path) >= needed_bytes:
                return "ready", already_eof
            if already_eof:
                return "eof", True
            ret = proc.poll()
            if ret is not None:
                if ret != 0:
                    return "failed", True
                return "eof", True
            time.sleep(_EXTRACT_POLL_INTERVAL)

    @staticmethod
    def _read_pcm_chunk(path: str, start_seconds: float, duration_seconds: float):
        """Read a time range from the raw PCM file as a float32 numpy array.

        Args:
            path: Raw s16le 16 kHz mono PCM file.
            start_seconds: Chunk start offset in seconds.
            duration_seconds: Chunk duration in seconds.

        Returns:
            numpy float32 array (values are raw int16 magnitudes, matching
            what FunASR expects for numpy input).  Short reads are clamped
            to the bytes actually available (final chunk).
        """
        import numpy as np

        byte_start = int(start_seconds * BYTES_PER_SECOND)
        byte_count = int(duration_seconds * BYTES_PER_SECOND)
        with open(path, "rb") as f:
            f.seek(byte_start)
            data = f.read(byte_count)
        # s16le needs an even byte count
        data = data[: len(data) - (len(data) % BYTES_PER_SAMPLE)]
        return np.frombuffer(data, dtype=np.int16).astype(np.float32)

    @staticmethod
    def _eta_string(inference_times: Deque[float], remaining_chunks: int) -> str:
        """Format an ETA string from recent per-chunk inference times."""
        if not inference_times or remaining_chunks <= 0:
            return ""
        avg = sum(inference_times) / len(inference_times)
        eta = avg * remaining_chunks
        if eta >= 90:
            return f", ETA ~{eta / 60:.0f} min"
        return f", ETA ~{eta:.0f}s"

    def _ffmpeg_error_message(self, proc: subprocess.Popen) -> str:
        """Build an error message from a failed FFmpeg process."""
        try:
            stderr_text = (
                proc.stderr.read().decode(errors="replace")[-500:]
                if proc.stderr is not None
                else ""
            )
        except Exception:
            stderr_text = ""
        return f"FFmpeg audio extraction failed (code {proc.returncode}): {stderr_text}"

    def _deduplicate_segments(
        self, new_segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove segments that overlap with existing ones.

        Strategy: skip new segments whose start overlaps with the tail of
        the last existing segment (< 0.5s gap).
        """
        if not self._all_segments:
            return new_segments

        last_end = self._all_segments[-1]["end"]
        deduped: List[Dict[str, Any]] = []

        for seg in new_segments:
            if seg["start"] < last_end - 0.5:
                continue
            deduped.append(seg)

        return deduped

    @Slot(float)
    def request_priority(self, time_seconds: float) -> None:
        """Request priority transcription for the chunk containing time_seconds.

        Thread-safe: called from GUI thread while run() executes in worker thread.
        Safe because int assignment is atomic under CPython GIL.
        Only takes effect if the region is already extracted (checked in loop).
        """
        target_chunk = int(time_seconds / self._chunk_seconds)
        if target_chunk not in self._completed_chunks:
            self._priority_chunk_index = target_chunk

    @Slot()
    def cancel(self) -> None:
        """Request cancellation. Checked at chunk boundaries and while
        waiting for extraction.

        Thread-safe: bool assignment is atomic under CPython GIL.
        """
        self._cancelled = True

    @Slot(str)
    def set_hotword(self, hotword: str) -> None:
        """Update the hotword mid-transcription (thread-safe).

        Callable from the GUI thread while ``_transcribe_loop`` runs in a
        worker thread.  A ``threading.Lock`` guards the read/write, which is
        correct and light under CPython's GIL for a plain string assignment.
        """
        with self._hotword_lock:
            self._hotword = hotword
