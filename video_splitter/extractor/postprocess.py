"""LLM full-text postprocessing for ASR transcripts.

Removes filler words, fixes sentence breaks, applies hotword corrections
via an LLM, then maps cleaned text back to original timestamps using
character-level sequence alignment.
"""
from __future__ import annotations

import difflib
import logging
import re
from typing import Any, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Prompt building
# ──────────────────────────────────────────────────────────────

_SEG_MARKER_RE = re.compile(r"\[SEG_(\d+)\]")


def build_postprocess_prompt(
    segments: list[dict],
    hotwords: str | None = None,
    language: str = "zh",
) -> str:
    """Build the LLM prompt for full-text ASR postprocessing.

    Constructs a prompt that asks the LLM to:
    1. Remove filler words and verbal tics
    2. Fix obvious sentence-break errors
    3. Preserve original semantics (no new content)
    4. Keep [SEG_N] markers intact (merge early marker when combining)
    5. Optionally correct hotword-related near-homophone errors

    Args:
        segments: List of segments, each with ``text`` key.
        hotwords: Optional comma-separated hotword list for correction.
        language: Language code (default ``"zh"``).

    Returns:
        The full prompt string ready for LLM submission.
    """
    lines = [
        "请对以下语音识别结果进行润色：",
        "1. 删除所有语气词和口头禅（如：啊、嗯、呃、哦、那个、就是说、然后、就是）",
        "2. 修正明显的断句错误，将不完整的分句合并到相邻句子",
        "3. 保持原文语义不变，不要添加原文没有的内容",
        "4. 保持段落边界标记 [SEG_N] 的格式和顺序不变；如确需将两个相邻的不完整 [SEG_N] 合并，",
        "   合并后保留较早的 [SEG_N]，删除较晚的标记。",
    ]

    if hotwords:
        lines.append(
            "5. 以下专业术语必须正确识别，如果原文有音近错误请修正："
        )
        lines.append(f"   {hotwords}")

    lines.append("直接输出润色后的文本，不要加任何解释。")
    lines.append("")
    lines.append("原文：")

    for seg in segments:
        lines.append(f"[SEG_{seg['id']}] {seg['text']}")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Response parsing
# ──────────────────────────────────────────────────────────────


def parse_postprocess_response(
    response_text: str,
    original_segments: list[dict],
) -> list[dict] | None:
    """Parse LLM response and extract cleaned segments.

    Uses regex ``[SEG_N]`` to split the response into per-segment chunks.
    Validates that the number of markers matches the input count.

    Args:
        response_text: Raw LLM response text.
        original_segments: Original segments used as fallback reference.

    Returns:
        List of cleaned segments (with ``text``, ``id``, ``start``, ``end``)
        or ``None`` if parsing fails (count mismatch, no markers found).
    """
    markers = list(_SEG_MARKER_RE.finditer(response_text))
    if not markers:
        return None

    if len(markers) != len(original_segments):
        return None

    cleaned: list[dict] = []
    for i, match in enumerate(markers):
        # Extract text between this marker and the next (or end of string)
        start_pos = match.end()
        end_pos = markers[i + 1].start() if i + 1 < len(markers) else len(response_text)
        text = response_text[start_pos:end_pos].strip()
        orig = original_segments[i]
        cleaned.append({
            "text": text,
            "id": orig["id"],
            "start": orig["start"],
            "end": orig["end"],
        })

    return cleaned


# ──────────────────────────────────────────────────────────────
# Sequence alignment (character-level)
# ──────────────────────────────────────────────────────────────


def align_segments(
    original: list[dict],
    polished: list[dict],
) -> list[dict]:
    """Align polished text back to original timestamps via difflib.

    Per-segment character-level alignment. Falls back to original when:
    - polished_len > 1.5 * original_len  (over-expansion)
    - polished_len < 0.3 * original_len  (over-contraction)

    Args:
        original: Original segments with ``text``, ``start``, ``end``, ``id``.
        polished: Polished segments from LLM (same count, ``text`` + ``id``).

    Returns:
        Aligned segments combining polished ``text`` with mapped timestamps.
    """
    result: list[dict] = []
    for orig, pol in zip(original, polished):
        orig_text = orig["text"]
        pol_text = pol["text"]
        duration = orig["end"] - orig["start"]

        # Fallback thresholds
        if len(pol_text) > 1.5 * len(orig_text) or len(pol_text) < 0.3 * len(orig_text):
            result.append({
                "text": orig_text,
                "id": orig["id"],
                "start": orig["start"],
                "end": orig["end"],
            })
            continue

        if not orig_text or not pol_text:
            result.append({
                "text": pol_text,
                "id": orig["id"],
                "start": orig["start"],
                "end": orig["end"],
            })
            continue

        # Build per-character timestamp map from original
        char_times: list[float] = []
        step = duration / len(orig_text)
        for j in range(len(orig_text)):
            char_times.append(orig["start"] + j * step)

        # difflib alignment
        matcher = difflib.SequenceMatcher(None, orig_text, pol_text, autojunk=False)
        opcodes = matcher.get_opcodes()

        # Map polished characters to timestamps
        polished_times: list[float] = []
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == "equal":
                for j in range(j1, j2):
                    orig_j = i1 + (j - j1)
                    if orig_j < len(char_times):
                        polished_times.append(char_times[orig_j])
            elif tag == "replace":
                # Distribute original character time window proportionally
                seg_duration = char_times[i2 - 1] - char_times[i1] + step if i2 > i1 else step * (j2 - j1)
                pol_step = seg_duration / (j2 - j1) if j2 > j1 else seg_duration
                base = char_times[i1] if i1 < len(char_times) else (orig["start"] + duration / 2)
                for j in range(j2 - j1):
                    polished_times.append(base + j * pol_step)
            elif tag == "delete":
                # Deleted chars — their time is absorbed by neighbors (no-op here)
                pass
            elif tag == "insert":
                # Inserted chars — borrow from adjacent timestamps
                # Use the midpoint of the surrounding context
                if polished_times:
                    last_time = polished_times[-1]
                elif i1 < len(char_times):
                    last_time = char_times[i1]
                else:
                    last_time = orig["start"]
                for _ in range(j2 - j1):
                    polished_times.append(last_time)

        # Derive start/end from polished_times
        if polished_times:
            new_start = polished_times[0]
            new_end = polished_times[-1] + step
        else:
            new_start = orig["start"]
            new_end = orig["end"]

        result.append({
            "text": pol_text,
            "id": orig["id"],
            "start": new_start,
            "end": new_end,
        })

    return result


# ──────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────


def postprocess_segments(
    segments: list[dict],
    llm_fn: Callable[[str], str],
    hotwords: str | None = None,
    language: str = "zh",
) -> tuple[list[dict], list[str]]:
    """Run full LLM postprocessing pipeline on segments.

    1. Build prompt → 2. Call LLM → 3. Parse → 4. Align timestamps.

    Args:
        segments: Input segments with ``text``, ``start``, ``end``, ``id``.
        llm_fn: Callable that takes a prompt string and returns the LLM response.
        hotwords: Optional hotword list for correction.
        language: Language code.

    Returns:
        Tuple of ``(cleaned_segments, warnings)``. If parsing fails or segment
        count changes by >20%, all segments revert to original and a warning
        is emitted.
    """
    warnings: list[str] = []

    if not segments:
        return [], warnings

    prompt = build_postprocess_prompt(segments, hotwords=hotwords, language=language)
    response = llm_fn(prompt)

    parsed = parse_postprocess_response(response, segments)

    if parsed is None:
        # Count mismatch or missing markers → full revert
        warnings.append(
            f"LLM postprocessing failed to parse {len(segments)} segments "
            f"(got mismatched/garbled output). Reverting to original."
        )
        return list(segments), warnings

    # Check segment count change >20%
    count_change = abs(len(parsed) - len(segments)) / max(len(segments), 1)
    if count_change > 0.2:
        warnings.append(
            f"LLM returned {len(parsed)} segments vs {len(segments)} original "
            f"(>20% change). Reverting all to original."
        )
        return list(segments), warnings

    aligned = align_segments(segments, parsed)
    return aligned, warnings
