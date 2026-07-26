"""End-to-end tests using real project test data.

Test data:
  测试数据/质量红线讲解.mp4          — 50-min training video
  测试数据/质量红线讲解.transcript.json — existing transcript (101 segments)
  测试数据/QIWC 02.006.4-2024....docx — hotword document

Strategy:
  - Real FFmpeg for audio extraction
  - Real FunASR for transcription (or resume from existing transcript)
  - Mocked LLM for chapter detection (external API dependency)
  - Validates full pipeline output structure

Run with:  pytest tests/test_e2e_real_data.py -v
Skip with: pytest tests/ -v --ignore=tests/test_e2e_real_data.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# ---------------------------------------------------------------------------
# Test data paths
# ---------------------------------------------------------------------------

_TEST_DATA_DIR = os.path.join(_PROJ_ROOT, "测试数据")
_TEST_VIDEO = os.path.join(_TEST_DATA_DIR, "质量红线讲解.mp4")
_TEST_TRANSCRIPT = os.path.join(_TEST_DATA_DIR, "质量红线讲解.transcript.json")
_HOTWORD_DOC = os.path.join(
    _TEST_DATA_DIR,
    "QIWC 02.006.4-2024浩鲸科技研发交付质量红线管理规定（20241014）.docx",
)


@pytest.fixture(scope="module")
def test_video() -> str:
    """Path to the real test video. Skip if missing."""
    if not os.path.exists(_TEST_VIDEO):
        pytest.skip(f"Test video not found: {_TEST_VIDEO}")
    return _TEST_VIDEO


@pytest.fixture(scope="module")
def test_transcript() -> dict:
    """Load the existing transcript JSON."""
    if not os.path.exists(_TEST_TRANSCRIPT):
        pytest.skip(f"Test transcript not found: {_TEST_TRANSCRIPT}")
    with open(_TEST_TRANSCRIPT, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def hotword_doc() -> str:
    """Path to the hotword docx file. Skip if missing."""
    if not os.path.exists(_HOTWORD_DOC):
        pytest.skip(f"Hotword doc not found: {_HOTWORD_DOC}")
    return _HOTWORD_DOC


def _mock_llm_response(num_chapters: int = 5, duration: float = 3023.0) -> str:
    """Generate a valid LLM JSON response for chapter detection."""
    chapter_duration = duration / num_chapters
    chapters = []
    for i in range(num_chapters):
        start_sec = i * chapter_duration
        end_sec = (i + 1) * chapter_duration
        start_ts = f"{int(start_sec // 3600):02d}:{int((start_sec % 3600) // 60):02d}:{int(start_sec % 60):02d}"
        end_ts = f"{int(end_sec // 3600):02d}:{int((end_sec % 3600) // 60):02d}:{int(end_sec % 60):02d}"
        chapters.append({
            "title": f"{i+1:02d}_章节{i+1}",
            "start": start_ts,
            "end": end_ts,
        })
    return json.dumps(chapters, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Layer 1: Audio Extraction (real FFmpeg)
# ---------------------------------------------------------------------------


class TestAudioExtraction:
    """Real FFmpeg audio extraction from the project test video."""

    def test_extract_produces_wav(self, test_video, tmp_path):
        from video_splitter.extractor.audio import AudioExtractor

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_path / "extracted.wav"),
        )

        assert os.path.exists(wav_path)
        assert wav_path.endswith(".wav")
        assert os.path.getsize(wav_path) > 0

    def test_extracted_audio_duration_matches_video(self, test_video, tmp_path):
        """Extracted audio duration should be close to video duration (~3023s)."""
        import subprocess

        from video_splitter.extractor.audio import AudioExtractor

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_path / "duration_test.wav"),
        )

        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(result.stdout.strip())
        # Video is ~3023s, allow 5% tolerance
        assert 2800 < duration < 3200, f"Unexpected audio duration: {duration}s"


# ---------------------------------------------------------------------------
# Layer 2: Hotword Loading
# ---------------------------------------------------------------------------


class TestHotwordLoading:
    """Load hotwords from the docx file for ASR enhancement."""

    def test_load_hotwords_from_docx(self, hotword_doc):
        from video_splitter.extractor.hotwords import load_hotwords_from_file

        hotwords = load_hotwords_from_file(hotword_doc)

        assert isinstance(hotwords, str)
        assert len(hotwords) > 0, "Hotwords should not be empty"
        # Should contain domain-specific terms
        assert "质量" in hotwords or "红线" in hotwords, (
            f"Expected domain terms in hotwords, got: {hotwords[:200]}"
        )

    def test_hotwords_are_space_separated(self, hotword_doc):
        from video_splitter.extractor.hotwords import load_hotwords_from_file

        hotwords = load_hotwords_from_file(hotword_doc)

        # Should be space-separated
        terms = hotwords.split()
        assert len(terms) > 10, f"Expected many hotword terms, got {len(terms)}"
        # No empty strings from double spaces
        assert all(t for t in terms)


# ---------------------------------------------------------------------------
# Layer 3: Transcription (existing transcript validation)
# ---------------------------------------------------------------------------


class TestTranscription:
    """Test transcription pipeline — uses existing transcript for speed."""

    def test_existing_transcript_structure(self, test_transcript):
        """Verify the existing transcript has correct structure."""
        assert "duration" in test_transcript
        assert "segments" in test_transcript
        assert isinstance(test_transcript["segments"], list)
        assert len(test_transcript["segments"]) > 50
        assert test_transcript["duration"] > 2800

    def test_existing_transcript_segments_have_required_fields(self, test_transcript):
        """Each segment must have text, start, end."""
        for seg in test_transcript["segments"]:
            assert "text" in seg, f"Segment missing 'text': {seg}"
            assert "start" in seg, f"Segment missing 'start': {seg}"
            assert "end" in seg, f"Segment missing 'end': {seg}"
            assert isinstance(seg["text"], str)
            assert isinstance(seg["start"], (int, float))
            assert isinstance(seg["end"], (int, float))
            assert seg["end"] > seg["start"]

    def test_srt_output_format(self, test_transcript):
        """SRT should have correct timestamp format."""
        from video_splitter.extractor.transcribe import to_srt

        srt_content = to_srt(test_transcript)

        assert isinstance(srt_content, str)
        assert len(srt_content) > 0

        # SRT format: index, timestamp line, text, blank line
        lines = srt_content.strip().split("\n")
        assert len(lines) > 10

        # Check timestamp format (HH:MM:SS,mmm --> HH:MM:SS,mmm)
        import re
        timestamp_pattern = r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}"
        timestamp_lines = [l for l in lines if re.match(timestamp_pattern, l)]
        assert len(timestamp_lines) > 50, (
            f"Expected many timestamp lines, got {len(timestamp_lines)}"
        )

    def test_srt_content_matches_transcript(self, test_transcript):
        """SRT text should match transcript segment text."""
        from video_splitter.extractor.transcribe import to_srt

        srt_content = to_srt(test_transcript)

        # First segment text should appear in SRT
        first_text = test_transcript["segments"][0]["text"]
        assert first_text in srt_content


# ---------------------------------------------------------------------------
# Layer 4: Chapter Detection (mocked LLM)
# ---------------------------------------------------------------------------


class TestChapterDetection:
    """Chapter detection with mocked LLM — validates parsing logic."""

    def test_chapter_detection_with_mocked_llm(self, test_transcript):
        """Run chapter detection with mocked LLM response."""
        from unittest.mock import patch

        from video_splitter.analyzer.chapter import ChapterDetector
        from video_splitter.config import SplitConfig

        config = SplitConfig()
        detector = ChapterDetector(config)

        mock_response = _mock_llm_response(num_chapters=5, duration=3023.0)

        # Mock _llm_request to return valid JSON
        with patch.object(detector, "_llm_request", return_value=mock_response):
            chapters = detector.detect(test_transcript)

        assert len(chapters) > 0
        for ch in chapters:
            assert hasattr(ch, "title")
            assert hasattr(ch, "start_seconds")
            assert hasattr(ch, "end_seconds")
            assert ch.start_seconds < ch.end_seconds

    def test_chapter_detection_returns_correct_count(self, test_transcript):
        """Should return the number of chapters from LLM response."""
        from unittest.mock import patch

        from video_splitter.analyzer.chapter import ChapterDetector
        from video_splitter.config import SplitConfig

        config = SplitConfig()
        detector = ChapterDetector(config)

        mock_response = _mock_llm_response(num_chapters=7, duration=3023.0)

        with patch.object(detector, "_llm_request", return_value=mock_response):
            chapters = detector.detect(test_transcript)

        assert len(chapters) == 7

    def test_chapter_validation_after_detection(self, test_transcript):
        """Full flow: detect chapters → validate → check structure."""
        from unittest.mock import patch

        from video_splitter.analyzer.chapter import ChapterDetector
        from video_splitter.analyzer.validator import ChapterValidator
        from video_splitter.config import SplitConfig

        config = SplitConfig()
        detector = ChapterDetector(config)
        validator = ChapterValidator(config)

        mock_response = _mock_llm_response(num_chapters=5, duration=3023.0)

        with patch.object(detector, "_llm_request", return_value=mock_response):
            chapters = detector.detect(test_transcript)

        # Validate
        validated = validator.validate(
            chapters,
            test_transcript.get("segments", []),
            "质量红线讲解",
        )

        assert len(validated) > 0
        # First chapter should start near 0
        assert validated[0].start_seconds < 10.0
        # Last chapter should end near video end
        assert validated[-1].end_seconds > 2900


# ---------------------------------------------------------------------------
# Layer 5: Pipeline Components Integration
# ---------------------------------------------------------------------------


class TestPipelineComponents:
    """Test pipeline components work together without full video cutting."""

    def test_transcript_to_chapters_to_srt_flow(self, test_transcript):
        """Transcript → chapters → SRT generation flow."""
        from unittest.mock import patch

        from video_splitter.analyzer.chapter import ChapterDetector
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.transcribe import to_srt

        config = SplitConfig()
        detector = ChapterDetector(config)

        mock_response = _mock_llm_response(num_chapters=5, duration=3023.0)

        with patch.object(detector, "_llm_request", return_value=mock_response):
            chapters = detector.detect(test_transcript)

        # Generate SRT from transcript
        srt_content = to_srt(test_transcript)
        assert len(srt_content) > 0

        # Chapters should cover full duration
        total_chapter_duration = sum(
            ch.end_seconds - ch.start_seconds for ch in chapters
        )
        assert total_chapter_duration > 2800  # Should cover most of the video

    def test_resume_mode_loads_existing_transcript(self, test_video, tmp_path):
        """Resume mode should load existing transcript instead of re-transcribing."""
        from unittest.mock import patch

        from video_splitter.config import SplitConfig
        from video_splitter.pipeline import Pipeline

        # Set up work directory with pre-existing transcript
        work_dir = tmp_path / "resume_test"
        work_dir.mkdir()
        video_copy = str(work_dir / "test_video.mp4")
        shutil.copy2(test_video, video_copy)

        # Pre-create transcript
        transcript_path = video_copy.replace(".mp4", ".transcript.json")
        shutil.copy2(_TEST_TRANSCRIPT, transcript_path)

        config = SplitConfig(resume=True)
        pipeline = Pipeline(config)

        # Track if transcribe is called
        transcribe_called = False
        original_extract = pipeline.audio.extract

        def mock_extract(*args, **kwargs):
            nonlocal transcribe_called
            transcribe_called = True
            return original_extract(*args, **kwargs)

        with patch.object(pipeline.audio, "extract", side_effect=mock_extract):
            # Mock chapter detection to avoid LLM call
            from video_splitter.analyzer.chapter import Chapter
            mock_chapters = [
                Chapter(title="01_测试", start_seconds=0.0, end_seconds=1500.0),
                Chapter(title="02_测试", start_seconds=1500.0, end_seconds=3023.0),
            ]
            with patch.object(pipeline.chapter_detector, "detect", return_value=mock_chapters):
                # Mock cutter to avoid actual cutting
                with patch.object(pipeline.cutter, "cut", return_value=[]):
                    result = pipeline.run(video_copy)

        # Should use existing transcript (resume), not re-extract audio
        assert not transcribe_called
        assert "transcribe" in result["steps_completed"]
