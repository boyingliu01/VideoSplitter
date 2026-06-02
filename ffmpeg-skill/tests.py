"""
Unit tests for FFmpeg Skill.

These tests require FFmpeg to be installed and available in the system PATH.
"""

import pytest
import os
import tempfile
from ffmpeg_skill import FFmpegSkill, FFmpegError


@pytest.fixture
def ffmpeg():
    """Fixture to create FFmpegSkill instance."""
    try:
        return FFmpegSkill()
    except FFmpegError:
        pytest.skip("FFmpeg not installed")


@pytest.fixture
def temp_dir():
    """Fixture to create temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_ffmpeg_initialization(ffmpeg):
    """Test that FFmpegSkill initializes correctly."""
    assert ffmpeg is not None
    assert ffmpeg.ffmpeg_path == "ffmpeg"


def test_invalid_preset(ffmpeg, temp_dir):
    """Test error handling for invalid resolution preset."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(ValueError, match="Invalid preset"):
        ffmpeg.resize_to_preset(
            input_path=input_file, output_path=output_file, preset="invalid_preset"
        )


def test_missing_input_file(ffmpeg, temp_dir):
    """Test error handling for missing input file."""
    input_file = os.path.join(temp_dir, "nonexistent.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    with pytest.raises(FileNotFoundError):
        ffmpeg.convert_format(input_path=input_file, output_path=output_file)


def test_watermark_without_text_or_image(ffmpeg, temp_dir):
    """Test that watermark requires either text or image path."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(
        ValueError, match="Either watermark_path or text must be provided"
    ):
        ffmpeg.add_watermark(input_path=input_file, output_path=output_file)


def test_cut_video_without_duration(ffmpeg, temp_dir):
    """Test that cut requires either duration or end_time."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(
        ValueError, match="Either duration or end_time must be provided"
    ):
        ffmpeg.cut(
            input_path=input_file, output_path=output_file, start_time="00:00:10"
        )


def test_merge_videos_single_file(ffmpeg, temp_dir):
    """Test that merge requires at least 2 files."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(ValueError, match="At least 2 input files are required"):
        ffmpeg.merge_videos(input_paths=[input_file], output_path=output_file)


def test_invalid_quality_preset(ffmpeg, temp_dir):
    """Test error handling for invalid quality preset."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(ValueError, match="Invalid preset"):
        ffmpeg.adjust_quality(
            input_path=input_file, output_path=output_file, preset="invalid_preset"
        )


def test_invalid_crf_range(ffmpeg, temp_dir):
    """Test error handling for CRF outside valid range."""
    input_file = os.path.join(temp_dir, "test.mp4")
    output_file = os.path.join(temp_dir, "output.mp4")

    # Create a dummy input file
    with open(input_file, "wb") as f:
        f.write(b"dummy")

    with pytest.raises(ValueError, match="CRF must be between 0 and 51"):
        ffmpeg.adjust_quality(input_path=input_file, output_path=output_file, crf=100)


def test_get_video_info_missing_file(ffmpeg, temp_dir):
    """Test error handling for getting info on missing file."""
    input_file = os.path.join(temp_dir, "nonexistent.mp4")

    with pytest.raises(FileNotFoundError):
        ffmpeg.get_video_info(input_file)


def test_resolution_presets():
    """Test that all resolution presets are defined."""
    presets = FFmpegSkill.RESOLUTION_PRESETS
    assert "4k" in presets
    assert "1080p" in presets
    assert "720p" in presets
    assert "480p" in presets
    assert "360p" in presets
    assert "240p" in presets


def test_video_codecs():
    """Test that video codec shortcuts are defined."""
    codecs = FFmpegSkill.VIDEO_CODECS
    assert "h264" in codecs
    assert "h265" in codecs
    assert "vp8" in codecs
    assert "vp9" in codecs
    assert "av1" in codecs


def test_audio_codecs():
    """Test that audio codec shortcuts are defined."""
    codecs = FFmpegSkill.AUDIO_CODECS
    assert "aac" in codecs
    assert "mp3" in codecs
    assert "opus" in codecs
    assert "vorbis" in codecs
    assert "flac" in codecs


def test_parse_time_format_hms():
    """Test parsing time in HH:MM:SS format."""
    ffmpeg = FFmpegSkill()
    assert ffmpeg._parse_time("00:00:10") == 10.0
    assert ffmpeg._parse_time("00:01:30") == 90.0
    assert ffmpeg._parse_time("01:00:00") == 3600.0


def test_parse_time_format_ms():
    """Test parsing time in MM:SS format."""
    ffmpeg = FFmpegSkill()
    assert ffmpeg._parse_time("00:10") == 10.0
    assert ffmpeg._parse_time("01:30") == 90.0


def test_parse_time_format_seconds():
    """Test parsing time in seconds format."""
    ffmpeg = FFmpegSkill()
    assert ffmpeg._parse_time("10") == 10.0
    assert ffmpeg._parse_time("90") == 90.0
    assert ffmpeg._parse_time("30.5") == 30.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
