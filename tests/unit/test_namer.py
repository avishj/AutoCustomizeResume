# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the file namer module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from autocustomizeresume.namer import build_variables
from autocustomizeresume.schemas import JDAnalysis

pytestmark = pytest.mark.unit


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
# build_variables
# ---------------------------------------------------------------------------


class TestBuildVariables:
    def test_all_expected_keys_present(self):
        v = build_variables(_make_config(), _make_analysis())
        assert set(v) == {"first", "last", "company", "role", "date", "timestamp"}
