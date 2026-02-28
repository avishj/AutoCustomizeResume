"""Tests for the LaTeX compiler and 1-page enforcement logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autocustomizeresume.compiler import (
    CompileError,
    _Droppable,
    _drop_element,
    _find_droppables,
    _selection_to_dict,
    compile_tex,
    compile_with_enforcement,
    get_page_count,
)
from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.schemas import (
    BulletDecision,
    ContentSelection,
    ItemDecision,
    SectionDecision,
    SkillCategoryDecision,
)


def _tectonic_available() -> bool:
    """Check if tectonic is available on PATH."""
    import shutil
    return shutil.which("tectonic") is not None


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
    return _make_selection(sections=[
        {
            "id": "experience", "include": True, "items": [
                {
                    "id": "acme", "include": True, "relevance_score": 80,
                    "bullets": [
                        {"id": "acme-1", "include": True, "edited_text": ""},
                        {"id": "acme-2", "include": True, "edited_text": ""},
                    ],
                },
                {
                    "id": "widgets", "include": True, "relevance_score": 30,
                    "bullets": [
                        {"id": "widgets-1", "include": True, "edited_text": ""},
                    ],
                },
            ],
        },
    ])


# ---------------------------------------------------------------------------
# _selection_to_dict
# ---------------------------------------------------------------------------

class TestSelectionToDict:
    def test_roundtrip(self):
        """from_dict(to_dict(sel)) should produce equivalent selection."""
        sel = _full_selection()
        d = _selection_to_dict(sel)
        rebuilt = ContentSelection.from_dict(d)
        assert len(rebuilt.sections) == len(sel.sections)
        assert rebuilt.sections[0].id == "experience"
        assert rebuilt.sections[0].items[0].id == "acme"
        assert rebuilt.sections[0].items[0].relevance_score == 80

    def test_preserves_skill_categories(self):
        sel = _make_selection(
            skill_categories=[
                {"name": "languages", "skills": ["Python", "Go"]},
            ],
        )
        d = _selection_to_dict(sel)
        assert d["skill_categories"][0]["name"] == "languages"
        assert d["skill_categories"][0]["skills"] == ["Python", "Go"]

    def test_preserves_edited_text(self):
        sel = _make_selection(sections=[{
            "id": "exp", "include": True, "items": [{
                "id": "acme", "include": True, "relevance_score": 70,
                "bullets": [
                    {"id": "b1", "include": True, "edited_text": "custom text"},
                ],
            }],
        }])
        d = _selection_to_dict(sel)
        assert d["sections"][0]["items"][0]["bullets"][0]["edited_text"] == "custom text"

    def test_empty_selection(self):
        sel = _make_selection()
        d = _selection_to_dict(sel)
        assert d == {"sections": [], "skill_categories": []}


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
        first_item_idx = min(
            i for i, d in enumerate(droppables) if d.bullet_id is None
        )
        assert last_bullet_idx < first_item_idx

    def test_sorted_by_score_within_group(self):
        sel = _full_selection()
        droppables = _find_droppables(sel)
        bullet_droppables = [d for d in droppables if d.bullet_id is not None]
        item_droppables = [d for d in droppables if d.bullet_id is None]
        # Bullets sorted ascending by score
        bullet_scores = [d.score for d in bullet_droppables]
        assert bullet_scores == sorted(bullet_scores)
        # Items sorted ascending by score
        item_scores = [d.score for d in item_droppables]
        assert item_scores == sorted(item_scores)

    def test_lowest_score_first(self):
        """Widgets (score=30) bullets should appear before Acme (score=80) bullets."""
        sel = _full_selection()
        droppables = _find_droppables(sel)
        assert droppables[0].item_id == "widgets"
        assert droppables[0].score == 30

    def test_excluded_items_not_listed(self):
        sel = _make_selection(sections=[{
            "id": "experience", "include": True, "items": [
                {
                    "id": "acme", "include": True, "relevance_score": 80,
                    "bullets": [
                        {"id": "acme-1", "include": True, "edited_text": ""},
                    ],
                },
                {
                    "id": "widgets", "include": False, "relevance_score": 30,
                    "bullets": [
                        {"id": "widgets-1", "include": True, "edited_text": ""},
                    ],
                },
            ],
        }])
        droppables = _find_droppables(sel)
        ids = {d.item_id for d in droppables}
        assert "widgets" not in ids

    def test_excluded_sections_not_listed(self):
        sel = _make_selection(sections=[{
            "id": "experience", "include": False, "items": [
                {
                    "id": "acme", "include": True, "relevance_score": 80,
                    "bullets": [
                        {"id": "acme-1", "include": True, "edited_text": ""},
                    ],
                },
            ],
        }])
        droppables = _find_droppables(sel)
        assert droppables == []

    def test_empty_selection(self):
        sel = _make_selection()
        assert _find_droppables(sel) == []


# ---------------------------------------------------------------------------
# _drop_element
# ---------------------------------------------------------------------------

class TestDropElement:
    def test_drop_bullet(self):
        sel = _full_selection()
        d = _selection_to_dict(sel)
        droppable = _Droppable(
            section_id="experience", item_id="acme",
            bullet_id="acme-1", score=80,
        )
        _drop_element(d, droppable)
        bullets = d["sections"][0]["items"][0]["bullets"]
        acme1 = next(b for b in bullets if b["id"] == "acme-1")
        assert acme1["include"] is False

    def test_drop_item(self):
        sel = _full_selection()
        d = _selection_to_dict(sel)
        droppable = _Droppable(
            section_id="experience", item_id="widgets",
            bullet_id=None, score=30,
        )
        _drop_element(d, droppable)
        widgets = next(
            it for it in d["sections"][0]["items"] if it["id"] == "widgets"
        )
        assert widgets["include"] is False

    def test_drop_nonexistent_is_noop(self):
        sel = _full_selection()
        d = _selection_to_dict(sel)
        droppable = _Droppable(
            section_id="experience", item_id="nonexistent",
            bullet_id=None, score=0,
        )
        # Should not raise
        _drop_element(d, droppable)

    def test_drop_bullet_leaves_other_bullets(self):
        sel = _full_selection()
        d = _selection_to_dict(sel)
        droppable = _Droppable(
            section_id="experience", item_id="acme",
            bullet_id="acme-1", score=80,
        )
        _drop_element(d, droppable)
        acme2 = next(
            b for b in d["sections"][0]["items"][0]["bullets"]
            if b["id"] == "acme-2"
        )
        assert acme2["include"] is True


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
    def test_no_pdf_produced(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # Don't create the PDF file
        with pytest.raises(CompileError, match="no PDF was produced"):
            compile_tex(r"\documentclass{article}", keep_dir=tmp_path)

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_uses_temp_dir_when_no_keep_dir(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Create a real temp dir, then patch mkdtemp to return it.
        import tempfile as _tempfile
        td = _tempfile.mkdtemp(prefix="test_acr_")
        (Path(td) / "resume.pdf").write_bytes(b"%PDF-1.4 fake")

        with patch("autocustomizeresume.compiler.tempfile") as mock_tempmod:
            mock_tempmod.mkdtemp.return_value = td
            result = compile_tex(r"\documentclass{article}")
            assert result == Path(td) / "resume.pdf"

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_writes_tex_file(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4 fake")
        tex_content = r"\documentclass{article}\begin{document}test\end{document}"
        compile_tex(tex_content, keep_dir=tmp_path)
        tex_file = tmp_path / "resume.tex"
        assert tex_file.exists()
        assert tex_file.read_text(encoding="utf-8") == tex_content

    @patch("autocustomizeresume.compiler.subprocess.run")
    def test_timeout_raises_compile_error(self, mock_run, tmp_path):
        import subprocess as _subprocess
        mock_run.side_effect = _subprocess.TimeoutExpired(
            cmd=["tectonic"], timeout=120
        )
        with pytest.raises(CompileError, match="timed out"):
            compile_tex(r"\documentclass{article}", keep_dir=tmp_path)


# ---------------------------------------------------------------------------
# get_page_count (unit tests with real tiny PDFs)
# ---------------------------------------------------------------------------

class TestGetPageCount:
    def test_invalid_file_raises(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"not a pdf")
        with pytest.raises(CompileError, match="Failed to read page count"):
            get_page_count(bad)

    def test_real_pdf(self, tmp_path):
        """Create a minimal valid PDF via pypdf and verify page count."""
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "test.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)
        assert get_page_count(pdf_path) == 1

    def test_multi_page_pdf(self, tmp_path):
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        pdf_path = tmp_path / "multi.pdf"
        with open(pdf_path, "wb") as f:
            writer.write(f)
        assert get_page_count(pdf_path) == 3


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
            return page_counts[idx]

        return (
            patch("autocustomizeresume.compiler.compile_tex", side_effect=mock_compile),
            patch("autocustomizeresume.compiler.get_page_count", side_effect=mock_pages),
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
        """PDF exceeds 1 page, drops lowest-scored content, then fits."""
        # First attempt: 2 pages, second: 1 page
        p1, p2 = self._patch_compile([2, 1])
        with p1, p2:
            pdf_path, final_sel = compile_with_enforcement(
                _make_parsed(), _full_selection()
            )
        # Something should have been dropped
        # The lowest scored item is widgets (30), so its bullet should be
        # dropped first (bullets come before items)
        widgets_bullets = final_sel.sections[0].items[1].bullets
        widgets_1 = next(
            (b for b in widgets_bullets if b.id == "widgets-1"), None
        )
        # Either the bullet was dropped or the item itself
        # (depends on ordering — widgets bullet at score=30 is first droppable)
        assert widgets_1 is None or widgets_1.include is False or \
            final_sel.sections[0].items[1].include is False

    def test_multiple_retries(self):
        """Needs 3 drops (all 3 retries) to fit."""
        # 4 attempts: 2, 2, 2, 1
        p1, p2 = self._patch_compile([2, 2, 2, 1])
        with p1, p2:
            pdf_path, final_sel = compile_with_enforcement(
                _make_parsed(), _full_selection()
            )
        assert pdf_path == Path("/tmp/fake/resume.pdf")

    def test_exceeds_after_all_retries(self):
        """Still > 1 page after max retries — raises CompileError."""
        # Provide enough 2-page results to exhaust all droppables.
        # The fixture has 3 bullets + 2 items = 5 droppable elements,
        # so we need at least 6 attempts (initial + 5 drops) all returning 2.
        p1, p2 = self._patch_compile([2] * 12)
        with p1, p2:
            with pytest.raises(CompileError, match="still exceeds 1 page"):
                compile_with_enforcement(
                    _make_parsed(), _full_selection()
                )

    def test_nothing_to_drop(self):
        """All items already excluded — raises immediately."""
        sel = _make_selection(sections=[{
            "id": "experience", "include": True, "items": [
                {
                    "id": "acme", "include": False, "relevance_score": 80,
                    "bullets": [],
                },
                {
                    "id": "widgets", "include": False, "relevance_score": 30,
                    "bullets": [],
                },
            ],
        }])
        p1, p2 = self._patch_compile([2])
        with p1, p2:
            with pytest.raises(CompileError, match="still exceeds 1 page"):
                compile_with_enforcement(_make_parsed(), sel)

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
            return next(page_calls)

        with patch("autocustomizeresume.compiler.compile_tex", side_effect=mock_compile), \
             patch("autocustomizeresume.compiler.get_page_count", side_effect=mock_pages), \
             patch("autocustomizeresume.assembler.assemble_tex") as mock_assemble:
            # Track the selection passed to assemble_tex
            def capture_assemble(parsed, sel):
                call_log.append(sel)
                return r"\documentclass{article}\begin{document}x\end{document}"
            mock_assemble.side_effect = capture_assemble

            compile_with_enforcement(_make_parsed(), _full_selection())

        # Second call should have one bullet dropped but all items still included
        assert len(call_log) == 2
        second_sel = call_log[1]
        # All items should still be included
        for sec in second_sel.sections:
            for it in sec.items:
                assert it.include is True, f"Item {it.id} should still be included"


# ---------------------------------------------------------------------------
# Integration test (requires tectonic)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not _tectonic_available(),
    reason="tectonic not installed",
)
class TestTectonicIntegration:
    """Integration tests that invoke tectonic. Skipped if not installed."""

    def test_compile_minimal(self, tmp_path):
        tex = (
            r"\documentclass{article}"
            "\n"
            r"\begin{document}"
            "\n"
            r"Hello, world!"
            "\n"
            r"\end{document}"
        )
        pdf_path = compile_tex(tex, keep_dir=tmp_path)
        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        assert get_page_count(pdf_path) == 1

    def test_compile_error_bad_latex(self, tmp_path):
        tex = r"\documentclass{article}\begin{document}\badcommand\end{document}"
        with pytest.raises(CompileError):
            compile_tex(tex, keep_dir=tmp_path)
