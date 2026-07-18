# Changelog

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
