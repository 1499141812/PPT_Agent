"""
PDF document parser using PyMuPDF (fitz).

Extracts: text blocks (heuristic heading detection), tables, and embedded images.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from src.models import SourceDocument
from src.parsing.source_document import _table_to_text
from src.parsing.source_document import _save_extracted_image


def parse_pdf(path: Path) -> SourceDocument:
    """Parse a .pdf file into a SourceDocument.

    Heading detection heuristic:
        - First text block on a page → likely a heading if bold / large font.
        - Text blocks that are short (< 100 chars) and separated by whitespace
          from surrounding blocks are treated as sub-headings.

    Args:
        path: Absolute path to the .pdf file.

    Returns:
        Fully populated SourceDocument.
    """
    doc = fitz.open(str(path))
    title: str = path.stem
    sections: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    # Try to extract title from PDF metadata
    meta_title = doc.metadata.get("title", "")
    if meta_title:
        title = meta_title

    image_counter = 0
    table_counter = 0
    current_section: dict[str, Any] | None = None

    def _flush_section() -> None:
        nonlocal current_section
        if current_section and current_section.get("paragraphs"):
            sections.append(current_section)
        current_section = None

    for page_num, page in enumerate(doc, start=1):
        # ── Extract text blocks ─────────────────────────────────────────
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if block["type"] == 0:  # text block
                text = ""
                font_sizes: list[float] = []
                is_bold = False

                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text += span["text"]
                        font_sizes.append(span["size"])
                        if "Bold" in (span.get("font", "") or ""):
                            is_bold = True

                text = text.strip()
                if not text:
                    continue

                avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 11.0

                # Heuristic: first text on a page or large/bold → heading
                is_heading = (
                    len(sections) == 0 and current_section is None
                ) or (
                    len(text) < 100
                    and (avg_font_size > 14 or is_bold)
                    and not text.endswith(".")
                )

                if is_heading:
                    _flush_section()
                    level = 1 if avg_font_size > 18 else 2
                    current_section = {
                        "heading": text,
                        "level": level,
                        "paragraphs": [],
                        "images": [],
                        "tables": [],
                        "page": page_num,
                    }
                    full_text_parts.append(f"\n{'#' * level} {text}\n")
                else:
                    if current_section is None:
                        current_section = {
                            "heading": "",
                            "level": 0,
                            "paragraphs": [],
                            "images": [],
                            "tables": [],
                            "page": page_num,
                        }
                    current_section["paragraphs"].append(text)
                    full_text_parts.append(text)

            elif block["type"] == 1:  # image block
                image_counter += 1
                # Extract image using fitz
                try:
                    base_image = doc.extract_image(block.get("image", None))
                    if base_image:
                        img_bytes = base_image["image"]
                        ext = base_image["ext"]
                        saved_path = _save_extracted_image(
                            img_bytes, path.stem, image_counter, ext
                        )
                        img_entry = {
                            "caption": f"Page {page_num} Image {image_counter}",
                            "path_to_saved_image": saved_path,
                            "page": page_num,
                        }
                        images.append(img_entry)
                        if current_section is not None:
                            current_section.setdefault("images", []).append(img_entry)
                except Exception:
                    pass  # Some inline images can't be extracted — skip gracefully

        # ── Extract tables on this page ──────────────────────────────────
        try:
            page_tables = page.find_tables()
            for tbl in page_tables:
                table_counter += 1
                extracted = tbl.extract()
                if extracted:
                    headers = [str(h) if h else "" for h in extracted[0]]
                    rows = [
                        [str(c) if c else "" for c in row]
                        for row in extracted[1:]
                    ]
                    table_entry = {
                        "caption": f"Table {table_counter} (Page {page_num})",
                        "headers": headers,
                        "rows": rows,
                        "page": page_num,
                    }
                    tables.append(table_entry)
                    if current_section is not None:
                        current_section.setdefault("tables", []).append(table_entry)
                    full_text_parts.append(_table_to_text(headers, rows))
        except Exception:
            pass  # find_tables may fail on some PDFs

    _flush_section()

    # If no sections detected, create one with all text
    if not sections:
        sections.append({
            "heading": title,
            "level": 0,
            "paragraphs": [p for p in full_text_parts if p.strip()],
            "images": images,
            "tables": tables,
        })

    doc.close()

    return SourceDocument(
        title=title,
        full_text="\n\n".join(full_text_parts),
        sections=sections,
        tables=tables,
        images=images,
        metadata={
            "filename": path.name,
            "type": "pdf",
            "page_count": doc.page_count if hasattr(doc, "page_count") else len(doc),
            "section_count": len(sections),
            "table_count": len(tables),
            "image_count": len(images),
        },
    )
