"""Tests for the JD analyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from autocustomizeresume.analyzer import analyze_jd
from autocustomizeresume.llm_client import LLMClient, LLMError
from autocustomizeresume.schemas import JDAnalysis

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_JD = """\
Software Engineer — Backend (Senior)
Acme Corp — San Francisco, CA

We're looking for a Senior Backend Engineer to join our Platform team.
You'll build scalable microservices in Python and Go, deploy on Kubernetes,
and work with PostgreSQL and Redis.  Experience with distributed systems,
CI/CD pipelines, and observability tooling (Prometheus, Grafana) is a plus.
"""

_SAMPLE_ANALYSIS_DICT = {
    "company": "Acme Corp",
    "role": "Senior Backend Engineer",
    "seniority": "senior",
    "domain": "platform engineering",
    "key_skills": ["distributed systems", "microservices", "CI/CD", "observability"],
    "technologies": [
        "Python",
        "Go",
        "Kubernetes",
        "PostgreSQL",
        "Redis",
        "Prometheus",
        "Grafana",
    ],
}


def _make_config() -> MagicMock:
    cfg = MagicMock()
    cfg.llm.base_url = "https://api.example.com/v1"
    cfg.llm.model = "test-model"
    cfg.llm.api_key = "test-key-123"
    return cfg


def _make_client(response_dict: dict) -> MagicMock:
    """Build a mock LLMClient whose chat returns *response_dict*."""
    client = MagicMock(spec=LLMClient)
    client.chat.return_value = response_dict
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAnalyzeJD:
    def test_returns_jd_analysis(self):
        client = _make_client(_SAMPLE_ANALYSIS_DICT)
        result = analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)

        assert isinstance(result, JDAnalysis)
        assert result.company == "Acme Corp"
        assert result.role == "Senior Backend Engineer"
        assert result.seniority == "senior"
        assert result.domain == "platform engineering"
        assert "distributed systems" in result.key_skills
        assert "Python" in result.technologies

    def test_passes_jd_as_user_prompt(self):
        client = _make_client(_SAMPLE_ANALYSIS_DICT)
        analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)

        call_kwargs = client.chat.call_args[1]
        user = call_kwargs["user"]
        assert _SAMPLE_JD in user
        # JD should be wrapped in XML delimiters for prompt-injection hardening
        assert user.startswith("<jd>")
        assert user.endswith("</jd>")

    def test_no_temperature_override(self):
        client = _make_client(_SAMPLE_ANALYSIS_DICT)
        analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)

        call_kwargs = client.chat.call_args[1]
        assert "temperature" not in call_kwargs

    def test_system_prompt_requests_json(self):
        client = _make_client(_SAMPLE_ANALYSIS_DICT)
        analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)

        call_kwargs = client.chat.call_args[1]
        system = call_kwargs["system"]
        assert "JSON" in system or "json" in system


# ---------------------------------------------------------------------------
# Missing / edge-case fields
# ---------------------------------------------------------------------------


class TestAnalyzeJDEdgeCases:
    def test_missing_company_defaults_unknown(self):
        data = {**_SAMPLE_ANALYSIS_DICT, "company": ""}
        client = _make_client(data)
        result = analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)
        assert result.company == "Unknown"

    def test_missing_key_entirely(self):
        data = {"role": "SWE"}  # minimal
        client = _make_client(data)
        result = analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)
        assert result.company == "Unknown"
        assert result.role == "SWE"
        assert result.key_skills == []
        assert result.technologies == []

    def test_seniority_normalised_to_lower(self):
        data = {**_SAMPLE_ANALYSIS_DICT, "seniority": "  Senior  "}
        client = _make_client(data)
        result = analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)
        assert result.seniority == "senior"

    def test_non_list_skills_coerced(self):
        data = {**_SAMPLE_ANALYSIS_DICT, "key_skills": "not a list"}
        client = _make_client(data)
        result = analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)
        assert result.key_skills == []


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestAnalyzeJDErrors:
    def test_llm_error_propagates(self):
        client = MagicMock(spec=LLMClient)
        client.chat.side_effect = LLMError("boom")

        with pytest.raises(LLMError, match="boom"):
            analyze_jd(_SAMPLE_JD, config=_make_config(), client=client)

    def test_creates_client_from_config_when_none(self):
        """When no client is passed, a new one is built from config."""
        with patch("autocustomizeresume.analyzer.LLMClient") as mock_cls:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.chat.return_value = _SAMPLE_ANALYSIS_DICT
            mock_cls.return_value = mock_instance

            cfg = _make_config()
            result = analyze_jd(_SAMPLE_JD, config=cfg)

            mock_cls.assert_called_once_with(cfg)
            assert isinstance(result, JDAnalysis)
