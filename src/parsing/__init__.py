"""
Source document parsing pipeline.

Unified entry-point: ``parse_document(path) → SourceDocument``
Automatically dispatches to the correct parser based on file extension.
"""

from src.parsing.source_document import parse_document, SourceDocument

__all__ = ["parse_document", "SourceDocument"]
