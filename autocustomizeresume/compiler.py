"""LaTeX compiler: invokes tectonic and enforces 1-page limit.

Compiles .tex to PDF via tectonic, checks page count, and retries
by dropping lowest-scored optional items if the result exceeds 1 page.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from pypdf import PdfReader

from autocustomizeresume.schemas import (
    ContentSelection,
    ItemDecision,
    SectionDecision,
)

if TYPE_CHECKING:
    from autocustomizeresume.models import ParsedResume

logger = logging.getLogger(__name__)

_COMPILE_TIMEOUT_SECS = 120


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
        temporary directory.  When *None*, a temporary directory is
        created; the caller owns cleanup of the directory containing
        the returned PDF path.

    Returns
    -------
    Path
        Path to the generated PDF file.

    Raises
    ------
    CompileError
        If tectonic exits with a non-zero code or times out.
    """
    if keep_dir is not None:
        work = keep_dir
        work.mkdir(parents=True, exist_ok=True)
        owns_dir = False
    else:
        work = Path(tempfile.mkdtemp(prefix="acr_"))
        owns_dir = True

    tex_path = work / "resume.tex"
    tex_path.write_text(tex_content, encoding="utf-8")

    logger.debug("Compiling %s with tectonic", tex_path)

    try:
        try:
            result = subprocess.run(
                ["tectonic", "-c", "minimal", str(tex_path)],
                capture_output=True,
                text=True,
                timeout=_COMPILE_TIMEOUT_SECS,
            )
        except subprocess.TimeoutExpired as exc:
            raise CompileError(
                f"tectonic timed out after {_COMPILE_TIMEOUT_SECS}s"
            ) from exc

        if result.returncode != 0:
            raise CompileError(
                f"tectonic failed (exit {result.returncode}):\n{result.stderr.strip()}"
            )

        pdf_path = tex_path.with_suffix(".pdf")
        if not pdf_path.exists():
            raise CompileError("tectonic exited successfully but no PDF was produced")
    except Exception:
        if owns_dir:
            shutil.rmtree(work, ignore_errors=True)
        raise

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
        raise CompileError(f"Failed to read page count from {pdf_path}: {exc}") from exc


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
                    bullets.append(
                        _Droppable(
                            section_id=sec.id,
                            item_id=it.id,
                            bullet_id=bd.id,
                            score=bd.relevance_score,
                        )
                    )
            # The item itself is droppable
            items.append(
                _Droppable(
                    section_id=sec.id,
                    item_id=it.id,
                    bullet_id=None,
                    score=it.relevance_score,
                )
            )

    # Sort each group by score ascending (drop lowest first)
    bullets.sort(key=lambda d: d.score)
    items.sort(key=lambda d: d.score)

    return bullets + items


@dataclass
class _Addable:
    """A candidate element that was excluded and can be re-added to fill space."""

    section_id: str
    item_id: str
    bullet_id: str | None  # None means re-add the whole item
    score: int  # relevance_score (higher = add first)


def _find_addables(selection: ContentSelection) -> list[_Addable]:
    """Collect all currently-excluded optional elements, sorted by score descending.

    Returns items first (highest score first), then bullets (highest first).
    This ordering means we try re-adding entire items before individual bullets.
    """
    bullets: list[_Addable] = []
    items: list[_Addable] = []

    for sec in selection.sections:
        if not sec.include:
            continue
        for it in sec.items:
            if not it.include:
                if it.relevance_score < 0:
                    continue  # already tried and overflowed
                # Whole item is excluded — candidate for re-adding
                items.append(
                    _Addable(
                        section_id=sec.id,
                        item_id=it.id,
                        bullet_id=None,
                        score=it.relevance_score,
                    )
                )
                continue
            # Item is included — check for excluded bullets
            for bd in it.bullets:
                if not bd.include:
                    if bd.relevance_score < 0:
                        continue  # already tried and overflowed
                    bullets.append(
                        _Addable(
                            section_id=sec.id,
                            item_id=it.id,
                            bullet_id=bd.id,
                            score=bd.relevance_score,
                        )
                    )

    # Sort each group by score descending (add highest first)
    items.sort(key=lambda a: a.score, reverse=True)
    bullets.sort(key=lambda a: a.score, reverse=True)

    return items + bullets


def _add_element(
    selection: ContentSelection, addable: _Addable
) -> ContentSelection:
    """Return a new *ContentSelection* with the given addable re-included."""
    new_sections: list[SectionDecision] = []
    for sec in selection.sections:
        if sec.id != addable.section_id:
            new_sections.append(sec)
            continue

        new_items: list[ItemDecision] = []
        for it in sec.items:
            if it.id != addable.item_id:
                new_items.append(it)
                continue

            if addable.bullet_id is not None:
                # Re-add a single bullet
                new_bullets = [
                    replace(bd, include=True) if bd.id == addable.bullet_id else bd
                    for bd in it.bullets
                ]
                new_items.append(replace(it, bullets=new_bullets))
            else:
                # Re-add the entire item, preserving original bullet states
                new_items.append(replace(it, include=True))

        new_sections.append(replace(sec, items=new_items))

    return replace(selection, sections=new_sections)


def _mark_skip(
    selection: ContentSelection, addable: _Addable
) -> ContentSelection:
    """Set an excluded element's score to -1 so _find_addables skips it."""
    new_sections: list[SectionDecision] = []
    for sec in selection.sections:
        if sec.id != addable.section_id:
            new_sections.append(sec)
            continue

        new_items: list[ItemDecision] = []
        for it in sec.items:
            if it.id != addable.item_id:
                new_items.append(it)
                continue

            if addable.bullet_id is not None:
                new_bullets = [
                    replace(bd, relevance_score=-1)
                    if bd.id == addable.bullet_id
                    else bd
                    for bd in it.bullets
                ]
                new_items.append(replace(it, bullets=new_bullets))
            else:
                new_items.append(replace(it, relevance_score=-1))

        new_sections.append(replace(sec, items=new_items))

    return replace(selection, sections=new_sections)


def _drop_element(
    selection: ContentSelection, droppable: _Droppable
) -> ContentSelection:
    """Return a new *ContentSelection* with the given droppable excluded."""
    new_sections: list[SectionDecision] = []
    for sec in selection.sections:
        if sec.id != droppable.section_id:
            new_sections.append(sec)
            continue

        new_items: list[ItemDecision] = []
        for it in sec.items:
            if it.id != droppable.item_id:
                new_items.append(it)
                continue

            if droppable.bullet_id is not None:
                # Drop a single bullet
                new_bullets = [
                    replace(bd, include=False) if bd.id == droppable.bullet_id else bd
                    for bd in it.bullets
                ]
                new_items.append(replace(it, bullets=new_bullets))
            else:
                # Drop the entire item
                new_items.append(replace(it, include=False))

        new_sections.append(replace(sec, items=new_items))

    return replace(selection, sections=new_sections)


# ---------------------------------------------------------------------------
# 1-page enforcement
# ---------------------------------------------------------------------------

_MAX_RETRIES = 10


def compile_with_enforcement(
    parsed: "ParsedResume",
    selection: ContentSelection,
    *,
    keep_dir: Path | None = None,
) -> tuple[Path, ContentSelection]:
    """Assemble, compile, and enforce the 1-page limit.

    If the compiled PDF exceeds 1 page, the lowest-scored optional
    element is dropped (bullets first, then whole items) and the
    document is recompiled.  Up to *_MAX_RETRIES* attempts are made.

    Parameters
    ----------
    parsed:
        Structured parsed resume from the parser.
    selection:
        The LLM's content selection decisions.
    keep_dir:
        If provided, write build artifacts here.  When *None*, a
        temporary directory is created; the caller owns cleanup of the
        directory containing the returned PDF path.

    Returns
    -------
    tuple[Path, ContentSelection]
        The PDF path and the (possibly modified) selection used.

    Raises
    ------
    CompileError
        If tectonic fails or the document still exceeds 1 page after
        all retry attempts.
    """
    from autocustomizeresume.assembler import assemble_tex

    # Use a single working directory for all retries to avoid temp dir leaks
    if keep_dir is not None:
        work_dir = keep_dir
        owns_dir = False
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="acr_"))
        owns_dir = True

    # Work on an immutable selection, producing new copies on each drop
    current_sel = selection
    attempt = 0

    try:
        # Phase 1: Drop content until it fits on 1 page
        for attempt in range(_MAX_RETRIES + 1):
            tex = assemble_tex(parsed, current_sel)
            pdf_path = compile_tex(tex, keep_dir=work_dir)
            pages = get_page_count(pdf_path)

            if pages <= 1:
                logger.info("PDF fits in 1 page (attempt %d)", attempt + 1)
                break

            logger.warning(
                "PDF has %d pages (attempt %d/%d), dropping content",
                pages,
                attempt + 1,
                _MAX_RETRIES + 1,
            )

            if attempt == _MAX_RETRIES:
                break

            # Find something to drop
            droppables = _find_droppables(current_sel)
            if not droppables:
                break

            target = droppables[0]
            kind = (
                f"bullet '{target.bullet_id}'"
                if target.bullet_id
                else f"item '{target.item_id}'"
            )
            logger.info(
                "Dropping %s (score=%d) from section '%s'",
                kind,
                target.score,
                target.section_id,
            )

            current_sel = _drop_element(current_sel, target)

        if pages > 1:
            if owns_dir:
                shutil.rmtree(work_dir, ignore_errors=True)
            raise CompileError(
                f"Resume still exceeds 1 page after {attempt + 1} attempts"
            )

        # Phase 2: Re-add excluded content to fill remaining space
        # Try adding back highest-scored excluded elements one at a time;
        # keep each addition only if the result still fits on 1 page.
        for fill_attempt in range(_MAX_RETRIES * 3):
            addables = _find_addables(current_sel)
            if not addables:
                break

            candidate = addables[0]
            trial_sel = _add_element(current_sel, candidate)

            tex = assemble_tex(parsed, trial_sel)
            trial_pdf = compile_tex(tex, keep_dir=work_dir)
            pages = get_page_count(trial_pdf)

            kind = (
                f"bullet '{candidate.bullet_id}'"
                if candidate.bullet_id
                else f"item '{candidate.item_id}'"
            )

            if pages <= 1:
                logger.info(
                    "Re-added %s (score=%d) from section '%s' — still fits",
                    kind,
                    candidate.score,
                    candidate.section_id,
                )
                current_sel = trial_sel
                pdf_path = trial_pdf
            else:
                # Re-compile with current_sel to restore the on-disk PDF
                # (compile_tex overwrites the same file in work_dir).
                tex = assemble_tex(parsed, current_sel)
                pdf_path = compile_tex(tex, keep_dir=work_dir)
                logger.info(
                    "Re-adding %s (score=%d) from section '%s' overflows — skipping",
                    kind,
                    candidate.score,
                    candidate.section_id,
                )
                # Mark this element as permanently excluded so we don't retry it
                # by dropping it from the current selection (it's already excluded,
                # but we need to remove it from addables consideration).
                # We do this by moving to the next candidate — _find_addables will
                # return the same list, so we need to actually exclude it.
                # The element is already excluded in current_sel, so we just need
                # to skip it. We set its score to -1 to deprioritize it.
                current_sel = _mark_skip(current_sel, candidate)

        return pdf_path, current_sel

    except Exception:
        # Clean up auto-created temp dir on failure so it doesn't leak
        if owns_dir:
            shutil.rmtree(work_dir, ignore_errors=True)
        raise
