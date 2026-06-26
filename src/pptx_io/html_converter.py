"""
PPTX ↔ HTML bidirectional converter.

Converts slide content to a simplified HTML representation that LLMs can
easily understand, and parses LLM-edited HTML back into edit operations.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from pptx.util import Inches, Pt, Emu

from src.pptx_io.reader import extract_slide_shapes


# ── PPTX → HTML ─────────────────────────────────────────────────────────────

def slide_to_html(slide: Any, slide_index: int = 0) -> str:
    """Convert a single slide to a simplified HTML fragment.

    The HTML uses a fixed CSS grid that maps to the slide's actual dimensions
    (in inches). Every shape becomes a positioned ``<div>`` with inline styles
    reflecting its real position, size, font, and color.

    Args:
        slide: A ``pptx.slide.Slide`` object.
        slide_index: The 0-based index, used as an ``id`` in the markup.

    Returns:
        HTML string representing the slide.
    """
    shapes = extract_slide_shapes(slide)

    # Convert slide dimensions from EMU to a CSS-friendly representation
    slide_width_inches = slide.slide_width / 914400 if hasattr(slide, "slide_width") else 10.0
    slide_height_inches = slide.slide_height / 914400 if hasattr(slide, "slide_height") else 7.5

    parts: list[str] = []
    parts.append(
        f'<div class="slide" id="slide-{slide_index}" '
        f'style="width:{slide_width_inches:.2f}in;height:{slide_height_inches:.2f}in;'
        f'position:relative;overflow:hidden;background:#ffffff;">'
    )

    for i, shape_info in enumerate(shapes):
        element_html = _shape_to_html(shape_info, i)
        if element_html:
            parts.append("  " + element_html)

    parts.append("</div>")
    return "\n".join(parts)


def pptx_to_html_snippets(pptx: Any) -> list[str]:
    """Convert every slide in a presentation to an HTML snippet.

    Args:
        pptx: A ``pptx.Presentation`` object.

    Returns:
        List of HTML strings, one per slide.
    """
    snippets: list[str] = []
    for idx, slide in enumerate(pptx.slides):
        snippets.append(slide_to_html(slide, idx))
    return snippets


def _shape_to_html(shape_info: dict[str, Any], index: int) -> str:
    """Convert a single extracted shape to an HTML element.

    Args:
        shape_info: Dict from ``extract_slide_shapes``.
        index: Shape index for the id attribute.

    Returns:
        HTML string for this shape, or empty string for unhandled types.
    """
    left_in = shape_info["left"] / 914400
    top_in = shape_info["top"] / 914400
    width_in = shape_info["width"] / 914400
    height_in = shape_info["height"] / 914400

    style_parts = [
        f"position:absolute;",
        f"left:{left_in:.3f}in;",
        f"top:{top_in:.3f}in;",
        f"width:{width_in:.3f}in;",
        f"height:{height_in:.3f}in;",
    ]

    text = shape_info.get("text") or ""

    if shape_info.get("font_name"):
        style_parts.append(f"font-family:'{shape_info['font_name']}',sans-serif;")
    if shape_info.get("font_size"):
        style_parts.append(f"font-size:{shape_info['font_size']:.0f}pt;")
    if shape_info.get("bold"):
        style_parts.append(f"font-weight:bold;")
    if shape_info.get("italic"):
        style_parts.append(f"font-style:italic;")
    if shape_info.get("color"):
        style_parts.append(f"color:#{shape_info['color']};")
    if shape_info.get("fill_color"):
        style_parts.append(f"background-color:#{shape_info['fill_color']};")

    style = " ".join(style_parts)

    shape_type = shape_info["shape_type"]
    name = shape_info.get("name", f"shape-{index}")
    placeholder = shape_info.get("placeholder_type", "")

    data_attrs = f'data-shape-id="{shape_info["shape_id"]}" data-shape-type="{shape_type}"'
    if placeholder:
        data_attrs += f' data-placeholder="{placeholder}"'

    if shape_type == "table" and "table_data" in shape_info:
        td = shape_info["table_data"]
        rows_html = []
        for row_idx, row in enumerate(td.get("content", [])):
            tag = "th" if row_idx == 0 else "td"
            cells = "".join(f"<{tag}>{_escape_html(c)}</{tag}>" for c in row)
            rows_html.append(f"<tr>{cells}</tr>")
        inner = f"<table>{''.join(rows_html)}</table>"
        return f'<div class="shape table" {data_attrs} style="{style}">{inner}</div>'

    elif shape_type == "picture" or shape_type == "PICTURE":
        alt = text or "image"
        # Use empty src to prevent LLM from hallucinating image paths
        inner = f'<div class="image-placeholder" style="width:100%;height:100%;background:#eee;display:flex;align-items:center;justify-content:center;color:#999;font-size:10pt;">[Image: {_escape_html(alt)}]</div>'
        return f'<div class="shape image" {data_attrs} style="{style}">{inner}</div>'

    elif shape_type == "chart":
        inner = f'<div class="chart-placeholder">[Chart: {_escape_html(text)}]</div>'
        return f'<div class="shape chart" {data_attrs} style="{style}">{inner}</div>'

    elif text:
        # Text content — wrap paragraphs
        lines = text.split("\n")
        if len(lines) == 1:
            inner = _escape_html(lines[0])
        else:
            inner = "".join(f"<p>{_escape_html(l)}</p>" for l in lines)
        return f'<div class="shape text-box" {data_attrs} style="{style}">{inner}</div>'

    else:
        # Empty / decorative shape
        return f'<div class="shape {shape_type}" {data_attrs} style="{style}"></div>'


def _escape_html(text: str) -> str:
    """Minimal HTML escaping."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
