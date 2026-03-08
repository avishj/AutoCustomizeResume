"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock, patch

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
from autocustomizeresume.pipeline import PipelineResult, run_pipeline
from autocustomizeresume.schemas import (
    ContentSelection,
    JDAnalysis,
    SectionDecision,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(cover_letter_enabled=False) -> Config:
    return Config(
        user=UserConfig(
            first_name="Jane",
            last_name="Doe",
            phone="555-0000",
            email="jane@example.com",
            linkedin="",
            website="",
            degree="MS CS",
            university="MIT",
        ),
        naming=NamingConfig(
            output_resume="{last}, {first} - Resume.pdf",
            output_cover="{last}, {first} - Cover Letter.pdf",
            history_resume="{company} - {role} - Resume - {timestamp}.pdf",
            history_cover="{company} - {role} - Cover Letter - {timestamp}.pdf",
        ),
        llm=LLMConfig(
            base_url="https://api.example.com/v1",
            model="test-model",
            api_key_env="TEST_API_KEY",
        ),
        cover_letter=CoverLetterConfig(
            enabled=cover_letter_enabled,
            template="templates/cover_letter_template.tex",
            signature_path="",
        ),
        paths=PathsConfig(
            master_resume="resume.tex",
            jd_file="jd.txt",
            output_dir="output",
            history_dir="history",
        ),
        watcher=WatcherConfig(debounce_seconds=5),
    )


@pytest.fixture
def resume_config(tmp_path):
    """Config with master_resume pointing to a real file in tmp_path."""
    resume_tex = tmp_path / "resume.tex"
    resume_tex.write_text(r"\documentclass{article}")
    return replace(
        _make_config(),
        paths=PathsConfig(
            master_resume=str(resume_tex),
            jd_file="jd.txt",
            output_dir="output",
            history_dir="history",
        ),
    )


def _make_analysis() -> JDAnalysis:
    return JDAnalysis(
        company="Acme",
        role="SWE",
        seniority="mid",
        domain="tech",
        key_skills=["Python"],
        technologies=["Django"],
    )


def _make_selection() -> ContentSelection:
    return ContentSelection(
        sections=[SectionDecision(id="exp", include=True)],
        skill_categories=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRunPipeline:
    @patch("autocustomizeresume.pipeline.compile_with_enforcement")
    @patch("autocustomizeresume.pipeline.select_content")
    @patch("autocustomizeresume.pipeline.analyze_jd")
    @patch("autocustomizeresume.pipeline.LLMClient")
    @patch("autocustomizeresume.pipeline.parse_resume")
    def test_resume_pipeline(
        self,
        mock_parse,
        _mock_llm_cls,
        mock_analyze,
        mock_select,
        mock_compile,
        tmp_path,
        resume_config,
    ):
        parsed = MagicMock()
        mock_parse.return_value = parsed
        analysis = _make_analysis()
        mock_analyze.return_value = analysis
        selection = _make_selection()
        mock_select.return_value = selection

        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("pdf")
        mock_compile.return_value = (fake_pdf, selection)

        # Run
        result = run_pipeline("Some JD text", resume_config)

        # Verify
        assert isinstance(result, PipelineResult)
        assert result.resume_pdf == fake_pdf
        assert result.analysis == analysis
        assert result.selection == selection
        assert result.cover_letter_pdf is None

        mock_parse.assert_called_once()
        mock_analyze.assert_called_once()
        mock_select.assert_called_once()
        mock_compile.assert_called_once()

    @patch("autocustomizeresume.pipeline.build_cover_letter")
    @patch("autocustomizeresume.pipeline.compile_with_enforcement")
    @patch("autocustomizeresume.pipeline.select_content")
    @patch("autocustomizeresume.pipeline.analyze_jd")
    @patch("autocustomizeresume.pipeline.LLMClient")
    @patch("autocustomizeresume.pipeline.parse_resume")
    def test_cover_letter_enabled(
        self,
        mock_parse,
        _mock_llm_cls,
        mock_analyze,
        mock_select,
        mock_compile,
        mock_build_cl,
        tmp_path,
        resume_config,
    ):
        config = replace(
            resume_config,
            cover_letter=replace(resume_config.cover_letter, enabled=True),
        )

        mock_parse.return_value = MagicMock()
        mock_analyze.return_value = _make_analysis()
        selection = _make_selection()
        mock_select.return_value = selection

        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("pdf")
        mock_compile.return_value = (fake_pdf, selection)

        cl_pdf = tmp_path / "cover.pdf"
        cl_pdf.write_text("cl")
        mock_build_cl.return_value = cl_pdf

        result = run_pipeline("Some JD text", config)

        assert result.cover_letter_pdf == cl_pdf
        mock_build_cl.assert_called_once()

    @patch("autocustomizeresume.pipeline.compile_with_enforcement")
    @patch("autocustomizeresume.pipeline.select_content")
    @patch("autocustomizeresume.pipeline.analyze_jd")
    @patch("autocustomizeresume.pipeline.LLMClient")
    @patch("autocustomizeresume.pipeline.parse_resume")
    def test_company_role_overrides(
        self,
        mock_parse,
        _mock_llm_cls,
        mock_analyze,
        mock_select,
        mock_compile,
        tmp_path,
        resume_config,
    ):
        mock_parse.return_value = MagicMock()
        mock_analyze.return_value = _make_analysis()
        selection = _make_selection()
        mock_select.return_value = selection

        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("pdf")
        mock_compile.return_value = (fake_pdf, selection)

        result = run_pipeline(
            "Some JD text", resume_config, company="Override Corp", role="Lead Dev"
        )

        assert result.analysis.company == "Override Corp"
        assert result.analysis.role == "Lead Dev"

    @patch("autocustomizeresume.pipeline.compile_with_enforcement")
    @patch("autocustomizeresume.pipeline.select_content")
    @patch("autocustomizeresume.pipeline.analyze_jd")
    @patch("autocustomizeresume.pipeline.LLMClient")
    @patch("autocustomizeresume.pipeline.parse_resume")
    def test_cover_letter_disabled(
        self,
        mock_parse,
        _mock_llm_cls,
        mock_analyze,
        mock_select,
        mock_compile,
        tmp_path,
        resume_config,
    ):
        mock_parse.return_value = MagicMock()
        mock_analyze.return_value = _make_analysis()
        selection = _make_selection()
        mock_select.return_value = selection

        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("pdf")
        mock_compile.return_value = (fake_pdf, selection)

        result = run_pipeline("Some JD text", resume_config)

        assert result.cover_letter_pdf is None
