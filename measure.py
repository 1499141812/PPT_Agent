# -*- coding: utf-8 -*-
"""One-shot metrics runner: runs the full pipeline once and prints all numbers.

Usage:
    python measure.py 源文档.docx 参考模板.pptx [-o out.pptx] [--runs 3]

Prints: 总耗时、平均评分、总修正次数、总编辑操作数、
        修正前后评分提升（每页）、触发修正的页数。
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "config.env")

from src.graph.workflow import build_workflow
from src.models import create_initial_state


def run_once(source: str, reference: str, output: str) -> dict:
    app = build_workflow()
    state = create_initial_state(
        source_path=source,
        reference_pptx_path=reference or "",
        output_pptx_path=output,
    )
    t0 = time.time()
    final = app.invoke(state)
    elapsed = time.time() - t0
    report = final.get("final_report", {})
    return {"elapsed": elapsed, "report": report}


def summarize(runs: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("量化指标（%d 次运行）" % len(runs))
    print("=" * 60)

    for i, r in enumerate(runs, 1):
        rep = r["report"]
        print(f"\n[第{i}次] 耗时 {r['elapsed']:.1f}s")
        print(f"  幻灯片数: {rep.get('total_slides', 0)}")
        print(f"  平均评分: {rep.get('average_score', 0):.2f}/10")
        print(f"  总修正次数: {rep.get('total_revisions', 0)}")
        print(f"  总编辑操作数: {rep.get('total_edit_operations', 0)}")

        # 修正前后提升（只统计真正触发过修正的页）
        gains = []
        for s in rep.get("per_slide_scores", []):
            hist = s.get("score_history", [])
            if len(hist) >= 2:
                gains.append((s["slide_idx"], hist[0], hist[-1], hist[-1] - hist[0]))
        if gains:
            print("  修正前后评分提升:")
            for idx, first, last, d in gains:
                print(f"    第{idx}页: {first:.1f} → {last:.1f}  (+{d:.1f})")
            avg_gain = sum(g[3] for g in gains) / len(gains)
            print(f"  平均提升: +{avg_gain:.1f} 分（{len(gains)} 页触发修正）")
        else:
            print("  修正前后提升: 本次无页触发修正")

        # 修正前→修正后 全局平均分（用于"X 分 → Y 分"这类表述）
        firsts = [s["score_history"][0] for s in rep.get("per_slide_scores", []) if s.get("score_history")]
        lasts = [s["score_history"][-1] for s in rep.get("per_slide_scores", []) if s.get("score_history")]
        if firsts:
            print(f"  修正前平均分: {sum(firsts)/len(firsts):.1f} → 修正后平均分: {sum(lasts)/len(lasts):.1f}")

    if len(runs) > 1:
        avg_t = sum(r["elapsed"] for r in runs) / len(runs)
        avg_s = sum(r["report"].get("average_score", 0) for r in runs) / len(runs)
        print(f"\n[均值] 耗时 {avg_t:.1f}s / 平均评分 {avg_s:.2f}/10")


def main() -> None:
    ap = argparse.ArgumentParser(description="Run pipeline and print metrics")
    ap.add_argument("source", help="源文档路径 (.docx/.pdf/.txt/.md)")
    ap.add_argument("reference", nargs="?", default=None, help="参考模板 PPT 路径")
    ap.add_argument("-o", "--output", default="output/measured.pptx")
    ap.add_argument("--runs", type=int, default=1, help="运行次数（取平均，默认 1）")
    args = ap.parse_args()

    if not Path(args.source).exists():
        print(f"源文档不存在: {args.source}")
        return

    runs = []
    for i in range(args.runs):
        print(f"运行 {i+1}/{args.runs} ...")
        out = args.output if args.runs == 1 else args.output.replace(".pptx", f"_{i+1}.pptx")
        runs.append(run_once(args.source, args.reference or "", out))

    summarize(runs)


if __name__ == "__main__":
    main()
