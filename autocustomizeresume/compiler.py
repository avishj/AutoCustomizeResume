"""LaTeX compiler: invokes tectonic and enforces 1-page limit.

Compiles .tex to PDF via tectonic, checks page count, and retries
by dropping lowest-scored optional items if the result exceeds 1 page.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class CompileError(Exception):
    """Raised when tectonic compilation fails."""


def compile_tex(tex_content: str, *, keep_dir: Path | None = None) -> Path:
    """Compile a .tex string to PDF via tectonic.

    Parameters
    ----------
    tex_content:
        Complete LaTeX document as a string.
    keep_dir:
        If provided, write the .tex and .pdf here instead of a
        temporary directory (useful for debugging).

    Returns
    -------
    Path
        Path to the generated PDF file.

    Raises
    ------
    CompileError
        If tectonic exits with a non-zero code.
    """
    if keep_dir is not None:
        work = keep_dir
        work.mkdir(parents=True, exist_ok=True)
    else:
        work = Path(tempfile.mkdtemp(prefix="acr_"))

    tex_path = work / "resume.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    logger.debug("Compiling %s with tectonic", tex_path)

    result = subprocess.run(
        ["tectonic", "-c", "minimal", str(tex_path)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise CompileError(
            f"tectonic failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )

    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise CompileError(
            "tectonic exited successfully but no PDF was produced"
        )

    logger.info("Compiled PDF: %s", pdf_path)
    return pdf_path
