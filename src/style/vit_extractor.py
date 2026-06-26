"""
ViT (Vision Transformer) feature extractor for slide images.

Uses HuggingFace transformers to load a pre-trained ViT model and extract
embedding vectors for each slide image. These vectors serve as the feature
space for layout clustering.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import torch
from PIL import Image
from transformers import ViTImageProcessor, ViTModel
from transformers import logging as transformers_logging

from src.config import StyleConfig, get_config


class ViTFeatureExtractor:
    """Extract fixed-size feature vectors from slide images using ViT.

    Usage::

        extractor = ViTFeatureExtractor()
        features = extractor.extract_features(image_paths)
        # features.shape → (N, 768) for vit-base-patch16-224
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        device: Optional[str] = None,
    ) -> None:
        """Initialize the ViT model and processor.

        Args:
            model_name: HuggingFace model ID (default from config).
            device: "cpu", "cuda", or "auto". Auto-detects GPU availability.
        """
        cfg = get_config().style
        self._model_name = model_name or cfg.vit_model_name

        if device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self._device = device

        # Apply HF_ENDPOINT for faster downloads (e.g. hf-mirror.com in China)
        import os
        hf_endpoint = get_config().style.hf_endpoint
        if hf_endpoint and hf_endpoint != "https://huggingface.co":
            os.environ.setdefault("HF_ENDPOINT", hf_endpoint)

        self._processor = ViTImageProcessor.from_pretrained(self._model_name)

        # Suppress the transformers "LOAD REPORT" print (classifier/pooler
        # mismatch is expected — we only need the encoder for embeddings).
        _prev_verbosity = transformers_logging.get_verbosity()
        transformers_logging.set_verbosity_error()

        self._model = ViTModel.from_pretrained(
            self._model_name,
            add_pooling_layer=True,        # match checkpoint's pooler
            ignore_mismatched_sizes=True,   # skip checkpoint's classifier head
        ).to(self._device)

        transformers_logging.set_verbosity(_prev_verbosity)
        self._model.eval()

    @property
    def feature_dim(self) -> int:
        """Dimensionality of the output feature vectors."""
        return self._model.config.hidden_size

    def extract_features(
        self,
        images: list[str | Path | Image.Image],
        batch_size: int = 8,
    ) -> np.ndarray:
        """Extract ViT [CLS] embedding for each image.

        Args:
            images: List of image paths or PIL Images.
            batch_size: Processing batch size.

        Returns:
            NumPy array of shape ``(N, feature_dim)``.
        """
        pil_images: list[Image.Image] = []
        for img in images:
            if isinstance(img, (str, Path)):
                pil_images.append(Image.open(img).convert("RGB"))
            elif isinstance(img, Image.Image):
                pil_images.append(img.convert("RGB"))
            else:
                raise TypeError(f"Unsupported image type: {type(img)}")

        all_features: list[np.ndarray] = []

        for i in range(0, len(pil_images), batch_size):
            batch = pil_images[i : i + batch_size]
            inputs = self._processor(
                images=batch,
                return_tensors="pt",
            ).to(self._device)

            with torch.no_grad():
                outputs = self._model(**inputs)
                # Use pooler_output if available (ViT with pooling head),
                # otherwise use [CLS] token (first position in last_hidden_state)
                if outputs.pooler_output is not None:
                    features = outputs.pooler_output
                else:
                    features = outputs.last_hidden_state[:, 0, :]

            all_features.append(features.cpu().numpy())

        return np.concatenate(all_features, axis=0)

    def extract_single_feature(self, image: str | Path | Image.Image) -> np.ndarray:
        """Extract feature vector for a single image.

        Args:
            image: Image path or PIL Image.

        Returns:
            1D NumPy array of shape ``(feature_dim,)``.
        """
        return self.extract_features([image])[0]
