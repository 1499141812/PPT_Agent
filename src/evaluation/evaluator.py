"""
Multi-dimension slide evaluator using LLM-as-judge.

Evaluates slides on:
- Content richness: Is the information complete and well-organized?
- Design aesthetics: Is the layout visually appealing and consistent?
- Structural coherence: Does the slide fit within the overall narrative?

Returns structured scores that feed into the self-correction loop.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.llm import LLMClient, get_llm_client
from src.pptx_io.html_converter import slide_to_html

logger = logging.getLogger(__name__)


def llm_evaluate(
    slide_html: str,
    content_summary: str,
    client: Optional[LLMClient] = None,
) -> tuple[float, str]:
    """LLM-based slide evaluation with actionable feedback.

    Returns (score, suggestions) where suggestions is text the editor
    can use to improve the slide on the next revision pass.
    """
    client = client or get_llm_client()
    prompt = (
        f"Score this slide 1-10 on content quality and conciseness.\n\n"
        f"Intended content: {content_summary}\n\n"
        f"Slide HTML:\n```html\n{slide_html[:3000]}\n```\n\n"
        f"Return JSON: {{\"score\": 7.5, \"suggestions\": \"具体的改进建议\"}}\n"
        f"Be critical. Suggest specific improvements: shorter title, better bullets, etc."
    )
    try:
        result = client.json_chat(prompt)
        score = float(result.get("score", 7.0))
        suggestions = str(result.get("suggestions", ""))
        return min(10, max(1, score)), suggestions
    except Exception:
        return 7.0, ""


@dataclass
class EvaluationResult:
    """Structured evaluation result for a single slide."""

    slide_idx: int
    content_richness: float          # 0–10
    design_aesthetics: float         # 0–10
    structural_coherence: float      # 0–10
    overall_score: float             # weighted average
    feedback: str                    # natural language critique
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    is_acceptable: bool = True       # True if overall >= threshold

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "slide_idx": self.slide_idx,
            "content_richness": self.content_richness,
            "design_aesthetics": self.design_aesthetics,
            "structural_coherence": self.structural_coherence,
            "overall_score": self.overall_score,
            "feedback": self.feedback,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "is_acceptable": self.is_acceptable,
        }


class SlideEvaluator:
    """Evaluate slide quality using LLM-as-judge.

    Usage::

        evaluator = SlideEvaluator()
        result = evaluator.evaluate(slide, slide_context)
        if not result.is_acceptable:
            # trigger revision with result.suggestions
    """

    # Weight distribution across dimensions
    _WEIGHTS = {
        "content_richness": 0.40,
        "design_aesthetics": 0.35,
        "structural_coherence": 0.25,
    }

    _SYSTEM_PROMPT = """\
You are an expert presentation quality auditor. You evaluate slides on three
dimensions and provide actionable feedback.

## Scoring Rubric (0–10 for each dimension)

### Content Richness (weight 40%)
- 0-3: Empty, irrelevant, or severely lacking information
- 4-6: Has basic information but missing details, too sparse or too dense
- 7-8: Good information density, well-organized, key points covered
- 9-10: Excellent coverage, insightful organization, perfect balance

### Design Aesthetics (weight 35%)
- 0-3: Cluttered, misaligned, poor color choices, unreadable fonts
- 4-6: Functional but bland, minor alignment/contrast issues
- 7-8: Visually appealing, good use of space, readable
- 9-10: Professional-grade design, excellent visual hierarchy

### Structural Coherence (weight 25%)
- 0-3: Disconnected from surrounding slides, no clear role in narrative
- 4-6: Somewhat fits the flow but unclear transitions
- 7-8: Good narrative fit, clear purpose in the presentation
- 9-10: Perfect narrative flow, reinforces the story arc

Output a JSON object with:
{
  "content_richness": float,
  "design_aesthetics": float,
  "structural_coherence": float,
  "overall_score": float,
  "feedback": "string — 2-3 sentence overall assessment",
  "issues": ["string — specific problem 1", ...],
  "suggestions": ["string — actionable fix 1", ...],
  "is_acceptable": true/false
}
"""

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        threshold: float = 7.0,
    ) -> None:
        """Initialize the evaluator.

        Args:
            client: LLM client. If None, uses global singleton.
            threshold: Overall score below which a slide needs revision.
        """
        self._client = client or get_llm_client()
        self._threshold = threshold

    def evaluate(
        self,
        slide: Any,
        slide_idx: int,
        *,
        outline_item: Optional[dict[str, Any]] = None,
        prev_slide_summary: Optional[str] = None,
        next_slide_summary: Optional[str] = None,
        schema: Optional[dict[str, Any]] = None,
    ) -> EvaluationResult:
        """Evaluate a single slide.

        Args:
            slide: The Slide object to evaluate.
            slide_idx: 0-based slide index.
            outline_item: The outline entry for this slide (what we intended).
            prev_slide_summary: Summary of the previous slide for coherence check.
            next_slide_summary: Summary of the next slide (if known).
            schema: The layout schema for this slide.

        Returns:
            An EvaluationResult with scores and feedback.
        """
        html = slide_to_html(slide, slide_idx)

        context_parts = [
            f"## Slide Index: {slide_idx}",
        ]
        if outline_item:
            context_parts.append(f"## Intended Content\n{json.dumps(outline_item, indent=2, ensure_ascii=False)}")
        if schema:
            context_parts.append(f"## Layout Schema\n{json.dumps(schema, indent=2, ensure_ascii=False)}")
        if prev_slide_summary:
            context_parts.append(f"## Previous Slide Summary\n{prev_slide_summary}")
        if next_slide_summary:
            context_parts.append(f"## Next Slide Summary\n{next_slide_summary}")

        context_parts.append(f"## Slide HTML\n```html\n{html}\n```")

        prompt = "\n\n".join(context_parts)

        raw = self._client.json_chat(
            prompt=prompt,
            system=self._SYSTEM_PROMPT,
        )

        return self._parse_result(raw, slide_idx)

    def evaluate_batch(
        self,
        slides: list[Any],
        outline: list[dict[str, Any]],
        schemas: dict[int, dict[str, Any]],
    ) -> list[EvaluationResult]:
        """Evaluate all slides in a presentation.

        Args:
            slides: List of Slide objects.
            outline: The full outline list.
            schemas: Mapping from slide_index → LayoutSchema.

        Returns:
            List of EvaluationResult, one per slide.
        """
        results: list[EvaluationResult] = []
        for idx, slide in enumerate(slides):
            prev_summary = (
                outline[idx - 1].get("content_summary", "")
                if idx > 0 and idx - 1 < len(outline) else None
            )
            next_summary = (
                outline[idx + 1].get("content_summary", "")
                if idx + 1 < len(outline) else None
            )
            result = self.evaluate(
                slide,
                idx,
                outline_item=outline[idx] if idx < len(outline) else None,
                prev_slide_summary=prev_summary,
                next_slide_summary=next_summary,
                schema=schemas.get(idx),
            )
            results.append(result)
        return results

    def needs_revision(self, result: EvaluationResult) -> bool:
        """Check if a slide needs revision based on score threshold.

        Args:
            result: The evaluation result.

        Returns:
            True if the slide should be re-edited.
        """
        return result.overall_score < self._threshold

    def _parse_result(self, raw: dict[str, Any], slide_idx: int) -> EvaluationResult:
        """Parse raw LLM output into an EvaluationResult."""
        return EvaluationResult(
            slide_idx=slide_idx,
            content_richness=float(raw.get("content_richness", 5.0)),
            design_aesthetics=float(raw.get("design_aesthetics", 5.0)),
            structural_coherence=float(raw.get("structural_coherence", 5.0)),
            overall_score=float(raw.get("overall_score", 5.0)),
            feedback=str(raw.get("feedback", "")),
            issues=[str(i) for i in raw.get("issues", [])],
            suggestions=[str(s) for s in raw.get("suggestions", [])],
            is_acceptable=bool(raw.get("is_acceptable", True)),
        )


class RuleBasedEvaluator:
    """Fast rule-based fallback evaluator (no LLM calls).

    Checks basic metrics:
    - Number of text elements
    - Text density (characters per slide)
    - Font consistency
    - Alignment consistency
    """

    def evaluate(self, slide: Any, slide_idx: int) -> EvaluationResult:
        """Perform a rule-based evaluation.

        Args:
            slide: The Slide object.
            slide_idx: Slide index.

        Returns:
            EvaluationResult with approximate scores.
        """
        from src.pptx_io.reader import extract_slide_shapes
        shapes = extract_slide_shapes(slide)

        text_shapes = [s for s in shapes if s.get("has_text") and s.get("text")]
        image_shapes = [s for s in shapes if s.get("shape_type") in ("picture", "PICTURE")]
        table_shapes = [s for s in shapes if s.get("shape_type") == "table"]

        # Content richness: text volume + media diversity
        total_chars = sum(len(s.get("text", "")) for s in text_shapes)
        if total_chars < 50:
            content_score = 3.0
        elif total_chars < 200:
            content_score = 6.0
        elif total_chars < 500:
            content_score = 8.0
        else:
            content_score = 9.0  # might be too dense, but LLM handles that

        # Design: element variety + basic checks
        design_score = 5.0
        if text_shapes:
            # Check font consistency
            fonts = {s.get("font_name") for s in text_shapes if s.get("font_name")}
            if len(fonts) <= 2:
                design_score += 1.5
            if len(set((s.get("left", 0), s.get("top", 0)) for s in text_shapes)) == len(text_shapes):
                design_score += 1.0  # no exact overlaps
            if image_shapes or table_shapes:
                design_score += 1.0

        design_score = min(design_score, 10.0)

        # Structural: basic completeness
        has_title = any(
            (s.get("font_size") or 0) > 20 and s.get("bold")
            for s in text_shapes
        )
        structure_score = 7.0 if has_title else 4.0
        if image_shapes or table_shapes:
            structure_score += 1.0

        overall = (
            content_score * 0.40
            + design_score * 0.35
            + structure_score * 0.25
        )

        return EvaluationResult(
            slide_idx=slide_idx,
            content_richness=content_score,
            design_aesthetics=design_score,
            structural_coherence=structure_score,
            overall_score=round(overall, 1),
            feedback="Rule-based evaluation.",
            issues=[],
            suggestions=[],
            is_acceptable=overall >= 7.0,
        )

