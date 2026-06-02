# FFmpeg Video Processing Skill - Setup & Usage Guide

## Overview

This is a comprehensive FFmpeg video processing skill for OpenCode. It provides a high-level Python API and CLI for common video/audio operations including format conversion, resizing, cutting, audio extraction, watermarking, merging, and quality adjustment.

## What's Included

```
E:\Study\LLM\skill开发\
├── .opencode/
│   └── skills/
│       └── ffmpeg-video/
│           └── SKILL.md          # OpenCode skill definition (READY FOR OPENCODE!)
├── ffmpeg-skill/
│   ├── __init__.py             # Core FFmpegSkill Python implementation
│   ├── examples.py              # Runnable examples
│   ├── tests.py                # Unit tests
│   └── ffmpeg_tool.py          # Standalone CLI tool
├── install.sh                   # Unix/Linux/macOS installation script
├── install.bat                  # Windows installation script
├── requirements.txt              # Python dependencies
├── package.json                 # Package metadata
├── README.md                    # Quick reference
└── skill.md                     # Full documentation
```

## Installation

### Prerequisites

1. **FFmpeg** must be installed and in system PATH
   - Download from: https://ffmpeg.org/download.html

2. **Python 3.8+** must be installed

### Quick Install

**On Windows:**
```cmd
install.bat
```

**On Linux/macOS:**
```bash
chmod +x install.sh
./install.sh
```

### Manual Install

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Verify FFmpeg is installed:
   ```bash
   ffmpeg -version
   ```

3. That's it! The OpenCode skill is already at `.opencode/skills/ffmpeg-video/SKILL.md`

## Using in OpenCode

### Automatic Loading

OpenCode automatically discovers skills from `.opencode/skills/` directory. The skill is already properly structured and will be available when you run OpenCode.

### How to Invoke

When using OpenCode, simply ask it to process videos using FFmpeg. For example:

```
"Please convert this video to WebM format with VP9 codec"
"Resize this video to 720p"
"Extract audio from this video"
"Add a watermark to this video"
"Cut this video from 10s to 40s"
```

OpenCode will automatically load the `ffmpeg-video` skill and use it to process your request.

### Manual Skill Loading

If you want to manually load the skill in OpenCode:

1. OpenCode will list available skills in the `skill` tool
2. Select or specify `ffmpeg-video` skill
3. The skill's full instructions will be loaded

## Standalone CLI Usage

The skill includes a standalone command-line `ffmpeg-tool` that can be used outside of OpenCode:

```bash
# Show help
python ffmpeg-skill/ffmpeg_tool.py --help

# Convert video
python ffmpeg-skill/ffmpeg_tool.py convert input.mp4 output.webm --vcodec libvpx-vp9

# Resize video
python ffmpeg-skill/ffmpeg_tool.py resize input.mp4 output.mp4 --preset 720p

# Cut video
python ffmpeg-skill/ffmpeg_tool.py cut input.mp4 segment.mp4 --start 00:00:10 --duration 00:00:30

# Extract audio
python ffmpeg-skill/ffmpeg_tool.py extract-audio video.mp4 audio.mp3 --codec libmp3lame

# Add watermark
python ffmpeg-skill/ffmpeg_tool.py watermark video.mp4 watermarked.mp4 --text "© My Company"

# Merge videos
python ffmpeg-skill/ffmpeg_tool.py merge part1.mp4 part2.mp4 part3.mp4 -o merged.mp4

# Adjust quality
python ffmpeg-skill/ffmpeg_tool.py quality input.mp4 output.mp4 --crf 20 --preset slow

# Get video info
python ffmpeg-skill/ffmpeg_tool.py info video.mp4
```

## Python API Usage

```python
from ffmpeg_skill import FFmpegSkill

# Initialize
ffmpeg = FFmpegSkill()

# Convert format
ffmpeg.convert_format('input.mp4', 'output.webm', video='libvpx-vp9')

# Resize to 720p
ffmpeg.resize_to_preset('input.mp4', 'output.mp4', '720p')

# Cut video
ffmpeg.cut('input.mp4', 'segment.mp4', '00:00:10', '00:00:30')

# Extract audio
ffmpeg.extract_audio('video.mp4', 'audio.mp3', codec='libmp3lame', bitrate='320k')

# Add watermark
ffmpeg.add_watermark('video.mp4', 'watermarked.mp4', text='© My Company')

# Merge videos
ffmpeg.merge_videos(['part1.mp4', 'part2.mp4'], 'merged.mp4')

# Adjust quality
ffmpeg.adjust_quality('input.mp4', 'output.mp4', crf=20, preset='slow')

# Get info
info = ffmpeg.get_video_info('video.mp4')
print(f"Resolution: {info['width']}x{info['height']}")
```

## Testing

Run unit tests:

```bash
python -m pytest ffmpeg-skill/tests.py -v
```

## Skill Verification

To verify the OpenCode skill is properly configured:

1. Check the skill file exists:
   ```bash
   ls -la .opencode/skills/ffmpeg-video/SKILL.md
   ```

2. Check SKILL.md has required frontmatter:
   ```bash
   head -20 .opencode/skills/ffmpeg-video/SKILL.md
   ```
   Should contain:
   - `name: ffmpeg-video`
   - `description: ...`

3. Verify Python implementation:
   ```bash
   python -c "from ffmpeg_skill import FFmpegSkill; print('OK')"
   ```

## Example Workflows

### Convert for Web Streaming

```python
from ffmpeg_skill import FFmpegSkill

ffmpeg = FFmpegSkill()

# Convert to WebM with VP9 (good for web)
ffmpeg.convert_format(
    'input.mp4',
    'output.webm',
    video_codec='libvpx-vp9',
    audio_codec='libopus',
    quality=18
)
```

### Batch Resize Videos

```python
import os
from ffmpeg_skill import FFmpegSkill

ffmpeg = FFmpegSkill()

for video in os.listdir('videos/'):
    if video.endswith('.mp4'):
        ffmpeg.resize_to_preset(
            f'videos/{video}',
            f'resized/{video}',
            '720p'
        )
```

### Extract Multiple Audio Tracks

```python
import os
from ffmpeg_skill import FFmpegSkill

ffmpeg = FFmpegSkill()

for video in os.listdir('videos/'):
    if video.endswith('.mp4'):
        audio_name = video.replace('.mp4', '.mp3')
        ffmpeg.extract_audio(
            f'videos/{video}',
            f'audio/{audio_name}',
            codec='libmp3lame',
            bitrate='320k'
        )
```

## Troubleshooting

### Skill Not Visible in OpenCode

1. **Check file location**:
   ```
   Should be at: .opencode/skills/ffmpeg-video/SKILL.md
   ```

2. **Check file name**: Must be `SKILL.md` (all caps)

3. **Check frontmatter**: Must include `name` and `description` fields

4. **Restart OpenCode**: Skills are loaded at startup

### FFmpeg Not Found

```
Error: FFmpeg not found at 'ffmpeg'
```

**Solution**: Install FFmpeg and add to PATH:
- Windows: Add to System Environment Variables
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### Python Import Error

```
ModuleNotFoundError: No module named 'ffmpeg_skill'
```

**Solution**: Make sure you're in the correct directory or add to Python path:
```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)/ffmpeg-skill"
```

## Documentation

- **SKILL.md** - Complete OpenCode skill documentation
- **skill.md** - Full API reference
- **examples.py** - Runnable code examples
- **tests.py** - Unit tests

## Support

- **FFmpeg Docs**: https://ffmpeg.org/documentation.html
- **FFmpeg Wiki**: https://trac.ffmpeg.org/wiki
- **OpenCode Skills**: https://opencode.ai/docs/skills/

## License

This skill wraps FFmpeg, which is licensed under GPL or LGPL.
Refer to FFmpeg documentation for specific licensing terms.

## Ready to Use!

The OpenCode skill is already configured at:
```
.opencode/skills/ffmpeg-video/SKILL.md
```

Just start OpenCode and ask it to process your videos!
