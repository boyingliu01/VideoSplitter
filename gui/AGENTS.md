# gui — PySide6 Desktop Application

## OVERVIEW

Phase A subtitle review GUI: video playback, background ASR transcription, interactive segment correction. PySide6 (Qt6), QObject+moveToThread pattern, MVC with signals.

## STRUCTURE

```
gui/
├── app.py                     # MainWindow + main() entry — menu, shortcuts, signal wiring
├── controllers/
│   └── review_controller.py   # ReviewController — state machine, segment navigation, progress persistence
├── widgets/
│   ├── video_player.py        # VideoPlayerWidget — QMediaPlayer + QVideoWidget + seek slider
│   ├── subtitle_panel.py      # SubtitlePanel — transcript display, correction edit, navigation buttons
│   └── status_bar.py          # StatusBarWidget — status text + progress display
└── workers/
    └── transcribe_worker.py   # TranscribeWorker — background ASR in QThread, signal-driven
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add menu item | `app.py:_build_menu()` | QAction + triggered.connect |
| Add keyboard shortcut | `app.py:_setup_shortcuts()` | Ctrl+key patterns |
| Change review flow | `controllers/review_controller.py` | Pure state machine, no Qt in tests |
| Change transcription UI | `app.py:_on_transcribe_*` + `workers/transcribe_worker.py` | Signal-driven progress |
| Add widget | `widgets/` — new file, add to `app.py:_build_central()` | Follow QWidget pattern |
| Fix video playback | `widgets/video_player.py` | Wraps QMediaPlayer |
| Transcript display | `widgets/subtitle_panel.py` | set_segment/set_correction/get_correction |

## CONVENTIONS

- **Threading**: `QObject` + `moveToThread(QThread)` — NEVER subclass QThread
- **Signals**: All cross-component communication via Qt signals (no direct method calls)
- **Imports**: `from video_splitter.xxx` (absolute) for core; `from gui.xxx` (absolute) internally
- **Signal naming**: Verb-past-tense (`position_changed`, `editing_started`); request signals (`prev_requested`, `save_next_requested`)
- **Type hints**: `QObject | None` for optionally-parented objects; `@Slot` decorators on worker methods
- **Testing**: Mock Qt at engine/IO boundaries; use `conftest.py` for `sys.path` setup

## ANTI-PATTERNS

- **Don't call widget internals from MainWindow** — use widget public APIs (e.g., `set_status()` not `._label.setText()`)
- **Don't access `QThread` from outside the worker** — use signals only
- **Don't create widgets without parents** — Qt parent-child manages lifecycle
- **Don't use `QThread` subclass** — always `QObject + moveToThread`
- **Don't import `gui` from `video_splitter`** — dependency direction is gui → video_splitter only
