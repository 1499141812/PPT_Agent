"""
Edit operation definitions — typed models for every supported edit action.

Uses Pydantic for validation so LLM-generated tool calls are automatically
checked before execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class EditOpType(str, Enum):
    """All supported atomic edit operations."""
    # Slide-level
    ADD_SLIDE = "add_slide"
    DELETE_SLIDE = "delete_slide"
    REORDER_SLIDE = "reorder_slide"

    # Content — text
    ADD_TEXT = "add_text"
    MODIFY_TEXT = "modify_text"

    # Content — media
    ADD_IMAGE = "add_image"
    ADD_TABLE = "add_table"
    ADD_CHART = "add_chart"

    # Structural
    DELETE_SHAPE = "delete_shape"
    MODIFY_STYLE = "modify_style"


# ── Position / Style sub-models ─────────────────────────────────────────────

class Position(BaseModel):
    """Position and size of an element on a slide.

    All values are in inches (will be converted to EMU internally).
    """
    left: float = Field(..., description="Left offset in inches")
    top: float = Field(..., description="Top offset in inches")
    width: float = Field(..., description="Width in inches")
    height: float = Field(..., description="Height in inches")


class TextStyle(BaseModel):
    """Text styling properties."""
    font_name: str = "Arial"
    font_size: float = 18.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"
    alignment: Literal["left", "center", "right"] = "left"


# ── Operation payloads ──────────────────────────────────────────────────────

class AddTextPayload(BaseModel):
    """Payload for adding a text box."""
    text: str
    position: Position
    style: TextStyle = Field(default_factory=TextStyle)


class ModifyTextPayload(BaseModel):
    """Payload for changing text content."""
    shape_id: Optional[int] = None
    shape_name: Optional[str] = None
    new_text: str


class ModifyStylePayload(BaseModel):
    """Payload for changing style properties."""
    shape_id: Optional[int] = None
    shape_name: Optional[str] = None
    changes: dict[str, Any] = Field(
        default_factory=dict,
        description="Dict of style properties to change (font_name, font_size, bold, color, etc.)"
    )


class AddImagePayload(BaseModel):
    """Payload for adding an image."""
    image_path: str = Field(..., description="Path to the image file on disk")
    position: Position
    alt_text: str = ""


class AddTablePayload(BaseModel):
    """Payload for adding a table."""
    headers: list[str]
    rows: list[list[str]]
    position: Position
    caption: str = ""


class AddChartPayload(BaseModel):
    """Payload for adding a chart."""
    chart_type: Literal["bar", "line", "pie", "scatter"] = "bar"
    data: dict[str, Any] = Field(..., description="Chart data in a plotly-friendly format")
    position: Position
    title: str = ""


class AddSlidePayload(BaseModel):
    """Payload for adding a new slide."""
    layout_index: int = 0
    cluster_id: Optional[int] = None
    schema_id: Optional[str] = None


class DeleteSlidePayload(BaseModel):
    """Payload for deleting a slide."""
    slide_index: int


class ReorderSlidePayload(BaseModel):
    """Payload for reordering slides."""
    from_index: int
    to_index: int


class DeleteShapePayload(BaseModel):
    """Payload for deleting a shape."""
    shape_id: Optional[int] = None
    shape_name: Optional[str] = None


# ── Unified Edit Operation ──────────────────────────────────────────────────

class EditOperation(BaseModel):
    """A single edit operation, fully typed and validated.

    This is the canonical representation used throughout the system.
    LLM function-calling outputs are parsed into this model.
    """
    op_type: EditOpType
    slide_idx: int = Field(default=0, ge=0, description="Target slide index (0-based)")
    payload: Union[
        AddTextPayload,
        ModifyTextPayload,
        ModifyStylePayload,
        AddImagePayload,
        AddTablePayload,
        AddChartPayload,
        AddSlidePayload,
        DeleteSlidePayload,
        ReorderSlidePayload,
        DeleteShapePayload,
        dict[str, Any],  # fallback for raw dicts
    ]

    # Optional metadata
    reason: str = Field(default="", description="Why this edit was made (for logging)")
    source: str = Field(default="llm", description="Who generated this edit: 'llm' | 'diff' | 'programmatic'")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict (compatible with the TypedDict version in models)."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EditOperation":
        """Deserialize from a plain dict."""
        return cls(**data)


# ── Tool definitions for LLM function calling ───────────────────────────────

EDIT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "add_text",
            "description": "Add a new text box to a slide with specified position, content, and style.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer", "description": "0-based slide index"},
                    "text": {"type": "string", "description": "The text content"},
                    "left": {"type": "number", "description": "Left position in inches"},
                    "top": {"type": "number", "description": "Top position in inches"},
                    "width": {"type": "number", "description": "Width in inches"},
                    "height": {"type": "number", "description": "Height in inches"},
                    "font_name": {"type": "string", "default": "Arial"},
                    "font_size": {"type": "number", "default": 18},
                    "bold": {"type": "boolean", "default": False},
                    "color": {"type": "string", "default": "#000000"},
                    "alignment": {"type": "string", "enum": ["left", "center", "right"], "default": "left"},
                    "reason": {"type": "string", "description": "Why this text is being added"},
                },
                "required": ["slide_idx", "text", "left", "top", "width", "height"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_text",
            "description": "Modify the text content of an existing text box.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer"},
                    "shape_id": {"type": "integer", "description": "The shape's ID from data-shape-id"},
                    "new_text": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["slide_idx", "shape_id", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "modify_style",
            "description": "Change the visual style of an existing element.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer"},
                    "shape_id": {"type": "integer"},
                    "changes": {
                        "type": "object",
                        "description": "Style properties to change: font_name, font_size, bold, color, fill_color, alignment",
                    },
                    "reason": {"type": "string"},
                },
                "required": ["slide_idx", "shape_id", "changes"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_image",
            "description": "Add an image to a slide.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer"},
                    "image_path": {"type": "string", "description": "Path to the image file"},
                    "left": {"type": "number"},
                    "top": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "alt_text": {"type": "string", "default": ""},
                    "reason": {"type": "string"},
                },
                "required": ["slide_idx", "image_path", "left", "top", "width", "height"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_table",
            "description": "Add a table to a slide.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer"},
                    "headers": {"type": "array", "items": {"type": "string"}},
                    "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                    "left": {"type": "number"},
                    "top": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                    "caption": {"type": "string", "default": ""},
                    "reason": {"type": "string"},
                },
                "required": ["slide_idx", "headers", "rows", "left", "top", "width", "height"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_shape",
            "description": "Remove an element from a slide.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slide_idx": {"type": "integer"},
                    "shape_id": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["slide_idx", "shape_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_slide",
            "description": "Add a new blank slide to the presentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "layout_index": {"type": "integer", "default": 0},
                    "reason": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish_editing",
            "description": "Signal that editing of the current slide is complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of what was done"},
                },
                "required": ["summary"],
            },
        },
    },
]
