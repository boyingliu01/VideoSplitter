"""Pipeline orchestrator: precheck → extract → transcribe → chapter → validate → cut."""
from __future__ import annotations

import json
import os
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import SplitConfig
from .extractor.audio import AudioExtractor
from .extractor.transcribe import transcribe, estimate_tokens, to_srt
from .extractor.hotwords import extract_hotwords
from .analyzer.chapter import Chapter, ChapterDetector
from .analyzer.validator import ChapterValidator
from .splitter.cutter import VideoCutter

logger = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates the full video splitting pipeline."""

    def __init__(self, config: Optional[SplitConfig] = None, reference_docs: Optional[list[str]] = None):
        self.config = config or SplitConfig.from_env()
        self.reference_docs = reference_docs
        self.audio = AudioExtractor()
        self.chapter_detector = ChapterDetector(self.config)
        self.validator = ChapterValidator(self.config)
        self.cutter = VideoCutter(self.config)

    def run(self, video_path: str) -> Dict[str, Any]:
        start_time = time.time()
        video_path = os.path.abspath(video_path)
        base = Path(video_path).stem
        transcript_path = str(Path(video_path).with_suffix(".transcript.json"))
        chapters_path = str(Path(video_path).with_suffix(".chapters.json"))
        output_dir = str(Path(video_path).parent / (base + "_segments"))
        srt_path = str(Path(video_path).with_suffix(".zh.srt"))

        result = {
            "video": video_path,
            "status": "success",
            "steps_completed": [],
            "output_files": [],
        }

        try:
            ok, msg = self.audio.precheck(video_path)
            logger.info(f"Precheck: {msg}")
            if not ok:
                raise RuntimeError(msg)
            result["steps_completed"].append("precheck")

            transcript = None
            if self.config.resume and os.path.exists(transcript_path):
                with open(transcript_path, "r", encoding="utf-8") as f:
                    transcript = json.load(f)
                logger.info("Resuming from existing transcript")
            else:
                logger.info("Extracting audio and transcribing...")
                audio_path = self.audio.extract(video_path)

                hotwords = None
                if self.reference_docs:
                    logger.info(
                        "Extracting hotwords from %d reference document(s)...",
                        len(self.reference_docs),
                    )
                    hotwords = extract_hotwords(
                        self.reference_docs,
                        max_count=self.config.hotword_max_count,
                    )
                    logger.info("Extracted %d hotwords", len(hotwords))
                else:
                    logger.warning(
                        "\u672a\u63d0\u4f9b\u53c2\u8003\u6587\u6863\u3002"
                        "\u4e3a\u63d0\u5347\u8bed\u97f3\u8bc6\u522b\u51c6\u786e\u6027\uff0c"
                        "\u60a8\u53ef\u4ee5\u901a\u8fc7 --reference-doc \u53c2\u6570"
                        "\u63d0\u4f9b\u4e00\u4e2a\u6216\u591a\u4e2a\u53c2\u8003\u6587\u6863"
                        "\uff08\u5982\u89c4\u7ae0\u5236\u5ea6\u3001\u4e13\u4e1a\u672f\u8bed\u8bf4\u660e\uff09\uff0c"
                        "\u7a0b\u5e8f\u5c06\u81ea\u52a8\u63d0\u53d6\u5173\u952e\u672f\u8bed\u4f5c\u4e3a hotword\uff0c"
                        "\u5e2e\u52a9 FunASR \u66f4\u51c6\u786e\u5730\u8bc6\u522b\u4e13\u6709\u540d\u8bcd\u3002"
                    )
                    hotwords = None

                transcript = transcribe(audio_path, self.config, hotwords=hotwords)
                with open(transcript_path, "w", encoding="utf-8") as f:
                    json.dump(transcript, f, ensure_ascii=False, indent=2)
                logger.info(f"Transcript saved: {transcript_path}")
            result["steps_completed"].append("transcribe")

            srt_content = to_srt(transcript)
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            result["srt_file"] = srt_path

            chapters = None
            if self.config.resume and os.path.exists(chapters_path):
                with open(chapters_path, "r", encoding="utf-8") as f:
                    chapters_data = json.load(f)
                chapters = [Chapter(**ch) for ch in chapters_data]
                logger.info("Resuming from existing chapters")
            else:
                token_est = estimate_tokens(transcript)
                logger.info(f"Estimated tokens: {token_est}")
                chapters = self.chapter_detector.detect(transcript)
                chapters_data = [ch.to_dict() for ch in chapters]
                with open(chapters_path, "w", encoding="utf-8") as f:
                    json.dump(chapters_data, f, ensure_ascii=False, indent=2)
                logger.info(f"Chapters saved: {chapters_path}")
            result["steps_completed"].append("chapter")

            chapters = self.validator.validate(
                chapters,
                transcript.get("segments", []),
                base,
            )
            logger.info(f"Validated {len(chapters)} segments")
            result["steps_completed"].append("validate")

            output_files = self.cutter.cut(video_path, chapters, output_dir)
            result["output_files"] = output_files
            result["steps_completed"].append("cut")
            logger.info(f"Cut complete: {len(output_files)} segments")

        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Pipeline failed: {e}")
            raise

        finally:
            result["elapsed_seconds"] = round(time.time() - start_time, 1)

        return result

    def dry_run(self, video_path: str) -> Dict[str, Any]:
        ok, msg = self.audio.precheck(video_path)
        if not ok:
            return {"status": "error", "message": msg}

        audio_path = self.audio.extract(video_path)

        hotwords = None
        if self.reference_docs:
            hotwords = extract_hotwords(
                self.reference_docs,
                max_count=self.config.hotword_max_count,
            )

        transcript = transcribe(audio_path, self.config, hotwords=hotwords)
        token_est = estimate_tokens(transcript)
        cost_est = (token_est / 1_000_000) * 0.10

        duration = transcript.get("duration", 0)
        return {
            "status": "ok",
            "duration_minutes": round(duration / 60, 1),
            "estimated_tokens": token_est,
            "estimated_cost_rmb": round(cost_est, 6),
            "llm_calls": 1 if token_est <= self.config.llm_token_budget else "multiple (chunked)",
        }
