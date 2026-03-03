"""LaTeX assembler: stitches selected content back into a .tex file.

Takes a ParsedResume and ContentSelection, produces a complete
LaTeX document with only the selected items included.
"""

from __future__ import annotations

import logging

from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.schemas import (
    ContentSelection,
    ItemDecision,
    SectionDecision,
    SkillCategoryDecision,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _section_decision(
    selection: ContentSelection, section_id: str
) -> SectionDecision | None:
    """Find the SectionDecision for *section_id*, or None."""
    return next((sd for sd in selection.sections if sd.id == section_id), None)


def _item_decision(section_dec: SectionDecision, item_id: str) -> ItemDecision | None:
    """Find the ItemDecision for *item_id* within a section decision."""
    return next((itd for itd in section_dec.items if itd.id == item_id), None)


def _skill_cat_decision(
    selection: ContentSelection, cat_name: str
) -> SkillCategoryDecision | None:
    """Find the SkillCategoryDecision for *cat_name*, or None."""
    return next(
        (scd for scd in selection.skill_categories if scd.name == cat_name),
        None,
    )


def _bullet_text(bullet: Bullet, item_dec: ItemDecision | None) -> str:
    """Return the text for *bullet*, applying edited_text if present."""
    if item_dec is not None:
        bd = next((b for b in item_dec.bullets if b.id == bullet.id), None)
        if bd is not None and bd.edited_text:
            return bd.edited_text
    return bullet.text


# ---------------------------------------------------------------------------
# Interstitial helpers
# ---------------------------------------------------------------------------


def _get_interstitial(interstitial: list[tuple[int, str]], position: int) -> str | None:
    """Return interstitial content for the given *position*, or None."""
    return next((text for pos, text in interstitial if pos == position), None)


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
    if item.tag_type == "optional":
        if item_dec is None or not item_dec.include:
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

    # If item has bullets defined but none survived, skip *optional* items.
    # Pinned items always keep their heading even with zero bullets.
    if item.bullets and not included_bullets and item.tag_type == "optional":
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
    if section.tag_type == "optional":
        if section_dec is None or not section_dec.include:
            return None

    assembled_items: list[str] = []
    pending_interstitials: list[str] = []
    for idx, item in enumerate(section.items):
        item_dec = None
        if section_dec is not None:
            item_dec = _item_decision(section_dec, item.id)

        # Collect interstitial at this position
        inter = _get_interstitial(section.interstitial, idx)
        if inter is not None:
            pending_interstitials.append(inter)

        assembled = _assemble_item(item, item_dec)
        if assembled is not None:
            # Flush pending interstitials before this item
            assembled_items.extend(pending_interstitials)
            pending_interstitials = []
            assembled_items.append(assembled)

    # If all items were excluded, omit optional sections entirely.
    # Pinned sections keep their header even with no items.
    if not assembled_items and section.tag_type == "optional":
        return None

    # Flush any remaining interstitials (for pinned sections with no items)
    if pending_interstitials:
        assembled_items.extend(pending_interstitials)

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
    if cat_dec is not None:
        skills = cat_dec.skills
    else:
        skills = cat.skills

    if not skills:
        return None

    skills_str = ", ".join(skills)
    return f"{cat.prefix}{skills_str}{cat.suffix}"


def _assemble_skills_section(
    section: SkillsSection,
    selection: ContentSelection,
) -> str | None:
    """Assemble the skills section with reordered skills."""
    # Skills section is always pinned in the plan, but handle optional too
    if section.tag_type == "optional":
        sd = _section_decision(selection, section.id)
        if sd is None or not sd.include:
            return None

    assembled_cats: list[str] = []
    pending_interstitials: list[str] = []
    for idx, cat in enumerate(section.categories):
        cat_dec = _skill_cat_decision(selection, cat.name)

        inter = _get_interstitial(section.interstitial, idx)
        if inter is not None:
            pending_interstitials.append(inter)

        assembled_cat = _assemble_skill_category(cat, cat_dec)
        if assembled_cat is not None:
            assembled_cats.extend(pending_interstitials)
            pending_interstitials = []
            assembled_cats.append(assembled_cat)

    # If all categories were empty, omit optional sections entirely.
    # Pinned sections keep their header even with no categories.
    if not assembled_cats and section.tag_type == "optional":
        return None

    # Flush any remaining interstitials (for pinned sections with no categories)
    if pending_interstitials:
        assembled_cats.extend(pending_interstitials)

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

    Returns
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
    assembled_sections: list[str] = []
    pending_interstitials: list[str] = []
    for idx, section in enumerate(parsed.sections):
        if isinstance(section, SkillsSection):
            assembled = _assemble_skills_section(section, selection)
        else:
            section_dec = _section_decision(selection, section.id)
            assembled = _assemble_regular_section(section, section_dec)

        inter = _get_interstitial(parsed.interstitial, idx)
        if inter is not None:
            pending_interstitials.append(inter)

        if assembled is not None:
            assembled_sections.extend(pending_interstitials)
            pending_interstitials = []
            assembled_sections.append(assembled)

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
