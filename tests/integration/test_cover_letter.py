"""Integration tests for the cover letter generator (real file I/O)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

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
    build_cover_letter,
    inject_template,
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
    JDAnalysis,
    SectionDecision,
    SkillCategoryDecision,
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
# inject_template — real template file
# ===========================================================================


class TestInjectTemplate:
    """Tests for inject_template() against the real template file."""

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


# ===========================================================================
# build_cover_letter — pipeline orchestration with real template
# ===========================================================================


class TestBuildCoverLetter:
    """Tests for build_cover_letter() that write real template files."""

    @patch("autocustomizeresume.cover_letter.compile_cover_letter")
    @patch("autocustomizeresume.cover_letter.generate_cover_letter_body")
    def test_calls_pipeline(self, mock_gen, mock_compile, tmp_path):
        """build_cover_letter calls generate -> escape -> inject -> compile."""
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

        mock_gen.return_value = "100% of $20.\n\nA & B."
        mock_compile.return_value = tmp_path / "out.pdf"

        build_cover_letter(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
        )

        filled_tex = mock_compile.call_args[0][0]
        assert r"\%" in filled_tex
        assert r"\$" in filled_tex
        assert r"\par" in filled_tex
