# 论文结论证据链

- `claims.csv` 由人工登记论文结论；`claim_id` 必须稳定，重要结论将 `importance` 标为 `major`。
- `evidence_links.csv` 把结论链接到真实结果文件，必须填写 `source_run_id`、相对文件路径和文件 SHA256。
- 自动脚本只检查 run、文件、指标和 hash 是否存在且可读，不自动理解论文自然语言。
- final 模式下，每条 major claim 至少需要一条状态为 `verified` 的有效证据，并由人工复核。
