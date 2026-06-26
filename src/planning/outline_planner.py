"""
Outline planner — generates a slide-by-slide plan.

Given the parsed source document and the extracted layout schemas,
the LLM produces a structured outline that maps content to slides,
selects the most appropriate layout schema for each slide, and plans
the overall narrative flow.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.llm import LLMClient, get_llm_client
from src.models import SourceDocument, LayoutSchema


class OutlinePlanner:
    """Generate a slide outline using LLM planning.

    The outline is a list of dicts, each describing one slide's:
        - title / heading
        - content assignment (bullet points, paragraphs)
        - which schema (layout cluster) to use
        - image and table hints
        - narrative role (opening, content, divider, closing)

    Usage::

        planner = OutlinePlanner()
        outline = planner.plan(source_doc, schemas)
    """

    _SYSTEM_PROMPT = """\
You are an expert presentation architect. Given a source document and a set
of available slide layouts, produce a detailed slide-by-slide outline.

## Design Principles
1. **Title Slide**: Use a "title" layout. Include document title and subtitle.
2. **Agenda/Overview**: Use a structured layout. List main sections.
3. **Content Slides**: Each major section becomes 1-3 slides.
   - One idea per slide
   - Use bullet points, not paragraphs
   - Assign images and tables where they add value
4. **Section Dividers**: Use a divider layout between major sections.
5. **Summary/Thank You**: Closing slide.

## Layout Selection
Review the available schemas and their `use_case` fields.
Assign the most appropriate schema to each slide.

## Content Distribution
- Extract key messages from the source document
- Transform long paragraphs into bullet points (3-5 per slide)
- Note which source images/tables should appear on which slide
- For data-heavy content, suggest chart types ("bar", "line", "pie")

Output a JSON array where each element is:
{
  "slide_idx": 0,
  "title": "Slide Title",
  "narrative_role": "title | agenda | content | divider | summary",
  "cluster_id": 0,
  "schema_id": "schema_0",
  "content": {
    "subtitle": "Optional subtitle",
    "bullet_points": ["Point 1", "Point 2", "Point 3"],
    "paragraphs": [],
    "image_hint": "caption of image to include, or null",
    "table_hint": "caption of table to include, or null",
    "chart_suggestion": null
  },
  "speaker_notes_hint": "Brief guidance for the presenter",
  "content_summary": "One-line summary for coherence evaluation"
}
"""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        """Initialize the planner.

        Args:
            client: LLM client. If None, uses global singleton.
        """
        self._client = client or get_llm_client()

    def plan(
        self,
        source_doc: SourceDocument,
        schemas: list[LayoutSchema],
        *,
        max_slides: int = 30,
        language: str = "zh",
    ) -> list[dict[str, Any]]:
        """Generate a slide outline.

        Args:
            source_doc: Parsed source document.
            schemas: Available layout schemas from style analysis.
            max_slides: Upper bound on slide count.
            language: Output language hint ("zh" or "en").

        Returns:
            List of outline items, one per planned slide.
        """
        # Prepare source document summary
        sections_text = _format_sections(source_doc["sections"])
        tables_text = _format_tables(source_doc["tables"])
        images_text = _format_images(source_doc["images"])

        # Prepare schema catalog
        schema_catalog = json.dumps(
            [{
                "schema_id": s["schema_id"],
                "cluster_id": s["cluster_id"],
                "description": s["description"],
                "use_case": s["use_case"],
                "element_roles": [e.get("role", "") for e in s.get("elements", [])],
            } for s in schemas],
            indent=2,
            ensure_ascii=False,
        )

        prompt = f"""\
Plan a presentation based on the source document below.

## Source Document Title
{source_doc["title"]}

## Document Sections
{sections_text}

## Available Tables
{tables_text}

## Available Images
{images_text}

## Available Layout Schemas
{schema_catalog}

## Constraints
- Maximum {max_slides} slides
- Use the most appropriate schema for each slide based on its use_case
- Distribute content evenly — avoid information overload
- Output in {language}

Generate the complete slide outline as a JSON array."""

        result = self._client.json_chat(
            prompt=prompt,
            system=self._SYSTEM_PROMPT,
        )

        # The result might be wrapped in a key
        if isinstance(result, dict):
            outline = result.get("outline", result.get("slides", [result]))
            if not isinstance(outline, list):
                outline = [outline]
        elif isinstance(result, list):
            outline = result
        else:
            outline = []

        # Validate and fix slide indices
        for i, item in enumerate(outline):
            item["slide_idx"] = i

        return outline

# ── Formatting helpers ──────────────────────────────────────────────────────

def _format_sections(sections: list[dict[str, Any]]) -> str:
    """Format document sections for the LLM prompt."""
    lines: list[str] = []
    for sec in sections:
        heading = sec.get("heading", "")
        level = sec.get("level", 0)
        prefix = "#" * max(level, 1)
        lines.append(f"{prefix} {heading}")
        for para in sec.get("paragraphs", [])[:5]:  # Limit per section
            lines.append(para[:500])
        if len(sec.get("paragraphs", [])) > 5:
            lines.append(f"... ({len(sec['paragraphs']) - 5} more paragraphs)")
        lines.append("")
    return "\n".join(lines)


def _format_tables(tables: list[dict[str, Any]]) -> str:
    """Format tables for the LLM prompt."""
    if not tables:
        return "None"
    lines: list[str] = []
    for t in tables[:10]:
        lines.append(f"### {t.get('caption', 'Table')}")
        headers = t.get("headers", [])
        if headers:
            lines.append(" | ".join(headers))
            lines.append(" | ".join(["---"] * len(headers)))
        for row in t.get("rows", [])[:5]:
            padded = row + [""] * (len(headers) - len(row))
            lines.append(" | ".join(padded[:len(headers)]))
        lines.append("")
    return "\n".join(lines)


def _format_images(images: list[dict[str, Any]]) -> str:
    """Format images for the LLM prompt."""
    if not images:
        return "None"
    lines: list[str] = []
    for img in images:
        lines.append(f"- {img.get('caption', 'Image')} → {img.get('path_to_saved_image', 'N/A')}")
    return "\n".join(lines)
