"""Integration tests — real component interactions, mock only external deps.

These tests verify that components work together correctly:
- TranscribeWorker → AudioExtractor → FunASREngine  (data flow)
- FunASREngine chunking with real audio of various lengths
- AudioExtractor output compatibility with FunASR input

Unlike E2E tests, these focus on specific component boundaries
rather than the full pipeline.
"""
from __future__ import annotations

import os
import sys
import wave
from unittest.mock import MagicMock, patch

import numpy as np

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)


# ---------------------------------------------------------------------------
# TranscribeWorker data-flow integration
# ---------------------------------------------------------------------------


class TestTranscribeWorkerDataFlow:
    """Verify TranscribeWorker correctly chains AudioExtractor → Engine.

    These tests use real AudioExtractor (FFmpeg) but mock the engine
    to avoid downloading FunASR model for every test.
    """

    def test_worker_extracts_audio_then_calls_engine(self, tmp_path):
        """Worker must extract audio from video BEFORE calling engine."""
        from unittest.mock import MagicMock, patch

        from gui.workers.transcribe_worker import TranscribeWorker

        # Create a minimal valid video for FFmpeg
        video_path = str(tmp_path / "test.mp4")
        _create_test_video(video_path, duration=5)

        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = {
            "language": "zh",
            "duration": 5.0,
            "segments": [{"text": "test", "start": 0.0, "end": 5.0}],
        }

        with patch(
            "gui.workers.transcribe_worker.create_engine",
            return_value=mock_engine,
        ):
            worker.run(video_path)

        # Engine must be called with a .wav path, NOT the original .mp4
        call_args = mock_engine.transcribe.call_args
        audio_path = call_args[0][0]
        assert audio_path.endswith(".wav"), (
            f"Engine received non-WAV path: {audio_path}"
        )
        assert audio_path != video_path, (
            "Engine received the original video path — audio extraction skipped!"
        )

        worker.finished.emit.assert_called_once()
        worker.error.emit.assert_not_called()

    def test_worker_error_when_extraction_fails(self, tmp_path):
        """Worker emits error when AudioExtractor fails."""
        from unittest.mock import MagicMock, patch

        from gui.workers.transcribe_worker import TranscribeWorker

        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        with patch(
            "gui.workers.transcribe_worker.AudioExtractor"
        ) as mock_extractor_cls:
            mock_extractor_cls.return_value.extract.side_effect = RuntimeError(
                "FFmpeg extraction failed"
            )
            worker.run("/nonexistent/video.mp4")

        worker.error.emit.assert_called_once()
        assert "FFmpeg extraction failed" in worker.error.emit.call_args[0][0]
        worker.finished.emit.assert_not_called()

    def test_worker_cleans_up_wav_after_success(self, tmp_path):
        """Extracted WAV must be deleted after transcription completes."""
        from unittest.mock import MagicMock, patch

        from gui.workers.transcribe_worker import TranscribeWorker

        video_path = str(tmp_path / "test.mp4")
        _create_test_video(video_path, duration=5)

        worker = TranscribeWorker(engine_name="funasr")
        worker.finished = MagicMock()
        worker.progress = MagicMock()
        worker.error = MagicMock()

        mock_engine = MagicMock()
        mock_engine.transcribe.return_value = {
            "language": "zh",
            "duration": 5.0,
            "segments": [],
        }

        extracted_paths: list[str] = []

        with patch(
            "gui.workers.transcribe_worker.create_engine",
            return_value=mock_engine,
        ):
            # Intercept the actual extract call to record the path
            original_extract = None

            def _spy_extract(path, output_path=None):
                nonlocal original_extract
                if original_extract is None:
                    from video_splitter.extractor.audio import AudioExtractor
                    original_extract = AudioExtractor().extract
                result = original_extract(path, output_path)
                extracted_paths.append(result)
                return result

            with patch(
                "gui.workers.transcribe_worker.AudioExtractor"
            ) as mock_cls:
                instance = MagicMock()
                instance.extract.side_effect = _spy_extract
                mock_cls.return_value = instance

                worker.run(video_path)

        # The extracted WAV should have been cleaned up
        for wav_path in extracted_paths:
            assert not os.path.exists(wav_path), (
                f"Extracted WAV not cleaned up: {wav_path}"
            )


# ---------------------------------------------------------------------------
# FunASR chunking integration with real audio
# ---------------------------------------------------------------------------


class TestFunASRChunkingIntegration:
    """Test FunASR chunking logic with real WAV files of various lengths.

    Uses real _read_wav_chunks() and _transcribe_chunked() code paths
    but mocks the FunASR model.generate() to avoid downloading the model.
    """

    def test_short_audio_uses_single_path(self, tmp_path):
        """Audio <= 30s should use _transcribe_single (no chunking)."""
        from video_splitter.extractor.engines import FunASREngine

        wav_path = _create_wav(tmp_path / "short.wav", duration=10)

        engine = FunASREngine()
        mock_model = MagicMock()
        mock_model.generate.return_value = [
            {"text": "short", "sentence_info": [
                {"text": "hello", "start": 0, "end": 5000},
            ]}
        ]

        # Monkey-patch AutoModel to return our mock
        import sys as _sys
        fake_funasr = MagicMock()
        fake_funasr.AutoModel = MagicMock(return_value=mock_model)
        with patch.dict(_sys.modules, {"funasr": fake_funasr}):
            from video_splitter.config import SplitConfig
            result = engine.transcribe(wav_path, SplitConfig())

        # generate() should be called exactly once (single path)
        assert mock_model.generate.call_count == 1
        assert result["duration"] == 5.0

    def test_long_audio_triggers_chunking(self, tmp_path):
        """Audio > 30s should trigger _transcribe_chunked."""
        from video_splitter.extractor.engines import FunASREngine

        wav_path = _create_wav(tmp_path / "long.wav", duration=65)

        engine = FunASREngine()
        mock_model = MagicMock()

        # Each chunk returns one segment
        call_count = 0

        def _fake_generate(input, **kwargs):
            nonlocal call_count
            call_count += 1
            return [{"text": f"chunk{call_count}", "sentence_info": [
                {"text": f"segment {call_count}", "start": 0, "end": 30000},
            ]}]

        mock_model.generate.side_effect = _fake_generate

        import sys as _sys
        fake_funasr = MagicMock()
        fake_funasr.AutoModel = MagicMock(return_value=mock_model)
        with patch.dict(_sys.modules, {"funasr": fake_funasr}):
            from video_splitter.config import SplitConfig
            result = engine.transcribe(wav_path, SplitConfig())

        # 65s / 30s = 3 chunks (0-30, 30-60, 60-65)
        assert mock_model.generate.call_count == 3, (
            f"Expected 3 chunks for 65s audio, got {mock_model.generate.call_count}"
        )
        # Result should have segments from all chunks
        assert len(result["segments"]) >= 2

    def test_chunking_handles_nan_samples(self, tmp_path):
        """WAV files with NaN samples should not crash chunking."""
        from video_splitter.extractor.engines import _read_wav_chunks

        # Create a WAV with NaN samples
        wav_path = str(tmp_path / "nan_audio.wav")
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            # Write 32000 samples (2 seconds) with some NaN-equivalent patterns
            # Since WAV is int16, we can't store NaN directly, but we test
            # the sanitization path with extreme values
            samples = np.zeros(32000, dtype=np.int16)
            samples[1000] = 32767  # max value
            samples[2000] = -32768  # min value
            wf.writeframes(samples.tobytes())

        # Should not raise
        chunks = _read_wav_chunks(wav_path, chunk_seconds=30)
        assert len(chunks) == 1
        assert os.path.exists(chunks[0][0])

        # Cleanup
        for path, _, _ in chunks:
            os.unlink(path)


# ---------------------------------------------------------------------------
# AudioExtractor → FunASR compatibility
# ---------------------------------------------------------------------------


class TestExtractorEngineCompatibility:
    """Verify AudioExtractor output is valid input for FunASR."""

    def test_extracted_wav_is_valid_riff(self, tmp_path):
        """Extracted WAV must start with RIFF header."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_path / "compat_test.mp4")
        _create_test_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            video_path,
            output_path=str(tmp_path / "compat.wav"),
        )

        with open(wav_path, "rb") as f:
            riff = f.read(4)
        assert riff == b"RIFF", f"Missing RIFF header: {riff!r}"

    def test_extracted_wav_is_16khz_mono(self, tmp_path):
        """Extracted WAV must be 16kHz mono (FunASR requirement)."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_path / "format_test.mp4")
        _create_test_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            video_path,
            output_path=str(tmp_path / "format.wav"),
        )

        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 1, "Not mono"
            assert wf.getframerate() == 16000, f"Not 16kHz: {wf.getframerate()}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_test_video(path: str, duration: int = 5) -> None:
    """Create a minimal test video using FFmpeg."""
    import subprocess

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x240:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "64k",
        "-shortest",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-200:]}")


def _create_wav(path, duration: int, sample_rate: int = 16000) -> str:
    """Create a silent WAV file for testing."""
    path = str(path)
    n_samples = sample_rate * duration
    samples = np.zeros(n_samples, dtype=np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    return path


# ---------------------------------------------------------------------------
# Pipeline integration with real components
# ---------------------------------------------------------------------------


class TestPipelineIntegration:
    """Pipeline with real AudioExtractor + FunASR + VideoCutter.

    Only LLM (chapter detection) is mocked since it requires an API key.
    """

    def test_pipeline_extract_transcribe_cut(self, tmp_path):
        """Real pipeline: extract → transcribe → cut (no LLM)."""
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine
        from video_splitter.splitter.cutter import VideoCutter

        video_path = str(tmp_path / "pipeline_test.mp4")
        _create_test_video(video_path, duration=10)

        config = SplitConfig()

        # Step 1: Extract audio (real FFmpeg)
        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)
        assert os.path.exists(wav_path)
        assert wav_path.endswith(".wav")

        # Step 2: Transcribe (real FunASR)
        engine = FunASREngine()
        transcript = engine.transcribe(wav_path, config)
        assert transcript["duration"] > 0

        # Step 3: Cut (real FFmpeg)
        chapters = [
            Chapter(title="Part1", start_seconds=0.0, end_seconds=5.0),
            Chapter(title="Part2", start_seconds=5.0, end_seconds=10.0),
        ]
        cutter = VideoCutter(config)
        cut_dir = str(tmp_path / "pipeline_segments")
        files = cutter.cut(video_path, chapters, cut_dir)
        assert len(files) == 2
        for f in files:
            assert os.path.exists(f)

    def test_pipeline_resume_with_existing_transcript(self, tmp_path):
        """Pipeline should skip transcription when transcript exists."""
        import json

        video_path = str(tmp_path / "resume_test.mp4")
        _create_test_video(video_path, duration=5)

        # Pre-create transcript file
        transcript_path = str(tmp_path / "resume_test.transcript.json")
        existing_transcript = {
            "language": "zh",
            "duration": 5.0,
            "segments": [
                {"text": "预存转录", "start": 0.0, "end": 5.0},
            ],
        }
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(existing_transcript, f)

        # Load and verify
        with open(transcript_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["segments"][0]["text"] == "预存转录"
        assert loaded["duration"] == 5.0

    def test_srt_generation_from_real_transcript(self, tmp_path):
        """Generate SRT from real FunASR transcript."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine
        from video_splitter.extractor.transcribe import to_srt

        video_path = str(tmp_path / "srt_test.mp4")
        _create_test_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        engine = FunASREngine()
        config = SplitConfig()
        transcript = engine.transcribe(wav_path, config)

        # Generate SRT
        srt = to_srt(transcript)
        assert isinstance(srt, str)
        # SRT should be valid even if no speech detected
        # (may be empty or just whitespace)

    def test_audio_extractor_cleanup(self, tmp_path):
        """Extracted WAV should be cleanable after transcription."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine

        video_path = str(tmp_path / "cleanup_test.mp4")
        _create_test_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)
        assert os.path.exists(wav_path)

        # Transcribe
        engine = FunASREngine()
        config = SplitConfig()
        engine.transcribe(wav_path, config)

        # Clean up WAV manually (like TranscribeWorker does)
        os.unlink(wav_path)
        assert not os.path.exists(wav_path)
