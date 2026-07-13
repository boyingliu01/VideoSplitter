# ffmpeg-skill — Local Knowledge Base

## OVERVIEW

Python package providing `FFmpegSkill` — a high-level API wrapping FFmpeg/ffprobe for video/audio processing. Also includes a standalone CLI tool. Superseded by `video_splitter/` for the main application; retained as a reusable library.

## STRUCTURE

```
ffmpeg-skill/
├── __init__.py       # FFmpegSkill class (673 lines) — all operations
├── ffmpeg_tool.py    # CLI entry point (282 lines) — argparse
├── examples.py       # Runnable examples — all commented out by default
└── tests.py          # pytest — validates parameter handling, error paths
```

## WHERE TO LOOK

- **Add a new operation**: `__init__.py` → add method to `FFmpegSkill` → add CLI subparser in `ffmpeg_tool.py`
- **Fix a CLI bug**: `ffmpeg_tool.py` — all CLI logic lives here
- **Update docs**: `.opencode/skills/ffmpeg-video/SKILL.md` (OpenCode) + `skill.md` (API reference) at project root
- **Add tests**: `tests.py` — test against dummy files, not real videos

## CONVENTIONS

- **Internal methods**: prefixed with `_` (`_run_command`, `_parse_time`, `_get_*_filter`, `_get_*_position`)
- **All public operations** accept optional `progress_callback: Callable[[float], None]`
- **Input validation**: `if not os.path.exists(input_path)` → `raise FileNotFoundError`; invalid params → `raise ValueError`
- **FFmpeg errors**: caught and re-raised as `FFmpegError`
- **`_run_command()`**: single execution path — all public methods build a `List[str]` command and call it
- **No streaming**: waits for process completion via `Popen.communicate()`

## ANTI-PATTERNS

- **Don't modify `__init__.py` without updating `SKILL.md`** — OpenCode reads the skill file, not the code directly
- **Don't commit real video files** to the repo
- **Tests should NOT require real video files** — use dummy file creation for existence checks
- **Don't suppress FFmpeg errors** — always surface via `FFmpegError`
