"""Structured output schemas for LLM responses.

Dataclasses representing the JSON shapes returned by the JD analyzer
and content selector.  Each class has a ``from_dict`` class-method that
validates raw ``dict`` data (as parsed from LLM JSON output) and returns
a typed instance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# JD analysis schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JDAnalysis:
    """Structured metadata extracted from a job description.

    Attributes
    ----------
    company:
        Company name (or ``"Unknown"`` if the JD doesn't name one).
    role:
        Job title / role name.
    seniority:
        Seniority level (e.g. ``"junior"``, ``"mid"``, ``"senior"``,
        ``"staff"``, ``"lead"``).  ``"unknown"`` if not determinable.
    domain:
        Industry / domain (e.g. ``"fintech"``, ``"healthcare"``).
    key_skills:
        Important skills, competencies, or qualifications mentioned.
    technologies:
        Specific technologies, frameworks, tools, or languages.
    """

    company: str
    role: str
    seniority: str
    domain: str
    key_skills: list[str]
    technologies: list[str]

    @classmethod
    def from_dict(cls, data: dict) -> JDAnalysis:
        """Parse and validate a dict (from LLM JSON) into a JDAnalysis."""
        return cls(
            company=str(data.get("company") or "Unknown").strip() or "Unknown",
            role=str(data.get("role") or "Unknown").strip() or "Unknown",
            seniority=str(data.get("seniority") or "unknown").strip().lower(),
            domain=str(data.get("domain") or "unknown").strip(),
            key_skills=_str_list(data.get("key_skills", [])),
            technologies=_str_list(data.get("technologies", [])),
        )


# ---------------------------------------------------------------------------
# Content selection schema
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BulletDecision:
    """Include/exclude decision for a single bullet, with optional edit.

    Attributes
    ----------
    id:
        The bullet's tag ID (e.g. ``"acme-1"``).
    include:
        Whether to include this bullet.
    edited_text:
        If non-empty, a minor rephrasing of the bullet text to better
        match JD terminology.  Must preserve the core meaning.  Empty
        string means keep the original text verbatim.
    """

    id: str
    include: bool
    edited_text: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> BulletDecision:
        if "include" not in data:
            logger.warning(
                "BulletDecision missing 'include' for id=%s, defaulting to True",
                data.get("id", "?"),
            )
        return cls(
            id=str(data.get("id", "")),
            include=bool(data.get("include", True)),
            edited_text=str(data.get("edited_text", "")),
        )


@dataclass(frozen=True)
class ItemDecision:
    """Include/exclude decision for a resume item (job, project, etc.).

    Attributes
    ----------
    id:
        The item's tag ID (e.g. ``"snap"``, ``"siemens"``).
    include:
        Whether to include this item.
    relevance_score:
        0-100 score indicating how relevant this item is to the JD.
    bullets:
        Per-bullet decisions for optional bullets within this item.
        Pinned bullets are always included and won't appear here.
    """

    id: str
    include: bool
    relevance_score: int
    bullets: list[BulletDecision] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ItemDecision:
        if "include" not in data:
            logger.warning(
                "ItemDecision missing 'include' for id=%s, defaulting to True",
                data.get("id", "?"),
            )
        return cls(
            id=str(data.get("id", "")),
            include=bool(data.get("include", True)),
            relevance_score=_coerce_score(data.get("relevance_score")),
            bullets=[
                BulletDecision.from_dict(b)
                for b in (data.get("bullets") or [])
            ],
        )


@dataclass(frozen=True)
class SectionDecision:
    """Include/exclude decision for a resume section.

    Attributes
    ----------
    id:
        The section's tag ID (e.g. ``"experience"``, ``"projects"``).
    include:
        Whether to include this section.  Pinned sections are always
        included and won't appear in the LLM output.
    items:
        Per-item decisions for optional items within this section.
    """

    id: str
    include: bool
    items: list[ItemDecision] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SectionDecision:
        if "include" not in data:
            logger.warning(
                "SectionDecision missing 'include' for id=%s, defaulting to True",
                data.get("id", "?"),
            )
        return cls(
            id=str(data.get("id", "")),
            include=bool(data.get("include", True)),
            items=[
                ItemDecision.from_dict(it)
                for it in (data.get("items") or [])
            ],
        )


@dataclass(frozen=True)
class SkillCategoryDecision:
    """Skill selection and ordering for a single subcategory.

    All subcategories are kept; the LLM decides which individual skills
    to include and in what order.

    Attributes
    ----------
    name:
        The skill category tag name (e.g. ``"languages"``).
    skills:
        Ordered list of skills to include.  Skills not in this list
        are excluded.  Order reflects JD relevance (most relevant first).
    """

    name: str
    skills: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> SkillCategoryDecision:
        return cls(
            name=str(data.get("name", "")),
            skills=_str_list(data.get("skills", [])),
        )


@dataclass(frozen=True)
class ContentSelection:
    """Full content selection result from the LLM.

    Combines section/item/bullet decisions with skill reordering.
    """

    sections: list[SectionDecision] = field(default_factory=list)
    skill_categories: list[SkillCategoryDecision] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> ContentSelection:
        return cls(
            sections=[
                SectionDecision.from_dict(s)
                for s in (data.get("sections") or [])
            ],
            skill_categories=[
                SkillCategoryDecision.from_dict(sc)
                for sc in (data.get("skill_categories") or [])
            ],
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_score(val: object, default: int = 50) -> int:
    """Coerce a value to an int score, clamped to 0-100."""
    if val is None:
        return default
    try:
        return max(0, min(100, int(float(val))))
    except (TypeError, ValueError):
        return default


def _str_list(val: object) -> list[str]:
    """Coerce a value into a list of non-empty strings."""
    if not isinstance(val, list):
        return []
    return [str(item).strip() for item in val if str(item).strip()]
