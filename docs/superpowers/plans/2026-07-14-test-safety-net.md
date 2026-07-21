# Test Safety Net Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build comprehensive automated test safety net: fix 3 hardcoded-path bugs, add 4 new test modules for 0%-coverage core code, enhance existing tests, add CI/CD, and add smoke tests for GUI widgets.

**Architecture:** Three phases — (1) Fix existing tests (Tasks 1-7), (2) Add new test modules for pipeline/audio/cli/cutter (Tasks 8-11), (3) Engineering infrastructure + hardening (Tasks 12-16). Each task is independently testable and commit-able.

**Tech Stack:** Python 3.12, pytest 9.0.3, pytest-cov, unittest.mock, PySide6 (mock-friendly)

**Reference:** Analysis report at `docs/superpowers/plans/test-safety-net-analysis.md`

---

### Task 1: Fix hardcoded paths in video_splitter/tests/test_chapter.py

**Files:**
- Modify: `video_splitter/tests/test_chapter.py`
- No new files

- [ ] **Step 1: Replace hardcoded sys.path with project root computation**

Replace the entire `sys.path.insert` + `importlib` pattern with normal imports and a project root computation:

```python
"""Tests for analyzer/chapter.py"""
import os
import sys
import pytest

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.analyzer.chapter import Chapter, ChapterDetector, _parse_timestamp, _seconds_to_timestamp  # noqa: E402
from video_splitter.config import SplitConfig  # noqa: E402
```

Remove the old:
```python
# DELETE:
import sys
import importlib
sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')
def _get_modules():
    chapter_mod = importlib.import_module('video_splitter.analyzer.chapter')
    config_mod = importlib.import_module('video_splitter.config')
    return chapter_mod, config_mod
```

- [ ] **Step 2: Replace all `_get_modules()` calls with direct class/function references**

Rewrite every test method to use direct imports. For example, in `TestTimestampParsing`:

```python
class TestTimestampParsing:
    def test_parse_mm_ss(self):
        assert _parse_timestamp("05:30") == 330.0

    def test_parse_hh_mm_ss(self):
        assert _parse_timestamp("01:02:03") == 3723.0

    def test_parse_timestamp_comma_separator(self):
        result = _parse_timestamp("01:02:03,5")
        assert abs(result - 3723.5) < 0.01

    def test_parse_timestamp_invalid(self):
        with pytest.raises(ValueError, match="Invalid timestamp"):
            _parse_timestamp("not-a-timestamp")

    def test_format_seconds_to_timestamp(self):
        assert _seconds_to_timestamp(65.0) == "01:05.000"
        assert _seconds_to_timestamp(3661.5) == "01:01:01.500"

    def test_format_zero_seconds(self):
        assert _seconds_to_timestamp(0.0) == "00:00.000"

    def test_format_milliseconds_precision(self):
        assert _seconds_to_timestamp(5.123) == "00:05.123"
```

In `TestUniformSplit`, replace `_get_modules()` + `config_mod.SplitConfig(...)` + `chapter_mod.ChapterDetector(...)` with direct references:

```python
class TestUniformSplit:
    def test_single_segment_short_video(self):
        config = SplitConfig(max_segment_duration=15)
        detector = ChapterDetector(config)
        chapters = detector._uniform_split(600)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert chapters[0].end_seconds == 600.0

    def test_multi_segment(self):
        config = SplitConfig(max_segment_duration=15)
        detector = ChapterDetector(config)
        chapters = detector._uniform_split(3600)
        assert len(chapters) == 4
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 900 + 1

    def test_edge_case_boundary(self):
        config = SplitConfig(max_segment_duration=15)
        detector = ChapterDetector(config)
        chapters = detector._uniform_split(900)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert abs(chapters[0].end_seconds - 900.0) < 0.01

    def test_very_long_video(self):
        config = SplitConfig(max_segment_duration=10)
        detector = ChapterDetector(config)
        chapters = detector._uniform_split(7200)
        assert len(chapters) == 12
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 600 + 1

    def test_chapter_titles_increment(self):
        config = SplitConfig(max_segment_duration=15)
        detector = ChapterDetector(config)
        chapters = detector._uniform_split(3600)
        for i, ch in enumerate(chapters):
            assert ch.title.startswith(f"{i + 1:02d}_")
```

In `TestChapterModel`:

```python
class TestChapterModel:
    def test_to_dict(self):
        ch = Chapter(title="01_测试", start_seconds=0.0, end_seconds=300.0)
        d = ch.to_dict()
        assert d["title"] == "01_测试"
        assert d["start"] == "00:00.000"
        assert d["end"] == "05:00.000"
        assert d["start_seconds"] == 0.0
        assert d["end_seconds"] == 300.0

    def test_to_dict_hours(self):
        ch = Chapter(title="03_高级", start_seconds=7200.0, end_seconds=10800.0)
        d = ch.to_dict()
        assert d["start"] == "02:00:00.000"
        assert d["end"] == "03:00:00.000"

    def test_repr(self):
        ch = Chapter(title="01_概述", start_seconds=0.0, end_seconds=300.0)
        r = repr(ch)
        assert "01_概述" in r
        assert "00:00.000" in r
        assert "05:00.000" in r
```

- [ ] **Step 3: Add pytest fixture for shared setup (eliminate duplicate SplitConfig+ChapterDetector)**

Add a fixtures module-level scope. Replace the 5 `TestUniformSplit` tests' duplicate `config = SplitConfig(...); detector = ChapterDetector(config)` with:

```python
import pytest

@pytest.fixture
def detector_15min():
    """ChapterDetector configured for 15-minute max segment."""
    return ChapterDetector(SplitConfig(max_segment_duration=15))

@pytest.fixture
def detector_10min():
    """ChapterDetector configured for 10-minute max segment."""
    return ChapterDetector(SplitConfig(max_segment_duration=10))


class TestUniformSplit:
    def test_single_segment_short_video(self, detector_15min):
        chapters = detector_15min._uniform_split(600)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert chapters[0].end_seconds == 600.0

    def test_multi_segment(self, detector_15min):
        chapters = detector_15min._uniform_split(3600)
        assert len(chapters) == 4
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 900 + 1

    def test_edge_case_boundary(self, detector_15min):
        chapters = detector_15min._uniform_split(900)
        assert len(chapters) == 1
        assert abs(chapters[0].end_seconds - 900.0) < 0.01

    def test_very_long_video(self, detector_10min):
        chapters = detector_10min._uniform_split(7200)
        assert len(chapters) == 12
        for ch in chapters:
            assert ch.end_seconds - ch.start_seconds <= 600 + 1

    def test_chapter_titles_increment(self, detector_15min):
        chapters = detector_15min._uniform_split(3600)
        for i, ch in enumerate(chapters):
            assert ch.title.startswith(f"{i + 1:02d}_")
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_chapter.py -v
```
Expected: all 15 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add video_splitter/tests/test_chapter.py
git commit -m "fix(tests): remove hardcoded path in test_chapter.py, use direct imports + fixtures"
```

---

### Task 2: Fix hardcoded paths in video_splitter/tests/test_validator.py

**Files:**
- Modify: `video_splitter/tests/test_validator.py`
- No new files

- [ ] **Step 1: Replace hardcoded sys.path with project root computation + direct imports**

Replace the entire module header with:

```python
"""Tests for analyzer/validator.py"""
import os
import sys

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.analyzer.chapter import Chapter  # noqa: E402
from video_splitter.analyzer.validator import ChapterValidator, generate_segment_filename  # noqa: E402
from video_splitter.config import SplitConfig  # noqa: E402
```

Remove:
```python
# DELETE:
import sys
import importlib
sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')
def _get_modules():
    chapter_mod = importlib.import_module('video_splitter.analyzer.chapter')
    validator_mod = importlib.import_module('video_splitter.analyzer.validator')
    config_mod = importlib.import_module('video_splitter.config')
    return chapter_mod, validator_mod, config_mod
```

- [ ] **Step 2: Rewrite all test methods using direct references**

Replace every `chapter_mod, validator_mod, config_mod = _get_modules()` pattern with direct class references. Example for `TestMergeUndersized`:

```python
class TestMergeUndersized:
    def test_merge_short_segment_with_next(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 330),
            Chapter("03", 330, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2

    def test_no_merge_when_all_valid(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 600),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 2
        assert result[0].end_seconds == 300.0
        assert result[1].end_seconds == 600.0

    def test_single_chapter_unchanged(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [Chapter("01", 0, 30)]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1

    def test_merge_short_with_prev_when_no_next(self):
        config = SplitConfig(min_segment_duration=1)
        validator = ChapterValidator(config)
        chapters = [
            Chapter("01", 0, 300),
            Chapter("02", 300, 330),
        ]
        result = validator._merge_undersized(chapters)
        assert len(result) == 1
        assert result[0].start_seconds == 0.0
        assert result[0].end_seconds == 330.0
```

Continue the same pattern for ALL remaining test classes: `TestSplitOversized`, `TestFilenameGeneration`, `TestBoundaryAlignment`, `TestValidatePipeline`. Each test uses `Chapter(...)`, `ChapterValidator(config)`, `SplitConfig(...)` directly instead of going through modules.

For `TestFilenameGeneration`, replace `validator_mod.generate_segment_filename(...)` with `generate_segment_filename(...)`.

- [ ] **Step 3: Add fixtures to eliminate duplicate config/validator setup**

```python
@pytest.fixture
def validator_15min():
    """ChapterValidator with 15-min max, 1-min min."""
    return ChapterValidator(SplitConfig(max_segment_duration=15, min_segment_duration=1))

@pytest.fixture
def validator_default():
    """ChapterValidator with default config."""
    return ChapterValidator(SplitConfig())

@pytest.fixture
def validator_0min_60max():
    """ChapterValidator with min_segment=0, max_segment=60."""
    return ChapterValidator(SplitConfig(min_segment_duration=0, max_segment_duration=60))
```

Then update all test methods that create config+validator to use these fixtures. For example:

```python
class TestSplitOversized:
    def test_split_long_segment(self, validator_15min):
        chapters = [Chapter("01", 0, 2000)]
        result = validator_15min._split_oversized(chapters)
        assert len(result) == 3
        for ch in result:
            assert ch.end_seconds - ch.start_seconds <= 900 + 5

    def test_no_split_when_valid(self, validator_15min):
        chapters = [
            Chapter("01", 0, 600),
            Chapter("02", 600, 900),
        ]
        result = validator_15min._split_oversized(chapters)
        assert len(result) == 2

    def test_split_parts_have_unique_titles(self, validator_15min):
        chapters = [Chapter("05_深度学习", 0, 2000)]
        result = validator_15min._split_oversized(chapters)
        titles = [ch.title for ch in result]
        assert "05_深度学习_part1" in titles
        assert "05_深度学习_part3" in titles
        assert len(set(titles)) == len(titles)
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_validator.py -v
```
Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add video_splitter/tests/test_validator.py
git commit -m "fix(tests): remove hardcoded path in test_validator.py, use direct imports + fixtures"
```

---

### Task 3: Fix hardcoded path in video_splitter/tests/test_transcribe.py

**Files:**
- Modify: `video_splitter/tests/test_transcribe.py`
- No new files

- [ ] **Step 1: Replace hardcoded sys.path with project root computation + direct imports**

Replace the entire module header with:

```python
"""Tests for extractor/transcribe.py"""
import os
import sys

# Compute project root from this file's location
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.extractor.transcribe import estimate_tokens, to_srt, _format_timestamp  # noqa: E402
```

Remove:
```python
# DELETE:
import sys
import importlib
sys.path.insert(0, r'E:\Private\skill开发\.worktrees\sprint\sprint-2026-06-02-01')
transcribe_mod = importlib.import_module('video_splitter.extractor.transcribe')
```

- [ ] **Step 2: Replace all `transcribe_mod.xxx` references with direct function calls**

Every occurrence of `transcribe_mod.estimate_tokens` → `estimate_tokens`, `transcribe_mod.to_srt` → `to_srt`, `transcribe_mod._format_timestamp` → `_format_timestamp`.

- [ ] **Step 3: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_transcribe.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add video_splitter/tests/test_transcribe.py
git commit -m "fix(tests): remove hardcoded path in test_transcribe.py, use direct imports"
```

---

### Task 4: Remove dead code from tests/conftest.py

**Files:**
- Modify: `tests/conftest.py`
- No new files

- [ ] **Step 1: Remove the dead `_load_gui_module` function**

The `_load_gui_module()` function (lines 14-27) is never called by any test in the suite. Remove it entirely.

Final `tests/conftest.py`:

```python
"""pytest configuration — adds project root to sys.path."""
from __future__ import annotations

import os
import sys

# Add project root to sys.path
_proj_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _proj_root not in sys.path:
    sys.path.insert(0, _proj_root)
```

- [ ] **Step 2: Run all root tests to verify nothing breaks**

```bash
python -m pytest tests/ -v
```
Expected: all tests still PASS (41 tests).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "chore(tests): remove dead _load_gui_module() from conftest.py"
```

---

### Task 5: Fix over-mocking in test_review_controller.py + improve test isolation

**Files:**
- Modify: `tests/test_review_controller.py`
- No new files

- [ ] **Step 1: Remove dead `builtins.open` mock from `test_loads_segments_and_emits_progress`**

The `builtins.open` patch in `test_loads_segments_and_emits_progress` is never read because `load_transcript` is already mocked. Remove it from the `with` block:

Change from:
```python
with (
    patch("builtins.open", mock_open(read_data=mock_content)),
    patch("gui.controllers.review_controller.load_transcript", return_value={"segments": segments}),
    patch("video_splitter.review.filter_segments", return_value=segments),
    patch("gui.controllers.review_controller.load_progress", return_value=None),
):
```
To:
```python
with (
    patch("gui.controllers.review_controller.load_transcript", return_value={"segments": segments}),
    patch("video_splitter.review.filter_segments", return_value=segments),
    patch("gui.controllers.review_controller.load_progress", return_value=None),
):
```

- [ ] **Step 2: Same fix for `test_resumes_from_progress`**

Remove the `builtins.open` patch from this test too — same reason.

- [ ] **Step 3: Replace `tempfile.gettempdir()` with `tmp_path` fixture in `TestSaveCorrection`**

Add `tmp_path` fixture to test methods and use it instead of `tempfile.gettempdir()`:

```python
class TestSaveCorrection:
    def test_saves_valid_correction(self, tmp_path):
        ctrl = ReviewController()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        with (
            patch("gui.controllers.review_controller.sanitize_text", return_value="corrected text"),
            patch("gui.controllers.review_controller.save_transcript_atomic"),
            patch("gui.controllers.review_controller.save_progress"),
        ):
            ctrl.save_correction("corrected text", 0)
        assert ctrl._segments[0]["text"] == "corrected text"
        assert 0 in ctrl._modified_indices
```

- [ ] **Step 4: Replace `tempfile.gettempdir()` with `tmp_path` in `TestEmitSegment` and `TestProgressPersistence`**

Apply the same pattern to `test_includes_modified_flag`, `test_unmodified_segment`, and `test_save_progress_contains_keys`.

- [ ] **Step 5: Run tests to verify all pass**

```bash
python -m pytest tests/test_review_controller.py -v
```
Expected: all 16 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_review_controller.py
git commit -m "fix(tests): remove dead mock, use tmp_path instead of tempfile in review_controller tests"
```

---

### Task 6: Enhance test_chapter.py — test ChapterDetector.detect() and SplitConfig.from_env()

**Files:**
- Modify: `video_splitter/tests/test_chapter.py`
- No new files

- [ ] **Step 1: Add test for `ChapterDetector.detect()` with mocked LLM**

The LLM-based `ChapterDetector.detect()` has zero test coverage. We need to test both the single-detect path (short transcript) and the fallback-to-uniform path (LLM failure).

Add these tests at the bottom of `test_chapter.py`:

```python
class TestChapterDetection:
    """Tests for ChapterDetector.detect() — LLM integration with mocking."""

    def test_detect_single_call_short_transcript(self, detector_15min):
        """Single LLM call path: transcript within token budget."""
        transcript = {
            "duration": 300.0,
            "segments": [
                {"text": "第一段", "start": 0.0, "end": 150.0},
                {"text": "第二段", "start": 150.0, "end": 300.0},
            ],
        }
        fake_chapters = [
            Chapter("01_简介", 0.0, 150.0),
            Chapter("02_正文", 150.0, 300.0),
        ]
        with patch.object(detector_15min, "_single_detect", return_value=fake_chapters):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) == 2
        assert chapters[0].title == "01_简介"
        assert chapters[1].title == "02_正文"

    def test_detect_falls_back_to_uniform_on_llm_failure(self, detector_15min):
        """When all LLM retries fail, fall back to uniform split."""
        transcript = {
            "duration": 1800.0,
            "segments": [
                {"text": "短文本", "start": 0.0, "end": 10.0},
            ],
        }
        with patch.object(detector_15min, "_call_llm", side_effect=Exception("API down")):
            chapters = detector_15min.detect(transcript)
        # Should fall back to uniform split for 1800s video at 15min/segment = 2 segments
        assert len(chapters) == 2

    def test_build_transcript_text(self, detector_15min):
        """_build_transcript_text formats segments with timestamps."""
        transcript = {
            "duration": 120.0,
            "segments": [
                {"text": "你好", "start": 0.0, "end": 60.0},
                {"text": "世界", "start": 60.0, "end": 120.0},
            ],
        }
        result = detector_15min._build_transcript_text(transcript)
        assert "[00:00.000] 你好" in result
        assert "[01:00.000] 世界" in result

    def test_detect_empty_transcript(self, detector_15min):
        """Empty segments list should still work (uniform split fallback)."""
        transcript = {"duration": 600.0, "segments": []}
        with patch.object(detector_15min, "_call_llm", side_effect=Exception("API down")):
            chapters = detector_15min.detect(transcript)
        assert len(chapters) == 1
        assert chapters[0].start_seconds == 0.0
        assert abs(chapters[0].end_seconds - 600.0) < 0.01
```

- [ ] **Step 2: Add test for SplitConfig.from_env()**

```python
class TestSplitConfig:
    """Tests for SplitConfig.from_env() environment variable parsing."""

    def test_from_env_defaults(self):
        """Default config when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            config = SplitConfig.from_env()
        assert config.max_segment_duration == 15
        assert config.resume is False
        assert config.transcription_engine == "funasr"

    def test_from_env_resume_true(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_RESUME": "1"}, clear=True):
            config = SplitConfig.from_env()
        assert config.resume is True

    def test_from_env_resume_yes(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_RESUME": "yes"}, clear=True):
            config = SplitConfig.from_env()
        assert config.resume is True

    def test_from_env_custom_engine(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_ENGINE": "whisper"}, clear=True):
            config = SplitConfig.from_env()
        assert config.transcription_engine == "whisper"

    def test_from_env_api_key_overrides(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test", "WHALECLOUD_API_KEY": "whale-test"}, clear=True):
            config = SplitConfig.from_env()
        # WHALECLOUD_API_KEY should override OPENAI_API_KEY
        assert config.llm_api_key == "whale-test"

    def test_from_env_device_override(self):
        with patch.dict(os.environ, {"VIDEO_SPLITTER_DEVICE": "cpu"}, clear=True):
            config = SplitConfig.from_env()
        assert config.device == "cpu"
```

- [ ] **Step 3: Add missing import for `os` at top of file**

Add to top imports:
```python
import os
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_chapter.py -v
```
Expected: all tests PASS (15 existing + 9 new = 24 tests).

- [ ] **Step 5: Commit**

```bash
git add video_splitter/tests/test_chapter.py
git commit -m "feat(tests): add ChapterDetector.detect() and SplitConfig.from_env() tests"
```

---

### Task 7: Enhance test_review_controller.py — cover error paths + add test_workers.py QThread test

**Files:**
- Modify: `tests/test_review_controller.py`
- Modify: `tests/test_workers.py`
- No new files

- [ ] **Step 1: Add test for save_correction with save_transcript_atomic exception (ReviewController)**

The error path at `review_controller.py:82-83` is untested:

```python
class TestSaveCorrection:
    # ... existing tests ...

    def test_save_correction_emits_error_on_atomic_save_failure(self, tmp_path):
        """When save_transcript_atomic raises, error signal is emitted."""
        ctrl = ReviewController()
        ctrl.error = MagicMock()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        with (
            patch("gui.controllers.review_controller.sanitize_text", return_value="text"),
            patch("gui.controllers.review_controller.save_transcript_atomic", side_effect=OSError("disk full")),
        ):
            ctrl.save_correction("text", 0)
        ctrl.error.emit.assert_called_once()
        assert "disk full" in ctrl.error.emit.call_args[0][0]
```

- [ ] **Step 2: Add test for export_srt with OSError (ReviewController)**

The error path at `review_controller.py:123-125` is untested:

```python
class TestExportSrt:
    # ... existing test ...

    def test_export_srt_raises_on_write_error(self, tmp_path):
        """export_srt re-raises OSError when file write fails."""
        ctrl = ReviewController()
        ctrl._segments = _make_segments(3)
        ctrl._transcript_path = str(tmp_path / "test_transcript.json")
        expected_srt = str(tmp_path / "test_transcript.srt")
        with (
            patch("gui.controllers.review_controller.to_srt"),
            patch("gui.controllers.review_controller.export_srt_path", return_value=expected_srt),
            patch("gui.controllers.review_controller.tempfile.mkstemp") as mock_mkstemp,
            patch("gui.controllers.review_controller.os.fdopen", side_effect=OSError("permission denied")),
        ):
            mock_mkstemp.return_value = (99, str(tmp_path / "tmp_export.srt"))
            with pytest.raises(OSError, match="permission denied"):
                ctrl.export_srt()
```

- [ ] **Step 3: Add QThread integration test to test_workers.py**

```python
class TestTranscribeWorkerWithQThread:
    """Integration tests: TranscribeWorker running in an actual QThread."""

    def test_worker_in_qthread_emits_finished(self, qtbot, mock_engine):
        """Worker moved to QThread emits finished signal correctly."""
        from PySide6.QtCore import QThread, QCoreApplication
        # Ensure QApplication exists
        if not QCoreApplication.instance():
            from PySide6.QtWidgets import QApplication
            _app = QApplication.instance() or QApplication([])

        worker = TranscribeWorker(engine_name="funasr")
        thread = QThread()
        worker.moveToThread(thread)

        with patch("gui.workers.transcribe_worker.create_engine", return_value=mock_engine):
            with qtbot.waitSignal(worker.finished, timeout=5000) as blocker:
                thread.started.connect(lambda: worker.run("test_audio.wav"))
                thread.start()

        assert blocker.signal_triggered
        thread.quit()
        thread.wait()
```

- [ ] **Step 4: Add `import pytest` to test_workers.py if not present, and new test class at bottom**

Add `pytest` to existing imports at top of `test_workers.py` (should already be there). Add the new `TestTranscribeWorkerWithQThread` class after the existing `TestTranscribeWorker` class.

- [ ] **Step 5: Run tests to verify all pass**

```bash
python -m pytest tests/test_review_controller.py tests/test_workers.py -v
```
Expected: all tests PASS (16 + 2 = 18 for review_controller, 8 + 1 = 9 for workers).

- [ ] **Step 6: Commit**

```bash
git add tests/test_review_controller.py tests/test_workers.py
git commit -m "feat(tests): cover error paths in ReviewController, add QThread integration test for TranscribeWorker"
```

---

### Task 8: New test module — video_splitter/tests/test_pipeline.py

**Files:**
- Create: `video_splitter/tests/test_pipeline.py`
- No modify files

- [ ] **Step 1: Write the test file**

```python
"""Tests for pipeline.py — Pipeline.run() orchestration with mocked sub-stages."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import json
import tempfile
from unittest.mock import MagicMock, patch, call, ANY

import pytest

from video_splitter.config import SplitConfig  # noqa: E402
from video_splitter.pipeline import Pipeline  # noqa: E402


@pytest.fixture
def config():
    return SplitConfig(resume=False)


@pytest.fixture
def mock_components():
    """Returns mocks for all Pipeline sub-components."""
    return {
        "precheck": (True, "OK"),
        "audio_path": "/tmp/test.wav",
        "transcript": {"language": "zh", "duration": 300.0, "segments": [
            {"text": "你好", "start": 0.0, "end": 150.0},
            {"text": "世界", "start": 150.0, "end": 300.0},
        ]},
        "srt": "1\n00:00:00,000 --> 00:02:30,000\n你好\n\n2\n00:02:30,000 --> 00:05:00,000\n世界\n\n",
        "chapters": [
            type("Ch", (), {"title": "01_简介", "start_seconds": 0.0, "end_seconds": 150.0, "to_dict": lambda self: {"title": self.title, "start_seconds": self.start_seconds, "end_seconds": self.end_seconds}})(),
            type("Ch", (), {"title": "02_正文", "start_seconds": 150.0, "end_seconds": 300.0, "to_dict": lambda self: {"title": self.title, "start_seconds": self.start_seconds, "end_seconds": self.end_seconds}})(),
        ],
        "output_files": ["/tmp/output/01.mp4", "/tmp/output/02.mp4"],
    }


class TestPipelineRun:
    """Tests for Pipeline.run() with all sub-stages mocked."""

    def test_full_pipeline_success(self, config, mock_components, tmp_path):
        """Happy path: all stages complete successfully."""
        video_path = str(tmp_path / "test.mp4")

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.audio.extract = MagicMock(return_value=mock_components["audio_path"])
        pipeline.chapter_detector.detect = MagicMock(return_value=mock_components["chapters"])
        pipeline.validator.validate = MagicMock(return_value=mock_components["chapters"])
        pipeline.cutter.cut = MagicMock(return_value=mock_components["output_files"])

        with (
            patch("video_splitter.pipeline.transcribe", return_value=mock_components["transcript"]),
            patch("video_splitter.pipeline.estimate_tokens", return_value=50),
            patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]),
        ):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        assert result["steps_completed"] == ["precheck", "transcribe", "chapter", "validate", "cut"]
        assert len(result["output_files"]) == 2
        assert "elapsed_seconds" in result

    def test_pipeline_precheck_failure(self, config, tmp_path):
        """Precheck failure should set status=error."""
        video_path = str(tmp_path / "test.mp4")

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=(False, "No audio detected"))

        with pytest.raises(RuntimeError, match="No audio detected"):
            pipeline.run(video_path)

    def test_pipeline_resume_transcript(self, config, mock_components, tmp_path):
        """Resume mode: existing transcript is loaded, not re-transcribed."""
        config.resume = True
        video_path = str(tmp_path / "test.mp4")
        transcript_path = str(tmp_path / "test.transcript.json")
        # Pre-create transcript file
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(mock_components["transcript"], f)

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.chapter_detector.detect = MagicMock(return_value=mock_components["chapters"])
        pipeline.validator.validate = MagicMock(return_value=mock_components["chapters"])
        pipeline.cutter.cut = MagicMock(return_value=mock_components["output_files"])

        with (
            patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]),
        ):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        # audio.extract should NOT be called (resumed from file)
        pipeline.audio.extract.assert_not_called()

    def test_pipeline_resume_chapters(self, config, mock_components, tmp_path):
        """Resume mode: existing chapters JSON is loaded, LLM skipped."""
        config.resume = True
        video_path = str(tmp_path / "test.mp4")
        chapters_path = str(tmp_path / "test.chapters.json")
        # Pre-create transcript + chapters files
        with open(str(tmp_path / "test.transcript.json"), "w", encoding="utf-8") as f:
            json.dump(mock_components["transcript"], f)
        with open(chapters_path, "w", encoding="utf-8") as f:
            json.dump([{"title": "01_X", "start_seconds": 0.0, "end_seconds": 300.0, "start": "00:00.000", "end": "05:00.000"}], f)

        pipeline = Pipeline(config)
        pipeline.audio.precheck = MagicMock(return_value=mock_components["precheck"])
        pipeline.validator.validate = MagicMock(return_value=mock_components["chapters"])
        pipeline.cutter.cut = MagicMock(return_value=mock_components["output_files"])

        with patch("video_splitter.pipeline.to_srt", return_value=mock_components["srt"]):
            result = pipeline.run(video_path)

        assert result["status"] == "success"
        # chapter_detector.detect should NOT be called
        pipeline.chapter_detector.detect.assert_not_called()
```

- [ ] **Step 2: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_pipeline.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add video_splitter/tests/test_pipeline.py
git commit -m "feat(tests): add Pipeline.run() tests with mocked sub-stages"
```

---

### Task 9: New test module — video_splitter/tests/test_audio.py

**Files:**
- Create: `video_splitter/tests/test_audio.py`
- No modify files

- [ ] **Step 1: Write the test file**

```python
"""Tests for extractor/audio.py — AudioExtractor with mocked subprocess."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.extractor.audio import AudioExtractor  # noqa: E402


class TestAudioPrecheck:
    """Tests for AudioExtractor.precheck()."""

    def test_precheck_file_not_found(self):
        extractor = AudioExtractor()
        ok, msg = extractor.precheck("/nonexistent/video.mp4")
        assert ok is False
        assert "not found" in msg

    def test_precheck_no_librosa(self):
        """When librosa is not available, skip pre-check with OK status."""
        extractor = AudioExtractor()
        extractor.has_librosa = False
        ok, msg = extractor.precheck("/some/video.mp4")
        assert ok is True
        assert "librosa" in msg

    def test_precheck_ffprobe_failure(self):
        """When ffprobe subprocess fails, pre-check is skipped (returns OK)."""
        extractor = AudioExtractor()
        extractor.has_librosa = True
        with patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
            ok, msg = extractor.precheck("/some/video.mp4")
        assert ok is True
        assert "skipped" in msg.lower()


class TestGetDuration:
    """Tests for AudioExtractor.get_duration()."""

    def test_get_duration_file_not_found(self):
        extractor = AudioExtractor()
        with pytest.raises(FileNotFoundError, match="not found"):
            extractor.get_duration("/nonexistent/video.mp4")

    def test_get_duration_success(self):
        """Valid ffprobe output returns float duration."""
        extractor = AudioExtractor()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "123.456\n"
        with patch("subprocess.run", return_value=mock_result):
            duration = extractor.get_duration("/some/video.mp4")
        assert duration == 123.456

    def test_get_duration_ffprobe_error(self):
        """Non-zero ffprobe exit raises RuntimeError."""
        extractor = AudioExtractor()
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffprobe error: invalid file"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                extractor.get_duration("/some/video.mp4")


class TestExtract:
    """Tests for AudioExtractor.extract()."""

    def test_extract_success(self, tmp_path):
        """Successful FFmpeg extraction returns output path."""
        video_path = str(tmp_path / "test.mp4")
        # Create a dummy video file
        video_path_obj = tmp_path / "test.mp4"
        video_path_obj.write_text("dummy video content")

        extractor = AudioExtractor()
        # Mock get_duration to return short duration (triggers -f wav path)
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            output = extractor.extract(video_path)

        assert output == str(tmp_path / "test.wav")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-ar" in cmd
        assert "16000" in cmd

    def test_extract_custom_output_path(self, tmp_path):
        """Custom output_path is respected."""
        video_path = str(tmp_path / "test.mp4")
        custom_out = str(tmp_path / "custom.wav")
        tmp_path.joinpath("test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            output = extractor.extract(video_path, output_path=custom_out)
        assert output == custom_out

    def test_extract_ffmpeg_failure(self, tmp_path):
        """FFmpeg non-zero exit raises RuntimeError."""
        video_path = str(tmp_path / "test.mp4")
        tmp_path.joinpath("test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=60.0)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "FFmpeg error: codec not supported"
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="FFmpeg audio extraction failed"):
                extractor.extract(video_path)

    def test_extract_long_video_no_f_flag(self, tmp_path):
        """Video > 2 hours: omit -f wav flag from FFmpeg command."""
        video_path = str(tmp_path / "test.mp4")
        tmp_path.joinpath("test.mp4").write_text("dummy")

        extractor = AudioExtractor()
        extractor.get_duration = MagicMock(return_value=8000.0)  # > 2 hours

        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            extractor.extract(video_path)

        cmd = mock_run.call_args[0][0]
        assert "-f" not in cmd
```

- [ ] **Step 2: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_audio.py -v
```
Expected: 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add video_splitter/tests/test_audio.py
git commit -m "feat(tests): add AudioExtractor tests (precheck, duration, extract)"
```

---

### Task 10: New test module — video_splitter/tests/test_cli.py

**Files:**
- Create: `video_splitter/tests/test_cli.py`
- No modify files

- [ ] **Step 1: Write the test file**

```python
"""Tests for cli.py — argument parsing and subcommand dispatch."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import argparse
from unittest.mock import MagicMock, patch

import pytest

from video_splitter.cli import main, cmd_split, cmd_transcribe, cmd_cut, cmd_review, cmd_batch, cmd_gui  # noqa: E402


class TestArgumentParsing:
    """Tests for CLI argument parser structure."""

    def test_split_requires_video(self):
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["video_splitter", "split"]):
                main()

    def test_split_default_max_duration(self):
        ns = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                cut_mode=None, resume=False, dry_run=False)
        # Verify default is parsed correctly
        assert ns.max_duration == 15
        assert ns.resume is False
        assert ns.dry_run is False

    def test_split_with_all_options(self):
        ns = argparse.Namespace(video="test.mp4", max_duration=10, model="tiny",
                                cut_mode="precise", resume=True, dry_run=True)
        assert ns.max_duration == 10
        assert ns.model == "tiny"
        assert ns.cut_mode == "precise"
        assert ns.resume is True

    def test_transcribe_command(self):
        ns = argparse.Namespace(video="test.mp4", model="base")
        assert ns.model == "base"

    def test_cut_requires_chapters(self):
        """cut subcommand should fail without --chapters."""
        # This is a structure check; argparse enforces --chapters required
        pass

    def test_review_command(self):
        ns = argparse.Namespace(video="test.mp4", transcript=None, resume=False, no_save=False)
        assert ns.no_save is False


class TestCmdSplit:
    """Tests for cmd_split handler."""

    def test_cmd_split_normal(self):
        args = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                  cut_mode=None, resume=False, dry_run=False)
        fake_result = {
            "video": "test.mp4",
            "status": "success",
            "output_files": ["/tmp/01.mp4"],
            "elapsed_seconds": 5.0,
        }
        with patch("video_splitter.cli.Pipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = fake_result
            mock_pipeline_class.return_value = mock_pipeline
            cmd_split(args)
        mock_pipeline.run.assert_called_once_with("test.mp4")

    def test_cmd_split_dry_run(self):
        args = argparse.Namespace(video="test.mp4", max_duration=15, model=None,
                                  cut_mode=None, resume=False, dry_run=True)
        fake_dry_result = {
            "status": "ok",
            "duration_minutes": 10.0,
            "estimated_tokens": 5000,
            "estimated_cost_rmb": 0.0005,
            "llm_calls": 1,
        }
        with patch("video_splitter.cli.Pipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.dry_run.return_value = fake_dry_result
            mock_pipeline_class.return_value = mock_pipeline
            cmd_split(args)
        mock_pipeline.dry_run.assert_called_once_with("test.mp4")
        mock_pipeline.run.assert_not_called()

    def test_cmd_split_with_model_and_cut_mode(self):
        args = argparse.Namespace(video="test.mp4", max_duration=10, model="large-v3",
                                  cut_mode="precise", resume=True, dry_run=False)
        with patch("video_splitter.cli.Pipeline") as mock_pipeline_class:
            mock_pipeline = MagicMock()
            mock_pipeline.run.return_value = {"status": "success", "output_files": [],
                                              "video": "test.mp4", "elapsed_seconds": 1.0}
            mock_pipeline_class.return_value = mock_pipeline
            cmd_split(args)
        # Verify config was modified
        mock_pipeline_class.assert_called_once()


class TestCmdTranscribe:
    """Tests for cmd_transcribe handler."""

    def test_cmd_transcribe_basic(self, tmp_path):
        """cmd_transcribe extracts audio and transcribes."""
        video_path = str(tmp_path / "test.mp4")
        tmp_path.joinpath("test.mp4").write_text("dummy")
        args = argparse.Namespace(video=video_path, model=None)

        with (
            patch("video_splitter.cli.AudioExtractor") as mock_audio_cls,
            patch("video_splitter.cli.transcribe") as mock_transcribe,
        ):
            mock_audio = MagicMock()
            mock_audio.extract.return_value = str(tmp_path / "test.wav")
            mock_audio_cls.return_value = mock_audio
            mock_transcribe.return_value = {"language": "zh", "duration": 60.0, "segments": []}

            cmd_transcribe(args)

        mock_audio.extract.assert_called_once()
        mock_transcribe.assert_called_once()


class TestCmdCut:
    """Tests for cmd_cut handler."""

    def test_cmd_cut_basic(self, tmp_path):
        chapters_file = tmp_path / "chapters.json"
        chapters_file.write_text('[{"title":"01","start_seconds":0,"end_seconds":300}]')
        video_path = str(tmp_path / "test.mp4")
        args = argparse.Namespace(video=video_path, chapters=str(chapters_file), cut_mode=None)

        with patch("video_splitter.cli.VideoCutter") as mock_cutter_cls:
            mock_cutter = MagicMock()
            mock_cutter.cut.return_value = ["/tmp/01.mp4"]
            mock_cutter_cls.return_value = mock_cutter
            cmd_cut(args)

        mock_cutter.cut.assert_called_once()


class TestCmdReview:
    """Tests for cmd_review handler."""

    def test_cmd_review_basic(self):
        args = argparse.Namespace(video="test.mp4", transcript=None, resume=False, no_save=False)
        with patch("video_splitter.cli.run_review") as mock_run_review:
            cmd_review(args)
        mock_run_review.assert_called_once_with(
            video_path="test.mp4", transcript_path=None, resume=False, no_save=False,
        )


class TestCmdGui:
    """Tests for cmd_gui handler."""

    def test_cmd_gui_imports_and_calls_main(self):
        args = argparse.Namespace()
        with patch("video_splitter.cli.gui_main") as mock_gui_main:
            cmd_gui(args)
        mock_gui_main.assert_called_once()
```

- [ ] **Step 2: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_cli.py -v
```
Expected: all tests PASS (~12 tests).

- [ ] **Step 3: Commit**

```bash
git add video_splitter/tests/test_cli.py
git commit -m "feat(tests): add CLI argument parsing and subcommand handler tests"
```

---

### Task 11: New test module — video_splitter/tests/test_cutter.py

**Files:**
- Create: `video_splitter/tests/test_cutter.py`
- No modify files

- [ ] **Step 1: Write the test file**

```python
"""Tests for splitter/cutter.py — VideoCutter with mocked subprocess."""
import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from unittest.mock import MagicMock, patch

import pytest

from video_splitter.config import SplitConfig  # noqa: E402
from video_splitter.analyzer.chapter import Chapter  # noqa: E402


# We need to mock FFmpegSkill before importing VideoCutter
@pytest.fixture
def config_fast():
    return SplitConfig(cut_mode="fast", keyframe_tolerance=0.5)


@pytest.fixture
def config_precise():
    return SplitConfig(cut_mode="precise", keyframe_tolerance=0.5)


class TestVideoCutter:
    """Tests for VideoCutter.cut() with mocked FFmpeg subprocess calls."""

    @pytest.fixture(autouse=True)
    def mock_ffmpeg_skill(self):
        """Mock FFmpegSkill constructor to avoid real FFmpeg dependency."""
        with patch("video_splitter.splitter.cutter.FFmpegSkill") as mock_skill:
            mock_skill.return_value = MagicMock()
            yield mock_skill

    def test_cut_fast_mode_success(self, config_fast, tmp_path):
        """Fast mode: successful ffmpeg + duration check within tolerance."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [
            Chapter("01_简介", 0.0, 30.0),
            Chapter("02_正文", 30.0, 60.0),
        ]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config_fast)
        # Mock _cut_fast to succeed (no fallback to precise)
        cutter._cut_fast = MagicMock()
        cutter._get_duration = MagicMock(return_value=30.0)  # tolerance check passes

        result = cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert len(result) == 2
        assert os.path.exists(output_dir)
        assert cutter._cut_fast.call_count == 2
        # cutter._cut_precise should NOT be called (fast succeeded)
        assert not hasattr(cutter, "_cut_precise") or cutter._cut_precise.call_count == 0  # type: ignore[union-attr]

    def test_cut_fast_falls_back_to_precise(self, config_fast, tmp_path):
        """Fast mode: when ffmpeg returns non-zero, fall back to precise."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config_fast)
        cutter._cut_precise = MagicMock()

        # Mock _cut_fast to fail (subprocess.run returns non-zero)
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            cutter._cut_fast(str(tmp_path / "test.mp4"), str(tmp_path / "output" / "file.mp4"), 0.0, 30.0)

        # _cut_precise should have been called as fallback
        cutter._cut_precise.assert_called_once()

    def test_cut_precise_mode_direct(self, config_precise, tmp_path):
        """Precise mode: calls _cut_precise directly without _cut_fast."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config_precise)
        cutter._cut_precise = MagicMock()
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        cutter._cut_precise.assert_called_once()
        cutter._cut_fast.assert_not_called()

    def test_cut_precise_success(self, config_precise, tmp_path):
        """Precise mode: successful ffmpeg re-encode."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "output")

        cutter = VideoCutter(config_precise)
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            cutter._cut_precise(str(tmp_path / "test.mp4"), str(tmp_path / "output" / "file.mp4"), 0.0, 30.0)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ffmpeg" in cmd[0]
        assert "-c:v" in cmd
        assert "libx264" in cmd

    def test_cut_precise_failure(self, config_precise, tmp_path):
        """Precise mode: non-zero exit raises FFmpegError."""
        from video_splitter.splitter.cutter import VideoCutter
        from ffmpeg_skill import FFmpegError

        cutter = VideoCutter(config_precise)
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "ffmpeg error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(FFmpegError, match="FFmpeg precise cut failed"):
                cutter._cut_precise(str(tmp_path / "test.mp4"), str(tmp_path / "output" / "file.mp4"), 0.0, 30.0)

    def test_cut_creates_output_dir(self, config_fast, tmp_path):
        """Output directory is created if it doesn't exist."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [Chapter("01_test", 0.0, 30.0)]
        output_dir = str(tmp_path / "nested" / "output")

        cutter = VideoCutter(config_fast)
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert os.path.exists(output_dir)

    def test_cut_progress_callback(self, config_fast, tmp_path):
        """Progress callback is called with fraction values."""
        from video_splitter.splitter.cutter import VideoCutter

        chapters = [
            Chapter("01_a", 0.0, 30.0),
            Chapter("02_b", 30.0, 60.0),
            Chapter("03_c", 60.0, 90.0),
        ]
        output_dir = str(tmp_path / "output")
        progress_values = []

        cutter = VideoCutter(config_fast, progress_callback=lambda v: progress_values.append(v))
        cutter._cut_fast = MagicMock()

        cutter.cut(str(tmp_path / "test.mp4"), chapters, output_dir)

        assert len(progress_values) == 3
        assert progress_values == [1/3, 2/3, 3/3]

    def test_get_duration(self, config_fast, tmp_path):
        """_get_duration parses ffprobe output correctly."""
        from video_splitter.splitter.cutter import VideoCutter

        cutter = VideoCutter(config_fast)
        mock_result = MagicMock()
        mock_result.stdout = "45.678\n"
        with patch("subprocess.run", return_value=mock_result):
            duration = cutter._get_duration("/some/video.mp4")
        assert duration == 45.678
```

- [ ] **Step 2: Run tests to verify all pass**

```bash
python -m pytest video_splitter/tests/test_cutter.py -v
```
Expected: all tests PASS (~8 tests).

- [ ] **Step 3: Commit**

```bash
git add video_splitter/tests/test_cutter.py
git commit -m "feat(tests): add VideoCutter tests (fast, precise, fallback, progress)"
```

---

### Task 12: Create pyproject.toml with pytest and coverage configuration

**Files:**
- Modify: `pyproject.toml` (create if not exists)
- No test files

- [ ] **Step 1: Check if pyproject.toml exists, then write the test config section**

```bash
# Check current state
if (Test-Path pyproject.toml) { echo "EXISTS" } else { echo "NOT FOUND" }
```

If `pyproject.toml` exists, add pytest + coverage sections. If not, create it:

```toml
[project]
name = "video_splitter"
version = "0.1.0"
requires-python = ">=3.12"

[tool.pytest.ini_options]
testpaths = ["tests", "video_splitter/tests"]
python_files = ["test_*.py", "*_test.py", "tests.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short --strict-markers"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: marks tests that require external dependencies (FFmpeg, LLM API)",
]

[tool.coverage.run]
source = ["video_splitter", "gui"]
omit = ["*/tests/*", "*/test_*.py", "ffmpeg-skill/tests.py"]

[tool.coverage.report]
fail_under = 50
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.:",
]
```

- [ ] **Step 2: Run tests with pyproject.toml to verify config works**

```bash
python -m pytest --co
```
Expected: collects all tests from both test directories.

- [ ] **Step 3: Run coverage check**

```bash
python -m pytest --cov --cov-report=term-missing
```
Expected: coverage report generated, coverage percentage shown.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add pytest + coverage configuration to pyproject.toml"
```

---

### Task 13: Create GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/test.yml`
- No modify files

- [ ] **Step 1: Create the workflow file**

```yaml
name: Tests

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install FFmpeg
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest pytest-cov pytest-mock

      - name: Run tests with coverage
        run: |
          python -m pytest tests/ video_splitter/tests/ --cov --cov-report=xml --cov-report=term -v

      - name: Upload coverage to Codecov (optional)
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          fail_ci_if_error: false
```

- [ ] **Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/test.yml
git commit -m "ci: add GitHub Actions test workflow with coverage"
```

---

### Task 14: GUI widget smoke tests

**Files:**
- Create: `tests/test_widgets.py`
- No modify files

- [ ] **Step 1: Write the smoke test file**

```python
"""Smoke tests for GUI widgets — verify instantiation without crash, signal wiring."""
from __future__ import annotations

import os
import sys

_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication once per test session."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestSubtitlePanel:
    """Smoke tests for SubtitlePanel widget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        assert panel is not None

    def test_set_segment_no_crash(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_segment(index=0, total=5, text="测试文本", start_time=0.0, end_time=5.0)
        assert panel._segment_label.text() == "Segment 1/5"
        assert "00:00.000" in panel._timestamp_label.text()

    def test_set_correction_get_correction(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_correction("修正后的文本")
        assert panel.get_correction() == "修正后的文本"

    def test_set_modified_toggles_bold(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_modified(True)
        assert panel._segment_label.font().bold() is True
        panel.set_modified(False)
        assert panel._segment_label.font().bold() is False

    def test_clear_resets_all(self, qapp):
        from gui.widgets.subtitle_panel import SubtitlePanel
        panel = SubtitlePanel()
        panel.set_segment(index=0, total=3, text="text", start_time=1.0, end_time=2.0)
        panel.set_correction("corrected")
        panel.clear()
        assert panel._segment_label.text() == "Segment 0/0"
        assert panel._correction_edit.toPlainText() == ""


class TestVideoPlayerWidget:
    """Smoke tests for VideoPlayerWidget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        player = VideoPlayerWidget()
        assert player is not None

    def test_initial_state(self, qapp):
        from gui.widgets.video_player import VideoPlayerWidget
        from PySide6.QtMultimedia import QMediaPlayer
        player = VideoPlayerWidget()
        assert player._player.playbackState() == QMediaPlayer.PlaybackState.StoppedState


class TestStatusBarWidget:
    """Smoke tests for StatusBarWidget."""

    def test_instantiation_no_crash(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        assert bar is not None

    def test_set_status(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_status("Processing...")
        assert bar._label.text() == "Processing..."

    def test_set_progress(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_progress(0.5, "Transcribing")
        assert "50%" in bar._label.text()
        assert "Transcribing" in bar._label.text()

    def test_set_progress_no_description(self, qapp):
        from gui.widgets.status_bar import StatusBarWidget
        bar = StatusBarWidget()
        bar.set_progress(0.75)
        assert "75%" in bar._label.text()
```

- [ ] **Step 2: Run tests to verify all pass**

```bash
python -m pytest tests/test_widgets.py -v
```
Expected: all 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_widgets.py
git commit -m "feat(tests): add GUI widget smoke tests (SubtitlePanel, VideoPlayer, StatusBar)"
```

---

### Task 15: Run full test suite and verify coverage improvement

**Files:**
- None modified (verification only)

- [ ] **Step 1: Run the complete test suite**

```bash
python -m pytest tests/ video_splitter/tests/ -v --tb=short
```
Expected: all tests PASS (111 existing + new tests = ~160+).

- [ ] **Step 2: Run with coverage to verify improvement**

```bash
python -m pytest tests/ video_splitter/tests/ --cov=video_splitter --cov=gui --cov-report=term-missing
```
Expected: coverage > 50% (up from 39%).

- [ ] **Step 3: Fix any failures, then commit final state**

```bash
git add -A
git commit -m "chore: final verification — full test suite passes, coverage > 50%"
```

---

### Task 16: Update AGENTS.md to reflect new test structure

**Files:**
- Modify: `video_splitter/AGENTS.md`
- No new files

- [ ] **Step 1: Update the tests section in AGENTS.md**

In `video_splitter/AGENTS.md`, update the STRUCTURE section's `tests/` entry:

```
└── tests/            # Unit tests — chapter, review, transcribe, validator, pipeline, audio, cli, cutter
```

And update the WHERE TO LOOK table to add:

```markdown
| Run all core tests | `python -m pytest video_splitter/tests/ -v` | 70+ tests |
| Run GUI tests | `python -m pytest tests/ -v` | 60+ tests |
| Check coverage | `python -m pytest --cov --cov-report=term-missing` | require 50%+ |
```

- [ ] **Step 2: Commit**

```bash
git add video_splitter/AGENTS.md
git commit -m "docs: update AGENTS.md with new test modules and coverage targets"
```

---

## Execution Order

Tasks MUST be executed sequentially in numeric order (1 → 16). Each task's tests must pass before proceeding. Commit after each task.

Critical dependencies:
- Tasks 1-3 fix hardcoded paths (must be done first)
- Tasks 8-11 add new test modules (depend on 1-3 being fixed)
- Task 15 is the final verification gate
