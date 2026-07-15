# 06_paper_assets

用于保存论文中实际引用的图表资产。

## 子目录

- `figures/`：Python 生成的图像，建议同时导出 PNG 和 PDF。
- `diagrams/`：draw.io / diagrams.net 流程图源文件和导出图。
- `tables/`：可供 LaTeX 引用的表格片段或 CSV 结果。
- `figure_manifest.csv`：记录图片来源 run、用途、坐标、单位、尺寸和人工复核状态。
- `figure_metadata/`：图像技术检查生成的本地 JSON；默认不进入 Git。

## 规则

- 论文只能引用本目录中真实存在的图表文件。
- 每张图必须有明确论证目的。
- 图表应由代码或可复现源文件生成，避免手工改数据。
- 不在图内部写长篇结论，结论写在正文。
- 自动检查只能验证文件、像素、DPI、尺寸和引用关系，不能判断图表是否真正支持论文结论。
- final 模式下，正文引用图必须由人工复核并在 manifest 中登记。
