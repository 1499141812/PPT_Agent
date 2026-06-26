"""
Configuration management for PPT Agent.

Loads settings from environment variables and config.env file.
All module-level configuration is centralized here for consistency.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv


# ── Locate and load config.env ──────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / "config.env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)


# ── Configuration data classes ──────────────────────────────────────────────

@dataclass
class LLMConfig:
    """LLM / API connection parameters."""

    api_key: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", "")
    )
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
    )
    model: str = field(
        default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    )
    temperature: float = field(
        default_factory=lambda: float(
            os.getenv("DEEPSEEK_TEMPERATURE", "0.7")
        )
    )
    max_tokens: int = field(
        default_factory=lambda: int(
            os.getenv("DEEPSEEK_MAX_TOKENS", "8192")
        )
    )
    request_timeout: int = field(
        default_factory=lambda: int(
            os.getenv("DEEPSEEK_TIMEOUT", "120")
        )
    )
    # Vision-capable model (for style analysis / image understanding)
    vision_model: str = field(
        default_factory=lambda: os.getenv(
            "DEEPSEEK_VISION_MODEL", "deepseek-chat"
        )
    )


@dataclass
class StyleConfig:
    """Parameters for style analysis and clustering."""

    vit_model_name: str = "google/vit-base-patch16-224"
    cluster_distance_threshold: float = 0.5
    min_cluster_size: int = 1
    slide_image_dpi: int = 100          # 100 dpi is fast and sufficient for ViT
    hf_endpoint: str = field(           # HuggingFace mirror for faster downloads in China
        default_factory=lambda: os.getenv(
            "HF_ENDPOINT", "https://huggingface.co"
        )
    )
    style_analysis_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "STYLE_ANALYSIS_ENABLED", "true"
        ).lower() == "true"
    )
    # ponytail: always copy all shapes — reference PPT is always a pure template


@dataclass
class EditingConfig:
    """Parameters for the edit-based generation loop."""

    max_revision_rounds: int = 3
    evaluation_threshold: float = 7.0  # 0-10 scale, re-edit if below
    evaluation_dimensions: list = field(
        default_factory=lambda: [
            "content_richness",
            "design_aesthetics",
            "structural_coherence",
        ]
    )


@dataclass
class GenerationConfig:
    """Parameters for chart / image generation."""

    chart_dpi: int = 150
    chart_format: str = "png"
    image_generation_enabled: bool = False
    image_api: str = "dalle3"  # "dalle3" or "tongyi"


@dataclass
class AppConfig:
    """Top-level application configuration."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    editing: EditingConfig = field(default_factory=EditingConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    project_root: Path = _PROJECT_ROOT
    output_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "output")
    temp_dir: Path = field(default_factory=lambda: _PROJECT_ROOT / "temp")
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )

    def __post_init__(self):
        """Ensure output and temp directories exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)


# ── Singleton instance ──────────────────────────────────────────────────────
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Return the global AppConfig singleton, creating it on first call."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def reset_config() -> None:
    """Reset the cached config (useful in tests)."""
    global _config
    _config = None
