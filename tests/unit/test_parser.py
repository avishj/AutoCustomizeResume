# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the resume parser."""

from __future__ import annotations

import pytest

from autocustomizeresume.models import (
    ResumeSection,
)
from autocustomizeresume.parser import ParseError, parse_resume

pytestmark = pytest.mark.unit


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

    def test_stray_end_in_header(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% END:pinned:foo
%%% BEGIN:pinned:edu
\section{Education}
%%% END:pinned:edu
\end{document}
"""
        with pytest.raises(ParseError, match="Unexpected END tag before any section"):
            parse_resume(tex)

    def test_stray_end_between_sections(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
%%% END:pinned:edu
%%% END:optional:ghost
%%% BEGIN:optional:exp
\section{Experience}
%%% END:optional:exp
\end{document}
"""
        with pytest.raises(ParseError, match="Unexpected END tag between sections"):
            parse_resume(tex)

    def test_stray_end_outside_item(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:edu
\section{Education}
    %%% END:pinned:ghost
    %%% BEGIN:pinned:mit
    \resumeSubheading{MIT}{2025}{MS}{MA}
    %%% END:pinned:mit
%%% END:pinned:edu
\end{document}
"""
        with pytest.raises(ParseError, match="Unexpected END tag outside any item"):
            parse_resume(tex)

    def test_stray_end_outside_bullet(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
    %%% BEGIN:pinned:acme
    \resumeSubheading{Acme}{2025}{SWE}{NY}
        %%% END:optional:ghost
        %%% BEGIN:optional:acme-1
        \resumeItem{Built REST API}
        %%% END:optional:acme-1
    %%% END:pinned:acme
%%% END:pinned:exp
\end{document}
"""
        with pytest.raises(ParseError, match="Unexpected END tag outside any bullet"):
            parse_resume(tex)

    def test_stray_end_skills_outside_category(self):
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:skills
\section{Skills}
    %%% END:SKILLS:ghost
    %%% SKILLS:languages
    \textbf{Languages}{: Python, Java.}
    %%% END:SKILLS:languages
%%% END:pinned:skills
\end{document}
"""
        with pytest.raises(
            ParseError, match="Unexpected END:SKILLS tag outside any category"
        ):
            parse_resume(tex)


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


# ---------------------------------------------------------------------------
# Compact heading
# ---------------------------------------------------------------------------


class TestCompactHeading:
    def test_compact_heading_parsed(self):
        """COMPACT tag is extracted and stored on the item."""
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
\section{Experience}
    %%% BEGIN:optional:ey
%%% COMPACT: \resumeProjectHeading{\textbf{Ernst \& Young}}{Jan 2022 -- Apr 2022}
    \resumeSubheading{Ernst \& Young}{Jan 2022 -- Apr 2022}{Intern}{Kolkata}
    \resumeItemListStart
        %%% BEGIN:optional:ey-1
        \resumeItem{Did consulting work.}
        %%% END:optional:ey-1
    \resumeItemListEnd
    %%% END:optional:ey
%%% END:pinned:exp
\end{document}
"""
        result = parse_resume(tex)
        exp = result.sections[0]
        assert isinstance(exp, ResumeSection)
        ey = exp.items[0]
        assert ey.compact_heading is not None
        assert r"\resumeProjectHeading" in ey.compact_heading
        assert "Ernst" in ey.compact_heading

    def test_compact_heading_absent(self):
        """Items without COMPACT tag have compact_heading=None."""
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
\section{Experience}
    %%% BEGIN:pinned:snap
    \resumeSubheading{Snap}{2025}{SWE}{PA}
    \resumeItemListStart
        %%% BEGIN:pinned:snap-1
        \resumeItem{Built stuff.}
        %%% END:pinned:snap-1
    \resumeItemListEnd
    %%% END:pinned:snap
%%% END:pinned:exp
\end{document}
"""
        result = parse_resume(tex)
        exp = result.sections[0]
        assert isinstance(exp, ResumeSection)
        assert exp.items[0].compact_heading is None

    def test_compact_heading_not_in_heading_lines(self):
        """COMPACT tag line should not appear in heading_lines."""
        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
\section{Experience}
    %%% BEGIN:optional:tata
%%% COMPACT: \resumeProjectHeading{\textbf{Tata Steel}}{Jun 2021 -- Aug 2021}
    \resumeSubheading{Tata Steel}{Jun 2021}{Intern}{India}
    \resumeItemListStart
        %%% BEGIN:optional:tata-1
        \resumeItem{Built dashboard.}
        %%% END:optional:tata-1
    \resumeItemListEnd
    %%% END:optional:tata
%%% END:pinned:exp
\end{document}
"""
        result = parse_resume(tex)
        exp = result.sections[0]
        assert isinstance(exp, ResumeSection)
        tata = exp.items[0]
        assert "COMPACT" not in tata.heading_lines
        assert r"\resumeSubheading" in tata.heading_lines

    def test_compact_heading_no_malformed_warning(self):
        """COMPACT tag should not trigger a malformed-tag warning."""
        import warnings as _warnings

        tex = r"""\documentclass{article}
\begin{document}
%%% BEGIN:pinned:exp
\section{Experience}
    %%% BEGIN:optional:ey
%%% COMPACT: \resumeProjectHeading{\textbf{EY}}{2022}
    \resumeSubheading{EY}{2022}{Intern}{India}
    %%% END:optional:ey
%%% END:pinned:exp
\end{document}
"""
        with _warnings.catch_warnings():
            _warnings.simplefilter("error")
            parse_resume(tex)
