"""
Unified source document parser — dispatches to Word / PDF / text parsers.

Every parser returns a ``SourceDocument`` dict so downstream nodes never
need to know which file format the input was.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.config import get_config

# Re-export the TypedDict so other modules can import from here
from src.models import SourceDocument


def parse_document(file_path: str | Path) -> SourceDocument:
    """Parse a source document into a unified representation.

    Supported formats:
        - ``.docx``  → python-docx
        - ``.pdf``   → PyMuPDF (fitz)
        - ``.txt``   → plain text with heuristic splitting
        - ``.md``    → plain text (Markdown preserved)

    Args:
        file_path: Absolute or relative path to the document.

    Returns:
        A ``SourceDocument`` with title, text, sections, tables, images, metadata.

    Raises:
        FileNotFoundError: If the path does not exist.
        ValueError: If the file extension is not supported.
    """
    path = Path(file_path).resolve()
    ext = path.suffix.lower()

    # Check format BEFORE existence (better error messages)
    if ext not in (".docx", ".pdf", ".txt", ".md", ".text", ".markdown"):
        raise ValueError(
            f"Unsupported document format: '{ext}'. "
            f"Supported: .docx, .pdf, .txt, .md"
        )

    if not path.exists():
        raise FileNotFoundError(f"Source document not found: {path}")

    if ext == ".docx":
        from src.parsing.word_parser import parse_docx
        return parse_docx(path)

    elif ext == ".pdf":
        from src.parsing.pdf_parser import parse_pdf
        return parse_pdf(path)

    elif ext in (".txt", ".md", ".text", ".markdown"):
        from src.parsing.text_parser import parse_text
        return parse_text(path)

    else:
        raise ValueError(
            f"Unsupported document format: '{ext}'. "
            f"Supported: .docx, .pdf, .txt, .md"
        )


def _save_extracted_image(
    image_bytes: bytes,
    prefix: str,
    index: int,
    ext: str = "png",
) -> str:
    """Save extracted image bytes to the temp directory.

    Args:
        image_bytes: Raw image data.
        prefix: Filename prefix (e.g. source document name).
        index: Sequential index for uniqueness.
        ext: File extension.

    Returns:
        Absolute path to the saved image file.
    """
    cfg = get_config()
    dest = cfg.temp_dir / f"{prefix}_img_{index:03d}.{ext}"
    dest.write_bytes(image_bytes)
    return str(dest)


def _table_to_text(headers: list[str], rows: list[list[str]]) -> str:
    """Render a table as markdown text."""
    lines = [" | ".join(headers)]
    lines.append(" | ".join(["---"] * len(headers)))
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        lines.append(" | ".join(padded[:len(headers)]))
    return "\n".join(lines)
