# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for the file namer module (real file I/O)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autocustomizeresume.namer import handle_output
from autocustomizeresume.pipeline import PipelineResult
from autocustomizeresume.schemas import JDAnalysis

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**overrides):
    """Build a minimal Config-like object for namer tests."""
    user = SimpleNamespace(
        first_name=overrides.get("first", "Jane"),
        last_name=overrides.get("last", "Doe"),
    )
    naming = SimpleNamespace(
        output_resume=overrides.get("output_resume", "{last}, {first} - Resume.pdf"),
        output_cover=overrides.get(
            "output_cover",
            "{last}, {first} - Cover Letter.pdf",
        ),
        history_resume=overrides.get(
            "history_resume",
            "{company} - {role} - Resume - {timestamp}.pdf",
        ),
        history_cover=overrides.get(
            "history_cover",
            "{company} - {role} - Cover Letter - {timestamp}.pdf",
        ),
    )
    paths = SimpleNamespace(
        output_dir=overrides.get("output_dir", "output"),
        history_dir=overrides.get("history_dir", "history"),
    )
    return SimpleNamespace(user=user, naming=naming, paths=paths)


def _make_analysis(company="Google", role="SWE"):
    return JDAnalysis(
        company=company,
        role=role,
        seniority="mid",
        domain="tech",
        key_skills=[],
        technologies=[],
    )


# ---------------------------------------------------------------------------
# handle_output
# ---------------------------------------------------------------------------


class TestHandleOutput:
    def test_copies_resume_to_output_and_history(self, tmp_path):
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("fake pdf content")

        out_dir = tmp_path / "output"
        hist_dir = tmp_path / "history"

        config = _make_config(output_dir=str(out_dir), history_dir=str(hist_dir))
        analysis = _make_analysis()
        result = PipelineResult(
            resume_pdf=fake_pdf,
            analysis=analysis,
            selection=None,
        )

        handle_output(result, config)

        output_files = list(out_dir.iterdir())
        history_files = list(hist_dir.iterdir())
        assert len(output_files) == 1
        assert len(history_files) == 1
        assert "Doe, Jane - Resume.pdf" in output_files[0].name

    def test_copies_cover_letter_when_present(self, tmp_path):
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
            selection=None,
            cover_letter_pdf=fake_cl,
        )

        handle_output(result, config)

        output_files = sorted(f.name for f in out_dir.iterdir())
        assert len(output_files) == 2
        assert any("Cover Letter" in f for f in output_files)
        assert any("Resume" in f for f in output_files)

    def test_creates_directories(self, tmp_path):
        fake_pdf = tmp_path / "resume.pdf"
        fake_pdf.write_text("fake")

        out_dir = tmp_path / "nested" / "output"
        hist_dir = tmp_path / "nested" / "history"

        config = _make_config(output_dir=str(out_dir), history_dir=str(hist_dir))
        analysis = _make_analysis()
        result = PipelineResult(
            resume_pdf=fake_pdf,
            analysis=analysis,
            selection=None,
        )

        handle_output(result, config)
        assert out_dir.exists()
        assert hist_dir.exists()
