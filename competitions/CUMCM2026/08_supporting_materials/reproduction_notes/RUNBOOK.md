# 复现说明

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s 04_code\tests -p 'test_*.py' -v
.\.venv\Scripts\python.exe 04_code\run_all.py
```

论文默认在 `07_paper` 下运行 `..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex`；配置使用 `bibtexu` 处理中文 UTF-8 文献。

结果工作簿位于 `05_model_results/tables/`，指标位于 `05_model_results/metrics/`。`model_results/manifest.csv` 记录冻结副本的 SHA256，可用来验证交付文件未被修改。
