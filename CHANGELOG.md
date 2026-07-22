# Changelog

## 0.6.0 (2026-07-21)

- Add streaming/incremental ASR transcription for GUI:
  - New `StreamingTranscribeWorker`: transcribes in 30s chunks, emits segments incrementally
  - UI becomes interactive immediately after opening video (no more waiting minutes)
  - Audio extraction + model loading run in parallel
  - Per-chunk FFmpeg extraction avoids large memory usage
  - Seek priority: dragging the seek bar triggers priority transcription of target chunk
  - Deduplication prevents overlapping segments between chunks
  - GC every 3 chunks to manage memory
- Add `ReviewController.merge_segments()` for incremental segment insertion
  - Sorted insertion by start time, dedup against existing tail
  - Preserves user's current viewing position
  - New `segments_merged` signal for UI updates
- Add CT-Transformer punctuation model integration:
  - FunASR `punc_model` parameter adds punctuation to ASR output
  - Configurable via `VIDEO_SPLITTER_FUNASR_PUNC_MODEL` env var
  - Can be disabled by setting env var to empty/"0"/"false"/"none"
- Add `VideoPlayerWidget.seeked` signal for seek-to-chunk transcription
- Add `SubtitlePanel` transcription status display (initializing, recognizing N/M...)
- Fix space key shortcut: use `QShortcut` + `ApplicationShortcut` context so play/pause works even when focus is in QTextEdit
- Fix `_on_streaming_complete` preserves user corrections made during streaming
- Add `engines.py` new APIs: `load_funasr_model()`, `transcribe_file_chunk()`, `_extract_audio_range()`
- Tests: 462 passed (243 GUI + 219 core), all clean

## 0.5.4 (2026-07-21)

- Improve progress bar visibility and clarity:
  - Progress bar height increased from 16px to 22px for better visibility
  - Status label uses bold font for clearer readability
  - Progress descriptions now show step-by-step pipeline stages:
    - Step 1/3: Extracting audio from video...
    - Step 2/3: Loading speech recognition model...
    - Step 3/3: Transcribing audio to text...
  - Long audio transcription shows per-segment progress
  - Model loading warns user if first time (may take minutes)
- Tests: all GUI + core tests pass

## 0.5.3 (2026-07-21)

- Add visual progress bar to StatusBarWidget for better user feedback
- TranscribeWorker now emits granular progress phases:
  - Audio extraction (0-10%)
  - Model loading + transcription (10-100%)
- Status bar shows real-time progress percentage and description
- Progress bar hides automatically when transcription completes or fails
- Tests: 69 GUI tests passed

## 0.5.2 (2026-07-21)

- Fix FunASR segment extraction: support text+timestamp format (FunASR 1.3.x Paraformer)
- Previous code only looked for `sentence_info` key which doesn't exist in current FunASR version
- New logic merges word-level timestamps into sentence-level segments for better readability
- Clean up diagnostic logging, keep only essential info/error messages
- Tests: 449 passed, all clean

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
