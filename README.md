# MathModelWorkspace 📘

这是一个为数学建模竞赛准备的可复现工作区。它把论文写作、Python 建模、LaTeX 编译、AI 辅助、Git 版本管理和提交前检查放在同一个清晰结构里，方便队伍协作和最终复核。🤝

## 我们想实现什么 🎯

- 用 `competitions/CUMCM2026/` 写正式训练和比赛论文。
- 用 `resources/MathModelHub/` 查资料、看模板、参考算法，但不在里面写正式论文。
- 用 Python 处理数据、建模、画图和导出表格。
- 用 `ctexart + XeLaTeX + BibTeX + gbt7714-numerical` 编译中文论文。
- 用 Codex 协助写 LaTeX、修复编译错误、生成分析代码和检查论文逻辑。
- 用 Git/GitHub 保存可追溯版本，避免最后一天文件混乱。

## 当前核心目录 🗂️

| 路径 | 用途 |
| --- | --- |
| `resources/MathModelHub/` | 参考资料库，只读使用 |
| `competitions/CUMCM2026/` | 当前正式数学建模工作项目 |
| `competitions/CUMCM2026/00_inbox/` | 队友临时投递题目 PDF、附件文件夹和说明文件 |
| `competitions/CUMCM2026/01_problem/` | 题目文件和题面说明 |
| `competitions/CUMCM2026/02_raw_data/` | 原始数据，只登记、不直接修改 |
| `competitions/CUMCM2026/04_code/` | Python 清洗、建模、验证、画图脚本 |
| `competitions/CUMCM2026/06_paper_assets/` | 论文要引用的图表资源 |
| `competitions/CUMCM2026/07_paper/` | LaTeX 论文主目录 |
| `competitions/CUMCM2026/10_submission_check/` | 提交前自动检查脚本和规则 |
| `competitions/CUMCM2026/11_final_submission/` | 最终冻结提交文件 |

## 队友第一次使用 🚀

详细步骤请看：[TEAM_SETUP.md](TEAM_SETUP.md)

最短流程如下：

```powershell
git clone --recurse-submodules https://github.com/li1408/MathModelWorkspace.git
cd MathModelWorkspace\competitions\CUMCM2026
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\scripts\setup_local_paths.ps1
.\scripts\check_latex_env.ps1
```

建议把仓库克隆到 E 盘或其他非 C 盘位置，避免虚拟环境、缓存和大数据占用 C 盘。💾

## 常用命令 🧰

进入项目目录：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026
```

检查 LaTeX 环境：

```powershell
.\scripts\check_latex_env.ps1
```

检查 Python 流水线：

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
```

编译论文：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026\07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex
```

提交前草稿检查：

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
```

## 协作规则 ✅

- 不把 `.venv/`、`.local/`、LaTeX 编译产物、临时缓存、大文件和本地敏感信息上传到 GitHub。
- 队友不会分类时，先把题目 PDF 和附件文件夹放到 `competitions/CUMCM2026/00_inbox/`，再让 Codex 整理。
- 原始数据放在 `02_raw_data/`，不要直接修改；清洗结果另存。
- 论文里的结论必须能追溯到代码、数据和输出结果。
- 没有真实数据和代码结果时，保留 `\placeholder{}`，不要编造数值、结论或参考文献。
- `resources/MathModelHub/` 只作为参考，不在其中写比赛论文。
- 最终提交前必须跑自动检查，也必须做人工双人交叉复核。👀

## 分支建议 🌱

- `main`：稳定版本。
- `dev`：日常整合版本。
- `feature/*`：题目分析、模型、论文章节等具体任务。
- `fix/*`：修复编译、检查脚本或数据处理问题。

## 遇到问题先看这里 🧭

- LaTeX 编译失败：先跑 `.\scripts\check_latex_env.ps1`。
- Python 包缺失：确认正在使用 `.venv\Scripts\python.exe`。
- GitHub 上看不到 MathModelHub 内容：运行 `git submodule update --init --recursive`。
- final 检查失败：这是正常的，直到占位符、敏感词、本地规则和最终 PDF 都处理完才会通过。

这个仓库的目标不是“把所有东西都塞进 Git”，而是让每一步工作都能被复现、检查和追踪。🙂
