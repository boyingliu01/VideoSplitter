---
name: ffmpeg-video
description: Comprehensive video processing skill using FFmpeg - format conversion, resizing, cutting, audio extraction, watermarking, merging, quality adjustment
license: MIT
compatibility: opencode
metadata:
  category: video-processing
  requires: ffmpeg
  version: 1.0.0
---

# FFmpeg Video Processing Skill

## What I Do

I provide a comprehensive, user-friendly interface for FFmpeg video and audio operations:

- **Format Conversion**: Convert between video/audio formats (MP4, WebM, AVI, MKV, MOV, FLV, etc.)
- **Resolution Modification**: Resize videos to custom dimensions or preset resolutions (4K, 1080p, 720p, 480p, 360p, 240p)
- **Video Cutting**: Extract video segments by start time and duration
- **Audio Extraction**: Extract audio tracks from videos (AAC, MP3, Opus, FLAC, etc.)
- **Watermarking**: Add text or image watermarks with position and opacity control
- **Video Merging**: Combine multiple video files into one
- **Quality Adjustment**: Control video quality via CRF, bitrate, and encoding presets
- **Video Information**: Extract metadata (duration, resolution, codec, FPS, etc.)
- **Batch Processing**: Process multiple files efficiently
- **Progress Tracking**: Real-time progress updates for long operations

## Prerequisites

Before using me, ensure:

1. **FFmpeg is installed** on your system and available in PATH
   - Windows: Download from https://ffmpeg.org/download.html and add to PATH
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg` or `sudo pacman -S ffmpeg`

2. **Python 3.8+** is installed

3. **Python dependencies** are installed:
   ```bash
   pip install numpy tqdm
   ```

## Triggers

Use this skill when:
- converting video/audio to different formats
- Need to resize or scale videos
- Need to cut/trim video segments
- Need to extract audio from video files
- Need to add watermarks to videos
- Need to merge multiple videos
- Need to adjust video quality or compression
- Need to get video metadata information
- Need to batch process multiple videos

## Workflow

The FFmpeg processing pipeline follows these steps:

1. Validate input file existence and FFmpeg availability
2. Parse and validate parameters (resolution, time formats, codec names)
3. Construct FFmpeg command with appropriate flags
4. Execute FFmpeg process and capture stdout/stderr
5. Parse FFmpeg progress output for real-time tracking
6. Handle errors and return structured results or error messages

### Architecture

I use a Python wrapper around FFmpeg that:
1. Validates inputs and parameters
2. Generates appropriate FFmpeg commands
3. Executes FFmpeg with proper error handling
4. Parses FFmpeg output for progress tracking
5. Returns structured results or clear error messages

### Error Handling

I provide clear error messages for:
- FFmpeg not installed or not in PATH
- Input files not found
- Invalid parameters (resolution presets, time formats, etc.)
- FFmpeg execution failures
- Permission issues

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|--------------|------------------|
| Hardcoding FFmpeg paths without fallback to PATH lookup | Use `shutil.which('ffmpeg')` or subprocess with 'ffmpeg' command |
| Ignoring FFmpeg exit codes and assuming success | Always check return code; raise error on non-zero exit |
| Using ultrafast preset for final/archived renders | Use medium or slow preset for best compression-to-quality ratio |
| Setting CRF below 18 for web streaming (wasteful file size) | Use CRF 20-24 for web; CRF 18-20 only for archiving |
| Merging videos with mismatched resolution/FPS/codecs | Validate stream compatibility before merge; re-encode to match if needed |
| Not testing on small segments before batch processing | Always test parameters on a short segment first |
| Forgetting to maintain aspect ratio on resize | Use `maintain_aspect=True` or proper scale/pad filters |

## API Reference

### Format Conversion

```python
from ffmpeg_skill import FFmpegSkill

ffmpeg = FFmpegSkill()

# Basic conversion
ffmpeg.convert_format('input.mp4', 'output.webm')

# With codecs and quality
ffmpeg.convert_format(
    input_path='input.mp4',
    output_path='output.webm',
    video_codec='libvpx-vp9',  # or 'libx264', 'libvpx', etc.
    audio_codec='libopus',      # or 'aac', 'libmp3lame', etc.
    quality=18                  # CRF: 0-51, lower is better (H.264)
)

# With progress tracking
def progress_callback(progress: float):
    print(f"Progress: {progress:.2f}%")

ffmpeg.convert_format('large.mp4', 'output.webm', progress_callback=progress_callback)
```

**Parameters:**
- `input_path` (str, required): Path to input file
- `output_path` (str, required): Path to output file
- `video_codec` (str, optional): Video codec name
- `audio_codec` (str, optional): Audio codec name
- `quality` (int, optional): Quality level (0-51 for CRF)
- `progress_callback` (callable, optional): Function for progress updates

### Resolution Modification

```python
# Resize to custom dimensions
ffmpeg.resize(
    input_path='input.mp4',
    output_path='output.mp4',
    width=1280,
    height=720,
    maintain_aspect=True  # Preserve aspect ratio with padding
)

# Resize to preset
ffmpeg.resize_to_preset(
    input_path='input.mp4',
    output_path='output.mp4',
    preset='720p'  # Available: 4k, 1080p, 720p, 480p, 360p, 240p
)
```

**Available Presets:**
- `4k`: 3840x2160
- `1080p`: 1920x1080
- `720p`: 1280x720
- `480p`: 854x480
- `360p`: 640x360
- `240p`: 426x240

### Video Cutting

```python
# Cut by start time and duration
ffmpeg.cut(
    input_path='input.mp4',
    output_path='segment.mp4',
    start_time='00:00:10',  # HH:MM:SS or seconds
    duration='00:00:30'     # HH:MM:SS or seconds
)

# Cut by start and end time
ffmpeg.cut(
    input_path='input.mp4',
    output_path='segment.mp4',
    start_time='00:01:00',
    end_time='00:02:30'
)
```

**Time Formats:**
- `HH:MM:SS` (e.g., '00:01:30' = 90 seconds)
- `MM:SS` (e.g., '01:30' = 90 seconds)
- Seconds (e.g., '90' = 90 seconds)

### Audio Extraction

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
    codec='aac',
    bitrate='192k'
)
```

**Supported Audio Codecs:**
- `aac`: AAC (default)
- `libmp3lame`: MP3
- `libopus`: Opus
- `libvorbis`: Vorbis
- `flac`: FLAC

### Watermarking

```python
# Text watermark
ffmpeg.add_watermark(
    input_path='input.mp4',
    output_path='watermarked.mp4',
    text='© My Company 2025',
    position='bottom-right',  # top-left, top-right, bottom-left, bottom-right, center
    opacity=0.7              # 0.0 to 1.0
)

# Image watermark
ffmpeg.add_watermark(
    input_path='input.mp4',
    output_path='watermarked.mp4',
    watermark_path='logo.png',
    position='top-right',
    opacity=0.8
)
```

**Position Options:**
- `top-left`: Top left corner
- `top-right`: Top right corner
- `bottom-left`: Bottom left corner
- `bottom-right`: Bottom right corner (default)
- `center`: Center of video

### Video Merging

```python
# Merge multiple videos
ffmpeg.merge_videos(
    input_paths=['part1.mp4', 'part2.mp4', 'part3.mp4'],
    output_path='merged.mp4'
)

# All input videos must have same:
# - Resolution
# - Frame rate
# - Audio codec
# - Video codec
```

### Quality Adjustment

```python
# Adjust quality with CRF (Constant Rate Factor)
ffmpeg.adjust_quality(
    input_path='input.mp4',
    output_path='output.mp4',
    crf=20,                # 0-51, lower is better
    preset='slow'            # ultrafast to veryslow
)

# Adjust quality with bitrate
ffmpeg.adjust_quality(
    input_path='input.mp4',
    output_path='output.mp4',
    bitrate='8M',            # Target bitrate
    preset='medium'
)
```

**CRF Values (H.264/H.265):**
- `0-18`: Lossless/near-lossless (very large files)
- `19-23`: Good quality (recommended)
- `24-28`: Acceptable quality
- `29-51`: Lower quality (smaller files)

**Encoding Presets (speed vs compression):**
- `ultrafast`: Fastest, lowest compression
- `superfast`, `veryfast`, `faster`, `fast`: Progressive
- `medium`: Balance (default)
- `slow`, `slower`, `veryslow`: Slowest, best compression

### Video Information

```python
# Get detailed video metadata
info = ffmpeg.get_video_info('video.mp4')

print(f"Duration: {info['duration']} seconds")
print(f"Resolution: {info['width']}x{info['height']}")
print(f"FPS: {info['fps']}")
print(f"Codec: {info['codec']}")
print(f"Audio Codec: {info.get('audio_codec', 'N/A')}")
print(f"Bitrate: {info['bit_rate']}")
```

**Returns:**
- `duration`: Video duration in seconds
- `width`: Video width in pixels
- `height`: Video height in pixels
- `fps`: Frames per second
- `codec`: Video codec name
- `audio_codec`: Audio codec name
- `sample_rate`: Audio sample rate
- `channels`: Number of audio channels
- `bit_rate`: Video bitrate
- `size`: File size in bytes
- `pixel_format`: Pixel format

## Common Use Cases

### Convert for Web

```python
# Optimized for web with VP9 and Opus
ffmpeg.convert_format(
    'input.mp4',
    'output.webm',
    video_codec='libvpx-vp9',
    audio_codec='libopus',
    quality=18
)
```

### Reduce File Size

```python
# Good balance of quality and size
ffmpeg.adjust_quality(
    'large_video.mp4',
    'compressed.mp4',
    crf=28,
    preset='slow'
)
```

### Create Thumbnail

```python
# Extract first frame as image
ffmpeg.cut('video.mp4', 'thumb.jpg', start_time='0', duration='0.1')
```

### Batch Processing

```python
# Resize all videos in directory
import os

for video in os.listdir('videos/'):
    if video.endswith('.mp4'):
        ffmpeg.resize_to_preset(
            f'videos/{video}',
            f'720p/{video}',
            preset='720p'
        )
```

### Extract Frames

```python
# Extract one frame per second
ffmpeg.run_command([
    'ffmpeg', '-i', 'video.mp4',
    '-vf', 'fps=1',
    'frame_%04d.jpg'
])
```

## Custom FFmpeg Commands

For operations not covered by the API:

```python
# Run custom command
ffmpeg.run_command([
    'ffmpeg',
    '-i', 'input.mp4',
    '-vf', 'scale=iw/2:ih/2',  # Scale to half size
    '-c:v', 'libx264',
    '-preset', 'slow',
    '-crf', '22',
    'output.mp4'
])
```

## Best Practices

1. **Always check FFmpeg availability** before operations
   ```python
   try:
       ffmpeg = FFmpegSkill()
   except FFmpegError:
       print("FFmpeg not installed")
   ```

2. **Use appropriate quality settings** based on use case:
   - Archiving: CRF 18-20
   - Web streaming: CRF 20-24
   - Mobile: CRF 24-28
   - Thumbnails: CRF 28-32

3. **Maintain aspect ratio** when resizing to avoid distortion

4. **Test on small segments** before processing large files

5. **Use slower presets** for final renders, faster for previews

6. **Handle errors gracefully** with try-except blocks

## Troubleshooting

### FFmpeg not found
```
Error: FFmpeg not found at 'ffmpeg'
```
**Solution**: Install FFmpeg and add to system PATH

### Codec not supported
```
Error: Unknown encoder 'libx265'
```
**Solution**: Install FFmpeg with all codecs or use different codec

### Permission error
```
Error: [Errno 13] Permission denied
```
**Solution**: Check write permissions for output directory

### Video merge fails
```
Error: Input streams mismatch
```
**Solution**: Ensure all videos have same resolution, FPS, and codecs

### Slow processing
**Solution**: Use faster encoding preset (`ultrafast` to `medium`)

## Installation

### Install FFmpeg

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Extract to folder (e.g., `C:\ffmpeg`)
3. Add `C:\ffmpeg\bin` to System PATH
4. Restart terminal
5. Verify: `ffmpeg -version`

**macOS:**
```bash
brew install ffmpeg
```

**Linux (Ubuntu/Debian):**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Linux (Arch):**
```bash
sudo pacman -S ffmpeg
```

### Install Python Dependencies

```bash
pip install numpy tqdm
```

### Verify Installation

```python
from ffmpeg_skill import FFmpegSkill

try:
FFmpegSkill()
    print("✓ FFmpeg skill ready!")
except FFmpegError as e:
    print(f"✗ Error: {e}")
```

## Examples

- Convert MP4 to WebM with VP9/Opus codec for web streaming
- Resize video to 720p preset while maintaining aspect ratio
- Cut a 30-second segment starting from 10 seconds into the video
- Extract audio track from video to high-quality MP3 (320kbit/s)
- Add semi-transparent text watermark to bottom-right corner
- Merge multiple video parts into a single concatenated file
- Compress large video with CRF 28 for smaller file size
- Extract video metadata (duration, resolution, codec, FPS)
- Batch resize all videos in a directory to 720p

See `examples.py` for runnable code demonstrating all features.

## Testing

Run unit tests:

```bash
python -m pytest ffmpeg-skill/tests.py -v
```

## License

This skill wraps FFmpeg, which is licensed under GPL or LGPL depending on configuration.
Refer to FFmpeg documentation: https://ffmpeg.org/legal.html

## Additional Resources

- [FFmpeg Official Docs](https://ffmpeg.org/documentation.html)
- [FFmpeg Wiki](https://trac.ffmpeg.org/wiki)
- [FFmpeg Codecs](https://ffmpeg.org/ffmpeg-codecs.html)
- [FFmpeg Filters](https://ffmpeg.org/ffmpeg-filters.html)

## Scope

- **IN**: Video format conversion, resolution scaling, segment extraction, audio extraction, watermarking, video merging, quality adjustment, metadata extraction, batch processing
- **IN**: FFmpeg command generation, parameter validation, error handling, progress tracking
- **Does NOT**: Edit video frames directly, apply visual effects (color grading, filters beyond scale), perform video analysis (object detection, scene recognition), or stream video to external services
- **Does NOT**: Provide GUI interfaces, web dashboards, or cloud processing — operates as a local CLI/Python library only

## Version

Current version: 1.0.0

---

**Ready to process your videos!** Use me whenever you need to convert, resize, cut, merge, or adjust video/audio files.
