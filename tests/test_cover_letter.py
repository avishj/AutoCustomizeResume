"""Tests for the cover letter generator."""

from __future__ import annotations

import logging
import re
import shutil
import tempfile as _tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autocustomizeresume.compiler import CompileError
from autocustomizeresume.config import (
    Config,
    CoverLetterConfig,
    LLMConfig,
    NamingConfig,
    PathsConfig,
    UserConfig,
    WatcherConfig,
)
from autocustomizeresume.cover_letter import (
    _build_signature_block,
    _escape_latex,
    _format_date,
    _plain_text_to_latex,
    _summarize_selected_content,
    build_cover_letter,
    compile_cover_letter,
    generate_cover_letter_body,
    inject_template,
)
from autocustomizeresume.llm_client import LLMClient
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
    JDAnalysis,
    SectionDecision,
    SkillCategoryDecision,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimal valid 1x1 RGB PNG (avoids struct/zlib at runtime).
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00"
    b"\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8"
    b"\xff\xff?\x00\x05\xfe\x02\xfe\r\xefF\xb8\x00\x00\x00\x00IEND\xaeB`\x82"
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides) -> Config:
    """Build a Config with sensible defaults for testing."""
    user_kw = overrides.pop("user", {})
    cl_kw = overrides.pop("cover_letter", {})

    user_defaults = {
        "first_name": "Jane",
        "last_name": "Doe",
        "phone": "555-123-4567",
        "email": "jane@example.com",
        "linkedin": "linkedin.com/in/janedoe",
        "website": "janedoe.dev",
        "degree": "MS Computer Science",
        "university": "MIT",
    }
    user_defaults.update(user_kw)

    cl_enabled: bool = cl_kw.get("enabled", True)
    cl_template: str = cl_kw.get("template", "templates/cover_letter_template.tex")
    cl_sig: str = cl_kw.get("signature_path", "")

    return Config(
        user=UserConfig(**user_defaults),
        naming=NamingConfig(
            output_resume="{company}_{role}_Resume.pdf",
            output_cover="{company}_{role}_CoverLetter.pdf",
            history_resume="{date}_{company}_{role}_Resume.pdf",
            history_cover="{date}_{company}_{role}_CoverLetter.pdf",
        ),
        llm=LLMConfig(
            base_url="https://api.example.com/v1",
            model="test-model",
            api_key_env="TEST_API_KEY",
        ),
        cover_letter=CoverLetterConfig(
            enabled=cl_enabled,
            template=cl_template,
            signature_path=cl_sig,
        ),
        paths=PathsConfig(
            master_resume="resume.tex",
            jd_file="jd.txt",
            output_dir="output",
            history_dir="history",
        ),
        watcher=WatcherConfig(debounce_seconds=5),
    )


def _make_jd_analysis() -> JDAnalysis:
    return JDAnalysis(
        company="Acme Corp",
        role="Senior Backend Engineer",
        seniority="senior",
        domain="platform engineering",
        key_skills=["distributed systems", "microservices"],
        technologies=["Python", "Go", "Kubernetes"],
    )


def _make_parsed_resume() -> ParsedResume:
    """Build a minimal ParsedResume with optional and pinned elements."""
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
                                tag_type="pinned",
                                id="acme-1",
                                text=r"\resumeItem{Built REST API serving 10k rps}",
                            ),
                            Bullet(
                                tag_type="optional",
                                id="acme-2",
                                text=(
                                    r"\resumeItem{Wrote unit tests"
                                    r" with 90\% coverage}"
                                ),
                            ),
                        ],
                    ),
                ],
            ),
            SkillsSection(
                tag_type="pinned",
                id="skills",
                categories=[
                    SkillCategory(
                        name="languages",
                        display_name="Languages",
                        skills=["Python", "Go", "Java"],
                        prefix=r"\textbf{Languages}{: ",
                        suffix=r"} \\",
                    ),
                    SkillCategory(
                        name="frameworks",
                        display_name="Frameworks",
                        skills=["FastAPI", "Django"],
                        prefix=r"\textbf{Frameworks}{: ",
                        suffix=r"}",
                    ),
                ],
            ),
        ],
        postamble=r"\end{document}",
    )


def _make_selection() -> ContentSelection:
    """Selection that includes experience + skills (matching _make_parsed_resume)."""
    return ContentSelection(
        sections=[
            SectionDecision(
                id="experience",
                include=True,
                items=[
                    ItemDecision(
                        id="acme",
                        include=True,
                        relevance_score=85,
                        bullets=[
                            BulletDecision(id="acme-2", include=True, edited_text=""),
                        ],
                    ),
                ],
            ),
        ],
        skill_categories=[
            SkillCategoryDecision(name="languages", skills=["Python", "Go"]),
            SkillCategoryDecision(name="frameworks", skills=["FastAPI"]),
        ],
    )


# ===========================================================================
# 5.4a — Resume context serializer + body generation (mocked LLM)
# ===========================================================================


class TestSummarizeSelectedContent:
    """Tests for _summarize_selected_content()."""

    def test_included_content_appears(self):
        """Pinned sections/bullets and selected optional content all appear."""
        summary = _summarize_selected_content(_make_parsed_resume(), _make_selection())
        # Pinned section + item
        assert "Education" in summary
        assert "MIT" in summary
        # Pinned bullet
        assert "TA for Distributed Systems" in summary
        # Optional section included by selection
        assert "Experience" in summary
        assert "Acme" in summary
        # Optional bullet included by selection
        assert "unit tests" in summary or "coverage" in summary
        # Skills section with selected subset
        assert "Languages" in summary
        assert "Python" in summary
        assert "Go" in summary
        assert "FastAPI" in summary
        # Unselected skill excluded
        assert "Java" not in summary

    def test_excluded_content_absent(self):
        """Excluded optional sections, items, and bullets do not appear."""
        sel = ContentSelection(
            sections=[
                SectionDecision(
                    id="experience",
                    include=True,
                    items=[
                        ItemDecision(
                            id="acme",
                            include=False,
                            relevance_score=85,
                            bullets=[],
                        ),
                    ],
                ),
            ],
            skill_categories=[],
        )
        summary = _summarize_selected_content(_make_parsed_resume(), sel)
        # Item excluded
        assert "Acme" not in summary

        # Entire section excluded
        sel2 = ContentSelection(
            sections=[SectionDecision(id="experience", include=False, items=[])],
            skill_categories=[],
        )
        summary2 = _summarize_selected_content(_make_parsed_resume(), sel2)
        assert "Experience" not in summary2

        # Empty selection: only pinned content
        sel3 = ContentSelection(sections=[], skill_categories=[])
        summary3 = _summarize_selected_content(_make_parsed_resume(), sel3)
        assert "Education" in summary3
        assert "Experience" not in summary3

    def test_uses_edited_text_when_present(self):
        sel = ContentSelection(
            sections=[
                SectionDecision(
                    id="experience",
                    include=True,
                    items=[
                        ItemDecision(
                            id="acme",
                            include=True,
                            relevance_score=85,
                            bullets=[
                                BulletDecision(
                                    id="acme-2",
                                    include=True,
                                    edited_text=(
                                        r"\resumeItem{Achieved 95\%"
                                        r" test coverage}"
                                    ),
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            skill_categories=[],
        )
        summary = _summarize_selected_content(_make_parsed_resume(), sel)
        assert "95" in summary


class TestGenerateCoverLetterBody:
    """Tests for generate_cover_letter_body() with mocked LLM."""

    def test_returns_stripped_body_with_correct_prompt(self):
        """LLM response is stripped; prompt contains JD analysis and resume summary."""
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = {"body": "  Body text here.  \n"}

        result = generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )
        assert result == "Body text here."

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "<jd_analysis>" in user
        assert "Acme Corp" in user
        assert "<resume_summary>" in user

    def test_creates_client_from_config_when_none(self):
        with patch("autocustomizeresume.cover_letter.LLMClient") as mock_cls:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.chat.return_value = {"body": "Body."}
            mock_cls.return_value = mock_instance

            cfg = _make_config()
            generate_cover_letter_body(
                _make_jd_analysis(),
                _make_parsed_resume(),
                _make_selection(),
                config=cfg,
            )

            mock_cls.assert_called_once_with(cfg)


# ===========================================================================
# 5.4b — LaTeX escaping + template injection
# ===========================================================================


class TestEscapeLatex:
    """Tests for _escape_latex()."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("A & B", r"A \& B"),
            ("100%", r"100\%"),
            ("$100", r"\$100"),
            ("#1", r"\#1"),
            ("foo_bar", r"foo\_bar"),
            ("~", r"\textasciitilde{}"),
            ("x^2", r"x\textasciicircum{}2"),
            ("{hello}", r"\{hello\}"),
            ("a\\b", r"a\textbackslash{}b"),
            ("Hello World", "Hello World"),
            ("", ""),
        ],
    )
    def test_escapes_special_chars(self, raw, expected):
        assert _escape_latex(raw) == expected

    def test_backslash_with_braces_no_double_escape(self):
        result = _escape_latex("\\{")
        assert r"\textbackslash{}" in result
        assert r"\{" in result


class TestPlainTextToLatex:
    """Tests for _plain_text_to_latex()."""

    def test_single_paragraph_unchanged(self):
        result = _plain_text_to_latex("Hello world.")
        assert result == "Hello world."
        assert r"\par" not in result

    def test_paragraphs_and_escaping(self):
        """Multiple paragraphs separated by \\par, blank lines collapsed, stripped."""
        result = _plain_text_to_latex("  100% of $20  \n\n\n\n  A & B  ")
        assert r"\%" in result
        assert r"\$" in result
        assert r"\&" in result
        assert result.count(r"\par") == 1
        # Paragraphs are stripped
        assert not result.startswith(" ")
        assert not result.endswith(" ")


class TestBuildSignatureBlock:
    """Tests for _build_signature_block()."""

    def test_empty_path_returns_empty(self):
        assert _build_signature_block("") == ""
        assert _build_signature_block("   ") == ""

    def test_builds_latex_with_detokenized_filename_only(self):
        result = _build_signature_block("/full/path/to/my_signature.png")
        assert r"\includegraphics" in result
        assert "/full/path/to/" not in result
        assert r"\detokenize{my_signature.png}" in result


class TestFormatDate:
    """Tests for _format_date()."""

    def test_format(self):
        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            result = _format_date()
            assert result == "February 28, 2026"


class TestInjectTemplate:
    """Tests for inject_template()."""

    def test_full_template(self):
        """Injection against the real template produces no remaining placeholders."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")
        template = template_path.read_text(encoding="utf-8")
        cfg = _make_config(cover_letter={"signature_path": "sig.png"})

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 1)
            mock_date.side_effect = date
            result = inject_template(template, config=cfg, body_text="Body text.")

        remaining = re.findall(r"\{\{[A-Z_]+\}\}", result)
        # {{PLACEHOLDER}} in a comment is expected -- filter it out
        remaining = [p for p in remaining if p != "{{PLACEHOLDER}}"]
        assert remaining == [], f"Unreplaced placeholders: {remaining}"

    def test_escapes_user_info(self):
        """User info with LaTeX special chars is properly escaped."""
        cfg = _make_config(user={"email": "user_name@example.com"})
        template = "{{EMAIL}}"
        result = inject_template(template, config=cfg, body_text="Body.")
        assert r"\_" in result

    def test_empty_signature_block(self):
        cfg = _make_config(cover_letter={"signature_path": ""})
        template = "before{{SIGNATURE_BLOCK}}after"
        result = inject_template(template, config=cfg, body_text="Body.")
        assert result == "beforeafter"

    def test_warns_on_unreplaced_placeholders(self, caplog):
        template = "{{FIRST_NAME}} {{UNKNOWN_THING}}"
        with caplog.at_level(logging.WARNING):
            inject_template(template, config=_make_config(), body_text="Body.")
        assert "UNKNOWN_THING" in caplog.text


# ===========================================================================
# 5.4c — Config flag / skip logic + compile_cover_letter unit tests
# ===========================================================================


class TestCompileCoverLetter:
    """Tests for compile_cover_letter() with mocked compile_tex."""

    @patch("autocustomizeresume.cover_letter.compile_tex")
    def test_copies_fonts(self, mock_compile, tmp_path):
        # Set up font source
        template_dir = tmp_path / "tpl"
        template_dir.mkdir()
        fonts_dir = template_dir / "fonts"
        fonts_dir.mkdir()
        (fonts_dir / "Regular.otf").write_bytes(b"font-data")

        cfg = _make_config(
            cover_letter={"template": str(template_dir / "template.tex")}
        )

        work = tmp_path / "work"
        mock_compile.return_value = work / "resume.pdf"

        compile_cover_letter(r"\documentclass{}", config=cfg, keep_dir=work)

        # Fonts should have been copied
        assert (work / "fonts" / "Regular.otf").exists()

    @patch("autocustomizeresume.cover_letter.compile_tex")
    def test_copies_signature(self, mock_compile, tmp_path):
        template_dir = tmp_path / "tpl"
        template_dir.mkdir()

        sig_file = tmp_path / "sig.png"
        sig_file.write_bytes(b"PNG-data")

        cfg = _make_config(
            cover_letter={
                "template": str(template_dir / "template.tex"),
                "signature_path": str(sig_file),
            }
        )

        work = tmp_path / "work"
        mock_compile.return_value = work / "resume.pdf"

        compile_cover_letter(r"\documentclass{}", config=cfg, keep_dir=work)

        assert (work / "sig.png").exists()

    @patch("autocustomizeresume.cover_letter.compile_tex")
    def test_missing_signature_warns(self, mock_compile, tmp_path, caplog):
        template_dir = tmp_path / "tpl"
        template_dir.mkdir()

        cfg = _make_config(
            cover_letter={
                "template": str(template_dir / "template.tex"),
                "signature_path": "/nonexistent/sig.png",
            }
        )

        work = tmp_path / "work"
        mock_compile.return_value = work / "resume.pdf"

        with caplog.at_level(logging.WARNING):
            compile_cover_letter(r"\documentclass{}", config=cfg, keep_dir=work)

        assert "not found" in caplog.text.lower()

    @patch("autocustomizeresume.cover_letter.compile_tex")
    def test_temp_dir_cleaned_on_failure(self, mock_compile, tmp_path):
        template_dir = tmp_path / "tpl"
        template_dir.mkdir()

        cfg = _make_config(
            cover_letter={"template": str(template_dir / "template.tex")}
        )

        mock_compile.side_effect = CompileError("boom")

        td = _tempfile.mkdtemp(prefix="test_acr_cl_")
        td_path = Path(td)

        with patch("autocustomizeresume.cover_letter.tempfile") as mock_tempmod:
            mock_tempmod.mkdtemp.return_value = td
            with pytest.raises(CompileError):
                compile_cover_letter(r"\documentclass{}", config=cfg)

        assert not td_path.exists(), "temp dir should be cleaned on failure"

    @patch("autocustomizeresume.cover_letter.compile_tex")
    def test_keep_dir_not_cleaned_on_failure(self, mock_compile, tmp_path):
        template_dir = tmp_path / "tpl"
        template_dir.mkdir()

        cfg = _make_config(
            cover_letter={"template": str(template_dir / "template.tex")}
        )

        work = tmp_path / "work"
        mock_compile.side_effect = CompileError("boom")

        with pytest.raises(CompileError):
            compile_cover_letter(r"\documentclass{}", config=cfg, keep_dir=work)

        # keep_dir should NOT be deleted
        assert work.exists()


class TestBuildCoverLetter:
    """Tests for build_cover_letter() — config flag + orchestration."""

    def test_disabled_returns_none(self):
        cfg = _make_config(cover_letter={"enabled": False})
        result = build_cover_letter(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
        )
        assert result is None

    def test_missing_template_raises(self, tmp_path):
        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(tmp_path / "nonexistent.tex"),
            }
        )
        with pytest.raises(FileNotFoundError, match="not found"):
            build_cover_letter(
                _make_jd_analysis(),
                _make_parsed_resume(),
                _make_selection(),
                config=cfg,
            )

    @patch("autocustomizeresume.cover_letter.compile_cover_letter")
    @patch("autocustomizeresume.cover_letter.generate_cover_letter_body")
    def test_calls_pipeline(self, mock_gen, mock_compile, tmp_path):
        """build_cover_letter calls generate → escape → inject → compile."""
        # Create template file
        template = tmp_path / "template.tex"
        template.write_text("{{BODY}}", encoding="utf-8")

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template),
            }
        )

        mock_gen.return_value = "Hello world."
        mock_compile.return_value = tmp_path / "output.pdf"

        result = build_cover_letter(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
        )

        mock_gen.assert_called_once()
        mock_compile.assert_called_once()
        assert result == tmp_path / "output.pdf"

    @patch("autocustomizeresume.cover_letter.compile_cover_letter")
    @patch("autocustomizeresume.cover_letter.generate_cover_letter_body")
    def test_body_is_escaped_before_injection(self, mock_gen, mock_compile, tmp_path):
        """Body text goes through _plain_text_to_latex before template injection."""
        template = tmp_path / "template.tex"
        template.write_text("{{BODY}}", encoding="utf-8")

        cfg = _make_config(cover_letter={"enabled": True, "template": str(template)})

        # Body with special chars + paragraph break
        mock_gen.return_value = "100% of $20.\n\nA & B."
        mock_compile.return_value = tmp_path / "out.pdf"

        build_cover_letter(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
        )

        # Check the filled_tex passed to compile_cover_letter
        filled_tex = mock_compile.call_args[0][0]
        assert r"\%" in filled_tex
        assert r"\$" in filled_tex
        assert r"\par" in filled_tex


# ===========================================================================
# 5.4d — Integration test (requires tectonic)
# ===========================================================================


def _tectonic_available() -> bool:
    return shutil.which("tectonic") is not None


@pytest.mark.skipif(
    not _tectonic_available(),
    reason="tectonic not installed",
)
class TestCoverLetterIntegration:
    """End-to-end compilation using the real template and tectonic."""

    def test_compile_cover_letter_produces_pdf(self, tmp_path):
        """Fill the real template and compile to a valid PDF."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": "",
            }
        )

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(
                template_tex,
                config=cfg,
                body_text="This is a test cover letter body paragraph.",
            )

        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        # Verify it's a real PDF
        header = pdf_path.read_bytes()[:5]
        assert header == b"%PDF-"

    def test_compile_with_signature(self, tmp_path):
        """Compile with a signature image (fake PNG)."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        sig_file = tmp_path / "signature.png"
        sig_file.write_bytes(_MINIMAL_PNG)

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": str(sig_file),
            }
        )

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(
                template_tex,
                config=cfg,
                body_text="Test body with signature.",
            )

        work = tmp_path / "build"
        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=work)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
        # Signature should have been copied to build dir
        assert (work / "signature.png").exists()

    def test_compile_with_special_chars_in_body(self, tmp_path):
        """Body with LaTeX special chars compiles cleanly after escaping."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")

        cfg = _make_config(
            cover_letter={
                "enabled": True,
                "template": str(template_path),
                "signature_path": "",
            }
        )

        # Body with special chars — this would break compilation if not escaped
        body_plain = (
            "I improved performance by 100% and saved $50k.\n\n"
            "Technologies: C++ & Python. Used the #1 framework."
        )
        body_latex = _plain_text_to_latex(body_plain)

        template_tex = template_path.read_text(encoding="utf-8")

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = date
            filled_tex = inject_template(template_tex, config=cfg, body_text=body_latex)

        pdf_path = compile_cover_letter(filled_tex, config=cfg, keep_dir=tmp_path)

        assert pdf_path.exists()
        assert pdf_path.suffix == ".pdf"
