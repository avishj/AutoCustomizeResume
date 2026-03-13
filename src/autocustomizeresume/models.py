"""Data models for a parsed tagged resume.

These dataclasses represent the structured output of the resume parser.
They are consumed by the LLM selector (to decide what to include/exclude/
tweak) and by the assembler (to reconstruct LaTeX from selections).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

#: The two valid tag types for BEGIN/END markers.
TagType = Literal["pinned", "optional"]


@dataclass
class Bullet:
    r"""A single \\resumeItem bullet within a resume item.

    The LLM can include/exclude individual bullets and make minor
    text edits (keyword incorporation) to optional bullets.
    """

    tag_type: TagType
    id: str  # e.g. "snap-1", "snap-2"
    text: str  # raw LaTeX of the bullet (the full \\resumeItem{...} line(s))


@dataclass
class ResumeItem:
    r"""A single entry within a section (e.g. one job, project, publication).

    Contains heading lines (the \\resumeSubheading etc.) and optionally
    tagged bullets underneath.
    """

    tag_type: TagType
    id: str  # e.g. "snap", "siemens", "addverb"
    heading_lines: str  # raw LaTeX for the heading (before bullets)
    bullets: list[Bullet] = field(default_factory=list)
    # Raw LaTeX fragments between/around bullets (list wrappers, spacing, etc.)
    # Stored as (position, text) pairs where position is the index in bullets
    # before which the content appears. len(bullets) means after the last bullet.
    interstitial: list[tuple[int, str]] = field(default_factory=list)
    # Optional compact one-liner (e.g. \resumeProjectHeading) used when the
    # item is included but all its bullets are excluded.
    compact_heading: str | None = None


@dataclass
class SkillCategory:
    """A single skill subcategory (e.g. Languages, Frameworks & Tools).

    The LLM can add, remove, and reorder skills within each category.
    """

    name: str  # tag ID, e.g. "languages", "cloud-infra"
    display_name: str  # as rendered, e.g. "Languages", "Cloud \\& Infra"
    skills: list[str]  # individual skills, e.g. ["Java", "Python", "C++"]
    prefix: str  # LaTeX before the skill list, e.g. "\\textbf{Languages}{: "
    suffix: str  # LaTeX after the skill list, e.g. ".} \\\\"


@dataclass
class ResumeSection:
    """A standard resume section (Education, Experience, Projects, etc.).

    Contains tagged items (jobs, projects, publications) with optional
    tagged bullets within each item.
    """

    tag_type: TagType
    id: str  # e.g. "education", "experience", "projects"
    items: list[ResumeItem] = field(default_factory=list)
    # Raw LaTeX content between/around items (section header, list wrappers, etc.)
    # Stored as (position, text) pairs where position is the index in items
    # before which the content appears. len(items) means after the last item.
    interstitial: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class SkillsSection:
    """The skills section with parseable subcategories.

    Uses SKILLS tags instead of regular BEGIN/END item tags.
    """

    tag_type: TagType
    id: str  # e.g. "skills"
    categories: list[SkillCategory] = field(default_factory=list)
    # Raw LaTeX around categories (section header, itemize wrappers, etc.)
    # Same (position, text) pattern as ResumeSection.interstitial.
    interstitial: list[tuple[int, str]] = field(default_factory=list)


@dataclass
class ParsedResume:
    """Top-level structured representation of a tagged resume.

    Produced by the parser, consumed by the selector and assembler.
    """

    preamble: str  # everything before \\begin{document}
    header: str  # \\begin{document} up to (not including) first tagged section
    sections: list[ResumeSection | SkillsSection] = field(default_factory=list)
    # Raw LaTeX between/around sections (spacing, comments, etc.)
    # Same (position, text) pattern.
    interstitial: list[tuple[int, str]] = field(default_factory=list)
    postamble: str = ""  # after the last section (e.g. \\end{document})
