# 论文编译依赖

论文采用 `ctexart + XeLaTeX + BibTeX + gbt7714-numerical`，正式构建由 `latexmk -xelatex` 驱动。

## 当前环境

- MiKTeX Portable 26.5：`E:\Tools\MiKTeXPortable-CUMCM`
- XeTeX/XeLaTeX：MiKTeX 26.5 Portable
- BibTeX：MiKTeX-BibTeX 4.2
- latexmk：4.88
- Perl：Strawberry Perl 5.42.2，安装于 E 盘
- `ctexart.cls`：已定位
- `gbt7714-numerical.bst`：已定位
- `gbt7714.sty`：已定位

项目通过 `.local/bin/*.cmd` 包装器调用真实 E 盘工具路径。不要通过 `.local/miktex-bin` junction 启动便携 MiKTeX，否则可能回退到另一个 Regular MiKTeX 配置。

## 环境检查

从项目根目录运行：

```powershell
.\scripts\setup_local_paths.ps1
.\scripts\check_latex_env.ps1
```

检查项包括 Perl、latexmk、MiKTeX Portable 配置、`ctexart.cls`、`gbt7714-numerical.bst` 和 `gbt7714.sty`。

## 正式编译

```powershell
cd 07_paper
..\.local\bin\latexmk.cmd -xelatex -outdir=build main.tex
```

`latexmkrc` 使用 E 盘便携 MiKTeX 的绝对 `xelatex`、`bibtex` 和 `xdvipdfmx` 路径，并禁用自动宏包安装。缺失依赖会立即报错，不会等待 MiKTeX 图形界面。

## 备用诊断

```powershell
cd 07_paper
$env:TEXINPUTS='..\styles;'
..\.local\bin\xelatex.cmd -disable-installer -interaction=nonstopmode -halt-on-error -file-line-error -output-directory=build main.tex
```

有真实引用后，备用完整顺序为 `xelatex -> bibtex -> xelatex -> xelatex`。不要引入 Biber、biblatex 或其他引用体系，也不要从非官方来源下载 `.bst` 文件。
