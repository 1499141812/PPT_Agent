"""
LLM-powered editor — single-turn JSON mode for slide editing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from src.llm import LLMClient, get_llm_client
from src.editing.operations import EditOperation

logger = logging.getLogger(__name__)


class LLMEditor:
    """Generate edit operations via single-turn JSON chat."""

    def __init__(self, client: Optional[LLMClient] = None) -> None:
        self._client = client or get_llm_client()

    def generate_edits_single_turn(
        self,
        slide_html: str,
        schema: dict[str, Any],
        content: dict[str, Any],
        *,
        is_fresh_slide: bool = True,
        available_images: Optional[list[dict[str, Any]]] = None,
        available_tables: Optional[list[dict[str, Any]]] = None,
    ) -> list[EditOperation]:
        """Generate edit operations via a single LLM JSON-mode call."""
        clean_html = slide_html.replace('src="[image]"', 'src=""')

        # ── Font info from reference ──────────────────────────────────
        fonts = content.pop("_fonts", None) or schema.get("extracted_fonts", {}) or {}
        main_font = fonts.get("main_font", "Arial")
        main_color = fonts.get("main_color", "333333")
        title_size = fonts.get("title_size", 32)

        # ── Image / table availability ─────────────────────────────────
        images = available_images or []
        tables = available_tables or []
        img_list = [{"caption": i.get("caption", ""), "path": i.get("image_path", i.get("path", ""))} for i in images]
        tbl_list = [{"caption": t.get("caption", ""), "cols": t.get("headers", [])} for t in tables]

        # ── Build constraints ──────────────────────────────────────────
        if is_fresh_slide:
            constraints = (
                "1. This is an EMPTY slide with no content shapes.\n"
                "2. You may ONLY use: add_text. (Do NOT use modify_text, "
                "modify_style, or delete_shape — there is nothing to modify.)\n"
                "3. Place text boxes at positions matching the schema.\n"
                f"4. use these font properties: font_name=\"{main_font}\", color=\"{main_color}\" (6-digit hex, no #), "
                f"title_size={title_size}pt bold, body_size={fonts.get('body_size', 16)}pt.\n"
                f"5. Title/heading text (>{title_size}pt or bold): ≤15 Chinese chars or ≤10 English words. "
                f"Body text: keep concise, use bullet points (•).\n"
            )
            op_example = (
                f'{{"op_type": "add_text", "slide_idx": 0, '
                f'"payload": {{"text": "Quarterly Review", '
                f'"position": {{"left": 1.0, "top": 0.5, "width": 8.0, "height": 1.2}}, '
                f'"style": {{"font_name": "{main_font}", "font_size": {title_size}, '
                f'"bold": true, "color": "{main_color}", "alignment": "left"}}}}}}'
            )
        else:
            constraints = (
                "1. Slide has empty text boxes (data-shape-id in HTML). "
                "Use modify_text to fill them.\n"
                "2. If images are available AND content has an image_hint, "
                "use add_image to insert the matching image.\n"
                "3. Do NOT use add_text — text boxes already exist.\n"
                "4. Identify box roles from HTML (top+largest font=title, lower=body).\n"
                "5. Title: ≤15 Chinese chars or ≤10 English words. "
                "Body: bullet points (•).\n"
            )
            op_example = (
                f'{{"op_type": "modify_text", "slide_idx": 0, '
                f'"payload": {{"shape_id": 42, "new_text": "Quarterly Review"}}}}, '
                f'{{"op_type": "modify_text", "slide_idx": 0, '
                f'"payload": {{"shape_id": 43, "new_text": "• Sales up 12%\\n• Costs reduced"}}}}'
            )

        # ── Content rewriting rules ─────────────────────────────────────
        rewriting = (
            "7. Preserve all numbers, facts, proper names. Condense, don't fabricate.\n"
        )

        # ── Output format ───────────────────────────────────────────────
        img_example = (
            f'{{"op_type": "add_image", "slide_idx": 0, '
            f'"payload": {{"image_path": "/path/to/image.png", '
            f'"position": {{"left": 5.0, "top": 2.0, "width": 4.0, "height": 3.0}}}}}}'
        )
        output_fmt = (
            "6. Output a single JSON array. Do NOT wrap in triple backticks.\n"
            f"Example (with optional image): [{op_example}, {img_example}]\n"
        )

        # ── Assemble prompt ─────────────────────────────────────────────
        schema_json = json.dumps(schema, indent=2, ensure_ascii=False) if schema else "{}"
        # ── Revision feedback ──────────────────────────────────────────
        feedback = content.pop("_revision_feedback", "")
        feedback_block = ""
        if feedback:
            feedback_block = (
                f"## Revision Feedback (IMPROVE based on this)\n"
                f"{feedback}\n\n"
            )

        # ── Shape size info ──────────────────────────────────────────
        shape_sizes = content.pop("_shape_sizes", {})
        shapes_info = ""
        if shape_sizes:
            lines = ["## Shape sizes (text must fit at this font size)"]
            for sid, info in shape_sizes.items():
                sz = info.get("font_size", "?")
                b = "bold" if info.get("bold") else "normal"
                lines.append(f"  shape_id={sid}: {sz}pt {b}")
            shapes_info = "\n".join(lines) + "\n\n"

        content_json = json.dumps(content, indent=2, ensure_ascii=False)

        prompt = (
            f"{feedback_block}"
            f"{shapes_info}"
            f"Edit this slide with the given content.\n\n"
            f"## Constraints\n{constraints}\n"
            f"{rewriting}\n"
            f"{output_fmt}\n"
            f"## Available Images\n{json.dumps(img_list, ensure_ascii=False) if img_list else '[] (none)'}\n\n"
            f"## Available Tables\n{json.dumps(tbl_list, ensure_ascii=False) if tbl_list else '[] (none)'}\n\n"
            f"## Layout Schema\n{schema_json}\n\n"
            f"## Content to Place\n{content_json}\n\n"
            f"## Current Slide HTML\n{clean_html}\n"
        )

        # ── Call LLM ───────────────────────────────────────────────────
        result = self._client.json_chat(prompt)
        if isinstance(result, dict):
            operations = result.get("operations", result.get("edits", [result]))
            if not isinstance(operations, list):
                operations = [operations]
        elif isinstance(result, list):
            operations = result
        else:
            logger.warning("Unexpected LLM output type: %s", type(result))
            return []

        edit_ops: list[EditOperation] = []
        for item in operations:
            try:
                edit_ops.append(EditOperation.from_dict(item))
            except Exception as e:
                logger.warning("Failed to parse edit op: %s — %s", e, item)

        return edit_ops
