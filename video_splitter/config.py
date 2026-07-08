"""Configuration management for video_splitter."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SplitConfig:
    model_size: str = "paraformer-zh"
    device: str = "auto"
    compute_type: str = "auto"  # No-op under FunASR; kept for backward compat
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
        return c
