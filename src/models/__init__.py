"""
LangGraph state definitions for the PPT Agent workflow.

The AgentState is a TypedDict that flows through all nodes
in the LangGraph graph, accumulating results at each step.
"""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from langgraph.graph import MessagesState


# ── Source Document Model ───────────────────────────────────────────────────

class SourceDocument(TypedDict):
    """Parsed content from a source document (Word / PDF / text)."""

    title: str
    full_text: str                          # complete plain-text body
    sections: list[dict[str, Any]]          # [{heading, level, paragraphs, images, tables}]
    tables: list[dict[str, Any]]            # [{caption, headers, rows, page/position}]
    images: list[dict[str, Any]]            # [{caption, path_to_saved_image, page}]
    metadata: dict[str, Any]                # {filename, type, page_count, ...}


# ── Reference PPT Models ────────────────────────────────────────────────────

class SlideCluster(TypedDict):
    """A group of slides that share a similar layout / style."""

    cluster_id: int
    slide_indices: list[int]                # 0-based indices into the reference PPT
    representative_idx: int                 # most "central" slide of this cluster
    feature_centroid: Optional[list[float]] # ViT feature centroid (optional after clustering)


class LayoutSchema(TypedDict):
    """Structured description of a slide layout extracted by LLM.

    NOTE: ``total=False`` means all keys are optional. This is REQUIRED
    because LangGraph serializes state between nodes using the TypedDict
    definition — any key NOT declared here is silently STRIPPED.
    """

    schema_id: str
    cluster_id: int
    description: str                        # natural language summary
    elements: list[dict[str, Any]]          # [{type, position, font, color, placeholder_hint, ...}]
    color_palette: list[str]                # hex colors extracted
    font_styles: dict[str, Any]             # {title_font, body_font, sizes, ...}
    use_case: str                           # e.g. "title slide", "content with image", "section divider"


# ── Slide Edit Models ───────────────────────────────────────────────────────

class EditOperation(TypedDict):
    """A single atomic edit to be applied to a slide."""

    op_type: str                            # "add_text" | "add_image" | "add_table" |
                                            # "modify_text" | "modify_style" | "delete_shape" |
                                            # "add_slide" | "delete_slide" | "reorder_slide"
    slide_idx: int
    target: dict[str, Any]                  # shape identifier, position info, etc.
    payload: dict[str, Any]                 # the actual content / style changes


class SlideState(TypedDict):
    """State of a single slide during the edit loop."""

    slide_idx: int
    cluster_id: int                         # which layout cluster this slide belongs to
    schema_id: str                          # which LayoutSchema to follow
    html_view: str                          # current HTML representation
    edit_history: list[EditOperation]
    evaluation_scores: dict[str, float]     # dimension → score
    overall_score: float
    revision_round: int
    is_acceptable: bool


# ── Main Agent State ────────────────────────────────────────────────────────

class AgentState(MessagesState):
    """Master state that flows through all LangGraph nodes.

    Extends MessagesState so we get `messages` for free (used by LLM nodes).
    """

    # ── Inputs ──────────────────────────────────────────────────────────
    source_path: str                        # path to source document
    reference_pptx_path: str                # path to reference PPT
    output_pptx_path: str                   # desired output path

    # ── Parsing results ─────────────────────────────────────────────────
    source_doc: Optional[SourceDocument]    # parsed source content
    reference_pptx: Optional[Any]           # python-pptx Presentation object (not serializable!)
    reference_slide_count: int

    # ── Style analysis ──────────────────────────────────────────────────
    slide_clusters: list[SlideCluster]
    layout_schemas: list[LayoutSchema]
    # Plain dict for enrichment data (bg_xml, fonts, shapes_xml per schema_id).
    # Using a separate dict because LangGraph may strip extra keys from
    # TypedDict fields during serialization.
    style_enrichment: dict[str, Any]

    # ── Planning ────────────────────────────────────────────────────────
    outline: list[dict[str, Any]]           # [{slide_idx, title, cluster_id, schema_id, content_summary}]

    # ── Editing state ───────────────────────────────────────────────────
    current_slide_idx: int
    slide_states: list[SlideState]
    edit_log: list[EditOperation]           # all edits across all slides

    # ── Output ──────────────────────────────────────────────────────────
    output_pptx: Optional[Any]              # the generated Presentation object
    final_report: dict[str, Any]            # summary report after generation


# ── Helpers ─────────────────────────────────────────────────────────────────

def create_initial_state(
    source_path: str,
    reference_pptx_path: str,
    output_pptx_path: str,
) -> AgentState:
    """Build the initial AgentState with defaults for every key.

    Args:
        source_path: Path to the source document (Word / PDF / .txt).
        reference_pptx_path: Path to the reference PPT for style extraction.
        output_pptx_path: Where to write the generated PPT.

    Returns:
        A fully initialized AgentState dict.
    """
    return AgentState(
        messages=[],
        source_path=source_path,
        reference_pptx_path=reference_pptx_path,
        output_pptx_path=output_pptx_path,
        source_doc=None,
        reference_pptx=None,
        reference_slide_count=0,
        slide_clusters=[],
        layout_schemas=[],
        style_enrichment={},
        outline=[],
        current_slide_idx=0,
        slide_states=[],
        edit_log=[],
        output_pptx=None,
        final_report={},
    )
