# FunASR Migration Design: Replacing faster-whisper with paraformer-zh

**Status:** Draft  
**Date:** 2026-07-08  
**Author:** Sisyphus-Junior  

---

## Architecture Overview

### Current Pipeline

```
Video file
  → AudioExtractor.extract()          [FFmpeg → 16kHz mono WAV]
  → transcribe()                      [faster-whisper WhisperModel]
     → Returns {language, duration, segments[{text, start, end}]}
  → estimate_tokens() / to_srt()      [operates on transcript dict]
  → ChapterDetector.detect()          [LLM-based chaptering]
```

### Target Pipeline

```
Video file
  → AudioExtractor.extract()          [FFmpeg → 16kHz mono WAV] ← UNCHANGED
  → transcribe()                      [FunASR AutoModel("paraformer-zh")]
     → Returns {language, duration, segments[{text, start, end}]}  ← SAME CONTRACT
  → estimate_tokens() / to_srt()      [UNCHANGED]
  → ChapterDetector.detect()          [UNCHANGED]
```

The only file that changes is `extractor/transcribe.py`. The pipeline, CLI, and all downstream consumers see the same API contract — a `transcribe()` function returning the same dict shape.

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Replace only `transcribe()`, not `AudioExtractor` | Paraformer-zh also expects 16kHz mono WAV — identical audio pipeline |
| Keep return format identical | `pipeline.py` line 62 calls `transcribe()` and serializes to JSON; `estimate_tokens()` and `to_srt()` consume segments dict — any format change would ripple through 3+ files |
| Map `model_size` to a FunASR-compatible value | Config field already represents "which model" — we repurpose it rather than adding a new field |
| Lazy-import FunASR inside the function | Same pattern as faster-whisper on line 27; FunASR + ModelScope downloads (~500MB) happen on first call only |
| `language` always returns `"zh"` | Paraformer-zh is Chinese-only. This is the existing default (`config.language = "zh"`). Non-zh configs will log a warning. |

---

## API Compatibility Strategy

### Current `transcribe()` Contract

```python
def transcribe(
    audio_path: str,
    config: SplitConfig,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """
    Returns: {
        "language": str,      # e.g. "zh"
        "duration": float,    # total audio duration in seconds
        "segments": [         # list of segment dicts
            {"text": str, "start": float, "end": float}
        ]
    }
    """
```

### FunASR Output → Contract Mapping

FunASR `model.generate()` returns `[result_dict]` where:

```python
res = model.generate(input="audio.wav")
result = res[0]                          # single result for single input file
full_text = result["text"]               # e.g. "今天天气很好。我们出去散步吧。"
sentence_info = result["sentence_info"]  # list of segment dicts
```

Each segment in `sentence_info`:
```python
{"text": "今天天气很好。", "start": 880, "end": 2120, ...}
#                                  ^^^          ^^^^
#                           MILLISECONDS   MILLISECONDS
```

Mapping:

| FunASR field | Contract field | Conversion |
|-------------|---------------|------------|
| `seg["text"]` | `segments[i]["text"]` | `.strip()` (as before) |
| `seg["start"]` | `segments[i]["start"]` | `ms / 1000 → seconds, rounded to 2dp` |
| `seg["end"]` | `segments[i]["end"]` | `ms / 1000 → seconds, rounded to 2dp` |
| N/A | `language` | Hardcoded `"zh"` |
| N/A | `duration` | Use last segment's end (ms→s) OR calculate from audio file |

### Duration Calculation

Two options:

1. **From last segment** (simplest, matches FunASR's notion of transcribed duration):
   ```python
   duration = round(sentence_info[-1]["end"] / 1000, 2)
   ```
2. **From audio file via `AudioExtractor.get_duration()`** (more accurate for total audio):
   ```python
   from .audio import AudioExtractor
   duration = AudioExtractor().get_duration(audio_path)  # wrong path: audio is already extracted
   ```

**Recommendation:** Use last segment's end timestamp (option 1). The audio at `audio_path` is already the extracted WAV — querying the original video duration via ffprobe would be awkward. FunASR's last segment end is the meaningful "transcribed duration." This matches faster-whisper's `info.duration` behavior (which also represents transcribed duration, not raw file duration).

### `language` Field Semantics

faster-whisper auto-detects language via `info.language`. FunASR paraformer-zh is Chinese-only.

**Strategy:** Return `"zh"` unconditionally. This is backward-compatible because:
- `config.language` defaults to `"zh"` (config.py line 23)
- All downstream code using this field already expects/passes `"zh"` for Chinese video processing
- We add a validation: if `config.language != "zh"`, log a warning but proceed — paraformer-zh will still produce Chinese output regardless

### `progress_callback` Handling

faster-whisper is a streaming generator — progress callback fires per-segment as we iterate. FunASR is batch: `model.generate()` blocks until complete.

**Strategy:** Two-phase progress:
1. Call `progress_callback(0.0)` before inference starts
2. Call `progress_callback(1.0)` after `model.generate()` completes

If the user really needs per-segment progress, we can iterate `sentence_info` and simulate it (segments count known after `generate()` returns). But the contract says `Optional[Callable]` — not required. Keep it simple.

```python
if progress_callback:
    progress_callback(0.0)

segments_out = []
text_segments = model.generate(input=audio_path)
sentence_info = text_segments[0].get("sentence_info", [])

# Simulate segment-level progress (optional, for backward compat)
n = len(sentence_info)
for i, seg in enumerate(sentence_info):
    segments_out.append({...})
    if progress_callback and n > 0:
        progress_callback((i + 1) / n)

if progress_callback:
    progress_callback(1.0)
```

---

## Configuration Changes

### Current `SplitConfig`

```python
@dataclass
class SplitConfig:
    model_size: str = "large-v3"   # faster-whisper model name
    device: str = "auto"           # "auto" | "cpu" | "cuda"
    compute_type: str = "auto"     # "auto" | "int8" | "float16" | etc.
    # ... other fields unchanged
```

### Strategy: Repurpose `model_size`

Rather than adding a new field, we expand `model_size` to accept FunASR model names alongside (or instead of) Whisper model names:

| Old value | New meaning | Notes |
|-----------|------------|-------|
| `"paraformer-zh"` | FunASR paraformer-zh model | **New default** |
| `"tiny"` | (kept for future hybrid support) | No-op if FunASR is the only engine |
| `"large-v3"` | (kept as legacy / fallback) | Can be used for English videos in future |

**Recommended:** Make `model_size` default to `"paraformer-zh"`. The CLI `--model` choices and config default change.

### `device` Mapping

| `config.device` | FunASR `AutoModel(device=...)` | |
|----------------|-------------------------------|-|
| `"auto"` | `"cuda"` if torch.cuda.is_available() else `"cpu"` | Matches faster-whisper auto-detect |
| `"cpu"` | `"cpu"` | Direct pass-through |
| `"cuda"` | `"cuda"` | Direct pass-through |

### `compute_type` — Not Used by FunASR

faster-whisper's `compute_type` (`int8`, `float16`, `int8_float16`) has no FunASR equivalent. FunASR uses FP32 by default.

**Strategy:** Ignore it. Keep the field on `SplitConfig` (don't want to break serialization) but add a comment noting it's a no-op under FunASR. The `transcribe()` function simply doesn't read it.

### `config.language` 

Already `"zh"` by default (config.py line 23). Under FunASR: if `config.language` is not `"zh"`, log a warning but proceed — the model only outputs Chinese.

---

## Implementation File Changes (File-by-File)

### 1. `video_splitter/extractor/transcribe.py` (THE ONLY FILE WITH CODE CHANGES)

**What changes:**
- Replace `from faster_whisper import WhisperModel` with `from funasr import AutoModel`
- Replace `WhisperModel(...)` + `.transcribe()` with `AutoModel(...)` + `.generate()`
- Map FunASR output (`sentence_info` with ms timestamps) to the contract format
- Handle progress callback (batch → simulate per-segment)
- Hardcode `language = "zh"`
- Compute `duration` from last segment's end timestamp

**What stays:**
- Function signature: `transcribe(audio_path, config, progress_callback)`
- Return type: `Dict[str, Any]` with same keys
- `estimate_tokens()` — unchanged
- `to_srt()` — unchanged
- `_format_timestamp()` — unchanged

**Pseudo-implementation:**

```python
"""FunASR paraformer-zh transcription with progress reporting."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional
import logging

if TYPE_CHECKING:
    from video_splitter.config import SplitConfig

logger = logging.getLogger(__name__)

_MODEL_CACHE: Dict[str, Any] = {}  # Simple singleton cache per model name

def _resolve_device(config: SplitConfig) -> str:
    """Map config.device to FunASR AutoModel device parameter."""
    if config.device == "auto":
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    return config.device

def transcribe(
    audio_path: str,
    config: SplitConfig,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Dict[str, Any]:
    """Transcribe audio using FunASR paraformer-zh.

    First call downloads ~500MB model from ModelScope. Subsequent calls use
    cached model instance.

    Args:
        audio_path: Path to 16kHz mono WAV audio file.
        config: SplitConfig instance (uses model_size, device).
        progress_callback: Optional callback receiving a float in [0, 1].

    Returns:
        Dict with keys ``language``, ``duration``, ``segments``.
    """
    from funasr import AutoModel

    if config.language and config.language != "zh":
        logger.warning(
            "config.language=%r but paraformer-zh only supports Chinese; "
            "output will be Chinese regardless",
            config.language,
        )

    if progress_callback:
        progress_callback(0.0)

    # Cache model per model_name to avoid repeated downloads
    model_name = config.model_size
    if model_name not in _MODEL_CACHE:
        _MODEL_CACHE[model_name] = AutoModel(
            model=model_name,
            device=_resolve_device(config),
        )

    model = _MODEL_CACHE[model_name]
    res = model.generate(input=audio_path)
    result = res[0]

    sentence_info = result.get("sentence_info", [])
    segments_out: list[Dict[str, Any]] = []

    n = len(sentence_info)
    for i, seg in enumerate(sentence_info):
        segments_out.append({
            "text": seg["text"].strip(),
            "start": round(seg["start"] / 1000, 2),
            "end": round(seg["end"] / 1000, 2),
        })
        if progress_callback and n > 0:
            progress_callback((i + 1) / n)

    total_duration = round(sentence_info[-1]["end"] / 1000, 2) if sentence_info else 0.0

    if progress_callback:
        progress_callback(1.0)

    return {
        "language": "zh",
        "duration": total_duration,
        "segments": segments_out,
    }

# estimate_tokens(), to_srt(), _format_timestamp() — UNCHANGED below
```

### 2. `video_splitter/config.py` — Default change only

```python
# Line 12: Change default model_size
model_size: str = "paraformer-zh"  # was "large-v3"
```

No other changes. `device`, `compute_type`, `language` stay as-is.

### 3. `video_splitter/cli.py` — Model choices update

**Line 188 (`split` subcommand):**
```python
# Before:
p.add_argument("--model", choices=["tiny", "base", "small", "medium", "large-v3"], ...)
# After:
p.add_argument("--model", choices=["paraformer-zh"], ...)
```

**Line 197 (`transcribe` subcommand):**
```python
# Before:
p.add_argument("--model", choices=["tiny", "base", "small", "medium", "large-v3"])
# After:
p.add_argument("--model", choices=["paraformer-zh"])
```

**Lines 101–124 (`cmd_check`):** Replace the faster-whisper check block with a FunASR check:

```python
# Replace faster-whisper check (lines 101-124) with:
try:
    from funasr import AutoModel
    print("[OK] FunASR: available")
    import tempfile, wave, time, os
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    with wave.open(tmp_path, "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(b'\x00' * 16000 * 2 * 10)
    t0 = time.time()
    model = AutoModel(model="paraformer-zh", device="cpu")
    res = model.generate(input=tmp_path)
    elapsed = time.time() - t0
    os.unlink(tmp_path)
    print(f"[OK] FunASR benchmark (paraformer-zh/cpu): {elapsed:.1f}s for 10s audio")
except Exception as e:
    issues.append(f"FunASR check failed: {e}")
    print(f"[FAIL] FunASR: {e}")
```

### 4. `video_splitter/pipeline.py` — No changes

The import `from .extractor.transcribe import transcribe, estimate_tokens, to_srt` (line 13) and all usage (lines 62, 68, 80, 119) remain identical. This is the key design win.

### 5. Dependency changes

| Change | Package | Notes |
|--------|---------|-------|
| **REMOVE** | `faster-whisper` | No longer imported anywhere |
| **ADD** | `funasr` | Core ASR engine |
| **ADD** | `modelscope` | FunASR dependency (model download) |
| **ADD** | `torch` (if not already present) | FunASR requires PyTorch. May already be pulled in by faster-whisper. Verify. |
| **KEEP** | `numpy`, `librosa` | Used by AudioExtractor.precheck(), unchanged |
| **KEEP** | `json-repair`, `openai` | Used by chapter detector, unchanged |

### Summary of Changes

| File | Type of change | Lines changed |
|------|---------------|---------------|
| `extractor/transcribe.py` | **Rewrite `transcribe()` body** (~30 lines) | ~30 lines new, ~30 removed |
| `config.py` | Default value | 1 line |
| `cli.py` | Model choices + `cmd_check` block | ~30 lines |
| `pipeline.py` | None | 0 |
| `extractor/audio.py` | None | 0 |
| `extractor/__init__.py` | None | 0 |

---

## Risk Assessment

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **Model download failure** (ModelScope unreachable in China-mainland networks) | High | Medium | Provide alternative download via HuggingFace mirror or manual tarball. Add error message with mirror instructions. FunASR supports `model_revision` and offline model paths via `model="/path/to/local/model"`. Document `VIDEO_SPLITTER_FUNASR_MODEL_DIR` env var for pre-downloaded models. |
| **Timestamp accuracy regression** — paraformer-zh timestamps may differ from Whisper's | Medium | Medium | Existing chapters JSON is validated by `ChapterValidator` (pipeline.py:89). Small timestamp drift doesn't affect chapter boundaries. Run A/B comparison on 3-5 representative videos before rollout. |
| **GPU memory mismatch** — FunASR's memory footprint differs from faster-whisper | Medium | Low | Add `torch.cuda.empty_cache()` in `transcribe()`. document that `device="cpu"` fallback is available. FunASR paraformer-zh on CPU is ~2-3x faster than Whisper large-v3 on CPU for Chinese, so even CPU-only is viable. |
| **Segment quality difference** — paraformer-zh might produce shorter/longer segments than Whisper's VAD | Low | Medium | FunASR's built-in VAD produces sentence-level segments. If chapter detection quality degrades, we can add `fsmn-vad` + `ct-punc` to the FunASR pipeline: `model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")` (single line change). |
| **Serialized transcripts incompatible** — existing `.transcript.json` files from faster-whisper | Low | High | Both produce `{language, duration, segments[{text, start, end}]}` — identical schema. Resume works. |
| **`compute_type` no-op** — `config.compute_type` is ignored silently | Low | Low | Add a comment to `config.py`. No runtime impact. If future needs FP16, FunASR doesn't expose a direct equivalent, but PyTorch `torch.cuda.amp.autocast()` can be used. |
| **Chinese-only limitation** — drops multilingual support | Medium | Low (for this project) | Project is designed for Chinese video processing (`language="zh"`, Chinese-named segments). If English support is needed later, keep the old `transcribe()` as `transcribe_whisper()` and route by `config.language` in a wrapper. Not in scope for this migration. |

---

## Migration Rollout Plan

### Phase 1: Implementation (this task)
1. Modify `transcribe()` in `extractor/transcribe.py`
2. Update `config.py` default
3. Update CLI `--model` choices and `cmd_check`
4. Update dependencies (pyproject.toml / requirements.txt)

### Phase 2: Verification
1. Run `cmd_check` to confirm FunASR works
2. Transcribe a known video, compare segment count and timestamps with Whisper baseline
3. Run full pipeline (`split`) on 2-3 test videos

### Phase 3: Documentation
1. Update README to mention FunASR / paraformer-zh
2. Add GPU/CPU performance expectations
3. Document offline model installation path (ModelScope → local dir → `VIDEO_SPLITTER_FUNASR_MODEL_DIR`)

---

## Appendix: FunASR `sentence_info` Segment Format Reference

From FunASR docs/testing:

```python
[
    {"text": "今天天气很好。", "start": 880, "end": 2120},
    {"text": "我们出去散步吧。", "start": 2280, "end": 3920},
    # start/end in MILLISECONDS
    # text is already punctuated (built-in ct-punc in paraformer-zh model)
]
```

Note: paraformer-zh includes punctuation by default (the model name "paraformer-zh" aliases the punctuated version). No separate punctuation model needed for basic usage.
