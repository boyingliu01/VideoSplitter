# FFmpeg Skill

## Description

A powerful and user-friendly Python wrapper for FFmpeg that simplifies video and audio processing operations. This skill provides a clean API for common FFmpeg tasks including format conversion, resolution modification, video cutting, audio extraction, watermarking, merging, and quality adjustment.

## Features

- **Format Conversion**: Convert between video/audio formats (MP4, AVI, MOV, MKV, WebM, etc.)
- **Resolution Modification**: Resize videos to common resolutions or custom dimensions
- **Video Cutting**: Extract segments from videos based on time
- **Audio Extraction**: Extract audio tracks from video files
- **Watermarking**: Add text or image watermarks to videos
- **Video Merging**: Combine multiple video files into one
- **Quality Adjustment**: Control video quality, bitrate, and compression
- **Batch Processing**: Process multiple files with a single command
- **Progress Tracking**: Real-time progress updates for long operations

## Requirements

- Python 3.8+
- FFmpeg installed and available in system PATH
  - Download from: https://ffmpeg.org/download.html
  - Install guide: https://ffmpeg.org/documentation.html

## Installation

1. Install FFmpeg (if not already installed):
   ```bash
   # Windows: Download and add to PATH
   # macOS: brew install ffmpeg
   # Linux: sudo apt install ffmpeg
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Quick Start

```python
from ffmpeg_skill import FFmpegSkill

# Initialize the skill
ffmpeg = FFmpegSkill()

# Convert video format
ffmpeg.convert_format(
    input_path='input.mp4',
    output_path='output.webm',
    video_codec='libvpx-vp9',
    audio_codec='libopus'
)

# Resize video
ffmpeg.resize(
    input_path='input.mp4',
    output_path='output_720p.mp4',
    width=1280,
    height=720
)

# Cut video segment
ffmpeg.cut(
    input_path='input.mp4',
    output_path='segment.mp4',
    start_time='00:00:10',
    duration='00:00:30'
)
```

## API Reference

### `convert_format(input_path, output_path, video_codec=None, audio_codec=None, quality=None)`

Convert video/audio to a different format.

**Parameters:**
- `input_path` (str): Path to input file
- `output_path` (str): Path to output file
- `video_codec` (str, optional): Video codec (e.g., 'libx264', 'libvpx-vp9')
- `audio_codec` (str, optional): Audio codec (e.g., 'aac', 'libopus')
- `quality` (int, optional): Quality level (1-51 for x264, lower is better)

**Example:**
```python
# Convert to WebM with VP9
ffmpeg.convert_format(
    input_path='video.mp4',
    output_path='video.webm',
    video_codec='libvpx-vp9',
    audio_codec='libopus'
)

# High quality conversion
ffmpeg.convert_format(
    input_path='input.avi',
    output_path='output.mp4',
    video_codec='libx264',
    quality=18
)
```

### `resize(input_path, output_path, width, height, maintain_aspect=True)`

Resize video to specified dimensions.

**Parameters:**
- `input_path` (str): Path to input file
- `output_path` (str): Path to output file
- `width` (int): Target width in pixels
- `height` (int): Target height in pixels
- `maintain_aspect` (bool): Whether to maintain aspect ratio

**Example:**
```python
# Resize to 720p
ffmpeg.resize(
    input_path='4k_video.mp4',
    output_path='720p.mp4',
    width=1280,
    height=720
)

# Resize to custom dimensions, maintaining aspect ratio
ffmpeg.resize(
    input_path='video.mp4',
    output_path='resized.mp4',
    width=1920,
    height=1080,
    maintain_aspect=True
)
```

### `resize_to_preset(input_path, output_path, preset)`

Resize to common resolution presets.

**Presets:**
- `4k`: 3840x2160
- `1080p`: 1920x1080
- `720p`: 1280x720
- `480p`: 854x480
- `360p`: 640x360

**Example:**
```python
ffmpeg.resize_to_preset(
    input_path='input.mp4',
    output_path='output.mp4',
    preset='720p'
)
```

### `cut(input_path, output_path, start_time, duration=None, end_time=None)`

Extract a segment from the video.

**Parameters:**
- `input_path` (str): Path to input file
- `output_path` (str): Path to output file
- `start_time` (str): Start time in HH:MM:SS or seconds format
- `duration` (str, optional): Duration in HH:MM:SS or seconds format
- `end_time` (str, optional): End time in HH:MM:SS format

**Example:**
```python
# Cut from 10s to 40s (30 second duration)
ffmpeg.cut(
    input_path='video.mp4',
    output_path='segment.mp4',
    start_time='00:00:10',
    duration='00:00:30'
)

# Cut from start to specific end time
ffmpeg.cut(
    input_path='video.mp4',
    output_path='segment.mp4',
    start_time='00:01:00',
    end_time='00:02:30'
)
```

### `extract_audio(input_path, output_path, codec='aac', bitrate='192k')`

Extract audio from video file.

**Parameters:**
- `input_path` (str): Path to input video file
- `output_path` (str): Path to output audio file
- `codec` (str): Audio codec (default: 'aac')
- `bitrate` (str): Audio bitrate (default: '192k')

**Example:**
```python
# Extract to MP3
ffmpeg.extract_audio(
    input_path='video.mp4',
    output_path='audio.mp3',
    codec='libmp3lame',
    bitrate='320k'
)

# Extract to AAC
ffmpeg.extract_audio(
    input_path='video.mp4',
    output_path='audio.aac',
    codec='aac'
)
```

### `add_watermark(input_path, output_path, watermark_path=None, text=None, position='bottom-right', opacity=0.7)`

Add watermark (image or text) to video.

**Parameters:**
- `input_path` (str): Path to input video file
- `output_path` (str): Path to output video file
- `watermark_path` (str, optional): Path to watermark image
- `text` (str, optional): Text watermark
- `position` (str): Position ('top-left', 'top-right', 'bottom-left', 'bottom-right', 'center')
- `opacity` (float): Opacity level (0.0-1.0)

**Example:**
```python
# Add image watermark
ffmpeg.add_watermark(
    input_path='video.mp4',
    output_path='watermarked.mp4',
    watermark_path='logo.png',
    position='bottom-right',
    opacity=0.8
)

# Add text watermark
ffmpeg.add_watermark(
    input_path='video.mp4',
    output_path='watermarked.mp4',
    text='My Watermark',
    position='center',
    opacity=0.5
)
```

### `merge_videos(input_paths, output_path, transition=None)`

Merge multiple video files into one.

**Parameters:**
- `input_paths` (list): List of input video file paths
- `output_path` (str): Path to output video file
- `transition` (str, optional): Transition effect between videos

**Example:**
```python
videos = ['part1.mp4', 'part2.mp4', 'part3.mp4']
ffmpeg.merge_videos(
    input_paths=videos,
    output_path='merged.mp4'
)
```

### `adjust_quality(input_path, output_path, crf=None, bitrate=None, preset='medium')`

Adjust video quality settings.

**Parameters:**
- `input_path` (str): Path to input file
- `output_path` (str): Path to output file
- `crf` (int, optional): Constant Rate Factor (0-51, lower is better)
- `bitrate` (str, optional): Target bitrate (e.g., '5M', '10M')
- `preset` (str): Encoding preset ('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow')

**Example:**
```python
# High quality with CRF
ffmpeg.adjust_quality(
    input_path='input.mp4',
    output_path='output.mp4',
    crf=18,
    preset='slow'
)

# Target bitrate
ffmpeg.adjust_quality(
    input_path='input.mp4',
    output_path='output.mp4',
    bitrate='8M',
    preset='medium'
)
```

### `get_video_info(input_path)`

Get detailed information about a video file.

**Parameters:**
- `input_path` (str): Path to video file

**Returns:** Dictionary with video information

**Example:**
```python
info = ffmpeg.get_video_info('video.mp4')
print(f"Duration: {info['duration']}")
print(f"Resolution: {info['width']}x{info['height']}")
print(f"Codec: {info['codec']}")
```

## Batch Processing

Process multiple files with batch operations:

```python
# Convert multiple videos
input_files = ['video1.mp4', 'video2.mp4', 'video3.mp4']
for i, input_file in enumerate(input_files):
    ffmpeg.convert_format(
        input_path=input_file,
        output_path=f'converted_{i}.webm',
        video_codec='libvpx-vp9'
    )

# Resize all videos in a directory
import os
for file in os.listdir('videos/'):
    if file.endswith('.mp4'):
        ffmpeg.resize_to_preset(
            input_path=f'videos/{file}',
            output_path=f'resized/{file}',
            preset='720p'
        )
```

## Error Handling

The skill provides clear error messages for common issues:

```python
try:
    ffmpeg.convert_format('input.mp4', 'output.webm')
except FFmpegError as e:
    print(f"FFmpeg operation failed: {e}")
except FileNotFoundError:
    print("Input file not found")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Advanced Usage

### Custom FFmpeg Commands

For operations not covered by the API, use the `run_command` method:

```python
ffmpeg.run_command([
    'ffmpeg',
    '-i', 'input.mp4',
    '-vf', 'scale=iw/2:ih/2',
    '-c:v', 'libx264',
    '-preset', 'slow',
    '-crf', '22',
    'output.mp4'
])
```

### Progress Callbacks

Add progress tracking for long operations:

```python
def progress_callback(progress):
    print(f"Progress: {progress}%")

ffmpeg.convert_format(
    input_path='large_video.mp4',
    output_path='output.webm',
    progress_callback=progress_callback
)
```

## Troubleshooting

**FFmpeg not found:**
- Ensure FFmpeg is installed and in system PATH
- Verify with: `ffmpeg -version` in terminal

**Codec not supported:**
- Check installed FFmpeg codecs: `ffmpeg -codecs`
- Reinstall FFmpeg with all codecs if needed

**Permission errors:**
- Ensure write permissions for output directory
- Check disk space availability

## License

This skill is based on FFmpeg, which is licensed under GPL or LGPL depending on configuration.
Refer to FFmpeg documentation for specific licensing details: https://ffmpeg.org/legal.html

## Contributing

Contributions are welcome! Please ensure:
- Code follows PEP 8 style guidelines
- All functions include docstrings
- Error handling is comprehensive
- Tests are included for new features

## Support

For FFmpeg-specific issues, refer to:
- Official documentation: https://ffmpeg.org/documentation.html
- Wiki: https://trac.ffmpeg.org/wiki
- Community forums: https://ffmpeg.org/contact.html
