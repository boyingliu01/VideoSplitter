#!/usr/bin/env python3
"""
FFmpeg Video Processor - Standalone CLI tool

This script provides a command-line interface for FFmpeg operations.
It can be run independently or invoked by OpenCode skills.
"""

import sys
import argparse
import json
import os

# Add current directory to path to import ffmpeg_skill
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ffmpeg_skill import FFmpegSkill, FFmpegError


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="FFmpeg Video Processor - Command-line interface for video operations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert video format
  ffmpeg-tool convert input.mp4 output.webm --vcodec libvpx-vp9 --acodec libopus

  # Resize video to 720p
  ffmpeg-tool resize input.mp4 output.mp4 --preset 720p

  # Cut video segment
  ffmpeg-tool cut input.mp4 segment.mp4 --start 00:00:10 --duration 00:00:30

  # Extract audio
  ffmpeg-tool extract-audio video.mp4 audio.mp3 --codec libmp3lame --bitrate 320k

  # Add watermark
  ffmpeg-tool watermark video.mp4 watermarked.mp4 --text "© My Company" --position bottom-right

  # Merge videos
  ffmpeg-tool merge part1.mp4 part2.mp4 part3.mp4 -o merged.mp4

  # Adjust quality
  ffmpeg-tool quality input.mp4 output.mp4 --crf 20 --preset slow

  # Get video info
  ffmpeg-tool info video.mp4
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Convert command
    convert_parser = subparsers.add_parser("convert", help="Convert video/audio format")
    convert_parser.add_argument("input", help="Input file path")
    convert_parser.add_argument("output", help="Output file path")
    convert_parser.add_argument(
        "--vcodec", help="Video codec (e.g., libx264, libvpx-vp9)"
    )
    convert_parser.add_argument("--acodec", help="Audio codec (e.g., aac, libopus)")
    convert_parser.add_argument("--quality", type=int, help="Quality level (0-51)")
    convert_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Resize command
    resize_parser = subparsers.add_parser("resize", help="Resize video")
    resize_parser.add_argument("input", help="Input file path")
    resize_parser.add_argument("output", help="Output file path")
    resize_parser.add_argument("--width", type=int, help="Target width in pixels")
    resize_parser.add_argument("--height", type=int, help="Target height in pixels")
    resize_parser.add_argument(
        "--preset", help="Resolution preset (4k, 1080p, 720p, 480p, 360p, 240p)"
    )
    resize_parser.add_argument(
        "--maintain-aspect",
        action="store_true",
        default=True,
        help="Maintain aspect ratio",
    )
    resize_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Cut command
    cut_parser = subparsers.add_parser("cut", help="Cut video segment")
    cut_parser.add_argument("input", help="Input file path")
    cut_parser.add_argument("output", help="Output file path")
    cut_parser.add_argument(
        "--start", required=True, help="Start time (HH:MM:SS or seconds)"
    )
    cut_parser.add_argument("--duration", help="Duration (HH:MM:SS or seconds)")
    cut_parser.add_argument("--end", help="End time (HH:MM:SS)")
    cut_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Extract audio command
    extract_parser = subparsers.add_parser(
        "extract-audio", help="Extract audio from video"
    )
    extract_parser.add_argument("input", help="Input video file path")
    extract_parser.add_argument("output", help="Output audio file path")
    extract_parser.add_argument(
        "--codec", default="aac", help="Audio codec (default: aac)"
    )
    extract_parser.add_argument(
        "--bitrate", default="192k", help="Audio bitrate (default: 192k)"
    )
    extract_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Watermark command
    watermark_parser = subparsers.add_parser("watermark", help="Add watermark to video")
    watermark_parser.add_argument("input", help="Input video file path")
    watermark_parser.add_argument("output", help="Output video file path")
    watermark_parser.add_argument("--text", help="Text watermark")
    watermark_parser.add_argument("--image", help="Image watermark path")
    watermark_parser.add_argument(
        "--position",
        default="bottom-right",
        help="Position (top-left, top-right, bottom-left, bottom-right, center)",
    )
    watermark_parser.add_argument(
        "--opacity",
        type=float,
        default=0.7,
        help="Opacity level (0.0-1.0, default: 0.7)",
    )
    watermark_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Merge command
    merge_parser = subparsers.add_parser("merge", help="Merge multiple videos")
    merge_parser.add_argument("inputs", nargs="+", help="Input video file paths")
    merge_parser.add_argument("-o", "--output", required=True, help="Output file path")
    merge_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Quality command
    quality_parser = subparsers.add_parser("quality", help="Adjust video quality")
    quality_parser.add_argument("input", help="Input file path")
    quality_parser.add_argument("output", help="Output file path")
    quality_parser.add_argument("--crf", type=int, help="Constant Rate Factor (0-51)")
    quality_parser.add_argument("--bitrate", help="Target bitrate (e.g., 5M, 10M)")
    quality_parser.add_argument(
        "--preset", default="medium", help="Encoding preset (ultrafast to veryslow)"
    )
    quality_parser.add_argument("--json", action="store_true", help="Output JSON")

    # Info command
    info_parser = subparsers.add_parser("info", help="Get video information")
    info_parser.add_argument("input", help="Input video file path")
    info_parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        ffmpeg = FFmpegSkill()

        if args.command == "convert":
            ffmpeg.convert_format(
                args.input,
                args.output,
                video_codec=getattr(args, "vcodec", None),
                audio_codec=getattr(args, "acodec", None),
                quality=getattr(args, "quality", None),
            )
            print_success(f"Converted {args.input} to {args.output}")

        elif args.command == "resize":
            if args.preset:
                ffmpeg.resize_to_preset(args.input, args.output, args.preset)
                print_success(
                    f"Resized {args.input} to {args.output} (preset: {args.preset})"
                )
            else:
                ffmpeg.resize(
                    args.input,
                    args.output,
                    args.width,
                    args.height,
                    args.maintain_aspect,
                )
                print_success(
                    f"Resized {args.input} to {args.output} ({args.width}x{args.height})"
                )

        elif args.command == "cut":
            ffmpeg.cut(args.input, args.output, args.start, args.duration, args.end)
            print_success(f"Extracted segment from {args.input} to {args.output}")

        elif args.command == "extract-audio":
            ffmpeg.extract_audio(args.input, args.output, args.codec, args.bitrate)
            print_success(f"Extracted audio from {args.input} to {args.output}")

        elif args.command == "watermark":
            ffmpeg.add_watermark(
                args.input,
                args.output,
                watermark_path=args.image,
                text=args.text,
                position=args.position,
                opacity=args.opacity,
            )
            print_success(f"Added watermark to {args.input} -> {args.output}")

        elif args.command == "merge":
            ffmpeg.merge_videos(args.inputs, args.output)
            print_success(f"Merged {len(args.inputs)} videos to {args.output}")

        elif args.command == "quality":
            ffmpeg.adjust_quality(
                args.input,
                args.output,
                crf=args.crf,
                bitrate=args.bitrate,
                preset=args.preset,
            )
            print_success(f"Adjusted quality: {args.input} -> {args.output}")

        elif args.command == "info":
            info = ffmpeg.get_video_info(args.input)
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                print_video_info(info)

        return 0

    except FFmpegError as e:
        print_error(f"FFmpeg Error: {e}")
        return 1
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        return 1
    except ValueError as e:
        print_error(f"Invalid parameter: {e}")
        return 1
    except KeyboardInterrupt:
        print_error("\nOperation cancelled by user")
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1


def print_success(message: str) -> None:
    """Print success message."""
    print(f"✓ {message}")


def print_error(message: str) -> None:
    """Print error message."""
    print(f"✗ {message}", file=sys.stderr)


def print_video_info(info: dict) -> None:
    """Print video information in readable format."""
    print("=" * 60)
    print("VIDEO INFORMATION")
    print("=" * 60)
    print(f"File:           {info.get('filename', 'N/A')}")
    print(f"Format:         {info.get('format_name', 'N/A')}")
    print(f"Duration:       {info.get('duration', 0):.2f} seconds")
    print(f"Size:           {info.get('size', 0):,} bytes")
    print(f"Bitrate:        {info.get('bit_rate', 0):,} bps")
    print()
    print("VIDEO STREAM")
    print("-" * 60)
    print(f"Codec:          {info.get('codec', 'N/A')}")
    print(f"Resolution:      {info.get('width', 0)}x{info.get('height', 0)}")
    print(f"FPS:            {info.get('fps', 0):.2f}")
    print(f"Pixel Format:   {info.get('pixel_format', 'N/A')}")
    print()
    print("AUDIO STREAM")
    print("-" * 60)
    print(f"Codec:          {info.get('audio_codec', 'N/A')}")
    print(f"Sample Rate:    {info.get('sample_rate', 'N/A')} Hz")
    print(f"Channels:       {info.get('channels', 0)}")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
