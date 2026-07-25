"""Configuration management for video_splitter.

Dataclass fields:
    model_size, device, compute_type: Whisper model config
    max_segment_duration, min_segment_duration: Segment length bounds (seconds)
    llm_*: LLM summarisation settings
    cut_mode, keyframe_tolerance: Cutting strategy
    language, naming_template, resume: Output settings
    transcription_engine: ASR engine name ("funasr"), overridable via VIDEO_SPLITTER_ENGINE env var
    engine_config: Engine-specific overrides (model_name, device, etc.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class SplitConfig:
    model_size: str = "large-v3"
    device: str = "auto"
    compute_type: str = "auto"
    max_segment_duration: int = 15
    min_segment_duration: int = 1
    llm_api_base: str = "https://lab.iwhalecloud.com/gpt-proxy"
    llm_api_key: str = ""
    llm_model: str = "MiniMax-M2.7"
    llm_token_budget: int = 60000
    llm_max_retries: int = 3
    cut_mode: str = "fast"
    keyframe_tolerance: float = 0.5
    language: str = "zh"
    naming_template: str = "{basename}_{seq:02d}_{title}"
    resume: bool = False
    transcription_engine: str = "funasr"
    engine_config: dict = field(default_factory=dict)
    hotword_file: str = ""  # Path to hotword document for ASR enhancement

    @classmethod
    def from_env(cls) -> SplitConfig:
        c = cls()
        # whalecloud local model (default for this config)
        c.llm_api_base = os.environ.get("OPENAI_API_BASE", c.llm_api_base)
        c.llm_api_key = os.environ.get("OPENAI_API_KEY", "")
        if os.environ.get("WHALECLOUD_API_KEY"):
            c.llm_api_key = os.environ["WHALECLOUD_API_KEY"]
        if os.environ.get("VIDEO_SPLITTER_DEVICE"):
            c.device = os.environ["VIDEO_SPLITTER_DEVICE"]
        if os.environ.get("VIDEO_SPLITTER_RESUME", "").lower() in ("1", "true", "yes"):
            c.resume = True
        if os.environ.get("VIDEO_SPLITTER_ENGINE"):
            c.transcription_engine = os.environ["VIDEO_SPLITTER_ENGINE"]
        if os.environ.get("VIDEO_SPLITTER_HOTWORD_FILE"):
            c.hotword_file = os.environ["VIDEO_SPLITTER_HOTWORD_FILE"]
        return c
