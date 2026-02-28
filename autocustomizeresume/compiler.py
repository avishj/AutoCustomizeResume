"""LaTeX compiler: invokes tectonic and enforces 1-page limit.

Compiles .tex to PDF via tectonic, checks page count, and retries
by dropping lowest-scored optional items if the result exceeds 1 page.
"""

from __future__ import annotations

import copy
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from autocustomizeresume.schemas import ContentSelection

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


def get_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a PDF file.

    Parameters
    ----------
    pdf_path:
        Path to an existing PDF file.

    Raises
    ------
    CompileError
        If the file cannot be read as a valid PDF.
    """
    try:
        reader = PdfReader(pdf_path)
        return len(reader.pages)
    except Exception as exc:
        raise CompileError(
            f"Failed to read page count from {pdf_path}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Droppable-element search
# ---------------------------------------------------------------------------

@dataclass
class _Droppable:
    """A candidate element that can be dropped to save space."""

    section_id: str
    item_id: str
    bullet_id: str | None  # None means drop the whole item
    score: int  # relevance_score (lower = drop first)


def _find_droppables(selection: ContentSelection) -> list[_Droppable]:
    """Collect all currently-included optional elements, sorted by score.

    Returns bullets first (lowest score first), then items (lowest first).
    This ordering means we try dropping individual bullets before
    escalating to entire items.
    """
    bullets: list[_Droppable] = []
    items: list[_Droppable] = []

    for sec in selection.sections:
        if not sec.include:
            continue
        for it in sec.items:
            if not it.include:
                continue
            # Collect droppable bullets within this item
            for bd in it.bullets:
                if bd.include:
                    bullets.append(_Droppable(
                        section_id=sec.id,
                        item_id=it.id,
                        bullet_id=bd.id,
                        score=it.relevance_score,
                    ))
            # The item itself is droppable
            items.append(_Droppable(
                section_id=sec.id,
                item_id=it.id,
                bullet_id=None,
                score=it.relevance_score,
            ))

    # Sort each group by score ascending (drop lowest first)
    bullets.sort(key=lambda d: d.score)
    items.sort(key=lambda d: d.score)

    return bullets + items


def _drop_element(
    selection_dict: dict, droppable: _Droppable
) -> None:
    """Mutate *selection_dict* to exclude the given droppable element."""
    for sec in selection_dict["sections"]:
        if sec["id"] != droppable.section_id:
            continue
        for it in sec["items"]:
            if it["id"] != droppable.item_id:
                continue
            if droppable.bullet_id is not None:
                # Drop a single bullet
                for bd in it["bullets"]:
                    if bd["id"] == droppable.bullet_id:
                        bd["include"] = False
                        return
            else:
                # Drop the entire item
                it["include"] = False
                return
