"""Hotword extraction module for ASR enhancement.

This module extracts hotwords from documents to improve speech recognition
accuracy for domain-specific terminology, names, and technical terms.

Supported formats:
- .txt: Plain text (one term per line or space-separated)
- .docx: Word documents (extracts text from paragraphs)
- .pdf: PDF documents (extracts text from pages)

Usage:
    from video_splitter.extractor.hotwords import load_hotwords_from_file

    hotwords = load_hotwords_from_file("regulations.txt")
    # Returns: "热词1 热词2 热词3"
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def load_hotwords_from_file(file_path: str) -> str:
    """Load hotwords from a document file.

    Args:
        file_path: Path to the document file (.txt, .docx, or .pdf).

    Returns:
        Space-separated hotword string for FunASR.
        Empty string if file doesn't exist or extraction fails.

    Raises:
        ValueError: If file format is not supported.
    """
    if not os.path.exists(file_path):
        logger.warning("Hotword file does not exist: %s", file_path)
        return ""

    ext = Path(file_path).suffix.lower()

    try:
        if ext == ".txt":
            return _extract_from_txt(file_path)
        elif ext == ".docx":
            return _extract_from_docx(file_path)
        elif ext == ".pdf":
            return _extract_from_pdf(file_path)
        else:
            raise ValueError(
                f"Unsupported hotword file format: {ext}. "
                f"Supported formats: .txt, .docx, .pdf"
            )
    except Exception as e:
        logger.error("Failed to extract hotwords from %s: %s", file_path, e)
        return ""


def _extract_from_txt(file_path: str) -> str:
    """Extract hotwords from a plain text file.

    Supports two formats:
    1. One term per line
    2. Space-separated terms on a single line

    Args:
        file_path: Path to the text file.

    Returns:
        Space-separated hotword string.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by newlines first
    lines = content.strip().split("\n")

    hotwords = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):  # Skip empty lines and comments
            continue
        # Split by spaces within the line
        words = line.split()
        hotwords.extend(words)

    return _format_hotwords(hotwords)


def _extract_from_docx(file_path: str) -> str:
    """Extract hotwords from a Word document.

    Args:
        file_path: Path to the .docx file.

    Returns:
        Space-separated hotword string.
    """
    try:
        from docx import Document
    except ImportError:
        logger.error(
            "python-docx not installed. Install with: pip install python-docx"
        )
        return ""

    doc = Document(file_path)
    hotwords = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        # Extract terms (Chinese words or English phrases)
        words = _extract_terms_from_text(text)
        hotwords.extend(words)

    return _format_hotwords(hotwords)


def _extract_from_pdf(file_path: str) -> str:
    """Extract hotwords from a PDF document.

    Args:
        file_path: Path to the .pdf file.

    Returns:
        Space-separated hotword string.
    """
    try:
        import PyPDF2
    except ImportError:
        logger.error(
            "PyPDF2 not installed. Install with: pip install PyPDF2"
        )
        return ""

    hotwords = []

    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text = page.extract_text() or ""
            words = _extract_terms_from_text(text)
            hotwords.extend(words)

    return _format_hotwords(hotwords)


def _extract_terms_from_text(text: str) -> list[str]:
    """Extract meaningful terms from text.

    Strategy:
    - Chinese: Extract sequences of Chinese characters (2+ chars)
    - English: Extract words (3+ chars)
    - Skip common stop words

    Args:
        text: Input text.

    Returns:
        List of extracted terms.
    """
    # Common Chinese and English stop words to skip
    stop_words = {
        "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
        "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
        "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
        "什么", "怎么", "如何", "为什么", "哪", "谁", "多少", "几", "吗", "呢",
        "吧", "啊", "呀", "哦", "嗯", "the", "a", "an", "is", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "do", "does",
        "did", "will", "would", "could", "should", "may", "might", "must",
        "can", "need", "dare", "ought", "used", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "both", "each", "few", "more", "most",
        "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "and", "but", "or", "if", "while",
    }

    terms = []

    # Extract Chinese character sequences (2+ chars)
    chinese_pattern = r"[\u4e00-\u9fff]{2,}"
    for match in re.finditer(chinese_pattern, text):
        term = match.group()
        if term not in stop_words:
            terms.append(term)

    # Extract English words (3+ chars)
    english_pattern = r"\b[a-zA-Z]{3,}\b"
    for match in re.finditer(english_pattern, text):
        word = match.group().lower()
        if word not in stop_words:
            terms.append(word)

    return terms


def _format_hotwords(terms: list[str]) -> str:
    """Format terms into FunASR hotword string.

    FunASR expects hotwords as space-separated string.
    Removes duplicates while preserving order.

    Args:
        terms: List of terms.

    Returns:
        Space-separated hotword string.
    """
    # Remove duplicates while preserving order
    seen = set()
    unique_terms = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return " ".join(unique_terms)


def load_hotwords_from_env() -> str:
    """Load hotwords from environment variable.

    Checks VIDEO_SPLITTER_HOTWORD_FILE environment variable.

    Returns:
        Space-separated hotword string, or empty string if not set.
    """
    hotword_file = os.environ.get("VIDEO_SPLITTER_HOTWORD_FILE", "")
    if not hotword_file:
        return ""
    return load_hotwords_from_file(hotword_file)
