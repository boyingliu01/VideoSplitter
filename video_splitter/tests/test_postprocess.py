"""Tests for extractor/postprocess.py — LLM full-text postprocessing."""
import os
import sys
from unittest.mock import MagicMock

import pytest

# Compute project root from this file's location (3 levels up: tests/ -> video_splitter/ -> project_root)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

from video_splitter.extractor.postprocess import (  # noqa: E402
    build_postprocess_prompt,
    parse_postprocess_response,
    align_segments,
    postprocess_segments,
)


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def sample_segments():
    """Three typical Chinese transcript segments with filler words."""
    return [
        {"text": "今天啊我们呃来讨论一下", "start": 0.0, "end": 3.5, "id": 0},
        {"text": "嗯这个项目的那个实施方案", "start": 4.0, "end": 7.2, "id": 1},
        {"text": "就是说首先呢我们要明确", "start": 8.0, "end": 11.0, "id": 2},
    ]


@pytest.fixture
def single_segment():
    return [{"text": "就一句话", "start": 0.0, "end": 2.0, "id": 0}]


@pytest.fixture
def empty_segments():
    return []


@pytest.fixture
def unicode_segments():
    return [
        {"text": "你好——世界！", "start": 0.0, "end": 2.0, "id": 0},
        {"text": "Hello——World！", "start": 2.5, "end": 4.0, "id": 1},
    ]


# ──────────────────────────────────────────────────────────────
# TestBuildPrompt
# ──────────────────────────────────────────────────────────────

class TestBuildPrompt:
    """Tests for build_postprocess_prompt()."""

    def test_basic_segments(self, sample_segments):
        """Prompt includes all segments with [SEG_N] markers."""
        prompt = build_postprocess_prompt(sample_segments)
        assert "[SEG_0]" in prompt
        assert "[SEG_1]" in prompt
        assert "[SEG_2]" in prompt
        assert "今天啊我们呃来讨论一下" in prompt
        assert "嗯这个项目的那个实施方案" in prompt
        assert "就是说首先呢我们要明确" in prompt
        # Check structural elements
        assert "请对以下语音识别结果进行润色" in prompt
        assert "删除所有语气词和口头禅" in prompt
        assert "保持段落边界标记" in prompt
        assert "直接输出润色后的文本" in prompt

    def test_empty_segments(self, empty_segments):
        """Empty segments list produces a prompt with just headers (no [SEG_N] markers)."""
        prompt = build_postprocess_prompt(empty_segments)
        assert "请对以下语音识别结果进行润色" in prompt
        assert "原文：" in prompt
        assert "[SEG_0]" not in prompt

    def test_segments_with_unicode(self, unicode_segments):
        """Unicode punctuation and mixed scripts rendered correctly."""
        prompt = build_postprocess_prompt(unicode_segments)
        assert "[SEG_0] 你好——世界！" in prompt
        assert "[SEG_1] Hello——World！" in prompt

    def test_single_segment(self, single_segment):
        """A single segment renders with one [SEG_0] marker."""
        prompt = build_postprocess_prompt(single_segment)
        assert "[SEG_0] 就一句话" in prompt
        assert "[SEG_1]" not in prompt

    def test_many_segments(self):
        """Prompt with 50 segments includes all markers."""
        segments = [
            {"text": f"text_{i}", "start": float(i), "end": float(i + 1), "id": i}
            for i in range(50)
        ]
        prompt = build_postprocess_prompt(segments)
        for i in range(50):
            assert f"[SEG_{i}]" in prompt

    def test_hotwords_injection(self, sample_segments):
        """When hotwords are provided, step 5 is injected into the prompt."""
        hotwords = "质量红线, QIWC, ISO9001"
        prompt = build_postprocess_prompt(sample_segments, hotwords=hotwords)
        assert "以下专业术语必须正确识别" in prompt
        assert "质量红线, QIWC, ISO9001" in prompt

    def test_no_hotwords_omits_step5(self, sample_segments):
        """Without hotwords, step 5 is not present."""
        prompt = build_postprocess_prompt(sample_segments)
        assert "以下专业术语必须正确识别" not in prompt


# ──────────────────────────────────────────────────────────────
# TestParseResponse
# ──────────────────────────────────────────────────────────────

class TestParseResponse:
    """Tests for parse_postprocess_response()."""

    def _make_seg(self, text, seg_id=0, start=0.0, end=2.0):
        return {"text": text, "start": start, "end": end, "id": seg_id}

    def test_perfect_match(self):
        """Parser extracts 3 cleaned segments matching input count."""
        original = [
            self._make_seg("今天啊我们呃来讨论一下", 0, 0.0, 3.5),
            self._make_seg("嗯这个项目的那个实施方案", 1, 4.0, 7.2),
            self._make_seg("就是说首先呢我们要明确", 2, 8.0, 11.0),
        ]
        response = (
            "[SEG_0] 今天我们来讨论一下\n"
            "[SEG_1] 这个项目的实施方案\n"
            "[SEG_2] 首先我们要明确"
        )
        result = parse_postprocess_response(response, original)
        assert result is not None
        assert len(result) == 3
        assert result[0]["text"] == "今天我们来讨论一下"
        assert result[1]["text"] == "这个项目的实施方案"
        assert result[2]["text"] == "首先我们要明确"

    def test_merged_segments(self):
        """Two [SEG_N] covering one response segment (merge) → treated as seg count mismatch."""
        original = [
            self._make_seg("嗯", 0, 0.0, 1.0),
            self._make_seg("啊", 1, 1.0, 2.0),
        ]
        # Only one [SEG_0] in response when 2 were expected
        response = "[SEG_0] 嗯啊"
        result = parse_postprocess_response(response, original)
        assert result is None  # count mismatch → fallback

    def test_split_segments(self):
        """More output segments than input → count mismatch → fallback."""
        original = [
            self._make_seg("今天我们来讨论一下这个项目的实施方案", 0, 0.0, 5.0),
        ]
        response = "[SEG_0] 今天我们来讨论一下\n[SEG_1] 这个项目的实施方案"
        result = parse_postprocess_response(response, original)
        assert result is None  # 2 output vs 1 input → mismatch

    def test_missing_markers(self):
        """Response without any [SEG_N] markers → fallback."""
        original = [self._make_seg("hello", 0, 0.0, 1.0)]
        response = "just plain text without markers"
        result = parse_postprocess_response(response, original)
        assert result is None

    def test_garbled_markers(self):
        """Non-sequential numbering still works, but count mismatch causes fallback."""
        original = [
            self._make_seg("a", 0, 0.0, 1.0),
            self._make_seg("b", 1, 1.0, 2.0),
        ]
        # Correct count but weird numbering — we still parse it
        response = "[SEG_5] a_clean\n[SEG_9] b_clean"
        result = parse_postprocess_response(response, original)
        assert result is not None
        assert len(result) == 2
        assert result[0]["text"] == "a_clean"
        assert result[1]["text"] == "b_clean"


# ──────────────────────────────────────────────────────────────
# TestAlignSegments
# ──────────────────────────────────────────────────────────────

class TestAlignSegments:
    """Tests for align_segments()."""

    def _make_seg(self, text, seg_id=0, start=0.0, end=2.0):
        return {"text": text, "start": start, "end": end, "id": seg_id}

    def test_identical_text_preserves_timestamps(self):
        """When original and polished texts are identical, timestamps are preserved."""
        original = [
            self._make_seg("今天我们来讨论一下", 0, 0.0, 3.5),
            self._make_seg("这个项目的实施方案", 1, 4.0, 7.2),
        ]
        polished = [
            {"text": "今天我们来讨论一下", "id": 0, "start": 0.0, "end": 3.5},
            {"text": "这个项目的实施方案", "id": 1, "start": 4.0, "end": 7.2},
        ]
        result = align_segments(original, polished)
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 3.5
        assert result[1]["start"] == 4.0
        assert result[1]["end"] == 7.2

    def test_deleted_characters_redistribute_time(self):
        """Deleted filler words distribute their time to remaining characters."""
        original = [
            self._make_seg("今天啊我们呃来", 0, 0.0, 5.0),
        ]
        polished = [
            {"text": "今天我们来", "id": 0, "start": 0.0, "end": 5.0},
        ]
        result = align_segments(original, polished)
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 5.0
        # characters inherit the full 5-second window

    def test_inserted_characters_borrow_time(self):
        """Inserted characters (e.g. corrected text) borrow from neighbors."""
        original = [
            self._make_seg("质量鸿线", 0, 0.0, 2.0),  # "鸿" should be "红"
        ]
        polished = [
            {"text": "质量红线", "id": 0, "start": 0.0, "end": 2.0},
        ]
        result = align_segments(original, polished)
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 2.0

    def test_expansion_over_1_5x_reverts(self):
        """When polished text > 1.5x original, the segment reverts to original."""
        original = [
            self._make_seg("嗯", 0, 0.0, 1.0),  # 1 char
        ]
        polished = [
            {"text": "嗯嗯嗯嗯嗯嗯嗯嗯嗯嗯", "id": 0, "start": 0.0, "end": 1.0},  # 10 chars, >>1.5x
        ]
        result = align_segments(original, polished)
        assert len(result) == 1
        # Should revert to original text
        assert result[0]["text"] == "嗯"
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 1.0

    def test_contraction_below_0_3x_reverts(self):
        """When polished text < 0.3x original, the segment reverts to original."""
        original = [
            self._make_seg("今天我们来讨论一下这个项目的实施方案", 0, 0.0, 10.0),  # 16 chars
        ]
        polished = [
            {"text": "今天", "id": 0, "start": 0.0, "end": 10.0},  # 2 chars, < 0.3x
        ]
        result = align_segments(original, polished)
        assert len(result) == 1
        # Should revert to original text
        assert result[0]["text"] == "今天我们来讨论一下这个项目的实施方案"


# ──────────────────────────────────────────────────────────────
# TestPostprocessPipeline
# ──────────────────────────────────────────────────────────────

class TestPostprocessPipeline:
    """End-to-end tests for postprocess_segments() orchestrator."""

    def _make_seg(self, text, seg_id=0, start=0.0, end=2.0):
        return {"text": text, "start": start, "end": end, "id": seg_id}

    def test_e2e_normal(self):
        """Full pipeline with mock LLM that strips filler words."""
        segments = [
            self._make_seg("今天啊我们呃来讨论一下", 0, 0.0, 3.5),
            self._make_seg("嗯这个项目的那个实施方案", 1, 4.0, 7.2),
            self._make_seg("就是说首先呢我们要明确", 2, 8.0, 11.0),
        ]

        def mock_llm(prompt: str) -> str:
            # Simulate LLM stripping filler words
            return (
                "[SEG_0] 今天我们来讨论一下\n"
                "[SEG_1] 这个项目的实施方案\n"
                "[SEG_2] 首先我们要明确"
            )

        cleaned, warnings = postprocess_segments(segments, mock_llm)
        assert len(cleaned) == 3
        assert cleaned[0]["text"] == "今天我们来讨论一下"
        assert cleaned[1]["text"] == "这个项目的实施方案"
        assert cleaned[2]["text"] == "首先我们要明确"
        assert warnings == []

    def test_e2e_empty_segments(self):
        """Empty segments list returns immediately without calling LLM."""
        called = False

        def mock_llm(prompt: str) -> str:
            nonlocal called
            called = True
            return ""

        cleaned, warnings = postprocess_segments([], mock_llm)
        assert cleaned == []
        assert warnings == []
        assert not called

    def test_e2e_all_reverted(self):
        """When LLM returns garbage, all segments fall back to original."""
        segments = [
            self._make_seg("今天我们来讨论", 0, 0.0, 3.0),
            self._make_seg("这个项目的实施方案", 1, 3.0, 6.0),
        ]

        def mock_llm(prompt: str) -> str:
            # Return completely different segment count → full revert
            return "[SEG_0] something completely different"

        cleaned, warnings = postprocess_segments(segments, mock_llm)
        assert len(cleaned) == 2
        # All should revert to original text
        assert cleaned[0]["text"] == segments[0]["text"]
        assert cleaned[1]["text"] == segments[1]["text"]
        assert len(warnings) > 0
