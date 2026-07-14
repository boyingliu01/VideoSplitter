# video_splitter — Core Application Package

## OVERVIEW

Smart video chaptering pipeline: audio extraction → ASR transcription → LLM chapter detection → validation → FFmpeg cutting. CLI-driven with configurable engines and a PySide6 GUI frontend.

## STRUCTURE

```
video_splitter/
├── cli.py            # argparse CLI (7 commands: split, transcribe, cut, check, review, gui, batch)
├── config.py         # SplitConfig — all tunables, env-driven
├── pipeline.py       # Pipeline.run(): orchestrates full flow with resume support
├── review.py         # TTY-based transcript review (load/save/export/sanitize)
├── extractor/
│   ├── audio.py      # AudioExtractor — FFmpeg audio extraction + quality pre-check
│   ├── engines.py    # TranscriptionEngine ABC + FunASR/Whisper implementations
│   └── transcribe.py # whisper transcription + SRT conversion + token estimation
├── analyzer/
│   ├── chapter.py    # ChapterDetector — LLM-based chapter detection with chunking fallback
│   └── validator.py  # ChapterValidator — boundary align, merge undersized, split oversized, name
├── splitter/
│   └── cutter.py     # VideoCutter — keyframe-aware FFmpeg cutting (fast/precise modes)
└── tests/            # Unit tests — chapter, review, transcribe, validator, pipeline, audio, cli, cutter (70+ tests)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add CLI command | `cli.py` — add subparser + handler function | Follow existing pattern |
| Add config field | `config.py:19` — add field to `SplitConfig` | Auto-picked by `from_env()` |
| Add ASR engine | `extractor/engines.py` — subclass `TranscriptionEngine`, register | ABC pattern |
| Change chapter detection | `analyzer/chapter.py` — `ChapterDetector.detect()` | Sliding-window fallback at L77 |
| Change validation rules | `analyzer/validator.py` — `ChapterValidator.validate()` | 4-step pipeline |
| Transcript IO | `review.py` — load/save/export/filter | All atomic writes |
| Video cutting | `splitter/cutter.py` — `VideoCutter.cut()` | Keyframe tolerance cfg |

## CONVENTIONS

- **Imports**: Absolute paths (`from video_splitter.xxx import ...`), never relative
- **Config**: `SplitConfig.from_env()` reads env vars; defaults in class body
- **Error types**: `VideoSplitterError` (from `__init__.py`) for domain errors; `FileNotFoundError`/`ValueError` for input validation
- **Progress callbacks**: Optional `Callable[[float, str], None]` on long operations
- **Testing**: Unit tests in `tests/` subpackage (70+ tests); use `tmp_path` for IO isolation, mock FFmpeg/LLM/ASR at boundaries
- **Running tests**: `python -m pytest tests/ video_splitter/tests/ -v` (167 tests, 66% coverage)
- **Coverage**: `python -m pytest --cov --cov-report=term-missing` — configured in `pyproject.toml` with `fail_under = 50`
- **CI**: `.github/workflows/test.yml` — runs on push/PR to master, Ubuntu + Python 3.12

## ANTI-PATTERNS

- **Don't import from `gui/`** — `video_splitter` is the core library; `gui` is a consumer
- **Don't use `from .xxx` relative imports** — absolute imports only
- **Don't suppress ASR errors silently** — surface via `VideoSplitterError` or signal
