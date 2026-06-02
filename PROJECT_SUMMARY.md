# FFmpeg Skill - Project Summary

## What was created

A comprehensive Python wrapper for FFmpeg that provides a high-level API for video and audio processing.

## Project Structure

```
E:\Study\LLM\skill开发\
├── package.json              # Skill manifest and metadata
├── requirements.txt          # Python dependencies
├── README.md               # Quick reference guide
├── skill.md                # Complete documentation
└── ffmpeg-skill/           # Main skill package
    ├── __init__.py        # Core FFmpegSkill implementation
    ├── examples.py        # Usage examples
    └── tests.py           # Unit tests
```

## Available Features

### Core Operations

1. **Format Conversion**
   - Convert between video/audio formats
   - Support for MP4, WebM, AVI, MKV, MOV, FLV, etc.

2. **Resolution Modification**
   - Resize to custom dimensions
   - Preset support: 4K, 1080p, 720p, 480p, 360p, 240p
   - Maintain aspect ratio option

3. **Video Cutting**
   - Extract segments by start time and duration
   - Time format support: HH:MM:SS or seconds

4. **Audio Extraction**
   - Extract audio tracks from videos
   - Multiple codec support (AAC, MP3, Opus, FLAC, etc.)

5. **Watermarking**
   - Text watermarks with position and opacity control
   - Image watermarks with overlay support

6. **Video Merging**
   - Combine multiple videos into one
   - Preserve audio and video streams

7. **Quality Adjustment**
   - CRF (Constant Rate Factor) control
   - Bitrate targeting
   - Encoding presets (ultrafast to veryslow)

8. **Video Information**
   - Get detailed metadata (duration, resolution, codec, FPS, etc.)

## Quick Usage

```python
from ffmpeg_skill import FFmpegSkill

# Initialize
ffmpeg = FFmpegSkill()

# Convert format
ffmpeg.convert_format('input.mp4', 'output.webm', video_codec='libvpx-vp9')

# Resize to 720p
ffmpeg.resize_to_preset('input.mp4', 'output_720p.mp4', preset='720p')

# Cut video segment
ffmpeg.cut('input.mp4', 'segment.mp4', start_time='00:00:10', duration='00:00:30')

# Extract audio
ffmpeg.extract_audio('video.mp4', 'audio.mp3', codec='libmp3lome', bitrate='320k')

# Add watermark
ffmpeg.add_watermark('video.mp4', 'watermarked.mp4', text='© My Company')

# Get video info
info = ffmpeg.get_video_info('video.mp4')
print(f"Resolution: {info['width']}x{info['height']}")
```

## Installation Steps

1. **Install FFmpeg** (if not already installed)
   - Windows: Download from https://ffmpeg.org/download.html and add to PATH
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

2. **Install Python dependencies**
   ```bash
   cd E:\Study\LLM\skill开发
   pip install -r requirements.txt
   ```

3. **Verify installation**
   ```bash
   ffmpeg -version
   python -c "from ffmpeg_skill import FFmpegSkill; print('OK')"
   ```

## Documentation

- **skill.md** - Complete API reference with detailed examples
- **README.md** - Quick start guide
- **examples.py** - Runnable example code
- **tests.py** - Unit tests for validation

## Testing

Run tests to ensure everything works:
```bash
python -m pytest ffmpeg-skill/tests.py -v
```

## Error Handling

The skill provides clear error messages:
- `FFmpegError` - FFmpeg operation failures
- `FileNotFoundError` - Missing input files
- `ValueError` - Invalid parameters

Example:
```python
try:
    ffmpeg.convert_format('input.mp4', 'output.webm')
except FFmpegError as e:
    print(f"FFmpeg error: {e}")
except FileNotFoundError:
    print("Input file not found")
```

## Advanced Features

### Progress Tracking
```python
def progress_callback(progress: float):
    print(f"Progress: {progress:.2f}%")

ffmpeg.convert_format(
    'large_video.mp4',
    'output.webm',
    progress_callback=progress_callback
)
```

### Custom FFmpeg Commands
```python
ffmpeg.run_command([
    'ffmpeg', '-i', 'input.mp4',
    '-vf', 'scale=iw/2:ih/2',
    '-c:v', 'libx264',
    'output.mp4'
])
```

## Common Use Cases

1. **Convert video for web**:
   ```python
   ffmpeg.convert_format('video.mp4', 'video.webm',
                        video_codec='libvpx-vp9', audio_codec='libopus')
   ```

2. **Reduce file size**:
   ```python
   ffmpeg.adjust_quality('video.mp4', 'compressed.mp4',
                        crf=28, preset='slow')
   ```

3. **Create thumbnail**:
   ```python
   ffmpeg.cut('video.mp4', 'thumb.jpg', start_time='00:00:05', duration='0.1')
   ```

4. **Batch process videos**:
   ```python
   for video in os.listdir('videos/'):
       ffmpeg.resize_to_preset(f'videos/{video}', f'720p/{video}', '720p')
   ```

## Support and Resources

- FFmpeg Official Docs: https://ffmpeg.org/documentation.html
- FFmpeg Wiki: https://trac.ffmpeg.org/wiki
- FFmpeg Codecs: https://ffmpeg.org/ffmpeg-codecs.html

## License

This skill is a wrapper around FFmpeg. FFmpeg is licensed under GPL or LGPL.
Please refer to the official FFmpeg documentation for specific licensing terms.

## Next Steps

1. Ensure FFmpeg is installed on your system
2. Install Python dependencies with pip
3. Review `examples.py` for usage patterns
4. Test with your own video files
5. Customize and extend as needed for your specific use cases
