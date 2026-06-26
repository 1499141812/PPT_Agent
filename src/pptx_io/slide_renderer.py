"""
Slide image renderer — converts slides to PNG images for ViT analysis.

Rendering strategies (tried in order):
    1. **LibreOffice headless** — best quality, requires LibreOffice on PATH
    2. **PowerPoint COM** (Windows) — requires PowerPoint installed
    3. **PIL fallback** — pure Python, always available, structurally accurate

For ViT layout analysis the PIL fallback is perfectly adequate since we
care about element positions and rough visual structure, not pixel perfection.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

from src.config import get_config

logger = logging.getLogger(__name__)

# Standard slide dimensions in inches (used as fallback)
DEFAULT_SLIDE_W = 10.0
DEFAULT_SLIDE_H = 7.5


# ── Public API ──────────────────────────────────────────────────────────────

def render_all_slides(
    pptx: Any,
    output_dir: str | Path,
    dpi: Optional[int] = None,
) -> list[Path]:
    """Render every slide in a presentation to PNG files.

    Args:
        pptx: The Presentation object.
        output_dir: Directory to save slide images.
        dpi: Rendering resolution.

    Returns:
        List of paths to the generated PNG files, in slide order.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    cfg = get_config()
    dpi = dpi or cfg.style.slide_image_dpi

    # Try LibreOffice first (fastest for bulk)
    if _libreoffice_available():
        try:
            return _render_all_via_libreoffice(pptx, output_dir, dpi)
        except Exception as e:
            logger.info("LibreOffice bulk render failed: %s — falling back to PIL", e)

    # Try PowerPoint COM
    if _powerpoint_com_available():
        try:
            return _render_all_via_powerpoint_com(pptx, output_dir, dpi)
        except Exception as e:
            logger.info("PowerPoint COM bulk render failed: %s — falling back to PIL", e)

    # PIL fallback — one slide at a time
    logger.info("Rendering %d slides via PIL fallback...", len(pptx.slides))
    for idx, slide in enumerate(pptx.slides):
        out_path = output_dir / f"slide_{idx:03d}.png"
        _render_via_pil(slide, out_path, dpi)
        paths.append(out_path)

    return paths


# ── Strategy 1: LibreOffice ─────────────────────────────────────────────────

def _libreoffice_available() -> bool:
    """Check if LibreOffice is available on PATH."""
    return shutil.which("soffice") is not None


def _render_via_libreoffice(
    prs: Any,
    slide: Any,
    output_path: Optional[str | Path],
    dpi: int,
) -> Image.Image:
    """Render via LibreOffice headless + PyMuPDF rasterize."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pptx_path = tmpdir_path / "temp.pptx"

        prs.save(str(pptx_path))
        _libreoffice_pptx_to_pdf(pptx_path, tmpdir_path)

        pdf_path = tmpdir_path / "temp.pdf"
        if not pdf_path.exists():
            candidates = list(tmpdir_path.glob("*.pdf"))
            pdf_path = candidates[0] if candidates else None
        if not pdf_path:
            raise RuntimeError("LibreOffice produced no PDF output")

        import fitz
        pdf_doc = fitz.open(str(pdf_path))
        slide_index = min(_find_slide_index(prs, slide), pdf_doc.page_count - 1)
        page = pdf_doc[slide_index]

        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        pdf_doc.close()

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        if output_path:
            img.save(str(output_path))
        return img


def _render_all_via_libreoffice(
    pptx: Any,
    output_dir: Path,
    dpi: int,
) -> list[Path]:
    """Render all slides via LibreOffice in one pass."""
    paths: list[Path] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pptx_path = tmpdir_path / "temp.pptx"
        pptx.save(str(pptx_path))
        _libreoffice_pptx_to_pdf(pptx_path, tmpdir_path)

        pdf_path = tmpdir_path / "temp.pdf"
        if not pdf_path.exists():
            candidates = list(tmpdir_path.glob("*.pdf"))
            pdf_path = candidates[0] if candidates else None
        if not pdf_path:
            raise RuntimeError("LibreOffice produced no PDF output")

        import fitz
        pdf_doc = fitz.open(str(pdf_path))
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        for page_num in range(pdf_doc.page_count):
            pix = pdf_doc[page_num].get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            out_path = output_dir / f"slide_{page_num:03d}.png"
            img.save(str(out_path))
            paths.append(out_path)

        pdf_doc.close()
    return paths


def _libreoffice_pptx_to_pdf(pptx_path: Path, output_dir: Path) -> None:
    """Convert PPTX → PDF via LibreOffice headless."""
    result = subprocess.run(
        [
            "soffice", "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(pptx_path),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed: {result.stderr}")


# ── Strategy 2: PowerPoint COM (Windows) ────────────────────────────────────

def _powerpoint_com_available() -> bool:
    """Check if PowerPoint COM automation is available (Windows only)."""
    if shutil.which("powershell") is None:
        return False
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "(New-Object -ComObject PowerPoint.Application).Quit()"],
            capture_output=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _render_via_powerpoint_com(
    prs: Any,
    slide: Any,
    output_path: Optional[str | Path],
    dpi: int,
) -> Image.Image:
    """Render via PowerPoint COM automation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pptx_path = tmpdir_path / "temp.pptx"
        png_path = tmpdir_path / "slide.png"

        prs.save(str(pptx_path))
        slide_index = _find_slide_index(prs, slide) + 1  # PowerPoint is 1-based

        # PowerShell script to export a single slide
        ps_script = f"""
$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = $false
$pres = $ppt.Presentations.Open('{pptx_path}')
$pres.Slides[{slide_index}].Export('{png_path}', 'PNG', {dpi}, {dpi})
$pres.Close()
$ppt.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
"""
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0 or not png_path.exists():
            raise RuntimeError(f"PowerPoint COM failed: {result.stderr}")

        img = Image.open(png_path).convert("RGB")
        if output_path:
            img.save(str(output_path))
        return img


def _render_all_via_powerpoint_com(
    pptx: Any,
    output_dir: Path,
    dpi: int,
) -> list[Path]:
    """Render all slides via PowerPoint COM."""
    paths: list[Path] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pptx_path = tmpdir_path / "temp.pptx"
        pptx.save(str(pptx_path))

        ps_script = f"""
$ppt = New-Object -ComObject PowerPoint.Application
$ppt.Visible = $false
$pres = $ppt.Presentations.Open('{pptx_path}')
for ($i = 1; $i -le $pres.Slides.Count; $i++) {{
    $out = '{tmpdir_path}' + "\\slide_" + ($i - 1).ToString('000') + ".png"
    $pres.Slides[$i].Export($out, 'PNG', {dpi}, {dpi})
}}
$pres.Close()
$ppt.Quit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
"""
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"PowerPoint COM bulk failed: {result.stderr}")

        for png_file in sorted(tmpdir_path.glob("slide_*.png")):
            dest = output_dir / png_file.name
            shutil.copy(png_file, dest)
            paths.append(dest)

    return paths


# ── Strategy 3: PIL fallback (always works) ─────────────────────────────────

# Named colors for shape type backgrounds
_SHAPE_COLORS = {
    "text-box": (240, 248, 255),   # light blue
    "picture": (255, 240, 230),    # light orange
    "PICTURE": (255, 240, 230),
    "table": (230, 255, 230),      # light green
    "chart": (255, 230, 255),      # light purple
    "auto_shape": (245, 245, 245), # light gray
    "group": (245, 245, 245),
    "placeholder": (255, 255, 240),# light yellow
}


def _render_via_pil(
    slide: Any,
    output_path: Optional[str | Path],
    dpi: int,
) -> Image.Image:
    """Render a slide using pure PIL — shows shape positions and text.

    This produces a simplified image that preserves the *layout structure*
    (element positions, sizes, text regions) which is exactly what ViT
    needs for clustering. It does NOT render fonts, gradients, or images.
    """
    from src.pptx_io.reader import extract_slide_shapes

    shapes = extract_slide_shapes(slide)

    # Get slide dimensions
    sw = (slide.slide_width / 914400) if hasattr(slide, "slide_width") else DEFAULT_SLIDE_W
    sh = (slide.slide_height / 914400) if hasattr(slide, "slide_height") else DEFAULT_SLIDE_H

    # Canvas size in pixels
    w_px = int(sw * dpi)
    h_px = int(sh * dpi)

    img = Image.new("RGB", (w_px, h_px), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Try to get a font; fall back to default
    try:
        font_sm = ImageFont.truetype("arial.ttf", max(10, int(9 * dpi / 72)))
        font_md = ImageFont.truetype("arial.ttf", max(12, int(12 * dpi / 72)))
        font_lg = ImageFont.truetype("arial.ttf", max(14, int(16 * dpi / 72)))
    except OSError:
        font_sm = font_md = font_lg = ImageFont.load_default()

    for shape_info in shapes:
        # Position in pixels
        left_px = int(shape_info["left"] / 914400 * dpi)
        top_px = int(shape_info["top"] / 914400 * dpi)
        w = int(shape_info["width"] / 914400 * dpi)
        h = int(shape_info["height"] / 914400 * dpi)

        # Clamp to canvas
        left_px = max(0, min(left_px, w_px - 1))
        top_px = max(0, min(top_px, h_px - 1))
        w = max(2, min(w, w_px - left_px))
        h = max(2, min(h, h_px - top_px))

        shape_type = shape_info.get("shape_type", "unknown")
        bg = _SHAPE_COLORS.get(shape_type, (245, 245, 245))

        # Draw shape background
        draw.rectangle(
            [left_px, top_px, left_px + w, top_px + h],
            fill=bg,
            outline=(180, 180, 180),
            width=max(1, dpi // 100),
        )

        # Draw text if present
        text = shape_info.get("text", "").strip()
        if text:
            font_size = shape_info.get("font_size")
            if font_size and font_size > 24:
                font = font_lg
            elif font_size and font_size > 14:
                font = font_md
            else:
                font = font_sm

            # Bold indicator
            is_bold = shape_info.get("bold", False)
            if is_bold:
                text = f"[B] {text}"

            # Truncate long text
            if len(text) > 80:
                text = text[:77] + "..."

            # Wrap text into multiple lines that fit the shape width
            lines = _wrap_text(text, font, draw, w - 6)
            y_offset = top_px + 3
            for line in lines:
                if y_offset + 14 > top_px + h:
                    break
                draw.text((left_px + 3, y_offset), line, fill=(40, 40, 40), font=font)
                y_offset += int(font_size or 14) + 2 if font_size else 16

        # Image placeholder icon (mountain + sun)
        if shape_type in ("picture", "PICTURE"):
            cx, cy = left_px + w // 2, top_px + h // 2
            r = min(w, h) // 4
            # Mountain
            draw.polygon(
                [(cx - r, cy + r // 2), (cx, cy - r // 2), (cx + r, cy + r // 2)],
                fill=(160, 160, 160), outline=(120, 120, 120),
            )
            # Sun
            sr = r // 2
            draw.ellipse(
                [cx + r // 2 - sr, cy - r // 2 - sr, cx + r // 2 + sr, cy - r // 2 + sr],
                fill=(255, 200, 50), outline=(200, 150, 30),
            )

        # Table indicator — draw grid lines
        if shape_type == "table":
            cols = 3
            rows = 3
            for ci in range(1, cols):
                x_line = left_px + ci * w // cols
                draw.line([(x_line, top_px), (x_line, top_px + h)], fill=(160, 160, 160), width=1)
            for ri in range(1, rows):
                y_line = top_px + ri * h // rows
                draw.line([(left_px, y_line), (left_px + w, y_line)], fill=(160, 160, 160), width=1)

    if output_path:
        img.save(str(output_path))
    return img


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    draw: ImageDraw.ImageDraw,
    max_width: int,
) -> list[str]:
    """Simple word-wrap for rendering text into a PIL shape bounding box."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines if lines else [text]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _find_slide_index(prs: Any, slide: Any) -> int:
    """Find the 0-based index of a slide within its presentation."""
    for idx, s in enumerate(prs.slides):
        if s is slide:
            return idx
    return 0

