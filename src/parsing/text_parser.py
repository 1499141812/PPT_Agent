"""
Plain text / Markdown document parser.

Uses blank-line splitting and Markdown-style heading markers for structure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.models import SourceDocument
from src.parsing.source_document import _table_to_text


def parse_text(path: Path) -> SourceDocument:
    """Parse a .txt or .md file into a SourceDocument.

    Splitting strategy:
        - Lines starting with ``#`` are headings.
        - Lines starting with ``-``, ``*``, or ``1.`` are list items.
        - Blank lines separate paragraphs / logical blocks.
        - ``|...|...|`` blocks are detected as tables.

    Args:
        path: Absolute path to the .txt / .md file.

    Returns:
        Fully populated SourceDocument.
    """
    raw_text = path.read_text(encoding="utf-8")
    title = path.stem

    sections: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    current_section: dict[str, Any] | None = None
    table_lines: list[str] = []
    in_table = False

    lines = raw_text.split("\n")

    for line in lines:
        stripped = line.strip()

        # ── Table detection ─────────────────────────────────────────────
        is_table_line = bool(re.match(r"^\|.+\|$", stripped))
        is_separator = bool(re.match(r"^\|[\s\-:|]+\|$", stripped)) if is_table_line else False

        if is_table_line:
            if not in_table:
                in_table = True
                table_lines = []
            table_lines.append(stripped)
            continue
        elif in_table:
            # End of table — a non-table line appeared
            _flush_table(table_lines, tables, full_text_parts, current_section)
            in_table = False
            table_lines = []

        # ── Heading detection ───────────────────────────────────────────
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)

            # Flush previous section
            if current_section and current_section.get("paragraphs"):
                sections.append(current_section)

            current_section = {
                "heading": heading_text,
                "level": level,
                "paragraphs": [],
                "images": [],
                "tables": [],
            }
            full_text_parts.append(f"\n{'#' * level} {heading_text}\n")
            if level == 1 and title == path.stem:
                title = heading_text
            continue

        # ── Blank line → paragraph break ────────────────────────────────
        if not stripped:
            continue

        # ── Regular paragraph ───────────────────────────────────────────
        if current_section is None:
            current_section = {
                "heading": "",
                "level": 0,
                "paragraphs": [],
                "images": [],
                "tables": [],
            }

        current_section["paragraphs"].append(stripped)
        full_text_parts.append(stripped)

    # Flush any remaining table at end of file
    if in_table:
        _flush_table(table_lines, tables, full_text_parts, current_section)

    # Flush last section
    if current_section and current_section.get("paragraphs"):
        sections.append(current_section)

    # Fallback
    if not sections:
        sections.append({
            "heading": title,
            "level": 0,
            "paragraphs": [p for p in full_text_parts if p.strip()],
            "images": [],
            "tables": tables,
        })

    return SourceDocument(
        title=title,
        full_text="\n\n".join(full_text_parts),
        sections=sections,
        tables=tables,
        images=[],  # .txt files have no embedded images
        metadata={
            "filename": path.name,
            "type": "txt",
            "page_count": None,
            "section_count": len(sections),
            "table_count": len(tables),
            "image_count": 0,
        },
    )




def _flush_table(
    table_lines: list[str],
    tables: list[dict[str, Any]],
    full_text_parts: list[str],
    current_section: dict[str, Any] | None,
) -> None:
    """Parse accumulated table lines and append a table entry.

    Handles both tables with and without a separator row.
    """
    if len(table_lines) < 1:
        return

    # Check if line 2 is a separator row (e.g. |---|----|)
    has_separator = (
        len(table_lines) >= 2
        and bool(re.match(r"^\|[\s\-:|]+\|$", table_lines[1]))
    )

    if has_separator:
        headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]
        rows = [
            [c.strip() for c in tl.split("|")[1:-1]]
            for tl in table_lines[2:]
        ]
    else:
        headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]
        rows = [
            [c.strip() for c in tl.split("|")[1:-1]]
            for tl in table_lines[1:]
        ]

    table_entry: dict[str, Any] = {
        "caption": f"Table {len(tables) + 1}",
        "headers": headers,
        "rows": rows,
        "page": None,
    }
    tables.append(table_entry)
    if current_section is not None:
        current_section.setdefault("tables", []).append(table_entry)
    full_text_parts.append(_table_to_text(headers, rows))
