"""Integration tests for the resume parser (fixture-based)."""

from __future__ import annotations

import warnings as _warnings
from pathlib import Path

from autocustomizeresume.models import (
    ParsedResume,
    ResumeSection,
    SkillsSection,
)
from autocustomizeresume.parser import parse_resume

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


import pytest


@pytest.fixture
def sample_resume() -> ParsedResume:
    return parse_resume(_load_fixture("sample_tagged.tex"))


# ---------------------------------------------------------------------------
# Full fixture parse — structural & content validation
# ---------------------------------------------------------------------------


class TestSampleFixtureParse:
    """Parse the sample fixture and verify the entire tree in a few tests."""

    def test_structural_split(self, sample_resume: ParsedResume):
        """Preamble, header, and postamble are correctly separated."""
        assert r"\documentclass" in sample_resume.preamble
        assert sample_resume.preamble.rstrip().endswith(r"\begin{document}")
        assert "Jane Doe" in sample_resume.header
        assert "%%% BEGIN" not in sample_resume.header
        assert r"\end{document}" in sample_resume.postamble

    def test_sections_and_items(self, sample_resume: ParsedResume):
        """All sections, items, and bullets are parsed with correct IDs and types."""
        types = [(s.tag_type, s.id) for s in sample_resume.sections]
        assert types == [
            ("pinned", "education"),
            ("optional", "experience"),
            ("optional", "projects"),
            ("pinned", "skills"),
        ]
        # Education: pinned item with 1 bullet, optional item with 0 bullets
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        assert [(i.id, i.tag_type, len(i.bullets)) for i in edu.items] == [
            ("mit", "pinned", 1),
            ("state-u", "optional", 0),
        ]
        # Experience: items with bullets preserving ids and tag types
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        assert [(b.id, b.tag_type) for b in exp.items[0].bullets] == [
            ("acme-1", "optional"),
            ("acme-2", "optional"),
            ("acme-3", "pinned"),
        ]
        # Heading content is preserved
        assert r"\resumeSubheading" in exp.items[0].heading_lines
        # Skills section has correct type
        assert isinstance(sample_resume.sections[3], SkillsSection)

    def test_skills_categories(self, sample_resume: ParsedResume):
        """Skill categories parse names, display names, skills list, prefix/suffix."""
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        names = [c.name for c in skills.categories]
        assert names == ["languages", "cloud", "frameworks"]
        # Display name and LaTeX-escaped display name
        assert skills.categories[0].display_name == "Languages"
        assert skills.categories[1].display_name == r"Cloud \& Infra"
        # Skills are parsed as list
        assert "Python" in skills.categories[0].skills
        assert len(skills.categories[0].skills) > 1
        # Prefix/suffix structure
        assert skills.categories[0].prefix.startswith(r"\textbf{")
        # Last category should not have trailing \\
        assert "\\\\" not in skills.categories[-1].suffix

    def test_interstitial_preserved(self, sample_resume: ParsedResume):
        """Interstitial content (section headers, list wrappers) is captured."""
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        section_text = " ".join(t for _, t in edu.interstitial)
        assert (
            r"\section{Education}" in section_text
            or r"\resumeSubHeadingListStart" in section_text
        )

        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        item_text = " ".join(t for _, t in acme.interstitial)
        assert (
            r"\resumeItemListStart" in acme.heading_lines
            or r"\resumeItemListStart" in item_text
        )


# ---------------------------------------------------------------------------
# Fixture-dependent error case
# ---------------------------------------------------------------------------


def test_valid_tags_no_warning():
    """The sample fixture should produce no warnings."""
    with _warnings.catch_warnings():
        _warnings.simplefilter("error")
        # Re-parse — if any warning fires, this will raise
        parse_resume(_load_fixture("sample_tagged.tex"))
