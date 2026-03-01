"""Tests for the file namer module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from autocustomizeresume.namer import build_name, build_variables, handle_output


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    first="Jane",
    last="Doe",
    output_resume="{last}, {first} - Resume.pdf",
    output_cover="{last}, {first} - Cover Letter.pdf",
    history_resume="{company} - {role} - Resume - {timestamp}.pdf",
    history_cover="{company} - {role} - Cover Letter - {timestamp}.pdf",
    output_dir="output",
    history_dir="history",
):
    """Build a minimal Config-like object for namer tests."""
    from types import SimpleNamespace

    user = SimpleNamespace(first_name=first, last_name=last)
    naming = SimpleNamespace(
        output_resume=output_resume,
        output_cover=output_cover,
        history_resume=history_resume,
        history_cover=history_cover,
    )
    paths = SimpleNamespace(output_dir=output_dir, history_dir=history_dir)
    return SimpleNamespace(user=user, naming=naming, paths=paths)


def _make_analysis(company="Google", role="SWE"):
    from autocustomizeresume.schemas import JDAnalysis
    return JDAnalysis(
        company=company,
        role=role,
        seniority="mid",
        domain="tech",
        key_skills=[],
        technologies=[],
    )


# ---------------------------------------------------------------------------
# build_name
# ---------------------------------------------------------------------------

class TestBuildName:
    def test_basic_substitution(self):
        v = {"last": "Doe", "first": "Jane"}
        assert build_name("{last}, {first} - Resume.pdf", v) == "Doe, Jane - Resume.pdf"

    def test_all_variables(self):
        v = {
            "first": "Jane", "last": "Doe",
            "company": "Acme", "role": "Dev",
            "date": "2026-01-01", "timestamp": "2026-01-01_120000",
        }
        result = build_name("{company} - {role} - {timestamp}.pdf", v)
        assert result == "Acme - Dev - 2026-01-01_120000.pdf"

    def test_missing_variable_raises(self):
        with pytest.raises(KeyError):
            build_name("{missing} file.pdf", {"first": "Jane"})


# ---------------------------------------------------------------------------
# build_variables
# ---------------------------------------------------------------------------

class TestBuildVariables:
    @patch("autocustomizeresume.namer.datetime")
    def test_all_keys_present(self, mock_dt):
        from datetime import datetime as real_dt
        fixed = real_dt(2026, 3, 15, 10, 30, 45)
        mock_dt.now.return_value = fixed
        mock_dt.side_effect = lambda *a, **kw: real_dt(*a, **kw)

        config = _make_config()
        analysis = _make_analysis()
        v = build_variables(config, analysis)

        assert v["first"] == "Jane"
        assert v["last"] == "Doe"
        assert v["company"] == "Google"
        assert v["role"] == "SWE"
        assert v["date"] == "2026-03-15"
        assert v["timestamp"] == "2026-03-15_103045"


# ---------------------------------------------------------------------------
# handle_output
# ---------------------------------------------------------------------------

class TestHandleOutput:
    def test_copies_resume_to_output_and_history(self, tmp_path):
        from autocustomizeresume.pipeline import PipelineResult

        # Create a fake PDF
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("fake pdf content")

        out_dir = tmp_path / "output"
        hist_dir = tmp_path / "history"

        config = _make_config(output_dir=str(out_dir), history_dir=str(hist_dir))
        analysis = _make_analysis()
        result = PipelineResult(
            resume_pdf=fake_pdf,
            analysis=analysis,
            selection=None,  # type: ignore[arg-type]
        )

        handle_output(result, config)

        output_files = list(out_dir.iterdir())
        history_files = list(hist_dir.iterdir())
        assert len(output_files) == 1
        assert len(history_files) == 1
        assert "Doe, Jane - Resume.pdf" in output_files[0].name

    def test_copies_cover_letter_when_present(self, tmp_path):
        from autocustomizeresume.pipeline import PipelineResult

        fake_resume = tmp_path / "resume.pdf"
        fake_resume.write_text("resume")
        fake_cl = tmp_path / "cover.pdf"
        fake_cl.write_text("cover letter")

        out_dir = tmp_path / "output"
        hist_dir = tmp_path / "history"

        config = _make_config(output_dir=str(out_dir), history_dir=str(hist_dir))
        analysis = _make_analysis()
        result = PipelineResult(
            resume_pdf=fake_resume,
            analysis=analysis,
            selection=None,  # type: ignore[arg-type]
            cover_letter_pdf=fake_cl,
        )

        handle_output(result, config)

        output_files = sorted(f.name for f in out_dir.iterdir())
        assert len(output_files) == 2
        assert any("Cover Letter" in f for f in output_files)
        assert any("Resume" in f for f in output_files)

    def test_creates_directories(self, tmp_path):
        from autocustomizeresume.pipeline import PipelineResult

        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("fake")

        out_dir = tmp_path / "nested" / "output"
        hist_dir = tmp_path / "nested" / "history"

        config = _make_config(output_dir=str(out_dir), history_dir=str(hist_dir))
        analysis = _make_analysis()
        result = PipelineResult(
            resume_pdf=fake_pdf,
            analysis=analysis,
            selection=None,  # type: ignore[arg-type]
        )

        handle_output(result, config)
        assert out_dir.exists()
        assert hist_dir.exists()
