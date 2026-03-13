"""Unit tests for the LaTeX compiler and 1-page enforcement logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autocustomizeresume.compiler import (
    CompileError,
    _Candidate,
    _drop_element,
    _find_droppables,
    compile_tex,
    compile_with_enforcement,
)
from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
)
from autocustomizeresume.schemas import (
    ContentSelection,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_selection(**overrides) -> ContentSelection:
    """Build a ContentSelection from a dict, with defaults."""
    data = {
        "sections": overrides.get("sections", []),
        "skill_categories": overrides.get("skill_categories", []),
    }
    return ContentSelection.from_dict(data)


def _make_parsed() -> ParsedResume:
    """Minimal ParsedResume for enforcement tests."""
    return ParsedResume(
        preamble=r"\documentclass{article}" "\n" r"\begin{document}",
        header=r"\textbf{Jane Doe}",
        sections=[
            ResumeSection(
                tag_type="pinned",
                id="education",
                items=[
                    ResumeItem(
                        tag_type="pinned",
                        id="mit",
                        heading_lines=r"\resumeSubheading{MIT}{2025}{MS CS}{MA}",
                        bullets=[
                            Bullet(
                                tag_type="pinned",
                                id="mit-1",
                                text=r"\resumeItem{TA for Distributed Systems}",
                            ),
                        ],
                    ),
                ],
            ),
            ResumeSection(
                tag_type="optional",
                id="experience",
                items=[
                    ResumeItem(
                        tag_type="optional",
                        id="acme",
                        heading_lines=r"\resumeSubheading{Acme}{2024}{SWE}{SF}",
                        bullets=[
                            Bullet(
                                tag_type="optional",
                                id="acme-1",
                                text=r"\resumeItem{Built REST API}",
                            ),
                            Bullet(
                                tag_type="optional",
                                id="acme-2",
                                text=r"\resumeItem{Wrote tests}",
                            ),
                        ],
                    ),
                    ResumeItem(
                        tag_type="optional",
                        id="widgets",
                        heading_lines=r"\resumeSubheading{Widgets}{2023}{Intern}{NY}",
                        bullets=[
                            Bullet(
                                tag_type="optional",
                                id="widgets-1",
                                text=r"\resumeItem{Built dashboard}",
                            ),
                        ],
                    ),
                ],
            ),
        ],
        postamble=r"\end{document}",
    )


def _full_selection() -> ContentSelection:
    """Selection that includes everything in _make_parsed()."""
    return _make_selection(
        sections=[
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
                                "relevance_score": 80,
                                "edited_text": "",
                            },
                            {
                                "id": "acme-2",
                                "include": True,
                                "relevance_score": 75,
                                "edited_text": "",
                            },
                        ],
                    },
                    {
                        "id": "widgets",
                        "include": True,
                        "relevance_score": 30,
                        "bullets": [
                            {
                                "id": "widgets-1",
                                "include": True,
                                "relevance_score": 30,
                                "edited_text": "",
                            },
                        ],
                    },
                ],
            },
        ]
    )


# ---------------------------------------------------------------------------
# _find_droppables
# ---------------------------------------------------------------------------


class TestFindDroppables:
    def test_returns_bullets_before_items(self):
        sel = _full_selection()
        droppables = _find_droppables(sel)
        # First entries should be bullets, last entries should be items
        bullet_droppables = [d for d in droppables if d.bullet_id is not None]
        item_droppables = [d for d in droppables if d.bullet_id is None]
        assert len(bullet_droppables) > 0
        assert len(item_droppables) > 0
        # All bullets come before all items in the list
        last_bullet_idx = max(
            i for i, d in enumerate(droppables) if d.bullet_id is not None
        )
        first_item_idx = min(i for i, d in enumerate(droppables) if d.bullet_id is None)
        assert last_bullet_idx < first_item_idx

    def test_excludes_already_excluded(self):
        sel = _make_selection(
            sections=[
                {
                    "id": "exp",
                    "include": True,
                    "items": [
                        {
                            "id": "acme",
                            "include": False,
                            "relevance_score": 80,
                            "bullets": [],
                        },
                    ],
                }
            ]
        )
        assert _find_droppables(sel) == []

    def test_sorts_by_score_ascending(self):
        sel = _full_selection()
        droppables = _find_droppables(sel)
        bullet_droppables = [d for d in droppables if d.bullet_id is not None]
        item_droppables = [d for d in droppables if d.bullet_id is None]
        # Bullets should be sorted ascending by score
        scores = [d.score for d in bullet_droppables]
        assert scores == sorted(scores)
        # Items should be sorted ascending by score
        scores = [d.score for d in item_droppables]
        assert scores == sorted(scores)

    def test_excluded_section_skipped(self):
        sel = _make_selection(
            sections=[
                {
                    "id": "exp",
                    "include": False,
                    "items": [
                        {
                            "id": "acme",
                            "include": True,
                            "relevance_score": 80,
                            "bullets": [{"id": "b1", "include": True}],
                        },
                    ],
                }
            ]
        )
        assert _find_droppables(sel) == []


# ---------------------------------------------------------------------------
# _drop_element
# ---------------------------------------------------------------------------


class TestDropElement:
    def test_drop_bullet(self):
        sel = _full_selection()
        candidate = _Candidate(
            section_id="experience",
            item_id="acme",
            bullet_id="acme-1",
            score=80,
        )
        new_sel = _drop_element(sel, candidate)
        acme = next(it for it in new_sel.sections[0].items if it.id == "acme")
        acme1 = next(b for b in acme.bullets if b.id == "acme-1")
        assert acme1.include is False

    def test_drop_item(self):
        sel = _full_selection()
        candidate = _Candidate(
            section_id="experience",
            item_id="widgets",
            bullet_id=None,
            score=30,
        )
        new_sel = _drop_element(sel, candidate)
        widgets = next(it for it in new_sel.sections[0].items if it.id == "widgets")
        assert widgets.include is False

    def test_drop_nonexistent_is_noop(self):
        sel = _full_selection()
        candidate = _Candidate(
            section_id="experience",
            item_id="nonexistent",
            bullet_id=None,
            score=0,
        )
        # Should not raise; returns unchanged selection
        new_sel = _drop_element(sel, candidate)
        assert len(new_sel.sections) == len(sel.sections)

    def test_original_selection_unchanged(self):
        """_drop_element must not mutate the original selection."""
        sel = _full_selection()
        candidate = _Candidate(
            section_id="experience",
            item_id="acme",
            bullet_id="acme-1",
            score=80,
        )
        _drop_element(sel, candidate)
        # Original should still have acme-1 included
        acme = next(it for it in sel.sections[0].items if it.id == "acme")
        acme1 = next(b for b in acme.bullets if b.id == "acme-1")
        assert acme1.include is True


# ---------------------------------------------------------------------------
# compile_tex (unit tests with mocked subprocess)
# ---------------------------------------------------------------------------


class TestCompileTex:
    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # Pre-create the expected PDF so compile_tex finds it
        tex_content = r"\documentclass{article}\begin{document}hello\end{document}"
        pdf_path = tmp_path / "resume.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        result = compile_tex(tex_content, keep_dir=tmp_path)
        assert result == pdf_path
        mock_run.assert_called_once()

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_failure_raises_compile_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1, stderr="error: undefined control sequence"
        )
        with pytest.raises(CompileError, match="tectonic failed"):
            compile_tex(r"\bad", keep_dir=tmp_path)

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_timeout_raises_compile_error(self, mock_run, tmp_path):
        import subprocess as _subprocess

        mock_run.side_effect = _subprocess.TimeoutExpired(cmd=["tectonic"], timeout=120)
        with pytest.raises(CompileError, match="timed out"):
            compile_tex(r"\documentclass{article}", keep_dir=tmp_path)

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_temp_dir_cleaned_on_failure(self, mock_run):
        """Temp dir is removed when compile_tex raises CompileError (no keep_dir)."""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        import tempfile as _tempfile

        td = _tempfile.mkdtemp(prefix="test_acr_leak_")
        td_path = Path(td)

        with patch("autocustomizeresume.compiler.tempfile") as mock_tempmod:
            mock_tempmod.mkdtemp.return_value = td
            with pytest.raises(CompileError):
                compile_tex(r"\bad")

        assert not td_path.exists(), "temp dir should be cleaned up on failure"


# ---------------------------------------------------------------------------
# compile_with_enforcement (mocked compile_tex + get_page_count)
# ---------------------------------------------------------------------------


class TestCompileWithEnforcement:
    """Test the enforcement loop with mocked compilation."""

    def _patch_compile(self, page_counts: list[int]):
        """Return patchers that simulate compile_tex and get_page_count.

        page_counts: sequence of page counts returned on successive calls.
        """
        call_idx = {"n": 0}
        fake_pdf = Path("/tmp/fake/resume.pdf")

        def mock_compile(tex, *, keep_dir=None):
            return fake_pdf

        def mock_pages(pdf_path):
            idx = call_idx["n"]
            call_idx["n"] += 1
            if idx < len(page_counts):
                return page_counts[idx]
            # Phase 2 (fill) calls: default to 1 page (fits)
            return 1

        return (
            patch("autocustomizeresume.compiler.compile_tex", side_effect=mock_compile),
            patch(
                "autocustomizeresume.compiler.get_page_count", side_effect=mock_pages
            ),
        )

    def test_fits_first_try(self):
        """PDF fits on first attempt — no retries."""
        p1, p2 = self._patch_compile([1])
        with p1, p2:
            pdf_path, final_sel = compile_with_enforcement(
                _make_parsed(), _full_selection()
            )
        assert pdf_path == Path("/tmp/fake/resume.pdf")
        # Selection should be unchanged
        assert final_sel.sections[0].items[0].include is True
        assert final_sel.sections[0].items[1].include is True

    def test_drops_content_on_retry(self):
        """PDF exceeds 1 page, drops lowest-scored content, then fits.

        Phase 1: 2 pages → drop lowest bullet → 1 page.
        Phase 2 (fill): re-adding the dropped bullet overflows → stays dropped.
        """
        # Phase 1: 2 pages, then 1 page after drop.
        # Phase 2: re-adding the dropped bullet → 2 pages (overflow, skip).
        p1, p2 = self._patch_compile([2, 1, 2])
        with p1, p2:
            _pdf_path, final_sel = compile_with_enforcement(
                _make_parsed(), _full_selection()
            )
        # The lowest scored bullet (widgets-1 at 30) should have been dropped
        # and stayed dropped because re-adding it overflowed.
        widgets_bullets = final_sel.sections[0].items[1].bullets
        widgets_1 = next((b for b in widgets_bullets if b.id == "widgets-1"), None)
        assert (
            widgets_1 is None
            or widgets_1.include is False
            or final_sel.sections[0].items[1].include is False
        )

    def test_exceeds_after_all_retries(self):
        """Still > 1 page after max retries — raises CompileError."""
        # Provide enough 2-page results to exhaust all droppables.
        # The fixture has 3 bullets + 2 items = 5 droppable elements,
        # so we need at least 6 attempts (initial + 5 drops) all returning 2.
        p1, p2 = self._patch_compile([2] * 12)
        with p1, p2, pytest.raises(CompileError, match="still exceeds 1 page"):
            compile_with_enforcement(_make_parsed(), _full_selection())

    def test_original_selection_not_mutated(self):
        """Enforcement should not modify the original selection object."""
        original = _full_selection()
        # Capture original state
        orig_items_included = [
            it.include for sec in original.sections for it in sec.items
        ]
        p1, p2 = self._patch_compile([2, 1])
        with p1, p2:
            compile_with_enforcement(_make_parsed(), original)
        # Original should be unchanged (frozen dataclass)
        after_items_included = [
            it.include for sec in original.sections for it in sec.items
        ]
        assert orig_items_included == after_items_included

    def test_drops_bullet_before_item(self):
        """First drop should be a bullet, not a whole item."""
        call_log: list[ContentSelection] = []

        def mock_compile(tex, *, keep_dir=None):
            return Path("/tmp/fake/resume.pdf")

        page_calls = iter([2, 1])

        def mock_pages(pdf_path):
            return next(page_calls, 1)  # default 1 for Phase 2 fill calls

        with (
            patch("autocustomizeresume.compiler.compile_tex", side_effect=mock_compile),
            patch(
                "autocustomizeresume.compiler.get_page_count", side_effect=mock_pages
            ),
            patch("autocustomizeresume.assembler.assemble_tex") as mock_assemble,
        ):
            # Track the selection passed to assemble_tex
            def capture_assemble(parsed, sel):
                call_log.append(sel)
                return r"\documentclass{article}\begin{document}x\end{document}"

            mock_assemble.side_effect = capture_assemble

            compile_with_enforcement(_make_parsed(), _full_selection())

        # Second call (first drop) should have one bullet dropped
        # but all items still included
        assert len(call_log) >= 2
        second_sel = call_log[1]
        # All items should still be included after first drop
        for sec in second_sel.sections:
            for it in sec.items:
                assert it.include is True, f"Item {it.id} should still be included"
