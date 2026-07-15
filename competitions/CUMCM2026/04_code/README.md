# 04_code

本目录保存 CUMCM2026 的 Python 数据处理、建模、验证、绘图和结果导出脚本。

## 模块顺序

| 文件 | 作用 |
| --- | --- |
| `00_config.py` | 统一路径、随机种子、配置读取、日志和安全写文件工具。 |
| `01_data_check.py` | 检查原始数据目录、manifest、校验文件和基础文件状态。 |
| `02_data_cleaning.py` | 从原始数据生成清洗数据；没有真实规则前不自动改写数据。 |
| `03_exploratory_analysis.py` | 对处理后数据做描述统计和探索性分析。 |
| `04_model_q1.py` | 问题一模型入口。 |
| `05_model_q2.py` | 问题二模型入口。 |
| `06_model_q3.py` | 问题三模型入口。 |
| `07_model_validation.py` | 模型检验、误差分析和一致性检查。 |
| `08_sensitivity_analysis.py` | 灵敏度和鲁棒性分析。 |
| `09_generate_figures.py` | 统一生成论文图表。 |
| `10_export_results.py` | 导出论文可引用结果和支撑材料。 |
| `run_all.py` | 保留原基线入口，并调度 practice、audit、final 三种可信度 profile。 |
| `run_context.py` | 生成 `run_id`，隔离结果并保存五类运行追踪文件。 |
| `flow_strategies.py` | 提供独立分流策略接口及权重合法性验证。 |
| `quality_gates.py` | 统一 ERROR、WARNING、INFO 结果和退出语义。 |
| `validation/` | FIFO 数值检验、空间收敛、替代结构比较、集合审计和冷启动复现。 |
| `reporting/` | 检查结论证据映射和图表 manifest。 |

## 运行方式

在项目根目录运行：

```powershell
.\.venv\Scripts\python.exe .\04_code\run_all.py --dry-run
```

无参数命令仍执行原有基线流程。扩展运行示例：

```powershell
.\.venv\Scripts\python.exe .\04_code\run_all.py --profile audit
.\.venv\Scripts\python.exe .\04_code\run_all.py --profile audit --stage algorithm_preconditions
.\.venv\Scripts\python.exe .\04_code\run_all.py --profile audit --from-stage convergence
.\.venv\Scripts\python.exe .\04_code\run_all.py --profile audit --stages alternatives,comparison_audit
```

扩展运行结果位于 `05_model_results/runs/<run_id>/`。只有同一 `run_id` 内、对象集合经过审计的结果才可标记为配对比较。

正式比赛开始后，先将原始数据登记到 `02_raw_data/data_manifest.csv`，再逐步启用各模块的真实逻辑。

## 规则

- 所有路径集中在 `00_config.py` 和 `config/paths.yml` 管理。
- 不在多个脚本中重复写绝对路径。
- 设置随机种子，保证结果可复现。
- 输出文件必须保存到固定目录。
- 不允许静默覆盖重要结果。
- 核心计算不依赖网络。
- 每个关键函数需要中文说明。
- 实验参数集中在 `config/experiment_plan.yml`，高风险假设集中在 `config/assumptions_registry.yml`。
- 检测到 FIFO 违反时必须切换非 FIFO 后备算法；后备算法不可用时不得输出正式路线。
