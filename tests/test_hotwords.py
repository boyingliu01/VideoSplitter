"""Unit tests for hotword extraction module."""

from __future__ import annotations

import os
import tempfile

import pytest

from video_splitter.extractor.hotwords import (
    load_hotwords_from_file,
    load_hotwords_from_env,
    _extract_from_txt,
    _extract_terms_from_text,
    _format_hotwords,
)


class TestLoadHotwordsFromFile:
    """Test load_hotwords_from_file function."""

    def test_nonexistent_file_returns_empty(self):
        """Non-existent file should return empty string."""
        result = load_hotwords_from_file("/nonexistent/path/file.txt")
        assert result == ""

    def test_unsupported_format_returns_empty(self, tmp_path):
        """Unsupported file format should return empty string (logged as error)."""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("some content")
        result = load_hotwords_from_file(str(bad_file))
        assert result == ""

    def test_txt_file_one_per_line(self, tmp_path):
        """Text file with one term per line should work."""
        txt_file = tmp_path / "hotwords.txt"
        txt_file.write_text("人工智能\n机器学习\n深度学习")
        result = load_hotwords_from_file(str(txt_file))
        assert "人工智能" in result
        assert "机器学习" in result
        assert "深度学习" in result

    def test_txt_file_space_separated(self, tmp_path):
        """Text file with space-separated terms should work."""
        txt_file = tmp_path / "hotwords.txt"
        txt_file.write_text("人工智能 机器学习 深度学习")
        result = load_hotwords_from_file(str(txt_file))
        assert "人工智能" in result
        assert "机器学习" in result
        assert "深度学习" in result

    def test_txt_file_skips_comments(self, tmp_path):
        """Text file should skip lines starting with #."""
        txt_file = tmp_path / "hotwords.txt"
        txt_file.write_text("# This is a comment\n人工智能\n# Another comment\n机器学习")
        result = load_hotwords_from_file(str(txt_file))
        assert "人工智能" in result
        assert "机器学习" in result
        assert "#" not in result
        assert "comment" not in result.lower()

    def test_txt_file_skips_empty_lines(self, tmp_path):
        """Text file should skip empty lines."""
        txt_file = tmp_path / "hotwords.txt"
        txt_file.write_text("人工智能\n\n\n机器学习\n\n")
        result = load_hotwords_from_file(str(txt_file))
        assert "人工智能" in result
        assert "机器学习" in result


class TestExtractFromTxt:
    """Test _extract_from_txt function."""

    def test_basic_extraction(self, tmp_path):
        """Basic text extraction should work."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("热词一\n热词二\n热词三")
        result = _extract_from_txt(str(txt_file))
        assert "热词一" in result
        assert "热词二" in result
        assert "热词三" in result


class TestExtractTermsFromText:
    """Test _extract_terms_from_text function."""

    def test_chinese_terms(self):
        """Should extract Chinese character sequences."""
        text = "这是一个测试文本包含多个中文词汇"
        terms = _extract_terms_from_text(text)
        assert len(terms) > 0
        # All terms should be Chinese characters
        for term in terms:
            assert all("\u4e00" <= c <= "\u9fff" for c in term)

    def test_english_terms(self):
        """Should extract English words (3+ chars)."""
        text = "This is a test with some English words like algorithm and machine"
        terms = _extract_terms_from_text(text)
        # Should extract words but skip stop words like "this", "is", "a"
        assert "test" in terms or "algorithm" in terms or "machine" in terms

    def test_skips_stop_words(self):
        """Should skip common stop words."""
        # Single stop words should be skipped
        text = "的 了 在 是 我"
        terms = _extract_terms_from_text(text)
        # Each word is a single character, won't match 2+ char pattern
        assert len(terms) == 0


class TestFormatHotwords:
    """Test _format_hotwords function."""

    def test_removes_duplicates(self):
        """Should remove duplicate terms."""
        terms = ["人工智能", "机器学习", "人工智能", "深度学习", "机器学习"]
        result = _format_hotwords(terms)
        assert result.count("人工智能") == 1
        assert result.count("机器学习") == 1
        assert "深度学习" in result

    def test_preserves_order(self):
        """Should preserve order of first occurrence."""
        terms = ["三", "一", "二", "一", "三"]
        result = _format_hotwords(terms)
        words = result.split()
        assert words == ["三", "一", "二"]

    def test_space_separated(self):
        """Should return space-separated string."""
        terms = ["词一", "词二", "词三"]
        result = _format_hotwords(terms)
        assert result == "词一 词二 词三"


class TestLoadHotwordsFromEnv:
    """Test load_hotwords_from_env function."""

    def test_no_env_var_returns_empty(self, monkeypatch):
        """Should return empty string if env var not set."""
        monkeypatch.delenv("VIDEO_SPLITTER_HOTWORD_FILE", raising=False)
        result = load_hotwords_from_env()
        assert result == ""

    def test_with_env_var(self, monkeypatch, tmp_path):
        """Should load hotwords from file specified in env var."""
        txt_file = tmp_path / "hotwords.txt"
        txt_file.write_text("人工智能\n机器学习")
        monkeypatch.setenv("VIDEO_SPLITTER_HOTWORD_FILE", str(txt_file))
        result = load_hotwords_from_env()
        assert "人工智能" in result
        assert "机器学习" in result
