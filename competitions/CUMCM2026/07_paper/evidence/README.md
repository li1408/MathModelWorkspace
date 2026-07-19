# 论文结论证据链

- `claims.csv` 由人工登记论文结论；`claim_id` 必须稳定，重要结论将 `importance` 标为 `major`。
- `evidence_links.csv` 把结论链接到真实结果文件，必须填写 `source_run_id`、相对文件路径和文件 SHA256。
- 自动脚本只检查 run、文件、指标和 hash 是否存在且可读，不自动理解论文自然语言。
- final 模式下，每条 major claim 至少需要一条状态为 `verified` 的有效证据，并由人工复核。
- `question_result_cards.csv` 每个小问只登记一个主结果，其他指标继续放在 `evidence_links.csv`；多个 evidence ID 使用 `|` 分隔。
- `abstract_matrix.csv` 每个小问一行，摘要中的数值必须出现在该行登记的 verified evidence value 中。
- 两张表只能引用 final submission run 的冻结 analysis parent；不得引用 practice、未冻结或其他 analysis run。
- 四张表验证通过后复制到 submission run 的 `outputs/evidence/`，并生成 `evidence_bundle.json`。H7/H8 绑定 run 内 bundle，不直接绑定仍可编辑的项目 CSV。
- 初始空表不是错误数据；它表示论文结果尚未经过冻结和人工复核。不得填入示例数值来消除 final ERROR。
