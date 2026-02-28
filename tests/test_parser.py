"""Tests for the resume parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.parser import ParseError, parse_resume

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def sample_resume() -> ParsedResume:
    return parse_resume(_load_fixture("sample_tagged.tex"))


@pytest.fixture
def minimal_resume() -> ParsedResume:
    return parse_resume(_load_fixture("minimal_tagged.tex"))


# ---------------------------------------------------------------------------
# Preamble / header / postamble extraction
# ---------------------------------------------------------------------------

class TestStructuralSplit:

    def test_preamble_contains_documentclass(self, sample_resume: ParsedResume):
        assert r"\documentclass" in sample_resume.preamble

    def test_preamble_ends_with_begin_document(self, sample_resume: ParsedResume):
        assert sample_resume.preamble.rstrip().endswith(r"\begin{document}")

    def test_header_contains_name(self, sample_resume: ParsedResume):
        assert "Jane Doe" in sample_resume.header

    def test_header_has_no_section_tags(self, sample_resume: ParsedResume):
        assert "%%% BEGIN" not in sample_resume.header

    def test_postamble_contains_end_document(self, sample_resume: ParsedResume):
        assert r"\end{document}" in sample_resume.postamble


# ---------------------------------------------------------------------------
# Section-level parsing
# ---------------------------------------------------------------------------

class TestSections:

    def test_section_count(self, sample_resume: ParsedResume):
        assert len(sample_resume.sections) == 4

    def test_section_types(self, sample_resume: ParsedResume):
        types = [(s.tag_type, s.id) for s in sample_resume.sections]
        assert types == [
            ("pinned", "education"),
            ("optional", "experience"),
            ("optional", "projects"),
            ("pinned", "skills"),
        ]

    def test_pinned_section(self, sample_resume: ParsedResume):
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        assert edu.tag_type == "pinned"

    def test_optional_section(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        assert exp.tag_type == "optional"

    def test_skills_section_type(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)


# ---------------------------------------------------------------------------
# Item-level parsing
# ---------------------------------------------------------------------------

class TestItems:

    def test_education_items(self, sample_resume: ParsedResume):
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        assert len(edu.items) == 2
        assert edu.items[0].id == "mit"
        assert edu.items[0].tag_type == "pinned"
        assert edu.items[1].id == "state-u"
        assert edu.items[1].tag_type == "optional"

    def test_experience_items(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        assert len(exp.items) == 2
        assert exp.items[0].id == "acme"
        assert exp.items[1].id == "widgets"

    def test_item_heading_preserved(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        assert "Acme Corp" in acme.heading_lines
        assert r"\resumeSubheading" in acme.heading_lines

    def test_item_without_bullets(self, sample_resume: ParsedResume):
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        state_u = edu.items[1]
        assert len(state_u.bullets) == 0
        assert "State University" in state_u.heading_lines


# ---------------------------------------------------------------------------
# Bullet-level parsing
# ---------------------------------------------------------------------------

class TestBullets:

    def test_bullet_count(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        assert len(acme.bullets) == 3

    def test_bullet_ids(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        ids = [b.id for b in acme.bullets]
        assert ids == ["acme-1", "acme-2", "acme-3"]

    def test_pinned_bullet(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        assert acme.bullets[2].tag_type == "pinned"
        assert acme.bullets[2].id == "acme-3"

    def test_optional_bullet(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        assert acme.bullets[0].tag_type == "optional"

    def test_bullet_text_content(self, sample_resume: ParsedResume):
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        assert "REST API" in acme.bullets[0].text
        assert "OAuth 2.0" in acme.bullets[1].text
        assert "p99 latency" in acme.bullets[2].text

    def test_single_bullet_item(self, sample_resume: ParsedResume):
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        mit = edu.items[0]
        assert len(mit.bullets) == 1
        assert mit.bullets[0].id == "mit-1"
        assert "Distributed Systems" in mit.bullets[0].text


# ---------------------------------------------------------------------------
# Skills parsing
# ---------------------------------------------------------------------------

class TestSkills:

    def test_category_count(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        assert len(skills.categories) == 3

    def test_category_names(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        names = [c.name for c in skills.categories]
        assert names == ["languages", "cloud", "frameworks"]

    def test_display_names(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        assert skills.categories[0].display_name == "Languages"
        assert skills.categories[1].display_name == r"Cloud \& Infra"

    def test_skills_list(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        lang = skills.categories[0]
        assert lang.skills == ["Python", "Java", "C++", "Go", "TypeScript", "SQL"]

    def test_skills_prefix_suffix(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        lang = skills.categories[0]
        assert lang.prefix == r"\textbf{Languages}{: "
        assert lang.suffix.startswith(".")

    def test_last_category_no_backslash(self, sample_resume: ParsedResume):
        skills = sample_resume.sections[3]
        assert isinstance(skills, SkillsSection)
        last = skills.categories[-1]
        assert "\\\\" not in last.suffix


# ---------------------------------------------------------------------------
# Interstitial content preservation
# ---------------------------------------------------------------------------

class TestInterstitial:

    def test_section_interstitial(self, sample_resume: ParsedResume):
        """Section header and list wrappers should be in interstitial."""
        edu = sample_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        # There should be interstitial content (section header, list start, etc.)
        all_text = " ".join(t for _, t in edu.interstitial)
        assert r"\section{Education}" in all_text or r"\resumeSubHeadingListStart" in all_text

    def test_item_interstitial(self, sample_resume: ParsedResume):
        """Bullet list wrappers should be in item interstitial."""
        exp = sample_resume.sections[1]
        assert isinstance(exp, ResumeSection)
        acme = exp.items[0]
        all_text = " ".join(t for _, t in acme.interstitial)
        # resumeItemListStart/End should be captured
        assert r"\resumeItemListStart" in acme.heading_lines or r"\resumeItemListStart" in all_text


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestErrors:

    def test_no_begin_document(self):
        with pytest.raises(ParseError, match=r"No \\begin\{document\}"):
            parse_resume(r"\documentclass{article} \section{Foo}")

    def test_unclosed_section(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
"""
        with pytest.raises(ParseError, match="Unclosed section tag"):
            parse_resume(tex)

    def test_unclosed_item(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
    %%% BEGIN:optional:mit
    \resumeSubheading{MIT}{2025}{MS}{MA}
%%% END:pinned:edu
"""
        with pytest.raises(ParseError, match="Unclosed item tag"):
            parse_resume(tex)

    def test_unclosed_bullet(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
    %%% BEGIN:pinned:mit
    \resumeSubheading{MIT}{2025}{MS}{MA}
        %%% BEGIN:optional:mit-1
        \resumeItem{TA for Distributed Systems}
    %%% END:pinned:mit
%%% END:pinned:edu
"""
        with pytest.raises(ParseError, match="Unclosed bullet tag"):
            parse_resume(tex)

    def test_unclosed_skills_tag(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:skills
\section{Skills}
    %%% SKILLS:languages
    \textbf{Languages}{: Python, Java.}
%%% END:pinned:skills
"""
        with pytest.raises(ParseError, match="Unclosed skills tag"):
            parse_resume(tex)

    def test_duplicate_section_ids(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
%%% END:pinned:edu
%%% BEGIN:optional:edu
\section{Education 2}
%%% END:optional:edu
\end{document}
"""
        with pytest.raises(ParseError, match="Duplicate ID 'edu'"):
            parse_resume(tex)

    def test_duplicate_item_ids(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
    %%% BEGIN:pinned:mit
    \resumeSubheading{MIT}{2025}{MS}{MA}
    %%% END:pinned:mit
    %%% BEGIN:optional:mit
    \resumeSubheading{MIT}{2020}{BS}{MA}
    %%% END:optional:mit
%%% END:pinned:edu
\end{document}
"""
        with pytest.raises(ParseError, match="Duplicate ID 'mit'"):
            parse_resume(tex)

    def test_duplicate_bullet_ids(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
    %%% BEGIN:pinned:acme
    \resumeSubheading{Acme}{2025}{SWE}{NY}
        %%% BEGIN:optional:b1
        \resumeItem{Built REST API}
        %%% END:optional:b1
        %%% BEGIN:optional:b1
        \resumeItem{Another bullet with same id}
        %%% END:optional:b1
    %%% END:pinned:acme
%%% END:pinned:exp
\end{document}
"""
        with pytest.raises(ParseError, match="Duplicate ID 'b1'"):
            parse_resume(tex)

    def test_malformed_tag_warns(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:invalid:foo
\section{Education}
%%% END:invalid:foo
\end{document}
"""
        with pytest.warns(UserWarning, match="malformed tag-like comment"):
            parse_resume(tex)

    def test_malformed_tag_missing_id_warns(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned
\section{Education}
\end{document}
"""
        with pytest.warns(UserWarning, match="malformed tag-like comment"):
            parse_resume(tex)

    def test_valid_tags_no_warning(self):
        """The sample fixture should produce no warnings."""
        import warnings as _warnings
        with _warnings.catch_warnings():
            _warnings.simplefilter("error")
            # Re-parse — if any warning fires, this will raise
            parse_resume(_load_fixture("sample_tagged.tex"))


# ---------------------------------------------------------------------------
# Minimal fixture tests
# ---------------------------------------------------------------------------

class TestMinimalFixture:
    """Tests using the minimal single-section fixture."""

    def test_single_section(self, minimal_resume: ParsedResume):
        assert len(minimal_resume.sections) == 1
        assert minimal_resume.sections[0].id == "education"

    def test_single_item(self, minimal_resume: ParsedResume):
        edu = minimal_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        assert len(edu.items) == 1
        assert edu.items[0].id == "mit"

    def test_single_bullet(self, minimal_resume: ParsedResume):
        edu = minimal_resume.sections[0]
        assert isinstance(edu, ResumeSection)
        mit = edu.items[0]
        assert len(mit.bullets) == 1
        assert "Distributed Systems" in mit.bullets[0].text

    def test_header(self, minimal_resume: ParsedResume):
        assert "Test User" in minimal_resume.header

    def test_postamble(self, minimal_resume: ParsedResume):
        assert r"\end{document}" in minimal_resume.postamble


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_section_no_items(self):
        """A section with content but no tagged items."""
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
Some untagged content here.
%%% END:pinned:edu
\end{document}
"""
        result = parse_resume(tex)
        assert len(result.sections) == 1
        edu = result.sections[0]
        assert isinstance(edu, ResumeSection)
        assert len(edu.items) == 0
        # Content should be in interstitial
        all_text = " ".join(t for _, t in edu.interstitial)
        assert "untagged content" in all_text

    def test_section_with_only_pinned_items(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
    %%% BEGIN:pinned:mit
    \resumeSubheading{MIT}{2025}{MS}{MA}
    %%% END:pinned:mit
%%% END:pinned:edu
\end{document}
"""
        result = parse_resume(tex)
        edu = result.sections[0]
        assert isinstance(edu, ResumeSection)
        assert len(edu.items) == 1
        assert edu.items[0].tag_type == "pinned"

    def test_no_tagged_sections(self):
        """Resume with no tags at all — everything is header + postamble."""
        tex = r"""\documentclass{article}
\begin{document}
\section{Education}
Some content
\end{document}
"""
        result = parse_resume(tex)
        assert len(result.sections) == 0
        assert "Education" in result.header or "Education" in result.postamble
