"""
Example usage of FFmpeg Skill.

This file demonstrates various use cases of the FFmpeg Skill API.
"""

from ffmpeg_skill import FFmpegSkill, FFmpegError


def example_convert_format():
    """Example: Convert video to WebM format."""
    print("Converting video to WebM format...")
    ffmpeg = FFmpegSkill()

    try:
        ffmpeg.convert_format(
            input_path="input.mp4",
            output_path="output.webm",
            video_codec="libvpx-vp9",
            audio_codec="libopus",
            quality=18,
        )
        print("Conversion complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_resize_video():
    """Example: Resize video to 720p."""
    print("Resizing video to 720p...")
    ffmpeg = FFmpegSkill()

    try:
        ffmpeg.resize_to_preset(
            input_path="input.mp4", output_path="output_720p.mp4", preset="720p"
        )
        print("Resizing complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_cut_video():
    """Example: Cut video segment."""
    print("Cutting video segment...")
    ffmpeg = FFmpegSkill()

    try:
        ffmpeg.cut(
            input_path="input.mp4",
            output_path="segment.mp4",
            start_time="00:00:10",
            duration="00:00:30",
        )
        print("Cutting complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_extract_audio():
    """Example: Extract audio from video."""
    print("Extracting audio from video...")
    ffmpeg = FFmpegSkill()

    try:
        ffmpeg.extract_audio(
            input_path="video.mp4",
            output_path="audio.mp3",
            codec="libmp3lame",
            bitrate="320k",
        )
        print("Audio extraction complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_add_watermark():
    """Example: Add text watermark to video."""
    print("Adding watermark to video...")
    ffmpeg = FFmpegSkill()

    try:
        # Text watermark
        ffmpeg.add_watermark(
            input_path="input.mp4",
            output_path="watermarked.mp4",
            text="© My Company",
            position="bottom-right",
            opacity=0.7,
        )
        print("Watermark added!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_merge_videos():
    """Example: Merge multiple videos."""
    print("Merging videos...")
    ffmpeg = FFmpegSkill()

    try:
        videos = ["part1.mp4", "part2.mp4", "part3.mp4"]
        ffmpeg.merge_videos(input_paths=videos, output_path="merged.mp4")
        print("Merging complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_adjust_quality():
    """Example: Adjust video quality."""
    print("Adjusting video quality...")
    ffmpeg = FFmpegSkill()

    try:
        ffmpeg.adjust_quality(
            input_path="input.mp4", output_path="output.mp4", crf=20, preset="slow"
        )
        print("Quality adjustment complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_get_video_info():
    """Example: Get video information."""
    print("Getting video information...")
    ffmpeg = FFmpegSkill()

    try:
        info = ffmpeg.get_video_info("video.mp4")
        print(f"Duration: {info['duration']} seconds")
        print(f"Resolution: {info['width']}x{info['height']}")
        print(f"Codec: {info['codec']}")
        print(f"FPS: {info['fps']}")
        print(f"Audio Codec: {info.get('audio_codec', 'N/A')}")
    except FFmpegError as e:
        print(f"Error: {e}")


def example_batch_processing():
    """Example: Batch process multiple videos."""
    print("Batch processing videos...")
    ffmpeg = FFmpegSkill()

    # List of videos to process
    videos = ["video1.mp4", "video2.mp4", "video3.mp4"]

    for i, video in enumerate(videos):
        try:
            ffmpeg.resize_to_preset(
                input_path=video, output_path=f"resized_video{i}.mp4", preset="720p"
            )
            print(f"Processed {video}")
        except FFmpegError as e:
            print(f"Error processing {video}: {e}")

    print("Batch processing complete!")


def example_progress_callback():
    """Example: Use progress callback."""
    print("Converting with progress tracking...")
    ffmpeg = FFmpegSkill()

    def progress_callback(progress: float):
        print(f"Progress: {progress:.2f}%")

    try:
        ffmpeg.convert_format(
            input_path="large_video.mp4",
            output_path="output.webm",
            video_codec="libvpx-vp9",
            progress_callback=progress_callback,
        )
        print("Conversion complete!")
    except FFmpegError as e:
        print(f"Error: {e}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("FFmpeg Skill Examples")
    print("=" * 60)
    print()

    # Note: Uncomment the examples you want to run
    # Make sure you have appropriate test files

    # example_convert_format()
    # example_resize_video()
    # example_cut_video()
    # example_extract_audio()
    # example_add_watermark()
    # example_merge_videos()
    # example_adjust_quality()
    # example_get_video_info()
    # example_batch_processing()
    # example_progress_callback()

    print("\nTo run these examples, uncomment them in the main() function")
    print("and ensure you have the required input files.")


if __name__ == "__main__":
    main()
