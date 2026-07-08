"""Core hotword extraction from reference documents using jieba TF-IDF."""

from __future__ import annotations

import logging
import os
import re
from typing import List

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = frozenset({".txt", ".md"})
_ENCODING_CHAIN = ("utf-8", "gbk", "latin-1")


def _strip_markdown_syntax(text: str) -> str:
    """Strip Markdown formatting to leave only plain text content.

    Handles:

    - Code fences (`` ```...``` ``)
    - Inline code (`` `...` ``)
    - Links ``[text](url)`` → ``text``
    - Images ``![alt](url)`` → removed
    - Table formatting ``|...|...|`` headers / separators
    - Headers ``# …`` through ``###### …``
    - Raw URLs (``http://`` / ``https://``)

    Args:
        text: Raw text that may contain Markdown syntax.

    Returns:
        Plain text with Markdown constructs stripped.
    """
    # 1. Remove fenced code blocks
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)

    # 2. Remove inline code
    text = re.sub(r"`[^`]+`", " ", text)

    # 3. Remove images ![alt](url) — must come before links
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)

    # 4. Remove Markdown links [text](url) → keep text
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # 5. Remove table formatting: separators (|---|---|) and leading/trailing pipes
    text = re.sub(r"^\s*\|[ \-:|]+\|\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\||\|\s*$", " ", text, flags=re.MULTILINE)

    # 6. Remove ATX headers (##, ###, etc.) — strip the markers, keep text
    text = re.sub(r"^#{1,6}\s+", " ", text, flags=re.MULTILINE)

    # 7. Remove raw URLs
    text = re.sub(r"https?://\S+", " ", text)

    return text


def _read_file_with_fallback(path: str) -> str:
    """Read a file with automatic encoding fallback.

    Tries encodings in order: utf-8 → gbk → latin-1.

    Args:
        path: Path to the file to read.

    Returns:
        File contents as a string.

    Raises:
        FileNotFoundError: If *path* does not exist.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")

    for encoding in _ENCODING_CHAIN:
        try:
            with open(path, "r", encoding=encoding) as fh:
                return fh.read()
        except (UnicodeDecodeError, UnicodeError):
            logger.debug("Failed to read %s as %s, trying next encoding", path, encoding)

    # latin-1 never raises UnicodeDecodeError, so we never reach here
    return ""


def _validate_extensions(paths: List[str]) -> None:
    """Validate that all file paths have supported extensions.

    Args:
        paths: List of file paths to validate.

    Raises:
        ValueError: If any path has an unsupported extension.
    """
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"Unsupported file extension {ext!r} for {p!r}. "
                f"Supported extensions: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
            )


def _should_keep(word: str) -> bool:
    """Decide whether a candidate hotword should be kept.

    Filters out:

    - Words with length ≤ 1
    - Words that consist entirely of digits
    - Words that consist entirely of punctuation / whitespace symbols

    Args:
        word: The candidate word.

    Returns:
        ``True`` if the word passes all filters.
    """
    if len(word) <= 1:
        return False
    if word.isdigit():
        return False
    if re.fullmatch(r"[\W_]+", word):
        return False
    return True


def extract_hotwords(
    paths: list[str],
    max_count: int = 30,
) -> list[str]:
    """Extract hotwords from reference documents using jieba TF-IDF.

    Reads each file, strips Markdown syntax, concatenates the plain text,
    then runs :func:`jieba.analyse.extract_tags` (TF-IDF) on the combined
    corpus.  The result is filtered to remove single-character tokens,
    purely-digit tokens, and purely-punctuation tokens.

    Args:
        paths: List of file paths to reference documents.  Only ``.txt``
            and ``.md`` files are supported.
        max_count: Maximum number of hotwords to return (default 30).

    Returns:
        List of hotword strings, ordered by TF-IDF weight (most important
        first).

    Raises:
        ValueError: If any path has an unsupported file extension.
        FileNotFoundError: If a path does not exist.
    """
    import jieba.analyse

    if not paths:
        return []

    _validate_extensions(paths)

    corpus_parts: list[str] = []
    for path in paths:
        raw = _read_file_with_fallback(path)
        cleaned = _strip_markdown_syntax(raw)
        if cleaned.strip():
            corpus_parts.append(cleaned)

    if not corpus_parts:
        logger.warning("No text content found in provided files")
        return []

    combined = "\n".join(corpus_parts)

    candidates_raw = jieba.analyse.extract_tags(
        combined,
        topK=max_count * 3,  # over-capture to account for filtering
        withWeight=False,
    )
    # jieba stubs are incomplete; withWeight=False always returns list[str]
    candidates: list[str] = list(candidates_raw)  # type: ignore[arg-type]

    result = [w for w in candidates if _should_keep(w)]
    return result[:max_count]
