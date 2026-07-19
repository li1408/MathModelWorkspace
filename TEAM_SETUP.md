# 队友上手指南 👋
## 1. 准备工具

- Git 与私有 GitHub 仓库权限
- VS Code
- Python 3.10 或更高版本
- MiKTeX、XeLaTeX、BibTeX
- Strawberry Perl，用于 `latexmk`
- VS Code 扩展：LaTeX Workshop、Python、Pylance、Jupyter、GitLens、Markdown All in One、Error Lens、Code Spell Checker

仓库、虚拟环境、数据、MiKTeX 包和临时复现目录建议放在 E 盘。不要把大文件放到 C 盘。

## 2. 克隆与安装

```powershell
cd E:\AI
git clone --recurse-submodules https://github.com/li1408/MathModelWorkspace.git
cd MathModelWorkspace
python -m venv competitions\CUMCM2026\.venv
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m pip install -r competitions\CUMCM2026\requirements.txt
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m pip install -e .
```

初始化项目本地工具并检查 LaTeX：

```powershell
cd competitions\CUMCM2026
.\scripts\setup_local_paths.ps1
.\scripts\check_latex_env.ps1
```

如果 Perl 或 `gbt7714` 缺失，先修复环境；不要把环境错误误判成论文源码错误。

## 3. 准备本地附件

题目 PDF 与附件不依赖公开 Git。把私有附件放入项目对应目录，再复制本地映射：

```powershell
Copy-Item config\local\assets.local.example.yml config\local\assets.local.yml
```

工作流会使用正式配置中的 `asset_id + logical_uri + SHA256` 核验文件。本地映射只能保存于 `config/local/`，不得提交。

## 4. 先验证旧流程

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py --dry-run
.\.venv\Scripts\python.exe -m unittest discover -s 04_code\tests -p "test_*.py"
```

无参数 `04_code/run_all.py` 始终是现有 Q1-Q4 基线入口。

## 5. 启动通用流程

回到仓库根目录：

```powershell
cd E:\AI\MathModelWorkspace
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice
```

看到 `run_id=...` 后保存该编号。流程会在人工门禁前返回 `3`，审批请求位于：

```text
competitions/CUMCM2026/05_model_results/runs/<run_id>/logs/approval_requests/
```

实际需要审核的文件已经自动整理到：

```text
competitions/CUMCM2026/09_review_packages/<run_id>/
```

打开 `00_REVIEW_INDEX.csv`，按 `01_H1` 到 `08_H8` 的顺序处理。每个门禁只需：

1. 在主 Codex 任务中说“开始审稿”，不需要自己整理或上传材料；
2. 主 Codex 控制 Chrome，在 Google AI Studio 完成第一份独立审核；
3. 主 Codex 将同一份冻结载荷发送给本题独立 Codex 审稿任务；
4. 工作流保存两份回复并生成 `03_AI_REVIEW.md` 与 `04_AI_CROSSCHECK.md`；
5. 队员完成 `04_HUMAN_CHECKLIST.md` 和 `05_HUMAN_DECISION.md`；
6. 队员执行 `06_APPROVE_COMMAND.txt` 中的命令。

如果本题尚未创建独立 Codex 审稿任务，流程会暂停并说明原因，不会伪造第二份审核。每套题只使用自己的审稿任务，避免不同题目的上下文互相污染。

如果源文件发生变化，不要覆盖旧审核包；工作流会根据新 hash 生成新版本。旧包保留用于追溯。

队员必须打开请求列出的文件，核对内容与 hash 后再批准：

```powershell
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.approve `
  --project competitions/CUMCM2026 --run-id <run_id> `
  --gate H1 --human-id M1 --confirm-ai-review --confirm-human-review
```

继续运行：

```powershell
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice --resume-run <run_id>
```

配置或代码 hash 改变后不能恢复旧 run，应创建带 `parent_run_id` 的新 run：

```powershell
python -m workflow_core.cli.run_all --project competitions/CUMCM2026 `
  --profile audit --parent-run <old_run_id>
```

## 6. H1-H8 检查内容

| 门禁 | 人工检查 |
| --- | --- |
| H1 | 题目画像、题型与候选插件 |
| H2 | 数据审计与预处理计划 |
| H3 | 假设、候选模型与淘汰理由 |
| H4 | 验证计划与 Audit 预算 |
| H5 | 基线结果与基本不变量 |
| H6 | 替代模型、结构敏感性和结论边界 |
| H7 | 证据、图表、模板与论文初稿 |
| H8 | 数值终审和论文合规终审 |

以上八类审核包由 `workflow_core` 通用生成，换成其他国赛或校赛项目时操作完全相同。矿井题不是审核逻辑的一部分，只是当前回归案例。

H8 示例：

```powershell
python -m workflow_core.cli.approve ... --gate H8 --human-id M1 `
  --reviewer-role model_numeric_reviewer --confirm-human-review
python -m workflow_core.cli.approve ... --gate H8 --human-id M2 `
  --reviewer-role paper_compliance_reviewer --confirm-human-review
```

两个角色不能由同一 `human_id` 担任。

H1、H3、H4 还会分别显示 `question_storyboard.yml` 的稳定投影。修改题目叙事字段只会使 H1 投影变化，修改模型字段只影响 H3，修改验证选择只影响 H4；任何对应 hash 变化都必须重新人工审批。

analysis run 冻结后，队员再填写：

```text
07_paper/evidence/question_result_cards.csv
07_paper/evidence/abstract_matrix.csv
```

不要提前填写预计数值。final 会检查每个小问是否完整、来源 run 是否等于冻结父 run，以及摘要中的数字是否出现在已验证 evidence 中。

## 7. 编译与提交检查

```powershell
cd E:\AI\MathModelWorkspace\competitions\CUMCM2026\07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex

cd ..
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
```

`final` 失败在论文尚未完成时是正常现象。占位符、敏感信息、未定义引用、缺失最终文件或错误 hash 都必须在提交前解决。

## 8. 团队纪律 ✅

- 不修改 `02_raw_data/` 中的原始文件。
- 不上传真实题目、私有附件、大型 run、身份映射和本机路径。
- 不上传 `00_inbox/reference_papers/` 中的优秀论文、提取文本或渲染图。
- 不把实时比赛原始附件、身份信息或 `config/local/` 上传给外部 AI；审核包默认不会复制这些内容。
- 支撑材料 artifact 必须显式标记为 `anonymous_candidate`；默认 `internal` 和 `private_reference` 均不能打包。
- 不填入虚构数据、结论、文献或官方规则。
- Codex 不能批准 H1-H8；审批只能由实际队员完成。
- 自动检查通过后仍要进行双人交叉复核。
