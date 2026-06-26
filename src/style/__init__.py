"""
Style analysis pipeline — ViT feature extraction, hierarchical clustering,
and LLM-powered layout schema extraction.
"""

from src.style.vit_extractor import ViTFeatureExtractor
from src.style.clustering import cluster_slides
from src.style.schema_extractor import LayoutSchemaExtractor

__all__ = [
    "ViTFeatureExtractor",
    "cluster_slides",
    "LayoutSchemaExtractor",
]
