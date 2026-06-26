"""
Hierarchical clustering of slide feature vectors.

Groups slides by visual similarity using agglomerative clustering
with a distance threshold, so the number of clusters is data-driven.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from scipy.spatial.distance import cdist

from src.config import StyleConfig, get_config
from src.models import SlideCluster


def cluster_slides(
    feature_vectors: np.ndarray,
    distance_threshold: Optional[float] = None,
) -> list[SlideCluster]:
    """Group slide feature vectors into layout clusters.

    Uses agglomerative (hierarchical) clustering with cosine distance.
    The number of clusters is determined automatically by the distance
    threshold — no need to pre-specify ``k``.

    Args:
        feature_vectors: NumPy array of shape ``(N, D)`` where N = number
            of slides and D = ViT feature dimension.
        distance_threshold: Cosine distance above which two clusters
            are considered distinct. Lower → more clusters.
            Default from config: 0.5.

    Returns:
        List of ``SlideCluster`` dicts, sorted by cluster size (largest first).
    """
    cfg = get_config().style
    threshold = distance_threshold or cfg.cluster_distance_threshold

    n_slides = feature_vectors.shape[0]

    # Edge case: too few slides to cluster meaningfully
    if n_slides < cfg.min_cluster_size:
        # Everything in one cluster
        centroid = feature_vectors.mean(axis=0).tolist() if n_slides > 0 else []
        return [
            SlideCluster(
                cluster_id=0,
                slide_indices=list(range(n_slides)),
                representative_idx=0,
                feature_centroid=centroid,
            )
        ]

    # Normalize for cosine distance
    norms = np.linalg.norm(feature_vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = feature_vectors / norms

    clustering = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=threshold,
        metric="cosine",
        linkage="average",
    )
    labels = clustering.fit_predict(normalized)

    # Build cluster objects
    unique_labels = np.unique(labels)
    clusters: list[SlideCluster] = []

    for label in unique_labels:
        indices = np.where(labels == label)[0].tolist()
        # Skip clusters smaller than min_size (merge into "misc")
        if len(indices) < cfg.min_cluster_size and len(unique_labels) > 1:
            continue

        # Compute centroid in original space
        centroid = feature_vectors[indices].mean(axis=0).tolist()

        # Find the most "central" slide (closest to centroid)
        centroid_arr = np.array(centroid).reshape(1, -1)
        if len(indices) > 1:
            distances = cdist(
                centroid_arr,
                feature_vectors[indices],
                metric="cosine",
            ).flatten()
            representative_idx = indices[int(np.argmin(distances))]
        else:
            representative_idx = indices[0]

        clusters.append(SlideCluster(
            cluster_id=int(label),
            slide_indices=indices,
            representative_idx=representative_idx,
            feature_centroid=centroid,
        ))

    # Sort by size descending, reassign cluster_ids
    clusters.sort(key=lambda c: len(c["slide_indices"]), reverse=True)
    for i, c in enumerate(clusters):
        c["cluster_id"] = i

    return clusters


def get_cluster_for_slide(
    slide_index: int,
    clusters: list[SlideCluster],
) -> Optional[SlideCluster]:
    """Find which cluster a given slide belongs to.

    Args:
        slide_index: 0-based slide index.
        clusters: List of clusters from ``cluster_slides``.

    Returns:
        The matching ``SlideCluster``, or None if not found.
    """
    for cluster in clusters:
        if slide_index in cluster["slide_indices"]:
            return cluster
    return None
