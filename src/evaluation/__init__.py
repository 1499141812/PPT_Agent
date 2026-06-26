"""
Multi-dimension automatic evaluation for generated slides.

Scores each slide on content richness, design aesthetics, and structural
coherence. If a score falls below the threshold, the agent triggers a
revision loop.
"""

from src.evaluation.evaluator import SlideEvaluator, EvaluationResult

__all__ = ["EvaluationResult"]
