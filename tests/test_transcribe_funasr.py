"""Unit tests for extractor/engines.py — FunASR, Whisper, and factory."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from video_splitter.config import SplitConfig
from video_splitter.extractor.engines import (
    FUNASR_MODEL,
    FunASREngine,
    WhisperEngine,
    create_engine,
    _ENGINE_REGISTRY,
)


class TestCreateEngine:
    """Factory: create_engine()."""

    def test_default_is_funasr(self):
        """create_engine() defaults to FunASREngine."""
        engine = create_engine()
        assert isinstance(engine, FunASREngine)

    def test_create_whisper_engine(self):
        """create_engine('whisper') returns WhisperEngine."""
        engine = create_engine("whisper")
        assert isinstance(engine, WhisperEngine)

    def test_create_funasr_engine(self):
        """create_engine('funasr') returns FunASREngine."""
        engine = create_engine("funasr")
        assert isinstance(engine, FunASREngine)

    def test_unknown_engine_raises(self):
        """create_engine with unknown name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown engine"):
            create_engine("nonexistent_engine")

    def test_registry_contains_both(self):
        """_ENGINE_REGISTRY has both funasr and whisper."""
        assert "funasr" in _ENGINE_REGISTRY
        assert "whisper" in _ENGINE_REGISTRY
        assert _ENGINE_REGISTRY["funasr"] is FunASREngine
        assert _ENGINE_REGISTRY["whisper"] is WhisperEngine


class TestFunASROutputMapping:
    """FunASR transcribe() — ms→seconds, fallback, edge cases."""

    def test_ms_to_seconds_conversion(self):
        """FunASR returns ms — converted to seconds with rount( , 2)."""
        engine = FunASREngine()
        sentence_info = [
            {"text": "你好世界", "start": 0, "end": 1500},
            {"text": "测试文本", "start": 2000, "end": 4500},
        ]
        fake_result: list[dict] = [{"text": "你好世界测试文本", "sentence_info": sentence_info}]

        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            transcript = engine.transcribe("dummy.wav", SplitConfig())

        segments = transcript["segments"]
        assert len(segments) == 2
        assert segments[0] == {"text": "你好世界", "start": 0.0, "end": 1.5}
        assert segments[1] == {"text": "测试文本", "start": 2.0, "end": 4.5}
        assert transcript["language"] == "zh"
        assert transcript["duration"] == 4.5

    def test_sentence_info_none_falls_back_to_text_format(self):
        """sentence_info=None → falls through to text+timestamp format."""
        engine = FunASREngine()
        fake_result = [{"text": "完整文本", "sentence_info": None}]
        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            with patch(
                "video_splitter.extractor.engines._get_audio_duration_ffprobe",
                return_value=10.5,
            ) as mock_dur:
                transcript = engine.transcribe("dummy.wav", SplitConfig())

        assert transcript["duration"] == 10.5
        # New behavior: text without timestamps returns as single segment
        assert len(transcript["segments"]) == 1
        assert transcript["segments"][0]["text"] == "完整文本"
        mock_dur.assert_called_once_with("dummy.wav")

    def test_sentence_info_empty_list_falls_back_to_text_format(self):
        """sentence_info=[] → falls through to text+timestamp format."""
        engine = FunASREngine()
        fake_result = [{"text": "文本", "sentence_info": []}]
        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            with patch(
                "video_splitter.extractor.engines._get_audio_duration_ffprobe",
                return_value=8.0,
            ):
                transcript = engine.transcribe("dummy.wav", SplitConfig())

        assert transcript["duration"] == 8.0
        # New behavior: text without timestamps returns as single segment
        assert len(transcript["segments"]) == 1
        assert transcript["segments"][0]["text"] == "文本"

    def test_segments_with_empty_text_are_skipped(self):
        """Segments with empty text are filtered out of result."""
        engine = FunASREngine()
        sentence_info = [
            {"text": "第一句", "start": 0, "end": 1000},
            {"text": "", "start": 1000, "end": 2000},
            {"text": "第三句", "start": 2000, "end": 3000},
        ]
        fake_result = [{"text": "", "sentence_info": sentence_info}]
        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            transcript = engine.transcribe("dummy.wav", SplitConfig())

        segments = transcript["segments"]
        assert len(segments) == 2
        assert segments[0]["text"] == "第一句"
        assert segments[1]["text"] == "第三句"

    def test_empty_result_list(self):
        """Empty result list → no segments, ffprobe fallback."""
        engine = FunASREngine()
        fake_result: list[dict] = []
        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            with patch(
                "video_splitter.extractor.engines._get_audio_duration_ffprobe",
                return_value=3.0,
            ):
                transcript = engine.transcribe("dummy.wav", SplitConfig())

        assert transcript["segments"] == []
        assert transcript["duration"] == 3.0

    def test_progress_callback_called(self):
        """Progress callback receives expected stage calls."""
        engine = FunASREngine()
        sentence_info = [{"text": "测试", "start": 0, "end": 1000}]
        fake_result = [{"text": "测试", "sentence_info": sentence_info}]
        mock_model = MagicMock()
        mock_model.generate.return_value = fake_result
        cb = MagicMock()

        with patch.dict(sys.modules, {"funasr": MagicMock(AutoModel=MagicMock(return_value=mock_model))}):
            engine.transcribe("dummy.wav", SplitConfig(), progress_callback=cb)

        assert cb.call_count >= 3
        call_args = [(args[0], args[1]) for args, _ in cb.call_args_list]
        assert (0.0, "Loading FunASR model...") in call_args
        assert (1.0, "Done") in call_args


class TestHealthCheck:
    """Health check tests for both engines."""

    def test_health_check_funasr_ok(self):
        """FunASREngine.health_check returns (True, 'ok') when deps available."""
        mock_model = MagicMock()
        mock_model.generate.return_value = None

        fake_funasr = MagicMock()
        fake_funasr.AutoModel = MagicMock(return_value=mock_model)

        with patch.dict(sys.modules, {"funasr": fake_funasr, "numpy": MagicMock()}):
            engine = FunASREngine()
            ok, msg = engine.health_check()

        assert ok is True
        assert msg == "ok"
        fake_funasr.AutoModel.assert_called_once_with(model=FUNASR_MODEL)
        mock_model.generate.assert_called_once()

    def test_health_check_funasr_import_error(self):
        """FunASREngine.health_check returns (False, ...) when funasr missing."""
        engine = FunASREngine()

        orig = __import__
        def _mock_import(name, *args, **kwargs):
            if name == "funasr":
                raise ImportError("No module named 'funasr'")
            return orig(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            ok, msg = engine.health_check()
            assert ok is False
            assert "not installed" in msg.lower() or "download" in msg.lower()

    def test_health_check_whisper_ok(self):
        """WhisperEngine.health_check returns (True, 'ok') when faster_whisper importable."""
        with patch.dict(sys.modules, {"faster_whisper": MagicMock(WhisperModel=MagicMock())}):
            engine = WhisperEngine()
            ok, msg = engine.health_check()

        assert ok is True
        assert msg == "ok"

    def test_health_check_whisper_import_error(self):
        """WhisperEngine.health_check returns (False, ...) when faster_whisper missing."""
        engine = WhisperEngine()

        orig = __import__
        def _mock_import(name, *args, **kwargs):
            if name == "faster_whisper":
                raise ImportError("No module named 'faster_whisper'")
            return orig(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_mock_import):
            ok, msg = engine.health_check()
            assert ok is False
            assert "not installed" in msg


class TestWhisperEngine:
    """Test WhisperEngine wrapper."""

    def test_transcribe_delegates_to_module(self):
        """WhisperEngine.transcribe returns {language, duration, segments}."""
        expected: dict = {
            "language": "en",
            "duration": 60.0,
            "segments": [{"text": "hello", "start": 0.0, "end": 2.0}],
        }

        with patch(
            "video_splitter.extractor.transcribe.transcribe",
            return_value=expected,
        ) as mock_transcribe:
            engine = WhisperEngine()
            result = engine.transcribe("test.wav", SplitConfig())

        assert result == expected
        mock_transcribe.assert_called_once()

    def test_progress_callback_forwarded(self):
        """Progress callback forwarded to underlying transcribe."""
        cb = MagicMock()
        expected = {
            "language": "en",
            "duration": 30.0,
            "segments": [{"text": "test", "start": 0.0, "end": 1.0}],
        }

        with patch(
            "video_splitter.extractor.transcribe.transcribe",
            return_value=expected,
        ):
            engine = WhisperEngine()
            result = engine.transcribe("test.wav", SplitConfig(), progress_callback=cb)

        assert result["duration"] == 30.0
        cb.assert_called()
