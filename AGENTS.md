# PROJECT KNOWLEDGE BASE

**Generated:** 2026-06-02
**Branch:** N/A (no git repo)

## OVERVIEW

FFmpeg Python wrapper packaged as an OpenCode skill. Provides high-level API + CLI for video/audio processing managed by Sisyphus.

## STRUCTURE

```
skill开发/                           # Project root
├── ffmpeg-skill/                   # Python implementation package
│   ├── __init__.py               # FFmpegSkill class + all operations
│   ├── ffmpeg_tool.py            # Standalone CLI (argparse)
│   ├── examples.py               # Runnable examples
│   └── tests.py                  # pytest unit tests
├── .opencode/
│   └── skills/ffmpeg-video/      # OpenCode skill definition
│       └── SKILL.md              # Skill manifest + instructions
├── install.bat / install.sh      # OS-specific installers
├── requirements.txt              # numpy, tqdm, pytest
├── package.json                  # Skill metadata manifest
├── skill.md                      # Full API reference docs
├── README.md                     # Quick start
├── PROJECT_SUMMARY.md            # Project summary (legacy)
├── COMPLETION_REPORT.md          # Completion report (legacy)
└── OPENCODE_SETUP.md             # Setup guide (legacy)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Core API implementation | `ffmpeg-skill/__init__.py` | `FFmpegSkill` class (~670 lines) |
| CLI tool | `ffmpeg-skill/ffmpeg_tool.py` | argparse-based, 8 subcommands |
| OpenCode skill definition | `.opencode/skills/ffmpeg-video/SKILL.md` | What OpenCode loads |
| Tests | `ffmpeg-skill/tests.py` | pytest, mostly validation/error-handling |
| Examples | `ffmpeg-skill/examples.py` | All functions commented out by default |
| Full API docs | `skill.md` | 417 lines, complete reference |
| Package metadata | `package.json` | skill name="ffmpeg-skill", version 1.0.0 |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `FFmpegSkill` | class | `__init__.py:23` | Main API class |
| `FFmpegError` | class | `__init__.py:17` | Custom exception |
| `convert_format()` | method | `__init__.py:174` | Format conversion |
| `resize()` | method | `__init__.py:209` | Custom dimension resizing |
| `resize_to_preset()` | method | `__init__.py:250` | Preset resolution scaling |
| `cut()` | method | `__init__.py:276` | Time-based segment extraction |
| `extract_audio()` | method | `__init__.py:336` | Audio track extraction |
| `add_watermark()` | method | `__init__.py:371` | Text/image watermark |
| `merge_videos()` | method | `__init__.py:470` | Multi-video concatenation |
| `adjust_quality()` | method | `__init__.py:516` | CRF/bitrate/preset control |
| `get_video_info()` | method | `__init__.py:567` | ffprobe metadata extraction |
| `run_command()` | method | `__init__.py:638` | Raw FFmpeg command passthrough |
| `create_ffmpeg_skill()` | function | `__init__.py:657` | Convenience factory |
| `main()` | function | `ffmpeg_tool.py:20` | CLI entry point |

## CONVENTIONS

- **Docstrings**: Google-style with Args/Raises/Returns sections
- **Error handling**: Custom `FFmpegError` exception class; functions raise `FileNotFoundError`, `ValueError` for input validation
- **Type hints**: Used throughout (`Optional`, `List`, `Dict`, `Callable`)
- **Progress tracking**: Optional `Callable[[float], None]` callback on all operations
- **Codec shortcuts**: Class-level dicts (`VIDEO_CODECS`, `AUDIO_CODECS`) map short names to FFmpeg codec names
- **Resolution**: Class-level `RESOLUTION_PRESETS` dict

## UNIQUE STYLES

- `_run_command()` is the single internal FFmpeg execution path — all public methods build args then call it
- `self.` methods for internal logic (`_check_ffmpeg`, `_parse_time`, `_get_watermark_filter`, `_get_text_watermark_filter`, `_get_text_position`)

## COMMANDS

```bash
# Install deps
pip install -r requirements.txt

# Run CLI
python ffmpeg-skill/ffmpeg_tool.py <command> [args]

# Run tests
python -m pytest ffmpeg-skill/tests.py -v

# OpenCode: skill auto-loaded from .opencode/skills/ffmpeg-video/SKILL.md
```

## NOTES

- FFmpeg must be installed separately and available in PATH (not bundled)
- Windows: install.bat requires admin-like privileges for PATH manipulation
- Tests create dummy files (not real videos) — they validate parameter handling, not actual FFmpeg output
- The SKILL.md in `.opencode/skills/ffmpeg-video/` is the **source of truth** for OpenCode; other docs (`skill.md`, `README.md`) are supplementary
- Three legacy docs exist: `PROJECT_SUMMARY.md`, `COMPLETION_REPORT.md`, `OPENCODE_SETUP.md` — useful for historical context, may contain stale info
