# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""LaTeX assembler: stitches selected content back into a .tex file.

Takes a ParsedResume and ContentSelection, produces a complete
LaTeX document with only the selected items included.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, TypeVar

from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.utils import escape_latex_special

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from autocustomizeresume.schemas import (
        ContentSelection,
        ItemDecision,
        SectionDecision,
        SkillCategoryDecision,
    )

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Bullet helpers
# ---------------------------------------------------------------------------


def _bullet_text(bullet: Bullet, item_dec: ItemDecision | None) -> str:
    """Return the text for *bullet*, applying edited_text if present."""
    if item_dec is not None:
        bd = next((b for b in item_dec.bullets if b.id == bullet.id), None)
        if bd is not None and bd.edited_text:
            return escape_latex_special(bd.edited_text)
    return bullet.text


# ---------------------------------------------------------------------------
# Interstitial helpers
# ---------------------------------------------------------------------------


def _get_interstitial(interstitial: list[tuple[int, str]], position: int) -> str | None:
    """Return interstitial content for the given *position*, or None."""
    return next((text for pos, text in interstitial if pos == position), None)


def _assemble_with_interstitials[T](
    elements: Sequence[_T],
    interstitials: list[tuple[int, str]],
    assemble_fn: Callable[[_T], str | None],
    *,
    keep_trailing_pending: bool = False,
) -> list[str]:
    """Assemble *elements* with interstitial content interleaved.

    For each element, *assemble_fn* is called and may return ``None`` to
    exclude it.  Interstitials at excluded positions are deferred and
    flushed before the next included element.

    When *keep_trailing_pending* is ``True``, any pending interstitials
    from excluded elements at the tail are flushed (useful for pinned
    sections that keep their structure even when all children are
    excluded).

    The trailing interstitial (at position ``len(elements)``) is **not**
    handled here — callers manage it because the append conditions vary
    (e.g. unconditional vs only-when-content-exists).
    """
    assembled: list[str] = []
    pending: list[str] = []
    for idx, element in enumerate(elements):
        inter = _get_interstitial(interstitials, idx)
        if inter is not None:
            pending.append(inter)

        result = assemble_fn(element)
        if result is not None:
            assembled.extend(pending)
            pending.clear()
            assembled.append(result)

    if keep_trailing_pending and pending:
        assembled.extend(pending)

    return assembled


# ---------------------------------------------------------------------------
# Item-level assembly
# ---------------------------------------------------------------------------


def _is_bullet_included(bullet: Bullet, item_dec: ItemDecision | None) -> bool:
    """Determine if a bullet should be included."""
    # Pinned bullets always included
    if bullet.tag_type == "pinned":
        return True
    # Optional bullets need an explicit include from the decision
    if item_dec is not None:
        for bd in item_dec.bullets:
            if bd.id == bullet.id:
                return bd.include
    # No decision found — include by default (defensive)
    logger.debug(
        "No bullet decision for optional bullet '%s', including by default",
        bullet.id,
    )
    return True


def _assemble_item(
    item: ResumeItem,
    item_dec: ItemDecision | None,
) -> str | None:
    """Assemble a single item's LaTeX, or None if excluded.

    Returns None when:
    - The item is optional and excluded by selection.
    - The item is optional, included, but all its bullets are excluded
      (and it has no heading-only content).
    """
    # Determine inclusion
    if item.tag_type == "optional" and (item_dec is None or not item_dec.include):
        return None

    # Build bullet list — only included bullets
    #
    # Interstitials are keyed by position (before which bullet they appear).
    # If that bullet is excluded, the interstitial must still appear before
    # the next included bullet so that list wrappers (e.g.
    # \resumeItemListStart) are not lost.
    included_bullets: list[str] = []
    pending_interstitials: list[str] = []
    for idx, bullet in enumerate(item.bullets):
        # Collect interstitial at this position
        inter = _get_interstitial(item.interstitial, idx)
        if inter is not None:
            pending_interstitials.append(inter)

        if _is_bullet_included(bullet, item_dec):
            # Flush any pending interstitials before this bullet
            included_bullets.extend(pending_interstitials)
            pending_interstitials = []
            included_bullets.append(_bullet_text(bullet, item_dec))

    # Trailing interstitial (after last bullet)
    trailing = _get_interstitial(item.interstitial, len(item.bullets))

    # If item has bullets defined but none survived, fall back to compact
    # heading (one-liner) if available, or skip optional items entirely.
    if item.bullets and not included_bullets:
        if item.compact_heading is not None:
            return item.compact_heading
        if item.tag_type == "optional":
            return None

    parts: list[str] = []
    parts.append(item.heading_lines)
    if included_bullets:
        parts.extend(included_bullets)
    if trailing is not None and included_bullets:
        parts.append(trailing)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Section-level assembly
# ---------------------------------------------------------------------------


def _assemble_regular_section(
    section: ResumeSection,
    section_dec: SectionDecision | None,
) -> str | None:
    """Assemble a regular section, or None if excluded/empty."""
    # Pinned sections always included; optional checked against decision
    if section.tag_type == "optional" and (
        section_dec is None or not section_dec.include
    ):
        return None

    def _assemble(item: ResumeItem) -> str | None:
        item_dec = section_dec.find_item(item.id) if section_dec is not None else None
        return _assemble_item(item, item_dec)

    is_pinned = section.tag_type == "pinned"
    assembled_items = _assemble_with_interstitials(
        section.items,
        section.interstitial,
        _assemble,
        keep_trailing_pending=is_pinned,
    )

    # If all items were excluded, omit optional sections entirely.
    # Pinned sections keep their header even with no items.
    if not assembled_items and not is_pinned:
        return None

    # Trailing interstitial (after last item)
    trailing = _get_interstitial(section.interstitial, len(section.items))
    if trailing is not None:
        assembled_items.append(trailing)

    return "\n".join(assembled_items)


def _assemble_skill_category(
    cat: SkillCategory,
    cat_dec: SkillCategoryDecision | None,
) -> str | None:
    """Assemble a single skill category line.

    If a SkillCategoryDecision is provided, use its skill list (already
    filtered and reordered by the LLM).  Otherwise, use the original.
    """
    skills = cat_dec.skills if cat_dec is not None else cat.skills

    if not skills:
        return None

    skills_str = ", ".join(escape_latex_special(s) for s in skills)
    return f"{cat.prefix}{skills_str}{cat.suffix}"


def _assemble_skills_section(
    section: SkillsSection,
    selection: ContentSelection,
) -> str | None:
    """Assemble the skills section with reordered skills."""
    # Skills section is always pinned in the plan, but handle optional too
    if section.tag_type == "optional":
        sd = selection.find_section(section.id)
        if sd is None or not sd.include:
            return None

    def _assemble(cat: SkillCategory) -> str | None:
        cat_dec = selection.find_skill_category(cat.name)
        return _assemble_skill_category(cat, cat_dec)

    is_pinned = section.tag_type == "pinned"
    assembled_cats = _assemble_with_interstitials(
        section.categories,
        section.interstitial,
        _assemble,
        keep_trailing_pending=is_pinned,
    )

    # If all categories were empty, omit optional sections entirely.
    # Pinned sections keep their header even with no categories.
    if not assembled_cats and not is_pinned:
        return None

    # Trailing interstitial (after last category)
    trailing = _get_interstitial(section.interstitial, len(section.categories))
    if trailing is not None:
        assembled_cats.append(trailing)

    return "\n".join(assembled_cats)


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------


def assemble_tex(
    parsed: ParsedResume,
    selection: ContentSelection,
) -> str:
    """Assemble a complete .tex document from parsed resume + selections.

    Parameters
    ----------
    parsed:
        The structured representation of the tagged master resume.
    selection:
        The LLM's content selection decisions.

    Returns:
    -------
    str
        A complete LaTeX document ready for compilation.
    """
    parts: list[str] = []

    # 1. Preamble
    parts.append(parsed.preamble)

    # 2. Header
    parts.append(parsed.header)

    # 3. Sections
    def _assemble_section(section: ResumeSection | SkillsSection) -> str | None:
        if isinstance(section, SkillsSection):
            return _assemble_skills_section(section, selection)
        section_dec = selection.find_section(section.id)
        return _assemble_regular_section(section, section_dec)

    assembled_sections = _assemble_with_interstitials(
        parsed.sections,
        parsed.interstitial,
        _assemble_section,
    )

    if assembled_sections:
        parts.extend(assembled_sections)

    # Trailing interstitial after last section
    trailing = _get_interstitial(parsed.interstitial, len(parsed.sections))
    if trailing is not None:
        parts.append(trailing)

    # 4. Postamble
    parts.append(parsed.postamble)

    tex = "\n".join(parts)

    logger.info("Assembled .tex document (%d chars)", len(tex))
    return tex
