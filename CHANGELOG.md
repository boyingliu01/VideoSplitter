# Changelog

## 0.5.1 (2026-07-20)

- Improve GUI startup responsiveness: move FunASR health check to background thread
- Add wait cursor and status bar feedback when loading video files
- Tests: 449 passed, all clean

## 0.5.0 (2026-07-20)

- Fix critical GUI wiring bugs: transcription result now correctly populates subtitle panel
- Fix `_on_transcribe_finished`: save transcript to disk, load into ReviewController, display first segment
- Fix `_on_open_transcript`: display first segment and pass transcript to SplitController
- Fix FunASR 1.3.14 model loading: use registered class name "Paraformer" with fallback chain
- Add GUI signal wiring integration tests (5 tests verifying end-to-end data flow)
- Add E2E test suite: CLI commands, review/export, edge cases, pipeline integration
- Add TranscribeWorker audio extraction step (was missing, causing RIFF header errors)
- Test count: 449+ tests, all passing

## 0.4.0 (2026-07-15)

- Test coverage raised from 71% to 88.91% (424 tests, all passing)
- New test_main_window.py: 38 tests covering MainWindow init, handlers, workflows
- Extended tests for split widgets, subtitle burn, CLI, and chapter detector
- Fixed all ruff lint warnings (F401, F841, F811)
- pyproject.toml: coverage fail_under 50 → 80, added E402 ignore for test files

## 0.3.0 (2026-07-15)

- Add subtitle burning feature: burn corrected subtitles into split video segments
- SubtitleBurner: per-chapter SRT generation with time-shifted timestamps
- BurnWorker: background QThread worker with cancel support
- GUI: "Burn Subtitles" button in Split panel, enabled after split completes
- 18 new tests for subtitle burning (SRT generation, burner, worker)

## 0.2.0 (2026-07-15)

- Add comprehensive unit test suite: 232 tests, 75%+ coverage
- Test coverage for Pipeline (dry_run, run), ChapterDetector (detect, chunked), Review (load/save/export)
- Test coverage for AudioExtractor, VideoCutter, TranscribeWorker, ReviewController
- Test coverage for CLI argument parsing and subcommand handlers
- Test coverage for GUI widgets (SubtitlePanel, VideoPlayerWidget, StatusBar)

## 0.1.0

- Initial release: CLI + GUI video chapter detection and splitting
