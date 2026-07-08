"""Tests for extractor/hotwords.py"""
import sys
import importlib

sys.path.insert(0, r'E:\Private\VideoSplitter\.worktrees\sprint\sprint-2026-07-08-03')
hotwords_mod = importlib.import_module('video_splitter.extractor.hotwords')


class TestStripMarkdownSyntax:
    def test_strip_fenced_code(self):
        text = "hello\n```python\nprint('hi')\n```\nworld"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "print" not in result
        assert "hello" in result
        assert "world" in result

    def test_strip_inline_code(self):
        text = "use the `config.yaml` file"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "use the" in result
        assert "file" in result
        assert "config.yaml" not in result  # inline code content removed

    def test_strip_links_keep_text(self):
        text = "see [文档](https://example.com/doc) for details"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "文档" in result
        assert "https://example.com/doc" not in result

    def test_strip_images(self):
        text = "图: ![架构图](https://img.com/a.png) design"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "架构图" not in result
        assert "img.com" not in result

    def test_strip_headers_keep_content(self):
        text = "## 质量红线\n内容\n### 规则说明"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "质量红线" in result
        assert "规则说明" in result
        assert "##" not in result

    def test_strip_urls(self):
        text = "visit https://github.com/repo or http://test.com"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "https://github.com/repo" not in result

    def test_strip_table_separators(self):
        text = "| Header | Value |\n|--------|-------|\n| name | test |"
        result = hotwords_mod._strip_markdown_syntax(text)
        assert "--------" not in result
        assert "Header" in result
        assert "name" in result


class TestShouldKeep:
    def test_single_char_rejected(self):
        assert not hotwords_mod._should_keep("A")
        assert not hotwords_mod._should_keep("中")

    def test_digits_rejected(self):
        assert not hotwords_mod._should_keep("123")
        assert not hotwords_mod._should_keep("2024")

    def test_punctuation_rejected(self):
        assert not hotwords_mod._should_keep("...")
        assert not hotwords_mod._should_keep("---")

    def test_valid_words_kept(self):
        assert hotwords_mod._should_keep("质量红线")
        assert hotwords_mod._should_keep("刘伯英")
        assert hotwords_mod._should_keep("AI")


class TestValidateExtensions:
    def test_txt_allowed(self):
        hotwords_mod._validate_extensions(["test.txt"])

    def test_md_allowed(self):
        hotwords_mod._validate_extensions(["readme.md"])

    def test_pdf_rejected(self):
        try:
            hotwords_mod._validate_extensions(["doc.pdf"])
            assert False, "should have raised"
        except ValueError as e:
            assert ".pdf" in str(e)
            assert ".txt" in str(e)

    def test_docx_rejected(self):
        try:
            hotwords_mod._validate_extensions(["report.docx"])
            assert False, "should have raised"
        except ValueError:
            pass


class TestExtractHotwords:
    def test_empty_paths(self):
        result = hotwords_mod.extract_hotwords([])
        assert result == []

    def test_extract_basic(self):
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("质量红线是产品交付的最低标准。质量红线包括代码审查、测试覆盖率。"
                     "刘伯英负责质量红线的制定和执行。")
            tmp_path = f.name
        try:
            result = hotwords_mod.extract_hotwords([tmp_path])
            assert len(result) > 0
            assert len(result) <= 30
            for w in result:
                assert len(w) > 1
        finally:
            os.unlink(tmp_path)

    def test_respects_max_count(self):
        import tempfile, os
        # Generate enough unique terms to hit the limit
        text = " ".join(f"术语{i}" for i in range(100))
        text += " " + text  # repeat for TF-IDF weight
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            tmp_path = f.name
        try:
            result = hotwords_mod.extract_hotwords([tmp_path], max_count=5)
            assert len(result) <= 5
        finally:
            os.unlink(tmp_path)
