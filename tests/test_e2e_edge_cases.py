"""E2E edge-case tests — unusual inputs and boundary conditions.

These tests verify the system handles edge cases gracefully:
- Video with no audio track
- Very short video (3s)
- Video with non-ASCII filename
- Cutting with overlapping chapters
- Burning with empty transcript segments
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)


def _create_video(
    path: str,
    duration: int = 5,
    has_audio: bool = True,
    resolution: str = "320x240",
) -> str:
    """Create a test video using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s={resolution}:d={duration}",
    ]
    if has_audio:
        cmd.extend([
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        ])
    cmd.extend([
        "-c:v", "libx264", "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
    ])
    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "64k"])
    cmd.extend(["-shortest", path])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {result.stderr[-200:]}")
    return path


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestEdgeCaseNoAudio:
    """Video with no audio track."""

    def test_extract_no_audio_raises(self, tmp_dir):
        """AudioExtractor should raise on video without audio."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_dir / "no_audio.mp4")
        _create_video(video_path, duration=5, has_audio=False)

        extractor = AudioExtractor()
        # FFmpeg will fail to extract audio from video without audio track
        with pytest.raises((RuntimeError, Exception)):
            extractor.extract(video_path)


class TestEdgeCaseShortVideo:
    """Very short video (3 seconds)."""

    def test_extract_short_video(self, tmp_dir):
        """Short video should extract valid WAV."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_dir / "short.mp4")
        _create_video(video_path, duration=3)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        assert os.path.exists(wav_path)
        assert wav_path.endswith(".wav")
        with open(wav_path, "rb") as f:
            assert f.read(4) == b"RIFF"

    def test_transcribe_short_video(self, tmp_dir):
        """Short video transcription should complete without error."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine

        video_path = str(tmp_dir / "short_transcribe.mp4")
        _create_video(video_path, duration=3)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        engine = FunASREngine()
        config = SplitConfig()
        transcript = engine.transcribe(wav_path, config)

        assert transcript["duration"] > 0
        assert isinstance(transcript["segments"], list)

    def test_cut_short_video(self, tmp_dir):
        """Cutting a short video should produce valid segments."""
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter

        video_path = str(tmp_dir / "short_cut.mp4")
        _create_video(video_path, duration=5)

        chapters = [
            Chapter(title="Part1", start_seconds=0.0, end_seconds=2.5),
            Chapter(title="Part2", start_seconds=2.5, end_seconds=5.0),
        ]
        config = SplitConfig()
        cutter = VideoCutter(config)
        output_dir = str(tmp_dir / "short_segments")
        files = cutter.cut(video_path, chapters, output_dir)

        assert len(files) == 2
        for f in files:
            assert os.path.exists(f)
            assert os.path.getsize(f) > 0


class TestEdgeCaseNonAsciiFilename:
    """Video with non-ASCII filename (Chinese characters)."""

    def test_extract_chinese_filename(self, tmp_dir):
        """Audio extraction should work with Chinese filename."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_dir / "测试视频.mp4")
        _create_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        assert os.path.exists(wav_path)
        assert wav_path.endswith(".wav")

    def test_cut_chinese_filename(self, tmp_dir):
        """Video cutting should work with Chinese filename."""
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter

        video_path = str(tmp_dir / "中文视频.mp4")
        _create_video(video_path, duration=10)

        chapters = [
            Chapter(title="第一章", start_seconds=0.0, end_seconds=5.0),
            Chapter(title="第二章", start_seconds=5.0, end_seconds=10.0),
        ]
        config = SplitConfig()
        cutter = VideoCutter(config)
        output_dir = str(tmp_dir / "中文输出")
        files = cutter.cut(video_path, chapters, output_dir)

        assert len(files) == 2
        for f in files:
            assert os.path.exists(f)

    def test_transcribe_chinese_filename(self, tmp_dir):
        """Transcription should work with Chinese filename."""
        from video_splitter.config import SplitConfig
        from video_splitter.extractor.audio import AudioExtractor
        from video_splitter.extractor.engines import FunASREngine

        video_path = str(tmp_dir / "中文转录.mp4")
        _create_video(video_path, duration=5)

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        engine = FunASREngine()
        config = SplitConfig()
        transcript = engine.transcribe(wav_path, config)

        assert transcript["duration"] > 0


class TestEdgeCaseOverlappingChapters:
    """Cutting with overlapping or invalid chapters."""

    def test_cut_overlapping_chapters(self, tmp_dir):
        """Overlapping chapters should still produce output."""
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter

        video_path = str(tmp_dir / "overlap.mp4")
        _create_video(video_path, duration=20)

        # Overlapping chapters (0-15, 10-20)
        chapters = [
            Chapter(title="Part1", start_seconds=0.0, end_seconds=15.0),
            Chapter(title="Part2", start_seconds=10.0, end_seconds=20.0),
        ]
        config = SplitConfig()
        cutter = VideoCutter(config)
        output_dir = str(tmp_dir / "overlap_segments")
        files = cutter.cut(video_path, chapters, output_dir)

        # Should produce 2 files (overlapping is allowed by FFmpeg)
        assert len(files) == 2
        for f in files:
            assert os.path.exists(f)


class TestEdgeCaseEmptyBurn:
    """Subtitle burning with empty or no segments."""

    def test_burn_empty_segments(self, tmp_dir):
        """Burning with empty segments should still produce output."""
        from video_splitter.analyzer.chapter import Chapter
        from video_splitter.config import SplitConfig
        from video_splitter.splitter.cutter import VideoCutter
        from video_splitter.splitter.subtitle_burner import SubtitleBurner

        video_path = str(tmp_dir / "empty_burn.mp4")
        _create_video(video_path, duration=10)

        chapters = [
            Chapter(title="Seg1", start_seconds=0.0, end_seconds=10.0),
        ]
        config = SplitConfig()
        cutter = VideoCutter(config)
        cut_dir = str(tmp_dir / "empty_burn_cut")
        seg_files = cutter.cut(video_path, chapters, cut_dir)

        chapter_dicts = [
            {"title": "Seg1", "start_seconds": 0.0, "end_seconds": 10.0},
        ]
        # Empty transcript segments
        burner = SubtitleBurner()
        result = burner.burn(seg_files, chapter_dicts, [])

        assert len(result) == 1
        assert os.path.exists(result[0])


class TestEdgeCaseVideoFormats:
    """Different video resolutions and formats."""

    def test_extract_hd_video(self, tmp_dir):
        """HD video (1280x720) should extract correctly."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_dir / "hd_video.mp4")
        _create_video(video_path, duration=5, resolution="1280x720")

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        assert os.path.exists(wav_path)
        with open(wav_path, "rb") as f:
            assert f.read(4) == b"RIFF"

    def test_extract_low_res_video(self, tmp_dir):
        """Low-res video (160x120) should extract correctly."""
        from video_splitter.extractor.audio import AudioExtractor

        video_path = str(tmp_dir / "lowres.mp4")
        _create_video(video_path, duration=5, resolution="160x120")

        extractor = AudioExtractor()
        wav_path = extractor.extract(video_path)

        assert os.path.exists(wav_path)
