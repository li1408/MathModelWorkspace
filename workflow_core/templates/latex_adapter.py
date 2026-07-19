"""Materialize and compile LaTeX templates without editing originals."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from workflow_core.evidence.artifacts import sha256_file


def template_hashes(template_root: Path) -> dict[str, str]:
    return {
        path.relative_to(template_root).as_posix(): sha256_file(path)
        for path in sorted(item for item in template_root.rglob("*") if item.is_file())
    }


def materialize_template(original_root: Path, destination: Path) -> dict[str, str]:
    before = template_hashes(original_root)
    if destination.exists():
        raise FileExistsError(f"Template destination already exists: {destination}")
    shutil.copytree(original_root, destination)
    after_original = template_hashes(original_root)
    if before != after_original:
        raise RuntimeError("Imported template changed while materializing its adapter copy.")
    return before


def compile_xelatex(paper_root: Path, latexmk_wrapper: Path) -> Path:
    subprocess.run(
        [str(latexmk_wrapper), "-xelatex", "-outdir=build", "main.tex"],
        cwd=paper_root,
        check=True,
    )
    pdf = paper_root / "build/main.pdf"
    if not pdf.is_file():
        raise RuntimeError("LaTeX compilation completed without producing build/main.pdf.")
    return pdf
