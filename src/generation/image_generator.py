"""
Image generator — creates images from text descriptions for slide illustration.

Supports:
- DALL·E 3 (OpenAI API)
- Tongyi Wanxiang (Alibaba Cloud)
- Placeholder mode (generates a colored placeholder with caption)

The generator is optional — presentations can be created without it.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional, Literal

from PIL import Image, ImageDraw, ImageFont

from src.config import get_config


class ImageGenerator:
    """Generate images from text prompts.

    Usage::

        gen = ImageGenerator()
        path = gen.generate("A futuristic city skyline at sunset", style="illustration")
    """

    def __init__(
        self,
        output_dir: Optional[str | Path] = None,
        api: Optional[Literal["dalle3", "tongyi", "placeholder"]] = None,
    ) -> None:
        """Initialize the image generator.

        Args:
            output_dir: Where to save generated images.
            api: Which API to use. Default from config (placeholder if no API key).
        """
        cfg = get_config()
        self._output_dir = Path(output_dir or cfg.output_dir / "images")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._api = api or cfg.generation.image_api or "placeholder"

    def generate(
        self,
        prompt: str,
        *,
        style: str = "photorealistic",
        size: str = "1024x1024",
        filename: Optional[str] = None,
    ) -> str:
        """Generate an image from a text prompt.

        Args:
            prompt: Text description of the desired image.
            style: Visual style guide.
            size: Image size (e.g. "1024x1024", "1792x1024").
            filename: Optional base filename.

        Returns:
            Absolute path to the generated image file.
        """
        if self._api == "dalle3":
            return self._generate_dalle(prompt, style, size, filename)
        elif self._api == "tongyi":
            return self._generate_tongyi(prompt, style, size, filename)
        else:
            return self._generate_placeholder(prompt, filename)

    def _generate_dalle(
        self,
        prompt: str,
        style: str,
        size: str,
        filename: Optional[str] = None,
    ) -> str:
        """Generate image via DALL·E 3 (requires OPENAI_API_KEY)."""
        from openai import OpenAI
        import base64
        import httpx

        cfg = get_config()
        client = OpenAI()  # Uses OPENAI_API_KEY from environment

        full_prompt = f"{prompt}. Style: {style}."
        try:
            response = client.images.generate(
                model="dall-e-3",
                prompt=full_prompt,
                size=size,
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            if not image_url:
                raise RuntimeError("DALL·E returned no image URL")

            # Download the image
            img_data = httpx.get(image_url, timeout=60).content
            if filename is None:
                filename = f"dalle_{uuid.uuid4().hex[:8]}"
            output_path = self._output_dir / f"{filename}.png"
            output_path.write_bytes(img_data)
            return str(output_path)

        except Exception as e:
            # Fallback to placeholder on API failure
            print(f"[WARN] DALL·E generation failed: {e}. Using placeholder.")
            return self._generate_placeholder(prompt, filename)

    def _generate_tongyi(
        self,
        prompt: str,
        style: str,
        size: str,
        filename: Optional[str] = None,
    ) -> str:
        """Generate image via Tongyi Wanxiang (placeholder — requires API setup)."""
        # Tongyi API requires dashscope SDK and specific auth.
        # This is a stub that falls back to placeholder.
        print("[INFO] Tongyi Wanxiang API not configured. Using placeholder.")
        return self._generate_placeholder(prompt, filename)

    def _generate_placeholder(
        self,
        prompt: str,
        filename: Optional[str] = None,
    ) -> str:
        """Generate a colored placeholder image with the prompt as caption.

        This is the fallback when no image generation API is available.
        The placeholder is visually identifiable so users know where to
        replace with real images.
        """
        width, height = 800, 600

        # Generate a deterministic color from the prompt hash
        import hashlib
        hash_val = int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
        r = (hash_val >> 16) & 0xFF
        g = (hash_val >> 8) & 0xFF
        b = hash_val & 0xFF
        bg_color = (
            min(r + 60, 255),
            min(g + 60, 255),
            min(b + 60, 255),
        )

        img = Image.new("RGB", (width, height), bg_color)
        draw = ImageDraw.Draw(img)

        # Draw a border
        draw.rectangle([0, 0, width - 1, height - 1], outline=(r, g, b), width=3)

        # Draw an icon (simple shapes)
        cx, cy = width // 2, height // 2 - 40
        # Mountain/triangle
        draw.polygon([(cx - 80, cy + 60), (cx, cy - 60), (cx + 80, cy + 60)],
                     fill=(r, g, b), outline=(r, g, b))
        # Sun/circle
        draw.ellipse([cx + 40, cy - 80, cx + 80, cy - 40], fill=(255, 215, 0), outline=(255, 215, 0))

        # Draw prompt text (wrap to fit)
        try:
            font = ImageFont.truetype("arial.ttf", 16)
        except OSError:
            font = ImageFont.load_default()

        # Word wrap
        words = prompt.split()
        lines: list[str] = []
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] < width - 40:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word
        if current_line:
            lines.append(current_line)

        y = height - 40 - len(lines) * 22
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            draw.text(((width - text_w) // 2, y), line, fill=(50, 50, 50), font=font)
            y += 22

        if filename is None:
            filename = f"placeholder_{uuid.uuid4().hex[:8]}"
        output_path = self._output_dir / f"{filename}.png"
        img.save(str(output_path))
        return str(output_path)

