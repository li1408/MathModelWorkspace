# 2026 Practice 01

这是一个干净、可复现、适合 Codex 辅助的数学建模练习项目。

## 快速开始

1. 用 VS Code 打开本目录。
2. 安装 `.vscode/extensions.json` 推荐的扩展。
3. 建立 Python 环境并安装依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

4. 将赛题和原始附件放入 `data/raw/`。
5. 使用 LaTeX Workshop 编译 `paper/main.tex`。

## 编译论文

当前项目通过 `.local/miktex-bin` 这个本地 junction 调用 MiKTeX，避免 VS Code 配置中直接写中文安装路径。若 `.local/miktex-bin` 不存在，先运行：

```powershell
.\scripts\setup_local_paths.ps1
```

也可以手动编译：

```powershell
$env:PATH = "$PWD\.local\miktex-bin;$env:PATH"
cd paper
xelatex -synctex=1 -interaction=nonstopmode -file-line-error -output-directory=E:/AI/MathModelWorkspace/competitions/2026-practice-01/output main.tex
xelatex -synctex=1 -interaction=nonstopmode -file-line-error -output-directory=E:/AI/MathModelWorkspace/competitions/2026-practice-01/output main.tex
```

## 数据流

- `data/raw/`：原始数据，不修改。
- `data/interim/`：中间结果，可由脚本重新生成。
- `data/processed/`：清洗后的数据。
- `figures/`：Python 和 draw.io 导出的论文图像。
- `tables/`：Python 输出的论文表格。
- `output/`：LaTeX 编译产物和最终 PDF。

## 写作流

1. 读题并记录到 `logs/decision_log.md`。
2. 把原始数据放入 `data/raw/`。
3. 编写 `code/preprocessing.py` 生成清洗数据。
4. 编写模型、验证和灵敏度脚本。
5. 将真实图表输出到 `figures/` 和 `tables/`。
6. 逐节完善 `paper/sections/`。
7. 使用 `checklist/final_checklist.md` 做提交前检查。
