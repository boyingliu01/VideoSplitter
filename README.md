# FFmpeg Skill

A powerful and user-friendly Python wrapper for FFmpeg that simplifies video and audio processing operations.

## Quick Start

```python
from ffmpeg_skill import FFmpegSkill

# Initialize
ffmpeg = FFmpegSkill()

# Convert video format
ffmpeg.convert_format('input.mp4', 'output.webm', video_codec='libvpx-vp9')

# Resize video
ffmpeg.resize_to_preset('input.mp4', 'output_720p.mp4', preset='720p')

# Cut video
ffmpeg.cut('input.mp4', 'segment.mp4', start_time='00:00:10', duration='00:00:30')
```

## Features

- Format Conversion (MP4, WebM, AVI, MKV, etc.)
- Resolution Modification (4K, 1080p, 720p, etc.)
- Video Cutting and Segmentation
- Audio Extraction
- Watermarking (text and image)
- Video Merging
- Quality Adjustment
- Batch Processing

## Installation

1. Install FFmpeg from https://ffmpeg.org/download.html
2. Install Python dependencies: `pip install -r requirements.txt`

## Examples

See `examples.py` for detailed usage examples.

## Testing

Run tests with: `python -m pytest ffmpeg-skill/tests.py`

## License

Based on FFmpeg (GPL/LGPL). Refer to FFmpeg documentation for details.
