# 🎨 PPT Agent — 智能PPT自动生成系统

基于 **编辑式生成** 范式的智能PPT生成Agent，能够分析参考PPT风格、解析源文档内容，并通过LLM驱动的增量编辑操作生成风格一致的新PPT，具备自动评价和自我修正能力。

## 🧠 核心概念

### 编辑式生成 (Edit-Based Generation)
不一次性生成整个PPT，而是将PPT生成建模为一系列对参考PPT的编辑操作：
- **增** (add_text, add_image, add_table, add_chart, add_slide)
- **删** (delete_shape, delete_slide)
- **改** (modify_text, modify_style)

每个操作由LLM通过 Function Call 输出，由 `python-pptx` 实际执行。

### 风格分析与迁移
1. **ViT 图像特征提取** — 使用 `google/vit-base-patch16-224` 提取每页幻灯片的视觉特征向量
2. **层次聚类** — 自动将幻灯片按版式分组（不需预设聚类数量）
3. **Schema 抽取** — LLM 分析每组代表性页面，提取结构化内容模式（元素位置、字体、配色）

### HTML 中间表示
将幻灯片转为简化HTML片段，LLM可以直接理解布局 → 输出编辑指令 → 转回 `python-pptx` 操作。

### 多维度自动评价与自我修正
- **内容丰富度** (40%)
- **设计美观性** (35%)
- **结构连贯性** (25%)
- 低于阈值 → 自动回溯重新编辑，形成"生成→评价→修正"闭环

## 📁 项目结构

```
PPT_Agent/
├── config.env                  # LLM配置（API Key等）
├── requirements.txt            # Python依赖
├── run.py                      # CLI 入口
├── streamlit_app.py            # Web UI (Streamlit)
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py               # 全局配置管理
│   ├── models/
│   │   └── __init__.py         # LangGraph State + TypedDict 定义
│   ├── llm/
│   │   └── __init__.py         # DeepSeek API 客户端
│   ├── parsing/
│   │   ├── __init__.py
│   │   ├── source_document.py  # 统一解析入口
│   │   ├── word_parser.py      # Word (.docx) 解析
│   │   ├── pdf_parser.py       # PDF 解析
│   │   └── text_parser.py      # 纯文本/Markdown 解析
│   ├── pptx_io/
│   │   ├── __init__.py
│   │   ├── reader.py           # PPT 读取与结构提取
│   │   ├── writer.py           # PPT 创建与写入
│   │   ├── html_converter.py   # PPTX ↔ HTML 双向转换
│   │   └── slide_renderer.py   # 幻灯片 → PNG 渲染
│   ├── style/
│   │   ├── __init__.py
│   │   ├── vit_extractor.py    # ViT 特征提取
│   │   ├── clustering.py       # 层次聚类
│   │   └── schema_extractor.py # LLM Schema 抽取
│   ├── editing/
│   │   ├── __init__.py
│   │   ├── operations.py       # 编辑操作类型定义 + Function Call Tools
│   │   ├── editor.py           # 编辑引擎（执行层）
│   │   └── llm_editor.py       # LLM 编辑指令生成
│   ├── evaluation/
│   │   ├── __init__.py
│   │   └── evaluator.py        # 多维度评价（LLM评委 + 规则回退）
│   ├── planning/
│   │   ├── __init__.py
│   │   └── outline_planner.py  # 大纲规划
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── chart_generator.py  # 图表生成 (matplotlib/plotly)
│   │   └── image_generator.py  # 图片生成 (DALL·E/占位图)
│   └── graph/
│       ├── __init__.py
│       └── workflow.py         # LangGraph 工作流编排
└── tests/
    ├── __init__.py
    ├── conftest.py             # 共享 fixtures
    ├── test_parsing.py
    ├── test_pptx_io.py
    ├── test_editing.py
    ├── test_evaluation.py
    └── test_style.py
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

编辑 `config.env`，填入你的 DeepSeek API Key（已预填示例key）。

### 3. 命令行使用

```bash
# 完整模式：源文档 + 参考PPT
python run.py report.docx template.pptx -o output.pptx

# 纯文本 + 参考PPT
python run.py notes.txt template.pptx --max-slides 15

# 无参考PPT（空白版式）
python run.py paper.pdf --no-style -o slides.pptx

# 调试模式
python run.py source.docx ref.pptx --debug

# 预演模式（仅解析+规划，不实际生成）
python run.py source.docx ref.pptx --dry-run
```

### 4. Web 界面

```bash
streamlit run streamlit_app.py
```

然后打开浏览器访问 `http://localhost:8501`，上传文件即可生成。

## 🏗️ LangGraph 工作流

```
┌─────────────────┐
│ 1. 解析文档      │  parse_documents
│   源文档+参考PPT │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. 风格分析      │  analyze_style
│   ViT→聚类→Schema│
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. 大纲规划      │  plan_outline
│   LLM分页+分派   │
└────────┬────────┘
         ▼
┌─────────────────┐     ┌─────────────────┐
│ 4. 逐页编辑      │◄───►│ 5. 自动评价      │
│   观察HTML→编辑  │     │   评分→修正决策   │
└────────┬────────┘     └─────────────────┘
         ▼
┌─────────────────┐
│ 6. 打包导出      │  finalize
│   保存PPT+报告   │
└─────────────────┘
```

## 🧪 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_parsing.py -v
pytest tests/test_editing.py -v

# 带覆盖率
pytest tests/ --cov=src --cov-report=html
```

## 📦 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| PPT操作 | python-pptx |
| LLM接口 | DeepSeek (OpenAI兼容API) |
| Agent框架 | LangGraph |
| UI | CLI (argparse + rich) / Streamlit |
| 图表 | matplotlib / plotly |
| 图片生成 | DALL·E 3 / 通义万相 (可选) |
| 图像特征 | HuggingFace ViT |
| 聚类 | scikit-learn 层次聚类 |
| 文档解析 | python-docx / PyMuPDF |

## 🔧 扩展点

- **更多LLM后端**：在 `src/llm/__init__.py` 的 `LLMClient` 中切换 `base_url`
- **自定义评价维度**：修改 `src/evaluation/evaluator.py` 中的权重和提示词
- **新编辑操作**：在 `src/editing/operations.py` 中添加新的 `EditOpType`，在 `editor.py` 中实现对应的 handler
- **微调评价模型**：`SlideEvaluator` 预留了 `_EVAL_MODEL_PATH` 接口
- **自定义图表样式**：扩展 `src/generation/chart_generator.py`
