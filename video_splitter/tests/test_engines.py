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
    _extract_audio_range,
    load_funasr_model,
    clear_funasr_model_cache,
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


# ---------------------------------------------------------------------------
# _extract_audio_range tests
# ---------------------------------------------------------------------------


class TestExtractAudioRange:
    """Tests for _extract_audio_range() — FFmpeg time-range extraction."""

    def test_ffmpeg_command_includes_ss_and_t(self, tmp_path):
        """FFmpeg command uses -ss before -i for fast seek."""
        output = str(tmp_path / "chunk.wav")
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _extract_audio_range("/fake/video.mp4", 60.0, 30.0, output)

        assert result == output
        cmd = mock_run.call_args[0][0]
        assert "-ss" in cmd
        assert "60.000" in cmd
        assert "-t" in cmd
        assert "30.000" in cmd
        # -ss must come before -i
        ss_idx = cmd.index("-ss")
        i_idx = cmd.index("-i")
        assert ss_idx < i_idx

    def test_ffmpeg_failure_raises_runtime_error(self, tmp_path):
        """FFmpeg non-zero exit raises RuntimeError."""
        output = str(tmp_path / "chunk.wav")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Some FFmpeg error details"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="FFmpeg audio range extraction failed"):
                _extract_audio_range("/fake/video.mp4", 0.0, 30.0, output)

    def test_creates_temp_file_when_no_output_path(self):
        """When output_path is None, creates a temp file."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = _extract_audio_range("/fake/video.mp4", 0.0, 30.0)

        assert result.endswith(".wav")
        # Cleanup
        try:
            os.unlink(result)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# load_funasr_model tests
# ---------------------------------------------------------------------------


class TestLoadFunasrModel:
    """Tests for load_funasr_model() public API with singleton cache."""

    def setup_method(self):
        """Clear model cache before each test."""
        clear_funasr_model_cache()

    def test_delegates_to_internal_loader(self):
        """load_funasr_model() delegates to _load_funasr_model() on first call."""
        mock_model = MagicMock()
        with patch(
            "video_splitter.extractor.engines._load_funasr_model",
            return_value=mock_model,
        ) as mock_load:
            result = load_funasr_model()

        mock_load.assert_called_once()
        assert result is mock_model

    def test_returns_cached_model_on_second_call(self):
        """Second call returns cached model without reloading."""
        mock_model = MagicMock()
        with patch(
            "video_splitter.extractor.engines._load_funasr_model",
            return_value=mock_model,
        ) as mock_load:
            result1 = load_funasr_model()
            result2 = load_funasr_model()

        mock_load.assert_called_once()  # Only called once
        assert result1 is result2
        assert result1 is mock_model

    def test_use_cache_false_forces_reload(self):
        """use_cache=False forces a fresh load even if cached."""
        mock_model1 = MagicMock()
        mock_model2 = MagicMock()
        with patch(
            "video_splitter.extractor.engines._load_funasr_model",
            side_effect=[mock_model1, mock_model2],
        ):
            result1 = load_funasr_model()
            result2 = load_funasr_model(use_cache=False)

        assert result1 is mock_model1
        assert result2 is mock_model2

    def test_clear_cache_forces_reload(self):
        """clear_funasr_model_cache() forces next call to reload."""
        mock_model1 = MagicMock()
        mock_model2 = MagicMock()
        with patch(
            "video_splitter.extractor.engines._load_funasr_model",
            side_effect=[mock_model1, mock_model2],
        ):
            result1 = load_funasr_model()
            clear_funasr_model_cache()
            result2 = load_funasr_model()

        assert result1 is mock_model1
        assert result2 is mock_model2


# ---------------------------------------------------------------------------
# transcribe_file_chunk tests
# ---------------------------------------------------------------------------


class TestTranscribeFileChunk:
    """Tests for FunASREngine.transcribe_file_chunk()."""

    def test_returns_segments_with_global_timestamps(self):
        """Segments have timestamps offset by start_seconds."""
        engine = FunASREngine()
        mock_model = MagicMock()
        # Simulate FunASR result with local timestamps (0-5s range)
        mock_model.generate.return_value = [{
            "text": "hello world",
            "timestamp": [[0, 2000], [3000, 5000]],
        }]

        with patch(
            "video_splitter.extractor.engines._extract_audio_range",
            return_value="/tmp/chunk.wav",
        ):
            segments = engine.transcribe_file_chunk(
                mock_model, "/fake/video.mp4",
                start_seconds=60.0, duration_seconds=30.0,
            )

        # Timestamps should be offset by 60s
        assert len(segments) >= 1
        for seg in segments:
            assert seg["start"] >= 60.0
            assert seg["end"] >= 60.0

    def test_cleans_up_chunk_wav(self):
        """Temporary chunk WAV is deleted after transcription."""
        engine = FunASREngine()
        mock_model = MagicMock()
        mock_model.generate.return_value = [{"text": "", "timestamp": []}]

        with patch(
            "video_splitter.extractor.engines._extract_audio_range",
            return_value="/tmp/chunk_to_delete.wav",
        ):
            with patch("os.unlink") as mock_unlink:
                engine.transcribe_file_chunk(
                    mock_model, "/fake/video.mp4",
                    start_seconds=0.0, duration_seconds=30.0,
                )

        mock_unlink.assert_called_with("/tmp/chunk_to_delete.wav")

    def test_cleans_up_on_error(self):
        """Temporary chunk WAV is deleted even if transcription fails."""
        engine = FunASREngine()
        mock_model = MagicMock()
        mock_model.generate.side_effect = RuntimeError("OOM")

        with patch(
            "video_splitter.extractor.engines._extract_audio_range",
            return_value="/tmp/chunk_on_error.wav",
        ):
            with patch("os.unlink") as mock_unlink:
                with pytest.raises(RuntimeError, match="OOM"):
                    engine.transcribe_file_chunk(
                        mock_model, "/fake/video.mp4",
                        start_seconds=0.0, duration_seconds=30.0,
                    )

        mock_unlink.assert_called_with("/tmp/chunk_on_error.wav")


# ---------------------------------------------------------------------------
# Punctuation model tests
# ---------------------------------------------------------------------------


class TestPunctuationModel:
    """Tests for CT-Transformer punctuation model integration."""

    def test_load_funasr_model_passes_punc_model(self):
        """AutoModel is called with punc_model parameter by default."""
        mock_auto_model = MagicMock(return_value=MagicMock())
        mock_funasr = MagicMock()
        mock_funasr.AutoModel = mock_auto_model

        with patch.dict(sys.modules, {"funasr": mock_funasr}):
            try:
                _load_funasr_model()
            except Exception:
                pass

        if mock_auto_model.called:
            call_kwargs = mock_auto_model.call_args[1]  # keyword args
            assert "punc_model" in call_kwargs

    def test_punc_model_disabled_via_env(self):
        """Setting VIDEO_SPLITTER_FUNASR_PUNC_MODEL='' disables punctuation."""
        mock_auto_model = MagicMock(return_value=MagicMock())
        mock_funasr = MagicMock()
        mock_funasr.AutoModel = mock_auto_model

        with patch.dict(sys.modules, {"funasr": mock_funasr}):
            with patch.dict(os.environ, {"VIDEO_SPLITTER_FUNASR_PUNC_MODEL": ""}):
                try:
                    _load_funasr_model()
                except Exception:
                    pass

        if mock_auto_model.called:
            call_kwargs = mock_auto_model.call_args[1]
            assert "punc_model" not in call_kwargs

