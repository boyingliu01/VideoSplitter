"""End-to-end tests using real video files and real components.

These tests exercise the full processing pipeline without mocking
core components (AudioExtractor, FunASR, VideoCutter, SubtitleBurner).
Only external dependencies (LLM API) are mocked.

Run with:  pytest tests/test_e2e.py -v
Skip with: pytest tests/ -v --ignore=tests/test_e2e.py
"""
from __future__ import annotations

import os
import sys

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

# Real test video: 60s, 640x360, 440Hz sine audio
_TEST_VIDEO = os.path.join(
    _PROJ_ROOT,
    "ffmpeg-video-workspace",
    "test-files",
    "acceptance_test.mp4",
)


@pytest.fixture(scope="module")
def test_video() -> str:
    """Return path to the real test video. Skip if missing."""
    if not os.path.exists(_TEST_VIDEO):
        pytest.skip(f"Test video not found: {_TEST_VIDEO}")
    return _TEST_VIDEO


@pytest.fixture(scope="module")
def tmp_out_dir(tmp_path_factory):
    """Shared output directory for all E2E tests in this module."""
    return tmp_path_factory.mktemp("e2e_output")


# ---------------------------------------------------------------------------
# Layer 1: Audio Extraction (real FFmpeg)
# ---------------------------------------------------------------------------


class TestE2EAudioExtraction:
    """Real FFmpeg audio extraction from video."""

    def test_extract_produces_valid_wav(self, test_video, tmp_out_dir):
        from video_splitter.extractor.audio import AudioExtractor

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_out_dir / "extracted.wav"),
        )

        assert os.path.exists(wav_path)
        assert wav_path.endswith(".wav")
        # Verify it's a valid RIFF/WAV file
        with open(wav_path, "rb") as f:
            header = f.read(4)
        assert header == b"RIFF", f"Not a valid WAV file: {header!r}"

        # Verify duration is close to 60s
        import subprocess

        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                wav_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(result.stdout.strip())
        assert 55.0 < duration < 65.0, f"Unexpected duration: {duration}s"


# ---------------------------------------------------------------------------
# Layer 2: Transcription (real FunASR, real audio)
# ---------------------------------------------------------------------------


class TestE2ETranscription:
    """Real FunASR transcription on real audio.

    Catches: OOM on long audio, chunking bugs, NaN handling,
    timestamp conversion errors.
    """

    def test_transcribe_short_audio(self, test_video, tmp_out_dir):
        """Transcribe the 60s test video — exercises chunking boundary."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine

        # Extract audio
        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_out_dir / "transcribe_test.wav"),
        )

        # Transcribe with real FunASR
        engine = FunASREngine()
        config = SplitConfig()
        transcript = engine.transcribe(wav_path, config)

        # Validate structure
        assert "language" in transcript
        assert "duration" in transcript
        assert "segments" in transcript
        assert transcript["language"] == "zh"
        assert transcript["duration"] > 0

        # 60s audio should trigger chunking (default threshold = 30s)
        # Even if no speech is detected, the chunking code path must execute
        # without OOM or errors.
        assert isinstance(transcript["segments"], list)

    def test_transcribe_progress_callback(self, test_video, tmp_out_dir):
        """Progress callback must fire during real transcription."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine

        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_out_dir / "progress_test.wav"),
        )

        engine = FunASREngine()
        config = SplitConfig()
        progress_log: list[tuple[float, str]] = []

        def _on_progress(frac: float, desc: str) -> None:
            progress_log.append((frac, desc))

        engine.transcribe(wav_path, config, progress_callback=_on_progress)

        # Must have at least start and end progress
        assert len(progress_log) >= 2
        assert progress_log[0][0] == 0.0  # starts at 0
        assert progress_log[-1][0] == 1.0  # ends at 1.0


# ---------------------------------------------------------------------------
# Layer 3: Video Cutting (real FFmpeg)
# ---------------------------------------------------------------------------


class TestE2EVideoCutting:
    """Real FFmpeg video cutting."""

    def test_cut_produces_valid_segments(self, test_video, tmp_out_dir):
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [
            Chapter(title="Part1", start_seconds=0.0, end_seconds=20.0),
            Chapter(title="Part2", start_seconds=20.0, end_seconds=40.0),
            Chapter(title="Part3", start_seconds=40.0, end_seconds=60.0),
        ]

        config = SplitConfig()
        cutter = VideoCutter(config)
        output_dir = str(tmp_out_dir / "cut_segments")
        files = cutter.cut(test_video, chapters, output_dir)

        assert len(files) == 3
        for f in files:
            assert os.path.exists(f)
            assert f.endswith(".mp4")
            # Each segment should be > 0 bytes
            assert os.path.getsize(f) > 0


# ---------------------------------------------------------------------------
# Layer 4: Subtitle Burning (real FFmpeg)
# ---------------------------------------------------------------------------


class TestE2ESubtitleBurn:
    """Real FFmpeg subtitle burning."""

    def test_burn_produces_subtitled_segments(self, test_video, tmp_out_dir):
        from video_splitter.splitter.subtitle_burner import SubtitleBurner

        # First cut the video
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [
            Chapter(title="Burn1", start_seconds=0.0, end_seconds=20.0),
            Chapter(title="Burn2", start_seconds=20.0, end_seconds=40.0),
        ]
        config = SplitConfig()
        cutter = VideoCutter(config)
        cut_dir = str(tmp_out_dir / "burn_cut")
        seg_files = cutter.cut(test_video, chapters, cut_dir)

        # Prepare transcript segments that overlap with chapters
        transcript_segments = [
            {"text": "第一段测试字幕", "start": 5.0, "end": 15.0},
            {"text": "第二段测试字幕", "start": 25.0, "end": 35.0},
        ]

        chapter_dicts = [
            {"title": "Burn1", "start_seconds": 0.0, "end_seconds": 20.0},
            {"title": "Burn2", "start_seconds": 20.0, "end_seconds": 40.0},
        ]

        burner = SubtitleBurner()
        result = burner.burn(seg_files, chapter_dicts, transcript_segments)

        assert len(result) == 2
        for f in result:
            assert os.path.exists(f)
            assert "_subtitled" in f
            assert os.path.getsize(f) > 0


# ---------------------------------------------------------------------------
# Layer 5: Full Pipeline (video → transcript → cut → burn)
# ---------------------------------------------------------------------------


class TestE2EFullPipeline:
    """Complete pipeline: extract → transcribe → cut → burn.

    Uses real FunASR for transcription.  Chapter detection is skipped
    (uses predefined chapters) to avoid needing an LLM API key.
    """

    def test_extract_transcribe_cut_burn(self, test_video, tmp_out_dir):
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine
        from video_splitter.splitter.cutter import VideoCutter
        from video_splitter.splitter.subtitle_burner import SubtitleBurner

        config = SplitConfig()

        # Step 1: Extract audio
        extractor = AudioExtractor()
        wav_path = extractor.extract(
            test_video,
            output_path=str(tmp_out_dir / "pipeline.wav"),
        )
        assert os.path.exists(wav_path)

        # Step 2: Transcribe (real FunASR)
        engine = FunASREngine()
        transcript = engine.transcribe(wav_path, config)
        assert transcript["duration"] > 0

        # Step 3: Cut video (predefined chapters)
        chapters = [
            Chapter(title="Seg1", start_seconds=0.0, end_seconds=30.0),
            Chapter(title="Seg2", start_seconds=30.0, end_seconds=60.0),
        ]
        cutter = VideoCutter(config)
        cut_dir = str(tmp_out_dir / "pipeline_segments")
        seg_files = cutter.cut(test_video, chapters, cut_dir)
        assert len(seg_files) == 2

        # Step 4: Burn subtitles (use whatever segments FunASR returned)
        chapter_dicts = [
            {"title": "Seg1", "start_seconds": 0.0, "end_seconds": 30.0},
            {"title": "Seg2", "start_seconds": 30.0, "end_seconds": 60.0},
        ]
        burner = SubtitleBurner()
        burn_result = burner.burn(seg_files, chapter_dicts, transcript["segments"])

        # All segments should produce output (even if no subtitles to burn)
        assert len(burn_result) == 2
        for f in burn_result:
            assert os.path.exists(f)
