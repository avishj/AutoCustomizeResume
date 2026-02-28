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
    for sd in selection.sections:
        if sd.id == section_id:
            return sd
    return None


def _item_decision(
    section_dec: SectionDecision, item_id: str
) -> ItemDecision | None:
    """Find the ItemDecision for *item_id* within a section decision."""
    for itd in section_dec.items:
        if itd.id == item_id:
            return itd
    return None


def _skill_cat_decision(
    selection: ContentSelection, cat_name: str
) -> SkillCategoryDecision | None:
    """Find the SkillCategoryDecision for *cat_name*, or None."""
    for scd in selection.skill_categories:
        if scd.name == cat_name:
            return scd
    return None


def _bullet_text(bullet: Bullet, item_dec: ItemDecision | None) -> str:
    """Return the text for *bullet*, applying edited_text if present."""
    if item_dec is None:
        return bullet.text
    for bd in item_dec.bullets:
        if bd.id == bullet.id and bd.edited_text:
            return bd.edited_text
    return bullet.text


# ---------------------------------------------------------------------------
# Interstitial helpers
# ---------------------------------------------------------------------------

def _get_interstitial(
    interstitial: list[tuple[int, str]], position: int
) -> str | None:
    """Return interstitial content for the given *position*, or None."""
    for pos, text in interstitial:
        if pos == position:
            return text
    return None


# ---------------------------------------------------------------------------
# Item-level assembly
# ---------------------------------------------------------------------------

def _is_bullet_included(
    bullet: Bullet, item_dec: ItemDecision | None
) -> bool:
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
    logger.warning(
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
    included_bullets: list[str] = []
    for idx, bullet in enumerate(item.bullets):
        # Interstitial before this bullet
        inter = _get_interstitial(item.interstitial, idx)
        bullet_included = _is_bullet_included(bullet, item_dec)
        if bullet_included:
            if inter is not None:
                included_bullets.append(inter)
            included_bullets.append(_bullet_text(bullet, item_dec))

    # Trailing interstitial (after last bullet)
    trailing = _get_interstitial(item.interstitial, len(item.bullets))

    # If item has bullets defined but none survived, skip the item entirely
    if item.bullets and not included_bullets:
        return None

    parts: list[str] = []
    parts.append(item.heading_lines)
    if included_bullets:
        parts.extend(included_bullets)
    if trailing is not None and included_bullets:
        parts.append(trailing)

    return "\n".join(parts)
