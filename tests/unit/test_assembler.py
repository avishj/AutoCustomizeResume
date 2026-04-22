# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the LaTeX assembler."""

from __future__ import annotations

import pytest

from autocustomizeresume.assembler import (
    _assemble_item,
    _assemble_regular_section,
    _assemble_skill_category,
    _assemble_skills_section,
    _bullet_text,
    _is_bullet_included,
)
from autocustomizeresume.models import (
    Bullet,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
    TagType,
)
from autocustomizeresume.schemas import (
    BulletDecision,
    ContentSelection,
    ItemDecision,
    SectionDecision,
    SkillCategoryDecision,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers for building test data
# ---------------------------------------------------------------------------


def _make_bullet(
    tag_type: TagType = "optional",
    bullet_id: str = "b1",
    text: str = r"\resumeItem{Did something.}",
) -> Bullet:
    return Bullet(tag_type=tag_type, id=bullet_id, text=text)


def _make_item(
    tag_type: TagType = "optional",
    item_id: str = "it1",
    **overrides,
) -> ResumeItem:
    return ResumeItem(
        tag_type=tag_type,
        id=item_id,
        heading_lines=overrides.get(
            "heading",
            r"\resumeSubheading{Co}{2024}{Role}{City}",
        ),
        bullets=overrides.get("bullets") or [],
        interstitial=overrides.get("interstitial") or [],
        compact_heading=overrides.get("compact_heading"),
    )


def _make_item_decision(
    item_id: str = "it1",
    include: bool = True,
    score: int = 50,
    bullets: list[BulletDecision] | None = None,
) -> ItemDecision:
    return ItemDecision(
        id=item_id, include=include, relevance_score=score, bullets=bullets or []
    )


def _make_section_decision(
    section_id: str = "s1",
    include: bool = True,
    items: list[ItemDecision] | None = None,
) -> SectionDecision:
    return SectionDecision(id=section_id, include=include, items=items or [])


def _make_selection(
    sections: list[SectionDecision] | None = None,
    skill_cats: list[SkillCategoryDecision] | None = None,
) -> ContentSelection:
    return ContentSelection(sections=sections or [], skill_categories=skill_cats or [])


# ---------------------------------------------------------------------------
# Bullet inclusion & text
# ---------------------------------------------------------------------------


class TestBulletBehavior:
    def test_pinned_always_included_regardless_of_decision(self):
        b = _make_bullet(tag_type="pinned")
        assert _is_bullet_included(b, None) is True

    def test_optional_follows_decision(self):
        b = _make_bullet(bullet_id="b1")
        included = _make_item_decision(bullets=[BulletDecision(id="b1", include=True)])
        excluded = _make_item_decision(bullets=[BulletDecision(id="b1", include=False)])
        assert _is_bullet_included(b, included) is True
        assert _is_bullet_included(b, excluded) is False
        # No decision defaults to included
        assert _is_bullet_included(b, None) is True

    def test_edited_text_replaces_original(self):
        b = _make_bullet(bullet_id="b1", text="original")
        itd = _make_item_decision(
            bullets=[BulletDecision(id="b1", include=True, edited_text="edited")]
        )
        assert _bullet_text(b, itd) == "edited"

    def test_original_text_when_no_edit(self):
        b = _make_bullet(bullet_id="b1", text="original")
        # No decision at all
        assert _bullet_text(b, None) == "original"
        # Empty edited_text
        itd = _make_item_decision(
            bullets=[BulletDecision(id="b1", include=True, edited_text="")]
        )
        assert _bullet_text(b, itd) == "original"
        # No matching bullet decision
        itd2 = _make_item_decision(
            bullets=[BulletDecision(id="other", include=True, edited_text="edited")]
        )
        assert _bullet_text(b, itd2) == "original"


# ---------------------------------------------------------------------------
# Item assembly
# ---------------------------------------------------------------------------


class TestAssembleItem:
    def test_pinned_item_always_included(self):
        item = _make_item(tag_type="pinned", heading="heading")
        assert _assemble_item(item, None) == "heading"

    def test_optional_item_excluded_without_decision_or_when_excluded(self):
        item = _make_item(tag_type="optional", item_id="it1")
        assert _assemble_item(item, None) is None
        assert (
            _assemble_item(item, _make_item_decision(item_id="it1", include=False))
            is None
        )

    def test_optional_included_with_bullets_and_interstitial(self):
        item = _make_item(
            item_id="it1",
            heading="heading",
            bullets=[_make_bullet(bullet_id="b1", text="bullet1")],
            interstitial=[(0, "\\resumeItemListStart"), (1, "\\resumeItemListEnd")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[BulletDecision(id="b1", include=True)],
        )
        result = _assemble_item(item, itd)
        assert result is not None
        assert "heading" in result
        assert "bullet1" in result
        assert "\\resumeItemListStart" in result
        assert "\\resumeItemListEnd" in result

    @pytest.mark.parametrize(
        ("tag_type", "expect_none"),
        [("optional", True), ("pinned", False)],
    )
    def test_all_bullets_excluded_drops_optional_keeps_pinned(
        self, tag_type: TagType, expect_none: bool
    ):
        item = _make_item(
            tag_type=tag_type,
            item_id="it1",
            heading="heading",
            bullets=[_make_bullet(bullet_id="b1", text="bullet1")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[BulletDecision(id="b1", include=False)],
        )
        result = _assemble_item(item, itd)
        if expect_none:
            assert result is None
        else:
            assert result is not None
            assert "heading" in result
            assert "bullet1" not in result

    def test_first_bullet_excluded_preserves_interstitial(self):
        item = _make_item(
            item_id="it1",
            heading="heading",
            bullets=[
                _make_bullet(bullet_id="b1", text="bullet1"),
                _make_bullet(bullet_id="b2", text="bullet2"),
            ],
            interstitial=[(0, "\\resumeItemListStart"), (2, "\\resumeItemListEnd")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[
                BulletDecision(id="b1", include=False),
                BulletDecision(id="b2", include=True),
            ],
        )
        result = _assemble_item(item, itd)
        assert result is not None
        assert "\\resumeItemListStart" in result
        assert "bullet2" in result
        assert "bullet1" not in result


# ---------------------------------------------------------------------------
# Skill category assembly
# ---------------------------------------------------------------------------


class TestAssembleRegularSectionPinned:
    """Tests for pinned sections that survive even when all items are excluded."""

    def test_pinned_section_empty_items_returns_header(self):
        """A pinned section with all items excluded still emits its header."""
        section = ResumeSection(
            tag_type="pinned",
            id="edu",
            items=[
                _make_item(tag_type="optional", item_id="it1", heading="Item1"),
            ],
            interstitial=[(0, r"\section{Education}")],
        )
        sec_dec = _make_section_decision(
            section_id="edu",
            include=True,
            items=[
                _make_item_decision(item_id="it1", include=False),
            ],
        )
        result = _assemble_regular_section(section, sec_dec)
        assert result is not None
        assert r"\section{Education}" in result
        assert "Item1" not in result

    def test_optional_section_empty_items_returns_none(self):
        """An optional section with all items excluded returns None."""
        section = ResumeSection(
            tag_type="optional",
            id="proj",
            items=[
                _make_item(tag_type="optional", item_id="it1", heading="Item1"),
            ],
            interstitial=[(0, r"\section{Projects}")],
        )
        sec_dec = _make_section_decision(
            section_id="proj",
            include=True,
            items=[
                _make_item_decision(item_id="it1", include=False),
            ],
        )
        result = _assemble_regular_section(section, sec_dec)
        assert result is None


class TestAssembleSkillCategory:
    def test_with_decision(self):
        cat = SkillCategory(
            name="lang",
            display_name="Languages",
            skills=["Python", "Java", "Go"],
            prefix=r"\textbf{Languages}{: ",
            suffix=r".} \\",
        )
        dec = SkillCategoryDecision(name="lang", skills=["Go", "Python"])
        result = _assemble_skill_category(cat, dec)
        assert result == r"\textbf{Languages}{: Go, Python.} \\"

    def test_without_decision_uses_original(self):
        cat = SkillCategory(
            name="lang",
            display_name="Languages",
            skills=["Python", "Java"],
            prefix=r"\textbf{Languages}{: ",
            suffix=r".}",
        )
        result = _assemble_skill_category(cat, None)
        assert result == r"\textbf{Languages}{: Python, Java.}"

    def test_empty_skills_returns_none(self):
        cat = SkillCategory(
            name="lang",
            display_name="Languages",
            skills=["Python"],
            prefix="pre",
            suffix="suf",
        )
        dec = SkillCategoryDecision(name="lang", skills=[])
        assert _assemble_skill_category(cat, dec) is None


class TestAssembleSkillsSectionPinned:
    """Tests for pinned skills sections with all categories emptied."""

    def test_pinned_skills_section_empty_cats_returns_header(self):
        """A pinned skills section with all categories empty still emits its header."""
        section = SkillsSection(
            tag_type="pinned",
            id="skills",
            categories=[
                SkillCategory(
                    name="lang",
                    display_name="Languages",
                    skills=["Python"],
                    prefix="pre",
                    suffix="suf",
                ),
            ],
            interstitial=[(0, r"\section{Technical Skills}")],
        )
        sel = _make_selection(
            skill_cats=[
                SkillCategoryDecision(name="lang", skills=[]),
            ]
        )
        result = _assemble_skills_section(section, sel)
        assert result is not None
        assert r"\section{Technical Skills}" in result

    def test_optional_skills_section_empty_cats_returns_none(self):
        """An optional skills section with all categories empty returns None."""
        section = SkillsSection(
            tag_type="optional",
            id="skills",
            categories=[
                SkillCategory(
                    name="lang",
                    display_name="Languages",
                    skills=["Python"],
                    prefix="pre",
                    suffix="suf",
                ),
            ],
            interstitial=[(0, r"\section{Technical Skills}")],
        )
        sel = _make_selection(
            sections=[_make_section_decision(section_id="skills", include=True)],
            skill_cats=[SkillCategoryDecision(name="lang", skills=[])],
        )
        result = _assemble_skills_section(section, sel)
        assert result is None


# ---------------------------------------------------------------------------
# Compact heading fallback
# ---------------------------------------------------------------------------


class TestCompactHeadingAssembly:
    def test_compact_used_when_all_bullets_excluded(self):
        """When all bullets are excluded, compact_heading is emitted."""
        compact = r"\resumeProjectHeading{\textbf{EY} $|$ \emph{SAP}}{2022}"
        item = _make_item(
            item_id="ey",
            bullets=[_make_bullet(bullet_id="ey-1")],
            interstitial=[(0, r"\resumeItemListStart"), (1, r"\resumeItemListEnd")],
            compact_heading=compact,
        )
        dec = _make_item_decision(
            item_id="ey",
            bullets=[
                BulletDecision(id="ey-1", include=False),
            ],
        )
        result = _assemble_item(item, dec)
        assert result == compact

    def test_compact_ignored_when_bullets_included(self):
        """When bullets survive, full heading + bullets are used, not compact."""
        compact = r"\resumeProjectHeading{\textbf{EY}}{2022}"
        item = _make_item(
            item_id="ey",
            bullets=[_make_bullet(bullet_id="ey-1")],
            interstitial=[(0, r"\resumeItemListStart"), (1, r"\resumeItemListEnd")],
            compact_heading=compact,
        )
        dec = _make_item_decision(
            item_id="ey",
            bullets=[
                BulletDecision(id="ey-1", include=True),
            ],
        )
        result = _assemble_item(item, dec)
        assert result is not None
        assert r"\resumeSubheading" in result
        assert r"\resumeProjectHeading" not in result

    def test_no_compact_optional_item_excluded_when_no_bullets(self):
        """Without compact_heading, optional item with 0 bullets returns None."""
        item = _make_item(
            item_id="ey",
            bullets=[_make_bullet(bullet_id="ey-1")],
            interstitial=[(0, r"\resumeItemListStart"), (1, r"\resumeItemListEnd")],
        )
        dec = _make_item_decision(
            item_id="ey",
            bullets=[
                BulletDecision(id="ey-1", include=False),
            ],
        )
        result = _assemble_item(item, dec)
        assert result is None

    def test_compact_on_pinned_item_all_optional_bullets_excluded(self):
        """Pinned item with compact_heading uses it when all bullets excluded."""
        compact = r"\resumeProjectHeading{\textbf{Addverb}}{2023 -- 2024}"
        item = _make_item(
            tag_type="pinned",
            item_id="addverb",
            bullets=[_make_bullet(bullet_id="addverb-1")],
            interstitial=[(0, r"\resumeItemListStart"), (1, r"\resumeItemListEnd")],
            compact_heading=compact,
        )
        dec = _make_item_decision(
            item_id="addverb",
            bullets=[
                BulletDecision(id="addverb-1", include=False),
            ],
        )
        result = _assemble_item(item, dec)
        assert result == compact
