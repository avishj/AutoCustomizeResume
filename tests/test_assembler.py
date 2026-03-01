"""Tests for the LaTeX assembler."""

from __future__ import annotations

from pathlib import Path

import pytest

from autocustomizeresume.assembler import (
    assemble_tex,
    _assemble_item,
    _assemble_regular_section,
    _assemble_skills_section,
    _assemble_skill_category,
    _is_bullet_included,
    _bullet_text,
    _get_interstitial,
    _section_decision,
    _item_decision,
    _skill_cat_decision,
)
from autocustomizeresume.models import (
    Bullet,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.parser import parse_resume
from autocustomizeresume.schemas import (
    BulletDecision,
    ContentSelection,
    ItemDecision,
    SectionDecision,
    SkillCategoryDecision,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


# ---------------------------------------------------------------------------
# Helpers for building test data
# ---------------------------------------------------------------------------


def _make_bullet(
    tag_type: str = "optional",
    bullet_id: str = "b1",
    text: str = r"\resumeItem{Did something.}",
) -> Bullet:
    return Bullet(tag_type=tag_type, id=bullet_id, text=text)


def _make_item(
    tag_type: str = "optional",
    item_id: str = "it1",
    heading: str = r"\resumeSubheading{Co}{2024}{Role}{City}",
    bullets: list[Bullet] | None = None,
    interstitial: list[tuple[int, str]] | None = None,
) -> ResumeItem:
    return ResumeItem(
        tag_type=tag_type,
        id=item_id,
        heading_lines=heading,
        bullets=bullets or [],
        interstitial=interstitial or [],
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
# Lookup helpers
# ---------------------------------------------------------------------------


class TestLookupHelpers:
    def test_section_decision_found(self):
        sd = _make_section_decision(section_id="exp")
        sel = _make_selection(sections=[sd])
        assert _section_decision(sel, "exp") is sd

    def test_section_decision_not_found(self):
        sel = _make_selection()
        assert _section_decision(sel, "exp") is None

    def test_item_decision_found(self):
        itd = _make_item_decision(item_id="acme")
        sd = _make_section_decision(items=[itd])
        assert _item_decision(sd, "acme") is itd

    def test_item_decision_not_found(self):
        sd = _make_section_decision()
        assert _item_decision(sd, "acme") is None

    def test_skill_cat_decision_found(self):
        scd = SkillCategoryDecision(name="lang", skills=["Python"])
        sel = _make_selection(skill_cats=[scd])
        assert _skill_cat_decision(sel, "lang") is scd

    def test_skill_cat_decision_not_found(self):
        sel = _make_selection()
        assert _skill_cat_decision(sel, "lang") is None


# ---------------------------------------------------------------------------
# Interstitial
# ---------------------------------------------------------------------------


class TestInterstitial:
    def test_found(self):
        inter = [(0, "before"), (2, "after")]
        assert _get_interstitial(inter, 0) == "before"
        assert _get_interstitial(inter, 2) == "after"

    def test_not_found(self):
        assert _get_interstitial([(0, "x")], 1) is None

    def test_empty(self):
        assert _get_interstitial([], 0) is None


# ---------------------------------------------------------------------------
# Bullet inclusion
# ---------------------------------------------------------------------------


class TestBulletInclusion:
    def test_pinned_always_included(self):
        b = _make_bullet(tag_type="pinned")
        assert _is_bullet_included(b, None) is True

    def test_optional_included_by_decision(self):
        b = _make_bullet(bullet_id="b1")
        itd = _make_item_decision(
            bullets=[
                BulletDecision(id="b1", include=True),
            ]
        )
        assert _is_bullet_included(b, itd) is True

    def test_optional_excluded_by_decision(self):
        b = _make_bullet(bullet_id="b1")
        itd = _make_item_decision(
            bullets=[
                BulletDecision(id="b1", include=False),
            ]
        )
        assert _is_bullet_included(b, itd) is False

    def test_optional_no_decision_defaults_true(self):
        b = _make_bullet(bullet_id="b1")
        assert _is_bullet_included(b, None) is True


class TestBulletText:
    def test_original_when_no_decision(self):
        b = _make_bullet(text="original")
        assert _bullet_text(b, None) == "original"

    def test_original_when_edited_text_empty(self):
        b = _make_bullet(bullet_id="b1", text="original")
        itd = _make_item_decision(
            bullets=[
                BulletDecision(id="b1", include=True, edited_text=""),
            ]
        )
        assert _bullet_text(b, itd) == "original"

    def test_edited_text_when_present(self):
        b = _make_bullet(bullet_id="b1", text="original")
        itd = _make_item_decision(
            bullets=[
                BulletDecision(id="b1", include=True, edited_text="edited"),
            ]
        )
        assert _bullet_text(b, itd) == "edited"

    def test_original_when_no_matching_bullet_decision(self):
        b = _make_bullet(bullet_id="b1", text="original")
        itd = _make_item_decision(
            bullets=[
                BulletDecision(id="other", include=True, edited_text="edited"),
            ]
        )
        assert _bullet_text(b, itd) == "original"


# ---------------------------------------------------------------------------
# Item assembly
# ---------------------------------------------------------------------------


class TestAssembleItem:
    def test_pinned_item_always_included(self):
        item = _make_item(tag_type="pinned", heading="heading")
        result = _assemble_item(item, None)
        assert result == "heading"

    def test_optional_excluded_when_no_decision(self):
        item = _make_item(tag_type="optional")
        assert _assemble_item(item, None) is None

    def test_optional_excluded_by_decision(self):
        item = _make_item(item_id="it1")
        itd = _make_item_decision(item_id="it1", include=False)
        assert _assemble_item(item, itd) is None

    def test_optional_included_with_bullets(self):
        item = _make_item(
            item_id="it1",
            heading="heading",
            bullets=[_make_bullet(bullet_id="b1", text="bullet1")],
            interstitial=[(0, "\\resumeItemListStart"), (1, "\\resumeItemListEnd")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[
                BulletDecision(id="b1", include=True),
            ],
        )
        result = _assemble_item(item, itd)
        assert "heading" in result
        assert "bullet1" in result
        assert "\\resumeItemListStart" in result
        assert "\\resumeItemListEnd" in result

    def test_all_bullets_excluded_drops_item(self):
        item = _make_item(
            item_id="it1",
            heading="heading",
            bullets=[_make_bullet(bullet_id="b1", text="bullet1")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[
                BulletDecision(id="b1", include=False),
            ],
        )
        assert _assemble_item(item, itd) is None

    def test_pinned_item_all_bullets_excluded_keeps_heading(self):
        """Pinned items should keep their heading even when all bullets are excluded."""
        item = _make_item(
            tag_type="pinned",
            item_id="it1",
            heading="heading",
            bullets=[_make_bullet(bullet_id="b1", text="bullet1")],
        )
        itd = _make_item_decision(
            item_id="it1",
            include=True,
            bullets=[
                BulletDecision(id="b1", include=False),
            ],
        )
        result = _assemble_item(item, itd)
        assert result is not None
        assert "heading" in result
        assert "bullet1" not in result

    def test_item_without_bullets(self):
        item = _make_item(tag_type="optional", item_id="it1", heading="heading only")
        itd = _make_item_decision(item_id="it1", include=True)
        result = _assemble_item(item, itd)
        assert result == "heading only"

    def test_first_bullet_excluded_preserves_interstitial(self):
        """Interstitial at position 0 should survive even if bullet 0 is excluded."""
        item = _make_item(
            item_id="it1",
            heading="heading",
            bullets=[
                _make_bullet(bullet_id="b1", text="bullet1"),
                _make_bullet(bullet_id="b2", text="bullet2"),
            ],
            interstitial=[
                (0, "\\resumeItemListStart"),
                (2, "\\resumeItemListEnd"),
            ],
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
        assert "\\resumeItemListStart" in result
        assert "bullet2" in result
        assert "bullet1" not in result
        assert "\\resumeItemListEnd" in result


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
# Full assembler (fixture-based)
# ---------------------------------------------------------------------------


class TestAssembleTexFixture:
    @pytest.fixture
    def parsed(self):
        return parse_resume(_load_fixture("sample_tagged.tex"))

    def test_include_all(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": True,
                                "relevance_score": 60,
                                "bullets": [
                                    {
                                        "id": "widgets-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                        ],
                    },
                    {
                        "id": "projects",
                        "include": True,
                        "items": [
                            {
                                "id": "chatbot",
                                "include": True,
                                "relevance_score": 50,
                                "bullets": [
                                    {
                                        "id": "chatbot-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                        ],
                    },
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python", "Java", "C++"]},
                    {"name": "cloud", "skills": ["AWS", "Docker"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Jane Doe" in result
        assert "MIT" in result
        assert "Acme Corp" in result
        assert "Widgets Inc" in result
        assert "Chatbot" in result
        assert r"\begin{document}" in result
        assert r"\end{document}" in result

    def test_exclude_section(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": True,
                                "relevance_score": 60,
                                "bullets": [
                                    {
                                        "id": "widgets-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Acme Corp" in result
        assert "Chatbot" not in result

    def test_exclude_item(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Acme Corp" in result
        assert "Widgets" not in result

    def test_exclude_bullet(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": False,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "REST API" in result
        assert "OAuth" not in result
        # Pinned bullet acme-3 always present
        assert "p99 latency" in result

    def test_edited_text_substitution(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": r"\resumeItem{Built a RESTful microservice.}",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "RESTful microservice" in result
        assert "10k requests" not in result

    def test_skill_reordering(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": True,
                                "relevance_score": 80,
                                "bullets": [
                                    {
                                        "id": "acme-1",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Go", "Python"]},
                    {"name": "cloud", "skills": ["Kubernetes", "AWS"]},
                    {"name": "frameworks", "skills": ["React"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Go, Python" in result
        assert "Kubernetes, AWS" in result
        # Original had 4 frameworks, now only React
        assert "Spring Boot" not in result

    def test_pinned_section_always_present(self, parsed):
        """Education (pinned) appears even with empty selection."""
        selection = ContentSelection.from_dict(
            {
                "sections": [],
                "skill_categories": [],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Education" in result
        assert "MIT" in result

    def test_empty_section_omitted(self, parsed):
        """Section with all items excluded is omitted entirely."""
        selection = ContentSelection.from_dict(
            {
                "sections": [
                    {
                        "id": "experience",
                        "include": True,
                        "items": [
                            {
                                "id": "acme",
                                "include": False,
                                "relevance_score": 0,
                                "bullets": [],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 0,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Experience" not in result
