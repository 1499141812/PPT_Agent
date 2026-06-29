"""
PPT Agent — Streamlit Web Interface.

Launch with:
    streamlit run streamlit_app.py
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# Load environment
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "config.env")

from src.config import get_config
from src.parsing import parse_document
from src.graph.workflow import build_workflow, run_ppt_generation
from src.models import create_initial_state


# ── Page config ─────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="PPT Agent — 智能PPT生成",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar() -> dict[str, Any]:
    """Render sidebar controls and return settings dict."""
    with st.sidebar:
        st.title("🎨 PPT Agent")
        st.markdown("---")

        st.subheader("📤 上传文件")

        source_file = st.file_uploader(
            "源文档",
            type=["docx", "pdf", "txt", "md"],
            help="Word文档、PDF、或纯文本文件",
        )

        reference_file = st.file_uploader(
            "参考PPT（可选）",
            type=["pptx"],
            help="上传参考PPT以提取风格",
        )

        st.markdown("---")
        st.subheader("⚙️ 生成设置")

        max_slides = st.slider(
            "最大幻灯片数",
            min_value=5,
            max_value=50,
            value=20,
            step=1,
        )

        temperature = st.slider(
            "LLM 温度",
            min_value=0.0,
            max_value=1.5,
            value=0.7,
            step=0.1,
            help="越高越有创意，越低越保守",
        )

        language = st.selectbox("输出语言", ["中文", "English"], index=0)
        use_style = st.checkbox("启用风格分析", value=True)

        st.markdown("---")
        st.caption(f"模型: {get_config().llm.model}")
        st.caption("Powered by LangGraph + DeepSeek")

        return {
            "source_file": source_file,
            "reference_file": reference_file,
            "max_slides": max_slides,
            "temperature": temperature,
            "use_style": use_style,
            "language": language,
        }


# ── Main page ───────────────────────────────────────────────────────────────

def render_main_page() -> None:
    """Render the main content area."""
    st.title("🎨 PPT Agent — 智能PPT自动生成")

    st.markdown("""
    <style>
    .big-text { font-size: 1.2em; }
    </style>
    <div class="big-text">
    上传一份<b>源文档</b>（Word/PDF/文本）和一个<b>参考PPT</b>，
    AI 将分析参考PPT的风格，然后将源文档内容自动排版生成风格一致的新PPT。
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Feature overview
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📄", "文档解析", help="支持 Word / PDF / Markdown")
    with col2:
        st.metric("🎨", "风格迁移", help="ViT 图像分析 + 层次聚类")
    with col3:
        st.metric("✏️", "编辑式生成", help="LLM 驱动的增量编辑")
    with col4:
        st.metric("✅", "自动评价", help="多维度评分 + 自我修正")

    st.markdown("---")

    # ── Usage instructions ──────────────────────────────────────────────
    with st.expander("📖 使用说明", expanded=False):
        st.markdown("""
        ### 工作流程
        1. **上传源文档**：支持 Word (.docx)、PDF (.pdf)、纯文本 (.txt, .md)
        2. **上传参考PPT**（可选）：用于提取风格和版式
        3. **点击生成**：AI 将自动完成以下步骤：
           - 解析源文档内容
           - 分析参考PPT的版式和风格
           - 规划幻灯片大纲
           - 逐页编辑生成
           - 多维度评价与自动修正
        4. **下载结果**：生成的PPT文件

        ### 生成原理
        - **编辑式生成**：不是模板填充，而是模仿"编辑PPT文件"的过程
        - **风格迁移**：用 ViT 模型提取每页幻灯片的视觉特征，聚类后识别版式
        - **HTML中间表示**：将幻灯片转为简化HTML，让大模型理解布局
        - **自动修正**：从内容丰富度、设计美观性、结构连贯性三个维度评分

        ### 注意事项
        - 首次运行需要下载 ViT 模型（约 350MB）
        - 生成速度取决于LLM响应时间和幻灯片数量
        - 参考PPT的质量直接影响生成效果
        """)


def run_generation(settings: dict[str, Any]) -> None:
    """Execute the PPT generation workflow and display progress.

    Args:
        settings: Dictionary from render_sidebar().
    """
    source_file = settings["source_file"]
    reference_file = settings["reference_file"]

    if source_file is None:
        st.warning("请先上传源文档")
        return

    # Save uploaded files to temp directory
    temp_dir = Path(tempfile.mkdtemp())
    source_path = temp_dir / source_file.name
    source_path.write_bytes(source_file.getvalue())

    ref_path: Optional[Path] = None
    if reference_file is not None:
        ref_path = temp_dir / reference_file.name
        ref_path.write_bytes(reference_file.getvalue())

    output_path = temp_dir / "generated.pptx"

    # ── Progress display ────────────────────────────────────────────────
    progress_bar = st.progress(0, "准备中...")
    status_area = st.empty()

    try:
        # Step 1: Parse source
        status_area.info("📄 正在解析源文档...")
        source_doc = parse_document(source_path)
        progress_bar.progress(20, "源文档解析完成")

        # Show source summary
        st.markdown("### 📊 文档概览")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("标题", source_doc["title"])
        col2.metric("章节数", len(source_doc["sections"]))
        col3.metric("表格数", len(source_doc["tables"]))
        col4.metric("图片数", len(source_doc["images"]))

        # Step 2-6: Run the full workflow
        status_area.info("🚀 正在运行PPT生成流水线...")

        app = build_workflow()
        initial_state = create_initial_state(
            source_path=str(source_path),
            reference_pptx_path=str(ref_path) if ref_path else "",
            output_pptx_path=str(output_path),
        )

        # Override config values from UI settings
        import os
        if settings["temperature"] != 0.7:
            os.environ["DEEPSEEK_TEMPERATURE"] = str(settings["temperature"])
            from src.config import reset_config
            reset_config()

        progress_bar.progress(30, "正在分析参考PPT风格...")

        # Set language for planner
        os.environ["PPT_LANGUAGE"] = "en" if settings["language"].startswith("E") else "zh"

        # Run the workflow with progress updates
        final_state = app.invoke(initial_state)

        progress_bar.progress(90, "正在保存PPT...")

        # Read generated PPT for download
        if output_path.exists():
            ppt_data = output_path.read_bytes()
            progress_bar.progress(100, "生成完成！")
            status_area.success("✅ PPT 生成完成！")

            # ── Show results ────────────────────────────────────────────
            st.markdown("---")
            st.markdown("### 📊 生成报告")

            report = final_state.get("final_report", {})

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("幻灯片数", report.get("total_slides", 0))
            col2.metric("平均评分", f"{report.get('average_score', 0):.1f}/10")
            col3.metric("总修正次数", report.get("total_revisions", 0))
            col4.metric("编辑操作数", report.get("total_edit_operations", 0))

            # Download button
            st.download_button(
                label="📥 下载生成的PPT",
                data=ppt_data,
                file_name=f"{source_doc['title']}.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                type="primary",
            )

            # Per-slide scores
            per_slide = report.get("per_slide_scores", [])
            if per_slide:
                st.markdown("### 📈 逐页评分")
                import pandas as pd
                df = pd.DataFrame(per_slide)
                df["Status"] = df["acceptable"].apply(
                    lambda x: "✅" if x else "⚠️"
                )
                st.dataframe(
                    df[["slide_idx", "score", "revisions", "Status"]],
                    hide_index=True,
                    use_container_width=True,
                )
        else:
            st.error("PPT 生成失败：输出文件未创建")

    except Exception as e:
        st.error(f"生成过程中出错: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

    finally:
        # Cleanup temp files
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    """Streamlit app entry point."""
    settings = render_sidebar()

    if st.sidebar.button("🚀 开始生成", type="primary", use_container_width=True):
        run_generation(settings)
    else:
        render_main_page()


if __name__ == "__main__":
    main()
