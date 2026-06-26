"""
Layout schema extraction using LLM.

For each slide cluster, we take the representative slide's HTML view
and ask the LLM to describe its "structured content pattern" — element
positions, fonts, colors, placeholder semantics — in a machine-readable
JSON schema. This schema later guides the generation of new slides that
share the same layout family.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.llm import LLMClient, get_llm_client
from src.models import SlideCluster, LayoutSchema
from src.pptx_io.html_converter import slide_to_html


class LayoutSchemaExtractor:
    """Extract structured layout descriptions from slide clusters.

    Usage::

        extractor = LayoutSchemaExtractor()
        schemas = extractor.extract_schemas(clusters, html_snippets)
        # schemas is list[LayoutSchema]
    """

    _SYSTEM_PROMPT = """\
You are an expert presentation designer analyzing slide layouts.
You will receive the HTML representation of a representative slide
from a group of visually similar slides.

Your task:
1. Describe the layout type (e.g., "title slide", "section divider",
   "content with image", "two-column text", "table-heavy", "chart page").
2. Identify every content element and its role.
3. Extract the exact position (as CSS-style measurements), font families,
   font sizes, colors, and alignment.
4. Deduce placeholder semantics — which regions hold titles, subtitles,
   body text, images, logos, page numbers, etc.
5. Extract the color palette used (background, text, accent colors).
6. Note any recurring decorative elements (lines, shapes, borders).

Output a JSON object with the following structure:
{
  "layout_type": "string — concise label",
  "description": "string — natural language summary of this layout",
  "use_case": "string — when to use this layout (e.g. 'chapter opening')",
  "page_dimensions": {"width_inches": 10.0, "height_inches": 7.5},
  "elements": [
    {
      "role": "string — title | subtitle | body | image | logo | page_number | decoration",
      "element_type": "text-box | picture | table | chart | shape",
      "position": {"left_inches": 1.0, "top_inches": 0.5, "width_inches": 8.0, "height_inches": 1.2},
      "style": {
        "font_name": "Arial",
        "font_size_pt": 32,
        "bold": true,
        "italic": false,
        "color_hex": "#333333",
        "bg_color_hex": "#ffffff",
        "alignment": "left | center | right"
      },
      "placeholder_text": "string — example text shown in this element",
      "notes": "string — additional observations"
    }
  ],
  "color_palette": ["#1a1a1a", "#ffffff", "#0066cc", "#f5f5f5"],
  "font_styles": {
    "title_font": "Arial",
    "body_font": "Arial",
    "title_size": 32,
    "subtitle_size": 24,
    "body_size": 14,
    "caption_size": 10
  },
  "spacing_notes": "string — observations about margins, padding, whitespace"
}
"""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        """Initialize the schema extractor.

        Args:
            client: LLM client. If None, uses the global singleton.
        """
        self._client = client or get_llm_client()

    def extract_schemas(
        self,
        clusters: list[SlideCluster],
        slide_html_map: dict[int, str],
    ) -> list[LayoutSchema]:
        """Extract layout schemas for all clusters.

        Args:
            clusters: Output from ``cluster_slides``.
            slide_html_map: Mapping from slide index → HTML snippet
                (from ``pptx_to_html_snippets``).

        Returns:
            List of ``LayoutSchema`` dicts, one per cluster.
        """
        schemas: list[LayoutSchema] = []
        for cluster in clusters:
            rep_idx = cluster["representative_idx"]
            html = slide_html_map.get(rep_idx, "")
            if not html:
                continue
            schema = self._extract_single(cluster, html)
            schemas.append(schema)
        return schemas

    def _extract_single(
        self,
        cluster: SlideCluster,
        html: str,
    ) -> LayoutSchema:
        """Extract a layout schema from one representative slide.

        Args:
            cluster: The slide cluster.
            html: HTML representation of the representative slide.

        Returns:
            A ``LayoutSchema`` dict.
        """
        user_prompt = f"""\
Analyze this slide layout and extract its structured pattern.

Cluster ID: {cluster["cluster_id"]}
Number of slides in this cluster: {len(cluster["slide_indices"])}

HTML of the representative slide:
```html
{html}
```

Return ONLY the JSON object as specified."""

        result = self._client.json_chat(
            prompt=user_prompt,
            system=self._SYSTEM_PROMPT,
        )

        return LayoutSchema(
            schema_id=f"schema_{cluster['cluster_id']}",
            cluster_id=cluster["cluster_id"],
            description=result.get("description", ""),
            elements=result.get("elements", []),
            color_palette=result.get("color_palette", []),
            font_styles=result.get("font_styles", {}),
            use_case=result.get("use_case", result.get("layout_type", "content")),
        )

    def extract_schema_batch(
        self,
        clusters: list[SlideCluster],
        slide_html_map: dict[int, str],
    ) -> list[LayoutSchema]:
        """Alias for extract_schemas (batch processing)."""
        return self.extract_schemas(clusters, slide_html_map)
