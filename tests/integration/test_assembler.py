# SPDX-FileCopyrightText: 2026 Avish Jha <avish.j@pm.me>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Integration tests for the LaTeX assembler (fixture-based)."""

from __future__ import annotations

from pathlib import Path

import pytest

from autocustomizeresume.assembler import assemble_tex
from autocustomizeresume.parser import parse_resume
from autocustomizeresume.schemas import ContentSelection

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestAssembleTexFixture:
    @pytest.fixture
    def parsed(self):
        return parse_resume(_load_fixture("sample_tagged.tex"))

    def test_exclude_bullet(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
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
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": False,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "REST API" in result
        assert "OAuth" not in result
        # Pinned bullet acme-3 always present
        assert "p99 latency" in result

    def test_edited_text_substitution(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
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
                                        "edited_text": (
                                            r"\resumeItem{Built a RESTful"
                                            r" microservice.}"
                                        ),
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Python"]},
                    {"name": "cloud", "skills": ["AWS"]},
                    {"name": "frameworks", "skills": ["FastAPI"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "RESTful microservice" in result
        assert "10k requests" not in result

    def test_skill_reordering(self, parsed):
        selection = ContentSelection.from_dict(
            {
                "sections": [
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
                                        "edited_text": "",
                                    },
                                    {
                                        "id": "acme-2",
                                        "include": True,
                                        "edited_text": "",
                                    },
                                ],
                            },
                            {
                                "id": "widgets",
                                "include": False,
                                "relevance_score": 20,
                                "bullets": [],
                            },
                        ],
                    },
                    {"id": "projects", "include": False, "items": []},
                ],
                "skill_categories": [
                    {"name": "languages", "skills": ["Go", "Python"]},
                    {"name": "cloud", "skills": ["Kubernetes", "AWS"]},
                    {"name": "frameworks", "skills": ["React"]},
                ],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Go, Python" in result
        assert "Kubernetes, AWS" in result
        # Original had 4 frameworks, now only React
        assert "Spring Boot" not in result

    def test_pinned_section_always_present(self, parsed):
        """Education (pinned) appears even with empty selection."""
        selection = ContentSelection.from_dict(
            {
                "sections": [],
                "skill_categories": [],
            }
        )
        result = assemble_tex(parsed, selection)
        assert "Education" in result
        assert "MIT" in result
