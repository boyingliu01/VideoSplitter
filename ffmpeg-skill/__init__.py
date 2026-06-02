"""
FFmpeg Skill - A comprehensive Python wrapper for FFmpeg operations.

This module provides a user-friendly interface for common FFmpeg operations
including format conversion, resolution modification, video cutting, audio
extraction, watermarking, merging, and quality adjustment.
"""

import subprocess
import json
import os
import re
from typing import List, Optional, Callable, Dict, Any
from pathlib import Path


class FFmpegError(Exception):
    """Custom exception for FFmpeg-related errors."""

    pass


class FFmpegSkill:
    """
    Main class for FFmpeg operations.

    This class provides a high-level API for common video and audio
    processing tasks using FFmpeg.
    """

    # Resolution presets
    RESOLUTION_PRESETS = {
        "4k": (3840, 2160),
        "1080p": (1920, 1080),
        "720p": (1280, 720),
        "480p": (854, 480),
        "360p": (640, 360),
        "240p": (426, 240),
    }

    # Common video codecs
    VIDEO_CODECS = {
        "h264": "libx264",
        "h265": "libx265",
        "vp8": "libvpx",
        "vp9": "libvpx-vp9",
        "av1": "libaom-av1",
    }

    # Common audio codecs
    AUDIO_CODECS = {
        "aac": "aac",
        "mp3": "libmp3lame",
        "opus": "libopus",
        "vorbis": "libvorbis",
        "flac": "flac",
    }

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """
        Initialize FFmpeg Skill.

        Args:
            ffmpeg_path: Path to FFmpeg executable (default: 'ffmpeg')
            ffprobe_path: Path to FFprobe executable (default: 'ffprobe')

        Raises:
            FFmpegError: If FFmpeg is not found or not working
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._check_ffmpeg()

    def _check_ffmpeg(self) -> None:
        """Check if FFmpeg is installed and working."""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise FFmpegError(
                    f"FFmpeg is not working properly. "
                    f"Please ensure FFmpeg is installed and in your PATH."
                )
        except FileNotFoundError:
            raise FFmpegError(
                f"FFmpeg not found at '{self.ffmpeg_path}'. "
                f"Please install FFmpeg from https://ffmpeg.org/download.html"
            )
        except subprocess.TimeoutExpired:
            raise FFmpegError("FFmpeg command timed out")

    def _run_command(
        self,
        command: List[str],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Execute an FFmpeg command.

        Args:
            command: List of command arguments
            progress_callback: Optional callback for progress updates

        Raises:
            FFmpegError: If command fails
        """
        process = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True,
            )

            # Read stderr for progress information
            if progress_callback and process.stderr:
                for line in process.stderr:
                    # Parse progress from FFmpeg output
                    time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
                    if time_match:
                        # This is a simplified progress tracking
                        # More sophisticated tracking would require duration parsing
                        progress_callback(0.0)

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                raise FFmpegError(
                    f"FFmpeg command failed with return code {process.returncode}: {stderr}"
                )

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            raise FFmpegError("FFmpeg command timed out")
        except Exception as e:
            raise FFmpegError(f"Error executing FFmpeg command: {str(e)}")

    def _get_duration(self, input_path: str) -> float:
        """
        Get video duration using ffprobe.

        Args:
            input_path: Path to video file

        Returns:
            Duration in seconds
        """
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_path,
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
            return 0.0
        except Exception:
            return 0.0

    def convert_format(
        self,
        input_path: str,
        output_path: str,
        video_codec: Optional[str] = None,
        audio_codec: Optional[str] = None,
        quality: Optional[int] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Convert video/audio to a different format.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            video_codec: Video codec (e.g., 'libx264', 'libvpx-vp9')
            audio_codec: Audio codec (e.g., 'aac', 'libopus')
            quality: Quality level (1-51 for x264, lower is better)
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        command = [self.ffmpeg_path, "-i", input_path]

        if video_codec:
            command.extend(["-c:v", video_codec])
        if audio_codec:
            command.extend(["-c:a", audio_codec])
        if quality is not None:
            command.extend(["-crf", str(quality)])

        command.append(output_path)
        self._run_command(command, progress_callback)

    def resize(
        self,
        input_path: str,
        output_path: str,
        width: int,
        height: int,
        maintain_aspect: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Resize video to specified dimensions.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            width: Target width in pixels
            height: Target height in pixels
            maintain_aspect: Whether to maintain aspect ratio
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if maintain_aspect:
            scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
        else:
            scale_filter = f"scale={width}:{height}"

        command = [
            self.ffmpeg_path,
            "-i",
            input_path,
            "-vf",
            scale_filter,
            "-c:a",
            "copy",
            output_path,
        ]

        self._run_command(command, progress_callback)

    def resize_to_preset(
        self,
        input_path: str,
        output_path: str,
        preset: str,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Resize to common resolution presets.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            preset: Resolution preset ('4k', '1080p', '720p', '480p', '360p')
            progress_callback: Optional callback for progress updates
        """
        if preset not in self.RESOLUTION_PRESETS:
            raise ValueError(
                f"Invalid preset. Available presets: {list(self.RESOLUTION_PRESETS.keys())}"
            )

        width, height = self.RESOLUTION_PRESETS[preset]
        self.resize(
            input_path, output_path, width, height, progress_callback=progress_callback
        )

    def cut(
        self,
        input_path: str,
        output_path: str,
        start_time: str,
        duration: Optional[str] = None,
        end_time: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Extract a segment from the video.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            start_time: Start time in HH:MM:SS or seconds format
            duration: Duration in HH:MM:SS or seconds format (optional if end_time is provided)
            end_time: End time in HH:MM:SS format (optional)
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if duration is None and end_time is None:
            raise ValueError("Either duration or end_time must be provided")

        command = [self.ffmpeg_path, "-ss", start_time, "-i", input_path]

        if duration:
            command.extend(["-t", duration])
        elif end_time:
            # Calculate duration from start and end time
            start_seconds = self._parse_time(start_time)
            end_seconds = self._parse_time(end_time)
            duration_seconds = end_seconds - start_seconds
            command.extend(["-t", str(duration_seconds)])

        command.extend(["-c", "copy", output_path])
        self._run_command(command, progress_callback)

    def _parse_time(self, time_str: str) -> float:
        """
        Parse time string to seconds.

        Args:
            time_str: Time string in HH:MM:SS or seconds format

        Returns:
            Time in seconds
        """
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 3:
                hours, minutes, seconds = map(float, parts)
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                minutes, seconds = map(float, parts)
                return minutes * 60 + seconds
        return float(time_str)

    def extract_audio(
        self,
        input_path: str,
        output_path: str,
        codec: str = "aac",
        bitrate: str = "192k",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Extract audio from video file.

        Args:
            input_path: Path to input video file
            output_path: Path to output audio file
            codec: Audio codec (default: 'aac')
            bitrate: Audio bitrate (default: '192k')
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        command = [
            self.ffmpeg_path,
            "-i",
            input_path,
            "-vn",
            "-c:a",
            codec,
            "-b:a",
            bitrate,
            output_path,
        ]

        self._run_command(command, progress_callback)

    def add_watermark(
        self,
        input_path: str,
        output_path: str,
        watermark_path: Optional[str] = None,
        text: Optional[str] = None,
        position: str = "bottom-right",
        opacity: float = 0.7,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Add watermark (image or text) to video.

        Args:
            input_path: Path to input video file
            output_path: Path to output video file
            watermark_path: Path to watermark image (optional if text is provided)
            text: Text watermark (optional if watermark_path is provided)
            position: Position ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'center')
            opacity: Opacity level (0.0-1.0)
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if watermark_path is None and text is None:
            raise ValueError("Either watermark_path or text must be provided")

        if watermark_path:
            if not os.path.exists(watermark_path):
                raise FileNotFoundError(f"Watermark image not found: {watermark_path}")

            # Get overlay position
            overlay_filter = self._get_watermark_filter(image=True, position=position)
            filter_complex = f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[wm];[0:v][wm]{overlay_filter}"
            command = [
                self.ffmpeg_path,
                "-i",
                input_path,
                "-i",
                watermark_path,
                "-filter_complex",
                filter_complex,
                output_path,
            ]
        else:
            # Text watermark
            assert text is not None  # text must be provided if watermark_path is None
            drawtext_filter = self._get_text_watermark_filter(text, position, opacity)
            command = [
                self.ffmpeg_path,
                "-i",
                input_path,
                "-vf",
                drawtext_filter,
                output_path,
            ]

        self._run_command(command, progress_callback)

    def _get_watermark_filter(self, image: bool, position: str) -> str:
        """Get overlay filter based on position."""
        if position == "top-left":
            return "overlay=0:0"
        elif position == "top-right":
            return "overlay=W-w:0"
        elif position == "bottom-left":
            return "overlay=0:H-h"
        elif position == "bottom-right":
            return "overlay=W-w:H-h"
        elif position == "center":
            return "overlay=(W-w)/2:(H-h)/2"
        else:
            return "overlay=W-w:H-h"

    def _get_text_watermark_filter(
        self, text: str, position: str, opacity: float
    ) -> str:
        """Get drawtext filter for text watermark."""
        x, y = self._get_text_position(position)
        return (
            f"drawtext=text='{text}':x={x}:y={y}:fontsize=24:fontcolor=white@{opacity}"
        )

    def _get_text_position(self, position: str) -> tuple:
        """Get x,y coordinates for text position."""
        if position == "top-left":
            return "10", "10"
        elif position == "top-right":
            return "W-tw-10", "10"
        elif position == "bottom-left":
            return "10", "H-th-10"
        elif position == "bottom-right":
            return "W-tw-10", "H-th-10"
        elif position == "center":
            return "(W-tw)/2", "(H-th)/2"
        else:
            return "W-tw-10", "H-th-10"

    def merge_videos(
        self,
        input_paths: List[str],
        output_path: str,
        transition: Optional[str] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Merge multiple video files into one.

        Args:
            input_paths: List of input video file paths
            output_path: Path to output video file
            transition: Transition effect between videos (optional)
            progress_callback: Optional callback for progress updates
        """
        if len(input_paths) < 2:
            raise ValueError("At least 2 input files are required for merging")

        for path in input_paths:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Input file not found: {path}")

        # Create concat list
        concat_filter = ""
        inputs = []
        for i, path in enumerate(input_paths):
            inputs.extend(["-i", path])
            concat_filter += f"[{i}:v][{i}:a]"

        concat_filter += f"concat=n={len(input_paths)}:v=1:a=1[outv][outa]"

        command = [
            self.ffmpeg_path,
            *inputs,
            "-filter_complex",
            concat_filter,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            output_path,
        ]

        self._run_command(command, progress_callback)

    def adjust_quality(
        self,
        input_path: str,
        output_path: str,
        crf: Optional[int] = None,
        bitrate: Optional[str] = None,
        preset: str = "medium",
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Adjust video quality settings.

        Args:
            input_path: Path to input file
            output_path: Path to output file
            crf: Constant Rate Factor (0-51, lower is better)
            bitrate: Target bitrate (e.g., '5M', '10M')
            preset: Encoding preset ('ultrafast' to 'veryslow')
            progress_callback: Optional callback for progress updates
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        valid_presets = [
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
            "slower",
            "veryslow",
        ]

        if preset not in valid_presets:
            raise ValueError(f"Invalid preset. Must be one of: {valid_presets}")

        command = [self.ffmpeg_path, "-i", input_path]

        if crf is not None:
            if not 0 <= crf <= 51:
                raise ValueError("CRF must be between 0 and 51")
            command.extend(["-crf", str(crf)])

        if bitrate:
            command.extend(["-b:v", bitrate])

        command.extend(["-preset", preset, output_path])
        self._run_command(command, progress_callback)

    def get_video_info(self, input_path: str) -> Dict[str, Any]:
        """
        Get detailed information about a video file.

        Args:
            input_path: Path to video file

        Returns:
            Dictionary with video information
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        command = [
            self.ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            input_path,
        ]

        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                raise FFmpegError(f"Failed to get video info: {result.stderr}")

            data = json.loads(result.stdout)

            # Extract relevant information
            info = {
                "filename": data.get("format", {}).get("filename", ""),
                "format_name": data.get("format", {}).get("format_name", ""),
                "duration": float(data.get("format", {}).get("duration", 0)),
                "size": int(data.get("format", {}).get("size", 0)),
                "bit_rate": int(data.get("format", {}).get("bit_rate", 0)),
            }

            # Get video stream info
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    info.update(
                        {
                            "codec": stream.get("codec_name", ""),
                            "width": stream.get("width", 0),
                            "height": stream.get("height", 0),
                            "fps": eval(stream.get("r_frame_rate", "0/1")),
                            "pixel_format": stream.get("pix_fmt", ""),
                        }
                    )
                elif stream.get("codec_type") == "audio":
                    info.update(
                        {
                            "audio_codec": stream.get("codec_name", ""),
                            "sample_rate": stream.get("sample_rate", ""),
                            "channels": stream.get("channels", 0),
                        }
                    )

            return info

        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse ffprobe output: {str(e)}")
        except subprocess.TimeoutExpired:
            raise FFmpegError("ffprobe command timed out")
        except Exception as e:
            raise FFmpegError(f"Error getting video info: {str(e)}")

    def run_command(
        self,
        command: List[str],
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Run a custom FFmpeg command.

        Args:
            command: List of command arguments
            progress_callback: Optional callback for progress updates

        This method allows you to execute any FFmpeg command that is not
        covered by the high-level API methods.
        """
        self._run_command(command, progress_callback)


# Convenience function for quick access
def create_ffmpeg_skill(
    ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"
) -> FFmpegSkill:
    """
    Create and return an FFmpegSkill instance.

    Args:
        ffmpeg_path: Path to FFmpeg executable
        ffprobe_path: Path to FFprobe executable

    Returns:
        FFmpegSkill instance
    """
    return FFmpegSkill(ffmpeg_path, ffprobe_path)


__all__ = ["FFmpegSkill", "FFmpegError", "create_ffmpeg_skill"]
