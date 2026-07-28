"""Worker object: LLM postprocessing in background thread.

Runs postprocess_segments() from video_splitter.extractor.postprocess
in a QThread so the GUI stays responsive during LLM API calls.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal, Slot

from video_splitter.config import SplitConfig
from video_splitter.extractor.postprocess import postprocess_segments

logger = logging.getLogger(__name__)


class PostprocessWorker(QObject):
    """LLM postprocessing worker running in a background QThread.

    Connects to an OpenAI-compatible LLM to clean filler words,
    fix sentence breaks, and optionally apply hotword corrections
    to ASR transcript segments.

    Signals:
        postprocess_complete: (list) cleaned segments
        postprocess_warning: (str) non-fatal warning (e.g. segment reverted)
        error: (str) fatal error message
    """

    postprocess_complete = Signal(list)
    postprocess_warning = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        config: Optional[SplitConfig] = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config if config is not None else SplitConfig()

    def _make_llm_fn(self, hotwords: str | None = None) -> Callable[[str], str]:
        """Create an LLM callable using the configured OpenAI-compatible API.

        Returns a callable that takes a prompt string and returns the response.
        This is a lightweight factory; no network call is made until the
        returned callable is invoked.

        Raises:
            ImportError: If the ``openai`` package is not installed.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("openai package required for LLM postprocessing")

        api_base = self._resolve_setting("POSTPROCESS_API_BASE", "llm_api_base")
        api_key = self._resolve_setting("POSTPROCESS_API_KEY", "llm_api_key")
        model = self._resolve_setting("POSTPROCESS_MODEL", "llm_model")

        if not api_key:
            raise ValueError(
                "No LLM API key configured. Set OPENAI_API_KEY or "
                "VIDEO_SPLITTER_POSTPROCESS_API_KEY environment variable."
            )

        client = OpenAI(api_key=api_key, base_url=api_base)
        logger.info("PostprocessWorker LLM: model=%s base_url=%s", model, api_base)

        def _call_llm(prompt: str) -> str:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是一个专业的语音识别后处理助手。"
                            "你的任务是润色ASR识别结果，删除语气词和口头禅，"
                            "修正断句错误。只输出润色后带[SEG_N]标记的文本，"
                            "不要添加任何解释。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=16384,
            )
            return response.choices[0].message.content.strip()  # type: ignore[union-attr]

        return _call_llm

    def _resolve_setting(self, dedicated_env: str, fallback_attr: str) -> str:
        """Resolve a setting: dedicated env var > fallback config attr."""
        import os

        env_var = f"VIDEO_SPLITTER_{dedicated_env}"
        env_val = os.environ.get(env_var, "")
        if env_val:
            return env_val
        return getattr(self._config, fallback_attr, "")

    @Slot(list, str, str, result=None)
    def run(
        self,
        segments: list,
        hotwords: str = "",
        language: str = "zh",
    ) -> None:
        """Execute LLM postprocessing on segments.

        Args:
            segments: List of segment dicts with ``text``, ``start``, ``end``, ``id``.
            hotwords: Comma-separated hotword list for correction.
            language: Language code (default ``"zh"``).
        """
        try:
            if not segments:
                self.postprocess_complete.emit([])
                return

            # Check if postprocessing is enabled
            import os
            if os.environ.get("VIDEO_SPLITTER_POSTPROCESS_ENABLED", "1") == "0":
                logger.info("Postprocessing disabled via env var, skipping")
                self.postprocess_complete.emit(segments)
                return

            llm_fn = self._make_llm_fn(hotwords if hotwords else None)
            cleaned, warnings = postprocess_segments(
                segments,
                llm_fn,
                hotwords=hotwords if hotwords else None,
                language=language,
            )

            for w in warnings:
                self.postprocess_warning.emit(w)

            self.postprocess_complete.emit(cleaned)

        except ImportError as exc:
            logger.warning("Postprocessing skipped: %s", exc)
            self.postprocess_complete.emit(segments)
        except Exception as exc:
            logger.error("Postprocessing failed: %s", exc)
            self.error.emit(str(exc))
