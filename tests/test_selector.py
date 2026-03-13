"""Tests for the content selector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autocustomizeresume.llm_client import LLMClient, LLMError
from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
)
from autocustomizeresume.schemas import (
    ContentSelection,
    JDAnalysis,
)
from autocustomizeresume.selector import (
    _serialize_resume,
    select_content,
)
from autocustomizeresume.utils import latex_preview

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.llm.base_url = "https://api.example.com/v1"
    cfg.llm.model = "test-model"
    cfg.llm.api_key = "test-key-123"
    return cfg


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
                        heading_lines=r"\resumeSubheading{Acme Corp}{2024}{SWE}{SF}",
                        bullets=[
                            Bullet(
                                tag_type="optional",
                                id="acme-1",
                                text=r"\resumeItem{Built REST API serving 10k rps}",
                            ),
                            Bullet(
                                tag_type="pinned",
                                id="acme-2",
                                text=r"\resumeItem{Reduced p99 latency by 40\%}",
                            ),
                            Bullet(
                                tag_type="optional",
                                id="acme-3",
                                text=r"\resumeItem{Implemented OAuth 2.0 auth flow}",
                            ),
                        ],
                    ),
                    ResumeItem(
                        tag_type="optional",
                        id="widgets",
                        heading_lines=r"\resumeSubheading{Widgets Inc}{2023}{Intern}{NY}",
                        bullets=[
                            Bullet(
                                tag_type="optional",
                                id="widgets-1",
                                text=r"\resumeItem{Built internal dashboard}",
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
                        skills=["Python", "Java", "C++", "Go"],
                        prefix=r"\textbf{Languages}{: ",
                        suffix=r".} \\",
                    ),
                    SkillCategory(
                        name="cloud",
                        display_name=r"Cloud \& Infra",
                        skills=["AWS", "Kubernetes", "Docker", "Terraform"],
                        prefix=r"\textbf{Cloud \& Infra}{: ",
                        suffix=".}",
                    ),
                ],
            ),
        ],
        postamble=r"\end{document}",
    )


_SAMPLE_SELECTION_DICT = {
    "sections": [
        {
            "id": "experience",
            "include": True,
            "items": [
                {
                    "id": "acme",
                    "include": True,
                    "relevance_score": 85,
                    "bullets": [
                        {"id": "acme-1", "include": True, "edited_text": ""},
                        {"id": "acme-3", "include": False, "edited_text": ""},
                    ],
                },
                {
                    "id": "widgets",
                    "include": False,
                    "relevance_score": 20,
                    "bullets": [
                        {"id": "widgets-1", "include": False, "edited_text": ""},
                    ],
                },
            ],
        },
    ],
    "skill_categories": [
        {"name": "languages", "skills": ["Python", "Go", "Java", "C++"]},
        {"name": "cloud", "skills": ["Kubernetes", "Docker", "AWS", "Terraform"]},
    ],
}


def _make_client(response_dict: dict) -> MagicMock:
    client = MagicMock(spec=LLMClient)
    client.chat.return_value = response_dict
    return client


# ---------------------------------------------------------------------------
# select_content() — happy path
# ---------------------------------------------------------------------------


class TestSelectContent:
    def test_returns_content_selection(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        assert isinstance(result, ContentSelection)

    def test_section_decisions(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        assert len(result.sections) == 1
        assert result.sections[0].id == "experience"
        assert result.sections[0].include is True

    def test_item_decisions(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        exp_section = result.sections[0]
        assert len(exp_section.items) == 2
        assert exp_section.items[0].id == "acme"
        assert exp_section.items[0].include is True
        assert exp_section.items[0].relevance_score == 85
        assert exp_section.items[1].id == "widgets"
        assert exp_section.items[1].include is False

    def test_bullet_decisions(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        acme = result.sections[0].items[0]
        assert len(acme.bullets) == 2
        assert acme.bullets[0].id == "acme-1"
        assert acme.bullets[0].include is True
        assert acme.bullets[1].id == "acme-3"
        assert acme.bullets[1].include is False

    def test_skill_categories(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        assert len(result.skill_categories) == 2
        langs = result.skill_categories[0]
        assert langs.name == "languages"
        # Python and Go should be first (most relevant to JD)
        assert langs.skills[0] == "Python"
        assert langs.skills[1] == "Go"

    def test_edited_text_preserved(self):
        selection_with_edit = {
            **_SAMPLE_SELECTION_DICT,
            "sections": [
                {
                    "id": "experience",
                    "include": True,
                    "items": [
                        {
                            "id": "acme",
                            "include": True,
                            "relevance_score": 90,
                            "bullets": [
                                {
                                    "id": "acme-1",
                                    "include": True,
                                    "edited_text": "Built scalable REST API handling 10k rps",
                                },
                            ],
                        },
                    ],
                },
            ],
        }
        client = _make_client(selection_with_edit)
        result = select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        assert result.sections[0].items[0].bullets[0].edited_text == (
            "Built scalable REST API handling 10k rps"
        )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    def test_user_prompt_contains_jd_analysis(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "Acme Corp" in user
        assert "Senior Backend Engineer" in user
        assert "distributed systems" in user
        assert "Python" in user

    def test_user_prompt_contains_resume_data(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert "experience" in user
        assert "acme" in user
        assert "skills" in user.lower()

    def test_system_prompt_mentions_json(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        call_kwargs = client.chat.call_args[1]
        system = call_kwargs["system"]
        assert "JSON" in system or "json" in system

    def test_system_prompt_mentions_rephrasing(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        call_kwargs = client.chat.call_args[1]
        system = call_kwargs["system"]
        assert "edited_text" in system
        assert "rephrasing" in system.lower() or "rephras" in system.lower()

    def test_no_temperature_override(self):
        client = _make_client(_SAMPLE_SELECTION_DICT)
        select_content(
            _make_jd_analysis(),
            _make_parsed_resume(),
            config=_make_config(),
            client=client,
        )
        call_kwargs = client.chat.call_args[1]
        assert "temperature" not in call_kwargs


# ---------------------------------------------------------------------------
# _serialize_resume()
# ---------------------------------------------------------------------------


class TestSerializeResume:
    def test_contains_section_ids(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "education" in result
        assert "experience" in result

    def test_contains_item_ids(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "acme" in result
        assert "widgets" in result

    def test_contains_bullet_ids(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "acme-1" in result
        assert "acme-3" in result

    def test_contains_tag_types(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "pinned" in result
        assert "optional" in result

    def test_contains_skill_categories(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "languages" in result
        assert "cloud" in result

    def test_contains_skill_lists(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "Python" in result
        assert "Kubernetes" in result

    def test_compact_flag_shown_when_set(self):
        parsed = _make_parsed_resume()
        exp = parsed.sections[1]
        assert isinstance(exp, ResumeSection)
        exp.items[0].compact_heading = r"\resumeProjectHeading{\textbf{Acme}}{2024}"
        result = _serialize_resume(parsed)
        assert "has_compact=yes" in result

    def test_compact_flag_absent_when_not_set(self):
        result = _serialize_resume(_make_parsed_resume())
        assert "has_compact" not in result


# ---------------------------------------------------------------------------
# latex_preview()
# ---------------------------------------------------------------------------


class TestLatexPreview:
    def test_strips_resume_item(self):
        result = latex_preview(r"\resumeItem{Built a REST API}")
        assert "Built a REST API" in result
        assert r"\resumeItem" not in result

    def test_strips_textbf(self):
        result = latex_preview(r"\textbf{Languages}{: Python, Java}")
        assert "Languages" in result
        assert r"\textbf" not in result

    def test_strips_href(self):
        result = latex_preview(r"\href{https://example.com}{My Site}")
        assert "My Site" in result
        assert "https://example.com" not in result

    def test_truncates_long_text(self):
        long_text = "x" * 400
        result = latex_preview(long_text)
        assert len(result) <= 300

    def test_collapses_whitespace(self):
        result = latex_preview("hello   \n  world")
        assert result == "hello world"

    def test_empty_input(self):
        assert latex_preview("") == ""


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestSelectContentErrors:
    def test_llm_error_propagates(self):
        client = MagicMock(spec=LLMClient)
        client.chat.side_effect = LLMError("boom")

        with pytest.raises(LLMError, match="boom"):
            select_content(
                _make_jd_analysis(),
                _make_parsed_resume(),
                config=_make_config(),
                client=client,
            )

    def test_creates_client_from_config_when_none(self):
        with patch("autocustomizeresume.selector.LLMClient") as mock_cls:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.chat.return_value = _SAMPLE_SELECTION_DICT
            mock_cls.return_value = mock_instance

            cfg = _make_config()
            result = select_content(
                _make_jd_analysis(),
                _make_parsed_resume(),
                config=cfg,
            )

            mock_cls.assert_called_once_with(cfg)
            assert isinstance(result, ContentSelection)


# ---------------------------------------------------------------------------
# Empty / minimal inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_resume(self):
        """Selector should handle a resume with no sections."""
        empty_resume = ParsedResume(
            preamble=r"\documentclass{article}" "\n" r"\begin{document}",
            header="",
            sections=[],
            postamble=r"\end{document}",
        )
        empty_selection = {"sections": [], "skill_categories": []}
        client = _make_client(empty_selection)

        result = select_content(
            _make_jd_analysis(),
            empty_resume,
            config=_make_config(),
            client=client,
        )
        assert result.sections == []
        assert result.skill_categories == []

    def test_no_optional_content(self):
        """Resume with only pinned content — LLM should return empty selections."""
        pinned_only = ParsedResume(
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
                            heading_lines=r"\resumeSubheading{MIT}{2025}{MS}{MA}",
                        ),
                    ],
                ),
            ],
            postamble=r"\end{document}",
        )
        empty_selection = {"sections": [], "skill_categories": []}
        client = _make_client(empty_selection)

        result = select_content(
            _make_jd_analysis(),
            pinned_only,
            config=_make_config(),
            client=client,
        )
        assert result.sections == []

    def test_float_relevance_score(self):
        """LLM may return a float relevance_score — should be truncated to int."""
        from autocustomizeresume.schemas import ItemDecision

        item = ItemDecision.from_dict(
            {
                "id": "acme",
                "include": True,
                "relevance_score": 85.7,
                "bullets": [],
            }
        )
        assert item.relevance_score == 85

    def test_string_float_relevance_score(self):
        """LLM may return relevance_score as a string like '85.5'."""
        from autocustomizeresume.schemas import ItemDecision

        item = ItemDecision.from_dict(
            {
                "id": "acme",
                "include": True,
                "relevance_score": "85.5",
                "bullets": [],
            }
        )
        assert item.relevance_score == 85

    def test_null_relevance_score(self):
        """LLM may return relevance_score as null — should default to 50."""
        from autocustomizeresume.schemas import ItemDecision

        item = ItemDecision.from_dict(
            {
                "id": "acme",
                "include": True,
                "relevance_score": None,
                "bullets": [],
            }
        )
        assert item.relevance_score == 50

    def test_zero_relevance_score_preserved(self):
        """A relevance_score of 0 is valid and must not become 50."""
        from autocustomizeresume.schemas import ItemDecision

        item = ItemDecision.from_dict(
            {
                "id": "acme",
                "include": True,
                "relevance_score": 0,
                "bullets": [],
            }
        )
        assert item.relevance_score == 0

    def test_null_jd_fields_default_gracefully(self):
        """LLM may return null for JDAnalysis fields — should use defaults."""
        from autocustomizeresume.schemas import JDAnalysis

        analysis = JDAnalysis.from_dict(
            {
                "company": None,
                "role": None,
                "seniority": None,
                "domain": None,
                "key_skills": None,
                "technologies": None,
            }
        )
        assert analysis.company == "Unknown"
        assert analysis.role == "Unknown"
        assert analysis.seniority == "unknown"
        assert analysis.domain == "unknown"
        assert analysis.key_skills == []
        assert analysis.technologies == []

    def test_null_lists_default_to_empty(self):
        """LLM may return null for list fields — should not crash."""
        from autocustomizeresume.schemas import (
            ContentSelection,
            ItemDecision,
            SectionDecision,
        )

        sel = ContentSelection.from_dict(
            {
                "sections": None,
                "skill_categories": None,
            }
        )
        assert sel.sections == []
        assert sel.skill_categories == []

        sec = SectionDecision.from_dict(
            {
                "id": "exp",
                "include": True,
                "items": None,
            }
        )
        assert sec.items == []

        item = ItemDecision.from_dict(
            {
                "id": "acme",
                "include": True,
                "relevance_score": 80,
                "bullets": None,
            }
        )
        assert item.bullets == []

    def test_missing_include_warns_and_defaults_true(self, caplog):
        """Missing 'include' key should log a warning and default to True."""
        import logging

        from autocustomizeresume.schemas import BulletDecision

        with caplog.at_level(logging.WARNING, logger="autocustomizeresume.schemas"):
            bullet = BulletDecision.from_dict({"id": "b1"})

        assert bullet.include is True
        assert "missing 'include'" in caplog.text.lower()
