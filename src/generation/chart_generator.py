"""
Chart generator — creates chart images from data for insertion into slides.

Supports matplotlib (static) and plotly (interactive, exported as static PNG).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from src.config import get_config


class ChartGenerator:
    """Generate chart images from structured data.

    Usage::

        gen = ChartGenerator()
        path = gen.generate_chart("bar", data, title="Sales by Quarter")
        # path → "output/charts/chart_<uuid>.png"
    """

    def __init__(self, output_dir: Optional[str | Path] = None) -> None:
        """Initialize the chart generator.

        Args:
            output_dir: Where to save chart images. Default: config.output_dir / "charts".
        """
        cfg = get_config()
        self._output_dir = Path(output_dir or cfg.output_dir / "charts")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._dpi = cfg.generation.chart_dpi
        self._format = cfg.generation.chart_format

    def generate_chart(
        self,
        chart_type: Literal["bar", "line", "pie", "scatter", "horizontal_bar"],
        data: dict[str, Any],
        title: str = "",
        *,
        filename: Optional[str] = None,
    ) -> str:
        """Generate a chart image and return its file path.

        Args:
            chart_type: Type of chart to generate.
            data: Chart data in a simplified format::

                {
                    "categories": ["Q1", "Q2", "Q3", "Q4"],
                    "series": [
                        {"name": "Revenue", "values": [100, 150, 200, 180]},
                        {"name": "Cost", "values": [60, 80, 90, 85]},
                    ]
                }

                For pie charts, use::

                {
                    "labels": ["Product A", "Product B", "Product C"],
                    "values": [35, 25, 40],
                }

            title: Chart title.
            filename: Optional base filename (without extension). Auto-generated if None.

        Returns:
            Absolute path to the generated PNG file.
        """
        import matplotlib
        matplotlib.use("Agg")  # Non-interactive backend
        import matplotlib.pyplot as plt
        import matplotlib.font_manager as fm
        import numpy as np

        # Try to find a CJK font for Chinese characters
        self._setup_cjk_font()

        fig, ax = plt.subplots(figsize=(8, 5), dpi=self._dpi)

        match chart_type:
            case "bar":
                self._draw_bar(ax, data, title)
            case "horizontal_bar":
                self._draw_horizontal_bar(ax, data, title)
            case "line":
                self._draw_line(ax, data, title)
            case "pie":
                self._draw_pie(ax, data, title)
            case "scatter":
                self._draw_scatter(ax, data, title)
            case _:
                raise ValueError(f"Unsupported chart type: {chart_type}")

        fig.tight_layout()

        if filename is None:
            filename = f"chart_{uuid.uuid4().hex[:8]}"
        output_path = self._output_dir / f"{filename}.{self._format}"
        fig.savefig(str(output_path), dpi=self._dpi, bbox_inches="tight")
        plt.close(fig)

        return str(output_path)

    def generate_chart_plotly(
        self,
        chart_type: Literal["bar", "line", "pie", "scatter"],
        data: dict[str, Any],
        title: str = "",
        *,
        filename: Optional[str] = None,
    ) -> str:
        """Generate a chart using plotly (more polished visuals).

        Args:
            chart_type: Chart type.
            data: Same format as ``generate_chart``.
            title: Chart title.
            filename: Optional base filename.

        Returns:
            Absolute path to the generated PNG file.
        """
        import plotly.graph_objects as go
        import plotly.io as pio

        pio.kaleido.scope.default_format = self._format

        match chart_type:
            case "bar":
                fig = go.Figure()
                categories = data.get("categories", [])
                for series in data.get("series", []):
                    fig.add_trace(go.Bar(
                        x=categories,
                        y=series.get("values", []),
                        name=series.get("name", ""),
                    ))
                fig.update_layout(title=title, barmode="group")

            case "line":
                fig = go.Figure()
                categories = data.get("categories", [])
                for series in data.get("series", []):
                    fig.add_trace(go.Scatter(
                        x=categories,
                        y=series.get("values", []),
                        name=series.get("name", ""),
                        mode="lines+markers",
                    ))
                fig.update_layout(title=title)

            case "pie":
                fig = go.Figure(data=[go.Pie(
                    labels=data.get("labels", []),
                    values=data.get("values", []),
                )])
                fig.update_layout(title=title)

            case "scatter":
                fig = go.Figure()
                for series in data.get("series", []):
                    fig.add_trace(go.Scatter(
                        x=series.get("x", []),
                        y=series.get("y", []),
                        name=series.get("name", ""),
                        mode="markers",
                    ))
                fig.update_layout(title=title)

            case _:
                raise ValueError(f"Unsupported chart type: {chart_type}")

        if filename is None:
            filename = f"chart_plotly_{uuid.uuid4().hex[:8]}"
        output_path = self._output_dir / f"{filename}.{self._format}"
        fig.write_image(str(output_path))
        return str(output_path)

    # ── matplotlib drawing helpers ──────────────────────────────────────

    def _draw_bar(self, ax: Any, data: dict[str, Any], title: str) -> None:
        import numpy as np
        categories = data.get("categories", [])
        series_list = data.get("series", [])
        n_groups = len(categories)
        n_series = len(series_list)
        width = 0.8 / max(n_series, 1)
        x = np.arange(n_groups)

        for i, series in enumerate(series_list):
            offset = (i - (n_series - 1) / 2) * width
            ax.bar(x + offset, series.get("values", []), width, label=series.get("name", ""))

        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        ax.set_title(title)
        ax.legend()

    def _draw_horizontal_bar(self, ax: Any, data: dict[str, Any], title: str) -> None:
        import numpy as np
        categories = data.get("categories", [])
        series_list = data.get("series", [])
        n_groups = len(categories)
        n_series = len(series_list)
        height = 0.8 / max(n_series, 1)
        y = np.arange(n_groups)

        for i, series in enumerate(series_list):
            offset = (i - (n_series - 1) / 2) * height
            ax.barh(y + offset, series.get("values", []), height, label=series.get("name", ""))

        ax.set_yticks(y)
        ax.set_yticklabels(categories)
        ax.set_title(title)
        ax.legend()

    def _draw_line(self, ax: Any, data: dict[str, Any], title: str) -> None:
        categories = data.get("categories", [])
        for series in data.get("series", []):
            ax.plot(categories, series.get("values", []), marker="o", label=series.get("name", ""))
        ax.set_title(title)
        ax.legend()

    def _draw_pie(self, ax: Any, data: dict[str, Any], title: str) -> None:
        labels = data.get("labels", [])
        values = data.get("values", [])
        ax.pie(values, labels=labels, autopct="%1.1f%%")
        ax.set_title(title)

    def _draw_scatter(self, ax: Any, data: dict[str, Any], title: str) -> None:
        for series in data.get("series", []):
            ax.scatter(series.get("x", []), series.get("y", []), label=series.get("name", ""))
        ax.set_title(title)
        ax.legend()

    @staticmethod
    def _setup_cjk_font() -> None:
        """Try to set a CJK-capable font for matplotlib."""
        import matplotlib.font_manager as fm
        import matplotlib.pyplot as plt
        # Common CJK fonts
        candidates = [
            "SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei",
            "Noto Sans CJK SC", "Source Han Sans SC", "Arial Unicode MS",
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        for font_name in candidates:
            if font_name in available:
                plt.rcParams["font.family"] = font_name
                return
        # Fallback: just suppress warnings
        plt.rcParams["font.family"] = "sans-serif"
