# CUMCM2026 项目工作区 📊
该目录保留已经跑通的矿井突水 Q1-Q4 练习流程，同时作为通用工作流第一轮回归案例。旧算法不迁入通用核心，也不因通用化而重写。

## 两个入口

### 兼容基线

```powershell
.\.venv\Scripts\python.exe 04_code\run_all.py
```

无参数行为保持不变：数据检查、清洗、Q1-Q4、验证、灵敏度、图表与导出。

### 通用人工门禁

在仓库根目录运行：

```powershell
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.run_all `
  --project competitions/CUMCM2026 --profile practice
```

通用流程不会直接导入 `04_code`，而是通过 `cases/registry.yml` 启动已登记案例 runner，并把输出复制到独立 run。

每次等待人工门禁时，通用核心会自动生成 `09_review_packages/<run_id>/`。该机制属于通用工作流，后续新题目也使用相同的 01-H1 至 08-H8 顺序，不需要重新设计审核文件夹。

## 项目配置

| 文件 | 作用 |
| --- | --- |
| `config/problem_profile.yml` | Codex 生成的题目画像初稿，H1 前不可视为批准 |
| `config/requirements_matrix.yml` | Q1-Q4 输入、输出、目标、验证和论文映射 |
| `config/question_storyboard.yml` | 每个小问的目标、模型理由、求解路线、验证选择和结论边界 |
| `config/data_catalog.yml` | 私有资产逻辑 URI、SHA256 与只读策略 |
| `config/preprocessing_plan.yml` | H2 审批的预处理操作与输出 |
| `config/assumptions_registry.yml` | 题面条件与作者假设分开登记 |
| `config/model_cards/` | 模型角色、插件、前提、指标和失败模式 |
| `config/validation_plan.yml` | 按风险选择的验证任务 |
| `config/audit_plan.yml` | A0-A3 审计级别与升级条件 |
| `config/supporting_materials_allowlist.yml` | 匿名支撑材料正向打包清单 |
| `config/local/` | 本机资产和身份映射；Git 忽略 |
| `09_review_packages/` | 自动生成的 AI+人工内部审核包；按 H1-H8 排序 |

## Run 生命周期

```text
created -> running -> waiting_approval/paused
        -> completed -> frozen
        -> failed/invalidated/tampered
```

每个 run 位于 `05_model_results/runs/<run_id>/`，包含配置与代码快照、输入 hash、环境、阶段报告、日志、输出和 artifact manifest。

- `completed` 后输出不得新增、删除或覆盖。
- 完整输出清单或 artifact hash 变化会把 run 标记为 `tampered`。
- final 只能引用 `frozen` analysis run。
- 配置变化必须创建新 run，并记录 `parent_run_id`。

## 数据规则 🔒

- 原始数据位于 `02_raw_data/`，只能读取。
- 正式配置不保存个人绝对路径。
- 本机路径只写入 `config/local/assets.local.yml`。
- H2 未批准时不得生成正式处理后数据。
- 冷启动正式输入只通过 `CUMCM_INPUT_ROOT` 提供。
- 大文件、临时目录和复现副本必须保存在项目所在 E 盘。

## 论文与证据

- 结论登记：`07_paper/evidence/claims.csv`
- 证据链接：`07_paper/evidence/evidence_links.csv`
- 小问结果卡：`07_paper/evidence/question_result_cards.csv`
- 摘要矩阵：`07_paper/evidence/abstract_matrix.csv`
- 图表清单：`06_paper_assets/figure_manifest.csv`
- 论文：`07_paper/main.tex`
- 编译：`ctexart + XeLaTeX + BibTeX + gbt7714-numerical`

major claim 必须有 direct evidence。稳定性、鲁棒性、准确性或最优性 major claim 还必须有 validation/robustness evidence，并写清条件和限制。

填写顺序固定为：冻结 analysis run，登记 claims 和 evidence links，填写逐问结果卡，最后压缩成摘要矩阵。final evidence 阶段验证通过后，会把四张表复制到 submission run 并生成 `evidence_bundle.json`；H7/H8 审批绑定该 bundle 的 hash。

初始结果卡和摘要矩阵只有表头，这是有意设计。不得为通过检查填入预测值、示例结果或虚构 reviewer。

## 当前待人工处理

- `00_official/` 没有全国规则原文快照，规则保持 `pending_confirmation`。
- `problem_profile`、需求矩阵、假设、验证计划均为初稿，需要 H1-H4。
- `claims.csv` 与 `evidence_links.csv` 当前不自动填入结论。
- `question_result_cards.csv` 与 `abstract_matrix.csv` 当前保持空表，需在真实 analysis run 冻结后填写。
- 图表清单中的旧图只迁移了结构，未登记冻结通用 run 的 artifact 与人工 reviewer。
- final 提交前必须清除论文占位符并完成 H7/H8。

## 审核包操作

工作流暂停后，直接打开：

```text
09_review_packages/<run_id>/00_REVIEW_INDEX.csv
```

每个包包含一份冻结共享载荷、Google AI Studio 提示词和独立 Codex 审稿任务交接说明。队员不需要自己上传：在主 Codex 任务中说“开始审稿”，主 Codex 负责浏览器上传、保存 Gemini 回复、发送第二份审核任务并生成交叉核对。任一 AI 回复、合并结果或人工结论仍有 `PENDING` 标记时，批准命令都会被拒绝。

当前没有创建本题的独立 Codex 审稿任务。以后创建后，只把任务 ID 写入 Git 忽略的 `config/local/review_tasks.local.yml`，不得写入正式配置或匿名提交包。

默认不复制题目原始 PDF、原始附件、优秀论文、AI 历史日志或本机配置。如果比赛规则不允许向外部 AI 提供材料，应停止 AI 审核，只进行人工复核并按届时规则调整工作流。

## 常用验证

```powershell
# 项目测试
.\.venv\Scripts\python.exe -m unittest discover -s 04_code\tests -p "test_*.py"
.\.venv\Scripts\python.exe -m unittest discover -s 10_submission_check\tests -p "test_*.py"

# LaTeX
.\scripts\check_latex_env.ps1
cd 07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex

# 提交检查
cd ..
.\.venv\Scripts\python.exe 10_submission_check\check_submission.py --root . --mode draft
```

自动检查不能替代人工合规复核，H8 必须由两个不同队员完成。
