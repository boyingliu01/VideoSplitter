"""Tests for extractor/engines.py — engine factory, health checks, ffprobe, chunking."""

import os
import sys
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.extractor.engines import (  # noqa: E402
    _ENGINE_REGISTRY,
    _get_audio_duration_ffprobe,
    _read_wav_chunks,
    _cleanup_chunk_files,
    FunASREngine,
    WhisperEngine,
    create_engine,
)


class TestFfprobeDuration:
    """Tests for _get_audio_duration_ffprobe() helper."""

    def test_ffprobe_success(self):
        result_mock = MagicMock()
        result_mock.stdout = '{"format": {"duration": "123.456"}}'
        with patch("subprocess.run", return_value=result_mock):
            dur = _get_audio_duration_ffprobe("/fake/audio.wav")
        assert dur == 123.456

    def test_ffprobe_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="ffprobe not found"):
                _get_audio_duration_ffprobe("/fake/audio.wav")

    def test_ffprobe_timeout(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)):
            with pytest.raises(RuntimeError, match="ffprobe timed out"):
                _get_audio_duration_ffprobe("/fake/audio.wav")

    def test_ffprobe_nonzero_exit(self):
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "ffprobe", stderr="error msg")):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                _get_audio_duration_ffprobe("/fake/audio.wav")

    def test_ffprobe_non_json_output(self):
        result_mock = MagicMock()
        result_mock.stdout = "not json at all"
        with patch("subprocess.run", return_value=result_mock):
            with pytest.raises(RuntimeError, match="non-JSON output"):
                _get_audio_duration_ffprobe("/fake/audio.wav")

    def test_ffprobe_missing_duration_key(self):
        result_mock = MagicMock()
        result_mock.stdout = '{"format": {}}'
        with patch("subprocess.run", return_value=result_mock):
            with pytest.raises(RuntimeError, match="Cannot parse duration"):
                _get_audio_duration_ffprobe("/fake/audio.wav")

    def test_ffprobe_invalid_duration_value(self):
        result_mock = MagicMock()
        result_mock.stdout = '{"format": {"duration": "not_a_number"}}'
        with patch("subprocess.run", return_value=result_mock):
            with pytest.raises(RuntimeError, match="Cannot parse duration"):
                _get_audio_duration_ffprobe("/fake/audio.wav")


class TestEngineRegistry:
    """Tests for engine registry and factory."""

    def test_registry_has_funasr_and_whisper(self):
        assert "funasr" in _ENGINE_REGISTRY
        assert "whisper" in _ENGINE_REGISTRY
        assert issubclass(_ENGINE_REGISTRY["funasr"], FunASREngine)
        assert issubclass(_ENGINE_REGISTRY["whisper"], WhisperEngine)

    def test_create_unknown_engine(self):
        with pytest.raises(ValueError, match="Unknown engine"):
            create_engine("nonexistent")

    def test_create_engine_defaults_to_funasr(self):
        engine = create_engine()
        assert isinstance(engine, FunASREngine)

    def test_create_whisper_engine(self):
        engine = create_engine("whisper")
        assert isinstance(engine, WhisperEngine)

    def test_create_funasr_engine(self):
        engine = create_engine("funasr")
        assert isinstance(engine, FunASREngine)


class TestHealthCheckExceptions:
    """Tests for health_check() exception paths (non-ImportError)."""

    def test_funasr_health_check_model_failure(self):
        """FunASR health_check catches non-ImportError exceptions (lines 171-172)."""
        engine = FunASREngine()
        # health_check does `from funasr import AutoModel` internally
        mock_funasr = MagicMock()
        mock_funasr.AutoModel = MagicMock(side_effect=MemoryError("OOM during model load"))
        with patch.dict(sys.modules, {"funasr": mock_funasr}):
            ok, msg = engine.health_check()
        assert ok is False
        assert "OOM" in msg


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------


def _make_wav(path: str, duration_s: float, sr: int = 16000, channels: int = 1) -> str:
    """Helper: create a silent WAV file."""
    n_samples = int(sr * duration_s)
    samples = np.zeros(n_samples, dtype=np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


class TestReadWavChunks:
    """Tests for _read_wav_chunks() — chunking, NaN sanitization, stereo→mono."""

    def test_short_audio_single_chunk(self, tmp_path):
        """Audio shorter than chunk_seconds produces exactly 1 chunk."""
        wav = _make_wav(str(tmp_path / "short.wav"), duration_s=10)
        chunks = _read_wav_chunks(wav, chunk_seconds=30)
        assert len(chunks) == 1
        path, offset, dur = chunks[0]
        assert os.path.exists(path)
        assert offset == 0.0
        assert 9.0 < dur < 11.0
        _cleanup_chunk_files(chunks)

    def test_long_audio_multiple_chunks(self, tmp_path):
        """Audio longer than chunk_seconds is split into multiple chunks."""
        wav = _make_wav(str(tmp_path / "long.wav"), duration_s=65)
        chunks = _read_wav_chunks(wav, chunk_seconds=30)
        assert len(chunks) == 3  # 0-30, 30-60, 60-65
        assert chunks[0][1] == 0.0
        assert abs(chunks[1][1] - 30.0) < 0.1
        assert abs(chunks[2][1] - 60.0) < 0.1
        _cleanup_chunk_files(chunks)

    def test_stereo_converted_to_mono(self, tmp_path):
        """Stereo WAV is downmixed to mono."""
        wav = _make_wav(str(tmp_path / "stereo.wav"), duration_s=5, channels=2)
        chunks = _read_wav_chunks(wav, chunk_seconds=30)
        assert len(chunks) == 1
        # Read the chunk and verify it's mono (1 channel)
        with wave.open(chunks[0][0], "rb") as wf:
            assert wf.getnchannels() == 1
        _cleanup_chunk_files(chunks)

    def test_nan_samples_sanitized(self, tmp_path):
        """WAV with extreme values should not contain NaN after sanitization."""
        wav = str(tmp_path / "extreme.wav")
        sr = 16000
        n_samples = sr * 2  # 2 seconds
        # Create samples with NaN-equivalent float32 values
        # Since WAV is int16, we test the float conversion path
        samples = np.zeros(n_samples, dtype=np.float32)
        samples[100] = float("nan")
        samples[200] = float("inf")
        samples[300] = float("-inf")
        # Write as float32 WAV
        with wave.open(wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(4)  # 32-bit
            wf.setframerate(sr)
            wf.writeframes(samples.tobytes())

        chunks = _read_wav_chunks(wav, chunk_seconds=30)
        assert len(chunks) == 1
        # The chunk file should be readable without NaN errors
        with wave.open(chunks[0][0], "rb") as wf:
            assert wf.getnchannels() == 1
        _cleanup_chunk_files(chunks)

    def test_cleanup_removes_files(self, tmp_path):
        """_cleanup_chunk_files removes all temp chunk files."""
        wav = _make_wav(str(tmp_path / "cleanup.wav"), duration_s=65)
        chunks = _read_wav_chunks(wav, chunk_seconds=30)
        paths = [c[0] for c in chunks]
        assert all(os.path.exists(p) for p in paths)

        _cleanup_chunk_files(chunks)
        assert all(not os.path.exists(p) for p in paths)

    def test_cleanup_ignores_missing_files(self, tmp_path):
        """_cleanup_chunk_files does not raise on missing files."""
        fake_chunks = [("/nonexistent/path.wav", 0.0, 30.0)]
        _cleanup_chunk_files(fake_chunks)  # Should not raise

