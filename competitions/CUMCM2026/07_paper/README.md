# 07_paper

用于保存中文 LaTeX 论文源文件。

## 子目录

- `sections/`：论文分节文件。
- `build/`：LaTeX Workshop、XeLaTeX、BibTeX 和 latexmk 的编译输出目录，默认不纳入 Git。

## 编译方式

正式完整编译方式保留为：

```powershell
latexmk -xelatex main.tex
```

`latexmk` 依赖 Perl。如果 `latexmk` 报告缺少 Perl，这属于环境阻塞项，不是 LaTeX 源码错误。

备用诊断流程为：

```powershell
xelatex main.tex
bibtex build/main
xelatex main.tex
xelatex main.tex
```

参考文献继续使用 BibTeX 和 `gbt7714-numerical`，不混用 Biber 或 `biblatex`。如果 `gbt7714-numerical.bst` 或 `gbt7714.sty` 无法定位，需要通过 MiKTeX 安装官方包 `gbt7714`，不要从非官方网络来源下载单独的 `.bst` 或 `.sty` 文件。

## 环境检查

从项目根目录运行：

```powershell
.\scripts\check_latex_env.ps1
```

## 规则

- 正式论文不生成目录页。
- 不编造摘要中的模型、结果和误差指标。
- 参考文献必须来自真实阅读或实际使用的来源。
- 论文引用的图表必须存在于 `06_paper_assets/`。
