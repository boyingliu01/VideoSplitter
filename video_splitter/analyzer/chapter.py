"""LLM-based semantic chapter detection with full fault tolerance."""
from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

try:
    from json_repair import repair_json  # type: ignore[import-untyped]

    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    repair_json = None  # type: ignore[assignment]


class Chapter:
    """A detected chapter segment with title and time boundaries."""

    def __init__(self, title: str, start_seconds: float, end_seconds: float) -> None:
        self.title = title
        self.start_seconds = start_seconds
        self.end_seconds = end_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "start": _seconds_to_timestamp(self.start_seconds),
            "end": _seconds_to_timestamp(self.end_seconds),
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
        }

    def __repr__(self) -> str:
        return (
            f"Chapter(title={self.title!r}, "
            f"start={_seconds_to_timestamp(self.start_seconds)}, "
            f"end={_seconds_to_timestamp(self.end_seconds)})"
        )


class ChapterDetector:
    """Detects semantic chapters from a transcript using LLM.

    Handles transcripts that fit within the token budget via a single LLM
    call, and longer transcripts via sliding-window chunking.  Falls back
    to uniform time-based splitting when the LLM is unreachable.
    """

    PROMPT_TEMPLATE = (
        "你是一位视频编辑专家。请分析以下中文培训视频转录稿，完成以下任务：\n\n"
        "1. 识别视频中的主要话题和知识点\n"
        "2. 找到每个话题的自然起止时间点（格式: MM:SS 或 HH:MM:SS）\n"
        "3. 为每个话题生成简洁的中文标题（≤12个字，不含特殊字符如 /:*?\"<>|）\n"
        "4. 每段时长尽量控制在3-15分钟之间\n\n"
        "必须严格按照以下JSON格式输出（不含任何其他文字，不要用markdown包裹）：\n"
        "[\n"
        '  {{"title": "01_系统架构概述", "start": "00:00:00", "end": "00:08:30"}},\n'
        '  {{"title": "02_部署方案", "start": "00:08:30", "end": "00:18:45"}}\n'
        "]\n\n"
        "规则：\n"
        "- 段落边界必须是自然话题转换点，不能强行在句子中间切断\n"
        "- 序号从01开始递增\n"
        "- start 和 end 必须在 00:00:00 到 {duration_ts} 之间\n"
        "- 相邻段落的 end 应等于下一段的 start (无间隙无重叠)\n"
        '- 标题按格式 "序号_中文标题" 命名\n\n'
        "转录稿（总时长 {duration_ts}，含时间戳）：\n"
        "---\n"
        "{transcript}\n"
        "---"
    )

    def __init__(self, config: Any) -> None:
        self.config = config

    def detect(self, transcript: Dict[str, Any]) -> List[Chapter]:
        """Detect chapters from a transcript.

        Args:
            transcript: Transcript dict with ``duration`` and ``segments`` keys.

        Returns:
            List of detected :class:`Chapter` objects.
        """
        transcript_text = self._build_transcript_text(transcript)
        token_count = len(transcript_text) // 1.5  # rough estimate

        if token_count <= self.config.llm_token_budget:
            return self._single_detect(transcript_text, transcript["duration"])
        else:
            return self._chunked_detect(transcript_text, transcript["duration"])

    def _build_transcript_text(self, transcript: Dict[str, Any]) -> str:
        segments = transcript.get("segments", [])
        lines: List[str] = []
        for seg in segments:
            ts = _seconds_to_timestamp(seg["start"])
            lines.append(f"[{ts}] {seg['text']}")
        return "\n".join(lines)

    def _single_detect(
        self, transcript_text: str, duration: float
    ) -> List[Chapter]:
        """Single LLM call for transcripts within the token budget."""
        duration_ts = _seconds_to_timestamp(duration)
        prompt = self.PROMPT_TEMPLATE.format(
            duration_ts=duration_ts,
            transcript=transcript_text,
        )
        return self._call_llm(prompt, duration)

    def _chunked_detect(
        self, transcript_text: str, duration: float
    ) -> List[Chapter]:
        """Sliding-window chunking for long transcripts.

        Splits the transcript into ~15-minute chunks with a 2-minute overlap
        for cross-boundary context, then detects chapters per chunk and
        deduplicates overlapping results.
        """
        lines = transcript_text.split("\n")
        chunk_duration = 15 * 60  # seconds
        overlap = 2 * 60  # seconds

        chunks: List[tuple[float, float, str]] = []
        current_chunk: List[str] = []
        current_start = 0.0
        current_end = 0.0

        for line in lines:
            match = re.match(r"\[(.*?)\]", line)
            if match:
                ts = _parse_timestamp(match.group(1))
                if current_chunk and ts - current_start > chunk_duration:
                    chunks.append(
                        (current_start, current_end, "\n".join(current_chunk))
                    )
                    current_chunk = []
                    overlap_start = ts - overlap
                    overlap_lines: List[str] = []
                    candidate_lines = (
                        current_chunk[-50:]
                        if len(current_chunk) > 50
                        else current_chunk
                    )
                    for ol in reversed(candidate_lines):
                        m = re.match(r"\[(.*?)\]", ol)
                        if m and _parse_timestamp(m.group(1)) >= overlap_start:
                            overlap_lines.insert(0, ol)
                        else:
                            break
                    current_chunk = overlap_lines
                    if overlap_lines:
                        current_start = _parse_timestamp(
                            re.match(r"\[(.*?)\]", overlap_lines[0]).group(1)  # type: ignore[union-attr]
                        )
                    else:
                        current_start = ts - overlap

                current_chunk.append(line)
                current_end = ts

        if current_chunk:
            chunks.append((current_start, current_end, "\n".join(current_chunk)))

        all_chapters: List[Chapter] = []
        for c_start, c_end, chunk_text in chunks:
            chunk_dur = c_end - c_start if c_end > c_start else 60.0
            chapters = self._single_detect(chunk_text, chunk_dur)
            for ch in chapters:
                ch.start_seconds += c_start
                ch.end_seconds += c_start
            all_chapters.extend(chapters)

        if len(all_chapters) > 1:
            deduped = [all_chapters[0]]
            for ch in all_chapters[1:]:
                last = deduped[-1]
                overlap_val = min(ch.end_seconds, last.end_seconds) - max(
                    ch.start_seconds, last.start_seconds
                )
                if overlap_val > 60:
                    if len(ch.title) > len(last.title):
                        deduped[-1] = ch
                else:
                    deduped.append(ch)
            all_chapters = deduped

        return all_chapters

    def _call_llm(
        self, prompt: str, video_duration: float
    ) -> List[Chapter]:
        """Call LLM with retry, json-repair, and uniform-split fallback."""
        last_error: Optional[Exception] = None
        for attempt in range(self.config.llm_max_retries + 1):
            try:
                if attempt > 0:
                    time.sleep(2**attempt)
                raw = self._llm_request(prompt)
                chapters = self._parse_response(raw, video_duration)
                return chapters
            except Exception as e:
                last_error = e
                continue

        return self._uniform_split(video_duration)

    def _llm_request(self, prompt: str) -> str:
        """Make the actual LLM API request (OpenAI-compatible).

        Raises:
            RuntimeError: If the ``openai`` package is not installed.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError("openai package required for LLM API")

        client = OpenAI(
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_api_base,
        )
        system_prompt = (
            "你是一个专业的视频编辑助手。你的任务是根据视频转录稿分析视频内容，"
            "划分章节。只输出纯JSON数组，不要输出任何其他文字、解释或markdown格式。JSON格式：[{\"title\":\"标题\",\"start\":\"HH:MM:SS\",\"end\":\"HH:MM:SS\"}]。"
        )
        response = client.chat.completions.create(
            model=self.config.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
            extra_headers={"HTTP-Referer": "https://lab.iwhalecloud.com"},
        )
        raw = response.choices[0].message.content.strip()  # type: ignore[union-attr]
        return raw

    def _parse_response(
        self, raw: str, video_duration: float
    ) -> List[Chapter]:
        """Parse LLM response JSON with json-repair fallback.

        Args:
            raw: Raw text response from the LLM.
            video_duration: Total video duration in seconds for bounds checking.

        Returns:
            Parsed chapter list.

        Raises:
            ValueError: If response is not a list, or timestamps are out of range.
        """
        raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
        raw = re.sub(r"\n?```\s*$", "", raw)

        if HAS_JSON_REPAIR and repair_json is not None:
            try:
                raw = repair_json(raw)
            except Exception:
                pass

        data = json.loads(raw)

        if not isinstance(data, list):
            raise ValueError(
                f"Expected JSON array, got {type(data).__name__}"
            )

        chapters: List[Chapter] = []
        idx = 1
        for item in data:
            title = item.get("title", f"{idx:02d}_片段{idx}")
            title = re.sub(r'[/:*?"<>|]', "", title)
            start = _parse_timestamp(item.get("start", "00:00:00"))
            end = _parse_timestamp(item.get("end", "00:00:00"))

            if start < 0 or end > video_duration + 5:
                raise ValueError(
                    f"Timecode out of range: start={start}, "
                    f"end={end}, duration={video_duration}"
                )
            if start >= end:
                raise ValueError(
                    f"Invalid time range: start={start} >= end={end}"
                )

            chapters.append(
                Chapter(
                    title=title,
                    start_seconds=start,
                    end_seconds=end,
                )
            )
            idx += 1

        return chapters

    def _uniform_split(self, duration: float) -> List[Chapter]:
        """Fallback: split video into uniform segments.

        When all LLM attempts fail, divide the video evenly into segments
        sized at ``max_segment_duration`` minutes.
        """
        seg_duration = self.config.max_segment_duration * 60
        num_segments = max(1, int(duration / seg_duration + 0.5))
        actual_seg = duration / num_segments

        chapters: List[Chapter] = []
        for i in range(num_segments):
            chapters.append(
                Chapter(
                    title=f"{i + 1:02d}_片段{i + 1}",
                    start_seconds=i * actual_seg,
                    end_seconds=min((i + 1) * actual_seg, duration),
                )
            )
        return chapters


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to ``MM:SS.sss`` or ``HH:MM:SS.sss``."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:06.3f}"
    return f"{m:02d}:{s:06.3f}"


def _parse_timestamp(ts: str) -> float:
    """Parse ``HH:MM:SS`` or ``MM:SS`` to seconds."""
    parts = ts.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    raise ValueError(f"Invalid timestamp: {ts}")
