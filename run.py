#!/usr/bin/env python3
"""
PPT Agent — CLI entry point.

Usage::

    python run.py source.docx reference.pptx -o output.pptx
    python run.py source.pdf reference.pptx --max-slides 15
    python run.py source.txt --no-style          # generate without reference
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment before anything else
load_dotenv(Path(__file__).resolve().parent / "config.env")

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import get_config, reset_config
from src.graph.workflow import build_workflow
from src.models import create_initial_state


console = Console()


def setup_logging(debug: bool = False) -> None:
    """Configure logging levels."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="PPT Agent — Intelligent PPT Auto-Generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py report.docx template.pptx -o output.pptx
  python run.py notes.txt template.pptx --max-slides 10
  python run.py paper.pdf --no-style -o slides.pptx
        """,
    )

    parser.add_argument(
        "source",
        type=str,
        help="Path to the source document (.docx, .pdf, .txt, .md)",
    )
    parser.add_argument(
        "reference",
        type=str,
        nargs="?",
        default=None,
        help="Path to the reference PPT for style extraction",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="output/generated.pptx",
        help="Output path for the generated PPT (default: output/generated.pptx)",
    )
    parser.add_argument(
        "--max-slides",
        type=int,
        default=30,
        help="Maximum number of slides to generate (default: 30)",
    )
    parser.add_argument(
        "--no-style",
        action="store_true",
        help="Skip style analysis (use blank layout if no reference PPT)",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="LLM temperature (overrides config.env)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse documents and plan outline, but skip generation",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.debug)

    console.print()
    console.print("🎨 [bold cyan]PPT Agent[/bold cyan] — Intelligent PPT Auto-Generation", highlight=False)
    console.print("=" * 60, highlight=False)
    console.print()

    # Validate inputs
    source_path = Path(args.source).resolve()
    if not source_path.exists():
        console.print(f"[red]Error: Source document not found: {source_path}[/red]")
        sys.exit(1)

    ref_path = None
    if args.reference:
        ref_path = Path(args.reference).resolve()
        if not ref_path.exists():
            console.print(f"[red]Error: Reference PPT not found: {ref_path}[/red]")
            sys.exit(1)

    if args.no_style or ref_path is None:
        console.print("[yellow]⚠ No reference PPT — using blank layout template[/yellow]")
        ref_path = None
        # We still need a placeholder — use a minimal internal template
        # or the workflow will create a blank presentation

    # ── Run the workflow ────────────────────────────────────────────────
    console.print(f"📄 Source:   [green]{source_path.name}[/green]")
    if ref_path:
        console.print(f"🎨 Reference: [green]{ref_path.name}[/green]")
    console.print(f"📁 Output:   [green]{args.output}[/green]")
    console.print()

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            if args.dry_run:
                # ── Dry run: only parse and plan ────────────────────────
                task = progress.add_task("Parsing documents...", total=None)
                from src.parsing import parse_document
                source_doc = parse_document(source_path)
                progress.update(task, description="Documents parsed")

                console.print()
                console.print(f"📊 [bold]Document Summary:[/bold]")
                console.print(f"   Title: {source_doc['title']}")
                console.print(f"   Sections: {len(source_doc['sections'])}")
                console.print(f"   Tables: {len(source_doc['tables'])}")
                console.print(f"   Images: {len(source_doc['images'])}")
                console.print(f"   Characters: {len(source_doc['full_text'])}")
                console.print()

                # Show section headings
                console.print("[bold]Section Structure:[/bold]")
                for sec in source_doc["sections"]:
                    indent = "  " * max(sec.get("level", 0) - 1, 0)
                    console.print(f"   {indent}• {sec.get('heading', '(untitled)')}")

                console.print()
                console.print("[green]✓ Dry run complete. Use without --dry-run to generate PPT.[/green]")
                return

            # ── Full generation ─────────────────────────────────────────
            task = progress.add_task("Initializing workflow...", total=None)

            # Build the workflow
            app = build_workflow()
            progress.update(task, description="Workflow compiled")

            # Create initial state
            initial_state = create_initial_state(
                source_path=str(source_path),
                reference_pptx_path=str(ref_path) if ref_path else "",
                output_pptx_path=args.output,
            )
            progress.update(task, description="Running pipeline...")

            # Run
            final_state = app.invoke(initial_state)
            progress.update(task, description="Complete!")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    # ── Display results ─────────────────────────────────────────────────
    report = final_state.get("final_report", {})
    console.print()
    console.print("[bold green]✓ Generation Complete![/bold green]")
    console.print()

    # Summary table
    table = Table(title="Generation Report")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Total Slides", str(report.get("total_slides", 0)))
    table.add_row("Average Score", f"{report.get('average_score', 0):.1f}/10")
    table.add_row("Total Revisions", str(report.get("total_revisions", 0)))
    table.add_row("Edit Operations", str(report.get("total_edit_operations", 0)))
    table.add_row("Output Path", str(report.get("output_path", args.output)))

    console.print(table)
    console.print()

    # Per-slide breakdown
    per_slide = report.get("per_slide_scores", [])
    if per_slide:
        slide_table = Table(title="Per-Slide Scores")
        slide_table.add_column("Slide", justify="right")
        slide_table.add_column("Score", justify="right")
        slide_table.add_column("Revisions", justify="right")
        slide_table.add_column("Status")

        for s in per_slide:
            status = "[green]✓[/green]" if s.get("acceptable") else "[yellow]⚠[/yellow]"
            slide_table.add_row(
                str(s["slide_idx"]),
                f"{s['score']:.1f}",
                str(s["revisions"]),
                status,
            )

        console.print(slide_table)

    console.print()
    console.print(f"📁 Output saved to: [bold]{args.output}[/bold]")


if __name__ == "__main__":
    main()
