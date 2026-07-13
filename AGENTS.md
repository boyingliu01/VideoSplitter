# PROJECT KNOWLEDGE BASE

**Generated:** 2026-07-13
**Commit:** fadccaa
**Branch:** master

## OVERVIEW

VideoSplitter — smart topic-based video chaptering via LLM + ASR transcription, with PySide6 GUI for subtitle review. Core stack: Python 3.12, faster-whisper/FunASR, OpenAI-compatible LLM, FFmpeg, PySide6.

## STRUCTURE

```
VideoSplitter/
├── video_splitter/           # Core application package
│   ├── cli.py              # CLI entry (7 subcommands)
│   ├── config.py           # SplitConfig dataclass
│   ├── pipeline.py         # Full pipeline orchestrator
│   ├── review.py           # TTY-based transcript review
│   ├── analyzer/           # LLM chapter detection + validation
│   ├── extractor/          # Audio extraction + ASR engines
│   ├── splitter/           # FFmpeg video cutting
│   └── tests/              # Unit tests (chapter, review, transcribe, validator)
├── gui/                    # PySide6 desktop application (Phase A)
│   ├── app.py              # MainWindow + QApplication entry
│   ├── controllers/        # ReviewController state machine
│   ├── widgets/            # VideoPlayer, SubtitlePanel, StatusBar
│   └── workers/            # TranscribeWorker (QThread)
├── ffmpeg-skill/           # Legacy FFmpeg wrapper (standalone API + CLI)
├── tests/                  # GUI integration tests (controllers, engines, workers)
├── .opencode/skills/       # OpenCode skills (ffmpeg-video, skill-cert)
└── ffmpeg-video-workspace/ # Skill certification benchmarks (not source)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| CLI entry point | `video_splitter/cli.py:207` | `main()` — 7 subcommands |
| GUI entry point | `gui/app.py:263` | `main()` — QApplication |
| Configuration | `video_splitter/config.py:19` | `SplitConfig` — all tunables |
| Add ASR engine | `video_splitter/extractor/engines.py` | ABC + registry pattern |
| Subtitle review logic | `gui/controllers/review_controller.py` | State machine + Qt signals |
| Transcript format | `video_splitter/review.py` | load/save/export/filter |
| Video cutting | `video_splitter/splitter/cutter.py` | Keyframe-aware via FFmpegSkill |
| GUI tests | `tests/` (root) | 41 tests, mocked PySide6 |
| Unit tests | `video_splitter/tests/` | chapter, review, transcribe, validator |
| OpenCode skills | `.opencode/skills/` | SKILL.md is source of truth |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SplitConfig` | class | `config.py:19` | All configuration, env-driven via `from_env()` |
| `Pipeline` | class | `pipeline.py:21` | Full pipeline: audio → transcribe → chapter → validate → cut |
| `main()` | function | `cli.py:207` | CLI entry with 7 subcommands |
| `cmd_gui()` | function | `cli.py:198` | Launches PySide6 GUI from CLI |
| `TranscriptionEngine` | class (ABC) | `engines.py:17` | Abstract base for FunASR/Whisper |
| `FunASREngine` | class | `engines.py:85` | Default Chinese ASR engine |
| `WhisperEngine` | class | `engines.py:175` | faster-whisper engine |
| `create_engine()` | function | `engines.py:228` | Factory by name |
| `ChapterDetector` | class | `chapter.py:43` | LLM chapter detection with sliding-window fallback |
| `ChapterValidator` | class | `validator.py:10` | Boundary align, merge, split, naming |
| `AudioExtractor` | class | `audio.py:12` | FFmpeg audio extraction with quality pre-check |
| `VideoCutter` | class | `cutter.py:22` | FFmpeg video segment cutting |
| `MainWindow` | class | `app.py:27` | PySide6 main window |
| `ReviewController` | class (QObject) | `review_controller.py:20` | Subtitle review state machine |
| `TranscribeWorker` | class (QObject) | `transcribe_worker.py:16` | Background ASR for QThread |
| `SubtitlePanel` | class (QWidget) | `subtitle_panel.py:19` | Transcript display + edit |
| `VideoPlayerWidget` | class (QWidget) | `video_player.py:18` | QMediaPlayer wrapper |
| `FFmpegSkill` | class | `ffmpeg-skill/__init__.py:22` | Legacy FFmpeg API wrapper |

## CONVENTIONS

- **Docstrings**: Google-style (Args/Raises/Returns)
- **Type hints**: Throughout; `dict | None` for optional returns, `@Slot` decorators on Qt slots
- **Error handling**: Custom `VideoSplitterError` (core), `FFmpegError` (ffmpeg-skill); explicit `FileNotFoundError`/`ValueError` for input validation
- **Config**: `SplitConfig` as single dataclass; env vars override defaults
- **ASR engine**: Registry pattern — subclass `TranscriptionEngine`, register in `_ENGINE_REGISTRY`
- **Qt threading**: `QObject + moveToThread` pattern (NOT QThread subclass)
- **Sprint workflow**: 6-phase sprint via xp-gate; Delphi review for complex changes

## ANTI-PATTERNS (THIS PROJECT)

- **Don't commit `__pycache__/`, `.pyc`, `.ruff_cache/`, `.benchmarks/`** — gitignored
- **Don't mock Qt signals directly** — use qtbot or mock at engine/IO boundaries
- **Don't use relative imports between sibling packages** — `video_splitter` and `gui` are siblings; use absolute imports
- **Don't skip Delphi review for complex changes** — Gate MW requires code walkthrough before push
- **Don't write test files that require real video files** — use dummy/temp files

## COMMANDS

```bash
# Install deps
pip install -r requirements.txt

# CLI
python video_splitter/cli.py transcribe video.mp4
python video_splitter/cli.py split video.mp4 --max-duration 15
python video_splitter/cli.py gui

# Run all tests
python -m pytest tests/ video_splitter/tests/ ffmpeg-skill/tests.py -v

# Lint (ruff)
ruff check video_splitter/ gui/ tests/

# Quality gates (pre-commit)
xp-gate check .
```

## NOTES

- FFmpeg must be installed separately in PATH
- FunASR downloads ~1.8GB model on first use; first launch may take minutes
- PySide6 requires no separate Qt SDK install
- `tests/` (root) tests GUI workers/controllers; `video_splitter/tests/` tests core logic
- No CI/CD configured; all gates run locally via xp-gate pre-commit hook
- `ffmpeg-video-workspace/` is benchmark output, not source code
- Legacy docs: `PROJECT_SUMMARY.md`, `COMPLETION_REPORT.md`, `OPENCODE_SETUP.md`
