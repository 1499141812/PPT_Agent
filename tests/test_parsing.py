"""
Tests for source document parsing (Word, PDF, Text).
"""

import tempfile
from pathlib import Path

import pytest

from src.parsing.source_document import parse_document
from src.parsing.word_parser import parse_docx
from src.parsing.text_parser import parse_text


class TestTextParser:
    """Tests for plain text / Markdown parsing."""

    def test_parse_simple_text(self) -> None:
        """Parse a simple text file with headings."""
        content = """# My Document Title

## Section 1

This is the first paragraph of section 1.
It spans multiple lines.

## Section 2

This is section 2 content.

| Name | Age | City |
|------|-----|------|
| Alice | 30 | NYC |
| Bob | 25 | LA |
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            doc = parse_text(tmp_path)
            assert doc["title"] == "My Document Title"
            assert len(doc["sections"]) >= 2
            assert len(doc["tables"]) == 1
            assert doc["tables"][0]["headers"] == ["Name", "Age", "City"]
            assert len(doc["tables"][0]["rows"]) == 2
        finally:
            tmp_path.unlink()

    def test_parse_flat_text(self) -> None:
        """Parse text without headings."""
        content = "Just some content without any headings.\nMore content here."
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            doc = parse_text(tmp_path)
            assert len(doc["sections"]) >= 1
            assert doc["full_text"] != ""
        finally:
            tmp_path.unlink()

    def test_parse_empty_file(self) -> None:
        """Parse an empty file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            tmp_path = Path(f.name)

        try:
            doc = parse_text(tmp_path)
            assert doc["title"] != ""
            assert doc["metadata"]["type"] == "txt"
        finally:
            tmp_path.unlink()


class TestDocumentDispatcher:
    """Tests for the unified parse_document dispatcher."""

    def test_dispatch_txt(self) -> None:
        """Dispatcher should route .txt to text parser."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Test\nContent")
            tmp_path = Path(f.name)

        try:
            doc = parse_document(tmp_path)
            assert doc["metadata"]["type"] == "txt"
            assert "Test" in doc["full_text"]
        finally:
            tmp_path.unlink()

    def test_dispatch_unsupported_extension(self) -> None:
        """Unsupported extensions should raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported"):
            parse_document(Path("/nonexistent/file.xyz"))

    def test_dispatch_file_not_found(self) -> None:
        """Missing files should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            parse_document(Path("/nonexistent/file.docx"))
