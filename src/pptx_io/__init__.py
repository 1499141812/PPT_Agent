"""
PPTX I/O — Read reference presentations, convert slides to HTML,
and write generated presentations.
"""

from src.pptx_io.reader import read_pptx, get_slide_count
from src.pptx_io.writer import write_pptx, create_blank_presentation
from src.pptx_io.html_converter import (
    slide_to_html,
    pptx_to_html_snippets,
)
from src.pptx_io.slide_renderer import render_all_slides

__all__ = [
    "read_pptx",
    "get_slide_count",
    "write_pptx",
    "create_blank_presentation",
    "slide_to_html",
    "pptx_to_html_snippets",
    "html_to_edit_operations",
    "render_slide_to_image",
    "render_all_slides",
]
