# 09_review_packages

该目录由通用工作流在 H1-H8 等待人工审批时自动生成，不需要队员手工挑选文件。

```text
09_review_packages/<run_id>/
├── 00_REVIEW_INDEX.csv
├── 01_H1_problem_definition_<hash>/
├── 02_H2_data_preprocessing_<hash>/
├── 03_H3_model_design_<hash>/
├── 04_H4_validation_plan_<hash>/
├── 05_H5_baseline_validation_<hash>/
├── 06_H6_alternatives_comparison_<hash>/
├── 07_H7_paper_evidence_<hash>/
└── 08_H8_final_submission_<hash>/
```

每个审核包包含待审文件副本、AI 提示词、AI 完整回复位置、人工清单、人工结论模板、批准命令和 SHA256 manifest。

正常情况下工作流会自动生成。需要为已有等待中的 run 补建时，在仓库根目录运行：

```powershell
.\competitions\CUMCM2026\.venv\Scripts\python.exe -m workflow_core.cli.prepare_review `
  --project competitions/CUMCM2026 --run-id <run_id> --gate H1 --ai-tool Gemini
```

审核源文件 hash 变化时必须创建新 run，不能用新内容覆盖旧审核包。

审核包是本地内部材料。除本 README 外，其余内容均被 Git 忽略，并被提交检查和匿名支撑材料打包排除。
