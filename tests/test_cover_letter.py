"""Tests for the cover letter generator."""

from __future__ import annotations

import shutil
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
# Shared helpers
# ---------------------------------------------------------------------------

def _make_config(**overrides) -> Config:
    """Build a Config with sensible defaults for testing."""
    user_kw = overrides.pop("user", {})
    cl_kw = overrides.pop("cover_letter", {})

    user_defaults = dict(
        first_name="Jane",
        last_name="Doe",
        phone="555-123-4567",
        email="jane@example.com",
        linkedin="linkedin.com/in/janedoe",
        website="janedoe.dev",
        degree="MS Computer Science",
        university="MIT",
    )
    user_defaults.update(user_kw)

    cl_defaults = dict(
        enabled=True,
        template="templates/cover_letter_template.tex",
        style="Professional and concise.",
        signature_path="",
    )
    cl_defaults.update(cl_kw)

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
        cover_letter=CoverLetterConfig(**cl_defaults),
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
                                text=r"\resumeItem{Wrote unit tests with 90\% coverage}",
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

    def test_includes_pinned_section(self):
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        assert "Education" in summary
        assert "MIT" in summary

    def test_includes_pinned_bullets(self):
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        # Pinned bullet text should appear (LaTeX stripped by _latex_preview)
        assert "TA for Distributed Systems" in summary

    def test_includes_optional_section_when_selected(self):
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        assert "Experience" in summary
        assert "Acme" in summary

    def test_excludes_optional_section_when_not_selected(self):
        sel = ContentSelection(
            sections=[
                SectionDecision(id="experience", include=False, items=[]),
            ],
            skill_categories=[],
        )
        summary = _summarize_selected_content(_make_parsed_resume(), sel)
        assert "Experience" not in summary

    def test_includes_selected_optional_bullet(self):
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        # acme-2 is optional and included
        assert "unit tests" in summary or "coverage" in summary

    def test_excludes_unselected_optional_bullet(self):
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
                                    id="acme-2", include=False, edited_text=""
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            skill_categories=[],
        )
        summary = _summarize_selected_content(_make_parsed_resume(), sel)
        # acme-2 text should not appear (excluded)
        assert "90" not in summary

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
                                    edited_text=r"\resumeItem{Achieved 95\% test coverage}",
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

    def test_includes_skills_section(self):
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        assert "Languages" in summary
        assert "Python" in summary
        assert "Go" in summary

    def test_skills_respects_selection(self):
        """Selected skills list is used, not the original full list."""
        summary = _summarize_selected_content(
            _make_parsed_resume(), _make_selection()
        )
        # "Java" is in the original but not in the selection
        assert "Java" not in summary
        # "FastAPI" is selected
        assert "FastAPI" in summary

    def test_excludes_item_when_not_included(self):
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
        # Item heading should not appear
        assert "Acme" not in summary

    def test_empty_selection(self):
        sel = ContentSelection(sections=[], skill_categories=[])
        summary = _summarize_selected_content(_make_parsed_resume(), sel)
        # Only pinned content appears
        assert "Education" in summary
        assert "Experience" not in summary


class TestGenerateCoverLetterBody:
    """Tests for generate_cover_letter_body() with mocked LLM."""

    def test_returns_llm_response_stripped(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "  Body text here.  \n"

        result = generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )
        assert result == "Body text here."

    def test_prompt_contains_jd_analysis(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "<jd_analysis>" in user
        assert "Acme Corp" in user
        assert "Senior Backend Engineer" in user

    def test_prompt_contains_resume_summary(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "<resume_summary>" in user
        # Should include content from the resume summary
        assert "Education" in user or "Experience" in user

    def test_prompt_contains_style(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        cfg = _make_config(cover_letter={"style": "Casual and friendly."})
        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "<style>" in user
        assert "Casual and friendly." in user

    def test_default_style_when_empty(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        cfg = _make_config(cover_letter={"style": ""})
        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=cfg,
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "Professional, concise." in user

    def test_uses_temperature_04(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        assert call_kwargs["temperature"] == pytest.approx(0.4)

    def test_creates_client_from_config_when_none(self):
        with patch("autocustomizeresume.cover_letter.LLMClient") as mock_cls:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.chat.return_value = "Body."
            mock_cls.return_value = mock_instance

            cfg = _make_config()
            generate_cover_letter_body(
                _make_jd_analysis(),
                _make_parsed_resume(),
                _make_selection(),
                config=cfg,
            )

            mock_cls.assert_called_once_with(cfg)

    def test_system_prompt_mentions_rules(self):
        client = MagicMock(spec=LLMClient)
        client.chat.return_value = "Body."

        generate_cover_letter_body(
            _make_jd_analysis(),
            _make_parsed_resume(),
            _make_selection(),
            config=_make_config(),
            client=client,
        )

        call_kwargs = client.chat.call_args[1]
        system = call_kwargs["system"]
        assert "plain text" in system.lower()
        assert "greeting" in system.lower() or "salutation" in system.lower()


# ===========================================================================
# 5.4b — LaTeX escaping + template injection
# ===========================================================================


class TestEscapeLatex:
    """Tests for _escape_latex()."""

    def test_ampersand(self):
        assert _escape_latex("A & B") == r"A \& B"

    def test_percent(self):
        assert _escape_latex("100%") == r"100\%"

    def test_dollar(self):
        assert _escape_latex("$100") == r"\$100"

    def test_hash(self):
        assert _escape_latex("#1") == r"\#1"

    def test_underscore(self):
        assert _escape_latex("foo_bar") == r"foo\_bar"

    def test_tilde(self):
        assert _escape_latex("~") == r"\textasciitilde{}"

    def test_caret(self):
        assert _escape_latex("x^2") == r"x\textasciicircum{}2"

    def test_braces(self):
        assert _escape_latex("{hello}") == r"\{hello\}"

    def test_backslash(self):
        assert _escape_latex("a\\b") == r"a\textbackslash{}b"

    def test_backslash_with_braces(self):
        """Backslash followed by braces: no double-escaping."""
        result = _escape_latex("\\{")
        assert r"\textbackslash{}" in result
        assert r"\{" in result

    def test_no_special_chars(self):
        assert _escape_latex("Hello World") == "Hello World"

    def test_multiple_specials(self):
        result = _escape_latex("A & B $100 #1 _x")
        assert r"\&" in result
        assert r"\$" in result
        assert r"\#" in result
        assert r"\_" in result

    def test_empty_string(self):
        assert _escape_latex("") == ""


class TestPlainTextToLatex:
    """Tests for _plain_text_to_latex()."""

    def test_single_paragraph(self):
        result = _plain_text_to_latex("Hello world.")
        assert result == "Hello world."
        assert r"\par" not in result

    def test_two_paragraphs(self):
        result = _plain_text_to_latex("Para one.\n\nPara two.")
        assert r"\par" in result
        assert "Para one." in result
        assert "Para two." in result

    def test_multiple_blank_lines(self):
        result = _plain_text_to_latex("A.\n\n\n\nB.")
        # Multiple blank lines should collapse to single \par
        assert result.count(r"\par") == 1

    def test_escapes_special_chars_in_paragraphs(self):
        result = _plain_text_to_latex("100% of $20\n\nA & B")
        assert r"\%" in result
        assert r"\$" in result
        assert r"\&" in result

    def test_strips_whitespace_from_paragraphs(self):
        result = _plain_text_to_latex("  A.  \n\n  B.  ")
        # Paragraphs should be stripped
        assert result.startswith("A.")
        assert result.endswith("B.")


class TestBuildSignatureBlock:
    """Tests for _build_signature_block()."""

    def test_empty_path_returns_empty(self):
        assert _build_signature_block("") == ""
        assert _build_signature_block("   ") == ""

    def test_returns_latex_with_filename(self):
        result = _build_signature_block("coverletter/signature.png")
        assert "signature.png" in result
        assert r"\includegraphics" in result

    def test_uses_only_filename(self):
        result = _build_signature_block("/full/path/to/sig.png")
        # Should NOT contain the full path
        assert "/full/path/to/" not in result
        assert "sig.png" in result


class TestFormatDate:
    """Tests for _format_date()."""

    def test_format(self):
        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 2, 28)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = _format_date()
            assert result == "February 28, 2026"


class TestInjectTemplate:
    """Tests for inject_template()."""

    def test_replaces_first_name(self):
        template = "Hello {{FIRST_NAME}}!"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "Jane" in result
        assert "{{FIRST_NAME}}" not in result

    def test_replaces_last_name(self):
        template = "Hello {{LAST_NAME}}!"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "Doe" in result

    def test_replaces_phone(self):
        template = "Phone: {{PHONE}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "555-123-4567" in result

    def test_replaces_email(self):
        template = "Email: {{EMAIL}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "jane@example.com" in result

    def test_replaces_linkedin(self):
        template = "{{LINKEDIN}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "linkedin.com/in/janedoe" in result

    def test_replaces_website(self):
        template = "{{WEBSITE}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "janedoe.dev" in result

    def test_replaces_degree(self):
        template = "{{DEGREE}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "MS Computer Science" in result

    def test_replaces_university(self):
        template = "{{UNIVERSITY}}"
        result = inject_template(
            template, config=_make_config(), body_text="Body."
        )
        assert "MIT" in result

    def test_replaces_body(self):
        template = "{{BODY}}"
        result = inject_template(
            template, config=_make_config(), body_text="My cover letter body."
        )
        assert "My cover letter body." in result
        assert "{{BODY}}" not in result

    def test_replaces_date(self):
        template = "{{DATE}}"
        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 15)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = inject_template(
                template, config=_make_config(), body_text="Body."
            )
        assert "March 15, 2026" in result

    def test_replaces_signature_block(self):
        cfg = _make_config(cover_letter={"signature_path": "sig.png"})
        template = "{{SIGNATURE_BLOCK}}"
        result = inject_template(template, config=cfg, body_text="Body.")
        assert r"\includegraphics" in result
        assert "sig.png" in result

    def test_empty_signature_block(self):
        cfg = _make_config(cover_letter={"signature_path": ""})
        template = "before{{SIGNATURE_BLOCK}}after"
        result = inject_template(template, config=cfg, body_text="Body.")
        assert result == "beforeafter"

    def test_escapes_user_info(self):
        """User info with LaTeX special chars is properly escaped."""
        cfg = _make_config(user={"email": "user_name@example.com"})
        template = "{{EMAIL}}"
        result = inject_template(template, config=cfg, body_text="Body.")
        assert r"\_" in result

    def test_warns_on_unreplaced_placeholders(self, caplog):
        template = "{{FIRST_NAME}} {{UNKNOWN_THING}}"
        import logging
        with caplog.at_level(logging.WARNING):
            inject_template(
                template, config=_make_config(), body_text="Body."
            )
        assert "UNKNOWN_THING" in caplog.text

    def test_full_template(self):
        """Injection against the real template produces no remaining placeholders."""
        template_path = Path("templates/cover_letter_template.tex")
        if not template_path.exists():
            pytest.skip("Template not available")
        template = template_path.read_text(encoding="utf-8")
        cfg = _make_config(cover_letter={"signature_path": "sig.png"})

        with patch("autocustomizeresume.cover_letter.date") as mock_date:
            mock_date.today.return_value = date(2026, 1, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            result = inject_template(template, config=cfg, body_text="Body text.")

        import re
        remaining = re.findall(r"\{\{[A-Z_]+\}\}", result)
        # {{PLACEHOLDER}} in a comment is expected — filter it out
        remaining = [p for p in remaining if p != "{{PLACEHOLDER}}"]
        assert remaining == [], f"Unreplaced placeholders: {remaining}"
