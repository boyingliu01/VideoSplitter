"""Model loader worker — loads FunASR model in a dedicated background thread.

Separated from StreamingTranscribeWorker so that model loading progress
can be reported to the UI independently, preventing the "Not Responding"
freeze when AutoModel() blocks for minutes on first load.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal, Slot

logger = logging.getLogger(__name__)


class ModelLoaderWorker(QObject):
    """Loads the FunASR ASR model in a background QThread.

    Emits progress signals so the UI stays responsive during the
    potentially long model initialization (first run can take minutes).
    Uses the module-level singleton cache in engines.py so subsequent
    calls return immediately.

    Signals:
        progress: (description: str) — human-readable loading step
        finished: (success: bool, message: str) — loading result
    """

    progress = Signal(str)
    finished = Signal(bool, str)

    @Slot()
    def run(self) -> None:
        """Load the FunASR model. Called from QThread.started."""
        try:
            from video_splitter.extractor.engines import (
                load_funasr_model,
                clear_funasr_model_cache,
            )

            # If model is already cached (e.g. from health check), return fast
            self.progress.emit("Checking model cache...")
            model = load_funasr_model(use_cache=True)
            if model is not None:
                self.progress.emit("Model ready (cached)")
                self.finished.emit(True, "Model loaded from cache")
                return

            # Force load (cache miss)
            self.progress.emit("Loading speech recognition model...")
            self.progress.emit("  - Loading Paraformer acoustic model...")
            model = load_funasr_model(use_cache=False)
            self.progress.emit("  - Loading CT-Transformer punctuation model...")
            self.progress.emit("Model loaded successfully")
            self.finished.emit(True, "Model loaded")

        except Exception as exc:
            logger.exception("Model loading failed")
            self.finished.emit(False, f"Model loading failed: {exc}")
