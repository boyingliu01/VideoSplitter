"""Interactive transcript review and correction for VideoSplitter."""

from __future__ import annotations

import json
import os
import logging
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROGRESS_SUFFIX = ".review_progress.json"


def load_transcript(path: str) -> dict[str, Any]:
    """Load transcript JSON file.

    Args:
        path: Path to the transcript JSON file.

    Returns:
        Dict with ``language``, ``duration``, ``segments``. Segments are
        filtered to remove empty and zero-length entries.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Transcript not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        transcript = json.load(f)
    transcript["segments"] = filter_segments(transcript["segments"])
    return transcript


def filter_segments(segments: list[dict]) -> list[dict]:
    """Filter out empty and zero-length segments.

    Segments with empty/whitespace-only text or identical start/end times
    are removed.

    Args:
        segments: List of segment dicts with ``text``, ``start``, ``end``.

    Returns:
        Filtered list of segments.
    """
    return [
        s for s in segments
        if s["text"].strip() != "" and s["start"] != s["end"]
    ]


def sanitize_text(text: str) -> str:
    """Strip control characters, null bytes, and normalize unicode.

    Removes C0 (0x00-0x1F) and C1 (0x7F-0x9F) control characters,
    strips null bytes, applies NFKC normalization, and strips whitespace.

    Args:
        text: Raw input text.

    Returns:
        Sanitized text string.
    """
    result = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 or (0x7F <= cp <= 0x9F):
            continue
        result.append(ch)
    cleaned = "".join(result)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    return cleaned.strip()


def save_transcript_atomic(path: str, transcript: dict[str, Any]) -> None:
    """Atomically write transcript JSON to disk.

    Writes to a temporary file then uses ``os.replace()`` for atomicity.

    Args:
        path: Target file path.
        transcript: Transcript dict to serialize.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(
        suffix=".json", dir=os.path.dirname(path)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(transcript, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def load_progress(video_path: str) -> dict[str, Any] | None:
    """Load review progress from ``.review_progress.json``.

    Args:
        video_path: Path to the video file.

    Returns:
        Progress dict or ``None`` if no progress file exists or the file
        is corrupted.
    """
    prog_path = video_path + _PROGRESS_SUFFIX
    if not os.path.exists(prog_path):
        return None
    try:
        with open(prog_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        corrupted_path = prog_path + ".corrupted"
        try:
            os.rename(prog_path, corrupted_path)
        except OSError:
            pass
        logger.warning(
            "Corrupted progress file, renamed to %s", corrupted_path
        )
        return None


def save_progress(video_path: str, progress: dict[str, Any]) -> None:
    """Write progress JSON file.

    Args:
        video_path: Path to the video file.
        progress: Progress dict to save.
    """
    prog_path = video_path + _PROGRESS_SUFFIX
    with open(prog_path, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def clear_progress(video_path: str) -> None:
    """Delete ``.review_progress.json`` if it exists.

    Args:
        video_path: Path to the video file.
    """
    prog_path = video_path + _PROGRESS_SUFFIX
    if os.path.exists(prog_path):
        os.unlink(prog_path)


def format_timestamp(seconds: float) -> str:
    """Format seconds to ``HH:MM:SS.mmm`` display format.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string.
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def format_segment_header(index: int, total: int, modified: int, seg: dict) -> str:
    """Format the per-segment display header with timecode.

    Args:
        index: Zero-based segment index.
        total: Total number of segments.
        modified: Number of segments modified so far.
        seg: Segment dict with ``text``, ``start``, ``end``.

    Returns:
        Formatted header string.
    """
    start_str = format_timestamp(seg["start"])
    end_str = format_timestamp(seg["end"])
    return (
        f"--- Segment {index + 1}/{total} "
        f"[{start_str} --> {end_str}] "
        f"({modified} changed) ---\n"
        f"  {seg['text']}"
    )


def run_review(
    video_path: str,
    transcript_path: str | None = None,
    resume: bool = False,
    no_save: bool = False,
) -> None:
    """Run the interactive transcript review loop.

    Args:
        video_path: Path to the input video.
        transcript_path: Path to the transcript JSON. Auto-derived from
            ``video_path`` if omitted (``.transcript.json`` suffix).
        resume: If ``True``, resume from the last saved checkpoint.
        no_save: If ``True``, do not save any changes (dry-run mode).

    Raises:
        FileNotFoundError: If the transcript file does not exist.
        ValueError: If the transcript format is invalid.
    """
    if transcript_path is None:
        # Auto-derive from video path: video.mp4 → video.transcript.json
        transcript_path = str(Path(video_path).with_suffix(".transcript.json"))

    transcript = load_transcript(transcript_path)
    segments = transcript["segments"]
    total = len(segments)

    if total == 0:
        print("No segments to review.")
        return

    # Load or initialize progress
    progress = load_progress(video_path) if resume else None
    if progress is None:
        progress = {"current_index": 0, "total": total}
    current_index = progress.get("current_index", 0)
    modified_count = progress.get("modified_count", 0)

    print(f"\n{'='*60}")
    print(f"Transcript Review: {os.path.basename(video_path)}")
    print(f"Segments: {total}  |  Language: {transcript.get('language', '?')}")
    print(f"Commands: Enter=keep  :q=quit  :p=prev  :h=help  :j N=jump")
    print(f"{'='*60}\n")

    last_input = None

    while current_index < total:
        seg = segments[current_index]
        print(format_segment_header(current_index, total, modified_count, seg))
        print("─" * 50)

        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nInterrupted. Saving progress...")
            save_progress(video_path, {
                "current_index": current_index,
                "total": total,
                "modified_count": modified_count,
            })
            return

        # Parse commands
        if user_input == ":q":
            print("Quitting. Progress saved.")
            save_progress(video_path, {
                "current_index": current_index,
                "total": total,
                "modified_count": modified_count,
            })
            return

        if user_input == ":p":
            if current_index > 0:
                current_index -= 1
            else:
                print("Already at first segment.")
            continue

        if user_input == ":h":
            print("Commands:")
            print("  Enter       — keep current text, go to next")
            print("  <new text>  — replace current text")
            print("  :q          — quit (save progress)")
            print("  :p          — go back to previous segment")
            print("  :j N        — jump to segment N (1-indexed)")
            print("  :h          — show this help")
            continue

        if user_input.startswith(":j "):
            try:
                target = int(user_input[3:].strip())
                if target < 1 or target > total:
                    print(f"Invalid segment: {target}. Must be 1-{total}.")
                else:
                    current_index = target - 1  # convert to 0-indexed
            except ValueError:
                print(f"Invalid jump target: {user_input[3:]}")
            continue

        # Treat as replacement text if non-empty
        if user_input != "":
            sanitized = sanitize_text(user_input)
            if sanitized != seg["text"]:
                if sanitized == "":
                    print("Warning: text is empty after sanitization. Keeping original.")
                else:
                    seg["text"] = sanitized
                    modified_count += 1
                    print(f"  ✓ Updated to: {sanitized}")

        last_input = user_input
        current_index += 1

        # Save progress after each segment
        if not no_save:
            save_progress(video_path, {
                "current_index": current_index,
                "total": total,
                "modified_count": modified_count,
            })

    # All segments reviewed
    if no_save:
        print(f"\n{'='*60}")
        print(f"Review complete (dry-run). {modified_count} segments would be changed.")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"Review complete. {modified_count} segments changed.")
        print(f"Saving transcript...")
        print(f"{'='*60}")

        # Atomic save transcript
        save_transcript_atomic(transcript_path, transcript)

        # Regenerate SRT via to_srt()
        try:
            from .extractor.transcribe import to_srt
            srt_content = to_srt(transcript)
            srt_path = str(Path(transcript_path).with_suffix("").with_suffix(".srt"))
            # Ensure we have a clean SRT path
            if not srt_path.endswith(".srt"):
                srt_path = str(Path(transcript_path).with_suffix(".srt"))
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            print(f"SRT updated: {srt_path}")
        except ImportError:
            logger.warning("Could not import to_srt; SRT not regenerated.")

        # Clear progress on successful completion
        clear_progress(video_path)
