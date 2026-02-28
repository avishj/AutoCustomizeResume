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
