"""Content selector: decides which optional items to include.

Uses LLM to score optional resume items against the JD analysis and
pick the best set.  Can do minor rephrasing of bullets to better match
JD terminology while preserving core meaning.  Reorders skills within
each subcategory to front-load the most relevant ones.
"""

from __future__ import annotations

import json
import logging
import re

from autocustomizeresume.config import Config
from autocustomizeresume.llm_client import LLMClient
from autocustomizeresume.models import (
    ParsedResume,
    ResumeSection,
    SkillsSection,
)
from autocustomizeresume.schemas import ContentSelection, JDAnalysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a resume content-selection assistant.

You will receive two inputs wrapped in XML tags:
1. **<jd_analysis>** — structured metadata about the target job (company, \
role, seniority, domain, key skills, technologies).
2. **<resume_data>** — the candidate's resume broken into sections, items, \
bullets, and skill categories.  Each element is marked as either \
"pinned" (always included) or "optional" (you decide).

Your job is to return a **single JSON object** that decides:
- Which optional **sections** to include.
- Which optional **items** (jobs, projects, etc.) to include, with a \
relevance score (0-100).
- Which optional **bullets** within included items to include.  You may \
also provide minor rephrasing of a bullet via the "edited_text" field — \
use this ONLY to incorporate JD-specific terminology or keywords while \
preserving the bullet's core meaning and factual content.  Set \
"edited_text" to "" (empty string) to keep the original text verbatim.
- Which **skills** to include within each subcategory, and in what order.  \
All skill subcategories are always kept — you only filter and reorder \
the individual skills within them.

Return this exact JSON structure (no markdown, no commentary, no extra keys):

{
  "sections": [
    {
      "id": "<section tag ID>",
      "include": true/false,
      "items": [
        {
          "id": "<item tag ID>",
          "include": true/false,
          "relevance_score": <0-100>,
          "bullets": [
            {
              "id": "<bullet tag ID>",
              "include": true/false,
              "edited_text": "<minor rephrasing or empty string>"
            }
          ]
        }
      ]
    }
  ],
  "skill_categories": [
    {
      "name": "<category tag name>",
      "skills": ["<skill>", "<skill>", ...]
    }
  ]
}

Rules:
- Only optional elements appear in your output.  Pinned sections, items, \
and bullets are always included automatically — do NOT list them.
- Every optional section, item, and bullet from the input MUST appear in \
your output with an explicit include decision.
- "relevance_score" should reflect how relevant the item is to the \
target JD (0 = irrelevant, 100 = perfect match).
- For bullets: "edited_text" must be empty ("") unless you are making a \
minor terminology adjustment.  Never change facts, metrics, or the core \
meaning.  Never add information that isn't in the original bullet.
- For skills: include only skills from the original list.  Order them by \
relevance to the JD (most relevant first).  You may exclude skills that \
are clearly irrelevant, but err on the side of inclusion.
- Return ONLY the JSON object.  No explanation, no markdown fences.\
"""


# ---------------------------------------------------------------------------
# Resume serialisation helpers
# ---------------------------------------------------------------------------

def _serialize_resume(parsed: ParsedResume) -> str:
    """Serialize resume structure into a compact text format for the LLM.

    Only includes information relevant to content selection decisions:
    tag types, IDs, and text content.  Pinned elements are labelled
    so the LLM knows not to include them in its output.
    """
    parts: list[str] = []

    for section in parsed.sections:
        if isinstance(section, SkillsSection):
            parts.append(_serialize_skills_section(section))
        elif isinstance(section, ResumeSection):
            parts.append(_serialize_regular_section(section))

    return "\n\n".join(parts)


def _serialize_regular_section(section: ResumeSection) -> str:
    """Serialize a regular (non-skills) section."""
    lines: list[str] = [
        f"SECTION: id={section.id}, tag={section.tag_type}"
    ]

    for item in section.items:
        lines.append(
            f"  ITEM: id={item.id}, tag={item.tag_type}"
        )
        # Include a brief summary from heading lines (strip LaTeX noise)
        heading_preview = _latex_preview(item.heading_lines)
        if heading_preview:
            lines.append(f"    heading: {heading_preview}")

        for bullet in item.bullets:
            bullet_text = _latex_preview(bullet.text)
            lines.append(
                f"    BULLET: id={bullet.id}, tag={bullet.tag_type}"
            )
            if bullet_text:
                lines.append(f"      text: {bullet_text}")

    return "\n".join(lines)


def _serialize_skills_section(section: SkillsSection) -> str:
    """Serialize the skills section."""
    lines: list[str] = [
        f"SKILLS SECTION: id={section.id}, tag={section.tag_type}"
    ]

    for cat in section.categories:
        skills_str = ", ".join(cat.skills)
        lines.append(
            f"  CATEGORY: name={cat.name}, "
            f"display={cat.display_name}, "
            f"skills=[{skills_str}]"
        )

    return "\n".join(lines)


def _latex_preview(text: str) -> str:
    r"""Extract a readable preview from a LaTeX snippet.

    Strips common LaTeX commands to give the LLM a cleaner view of
    the content, while keeping it recognisable.  Not a full LaTeX
    parser — just enough to be useful.
    """
    preview = text.strip()
    # Remove common LaTeX line-break commands
    preview = preview.replace("\\\\", " ")
    preview = preview.replace("\\newline", " ")
    # Remove \href{url}{text} — keep text (before brace stripping)
    preview = re.sub(r"\\href\{[^}]*\}\{([^}]*)\}", r"\1", preview)
    # Remove \textbf{...} / \textit{...} — keep content
    preview = re.sub(r"\\text\w+\{([^}]*)\}", r"\1", preview)
    # Remove \resumeItem{...} wrapper — keep the content
    preview = re.sub(r"\\resumeItem\{", "", preview)
    # Remove \resumeSubheading and similar — keep args
    preview = re.sub(r"\\resume\w+\{", "", preview)
    # Strip leftover braces from the above removals
    preview = preview.replace("{", " ").replace("}", " ")
    # Collapse whitespace
    preview = re.sub(r"\s+", " ", preview).strip()
    # Truncate for sanity
    if len(preview) > 300:
        preview = preview[:297] + "..."
    return preview


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def select_content(
    jd_analysis: JDAnalysis,
    parsed_resume: ParsedResume,
    *,
    config: Config,
    client: LLMClient | None = None,
) -> ContentSelection:
    """Select which optional resume content to include for a given JD.

    Parameters
    ----------
    jd_analysis:
        Structured metadata extracted from the job description.
    parsed_resume:
        The fully parsed tagged resume.
    config:
        Application config (used to build a client if *client* is None).
    client:
        Optional pre-built LLM client (useful for testing / reuse).

    Returns
    -------
    ContentSelection
        Per-section, per-item, per-bullet decisions plus skill ordering.
    """
    if client is None:
        client = LLMClient(config)

    # Build user prompt with both JD analysis and resume data
    jd_block = json.dumps(
        {
            "company": jd_analysis.company,
            "role": jd_analysis.role,
            "seniority": jd_analysis.seniority,
            "domain": jd_analysis.domain,
            "key_skills": jd_analysis.key_skills,
            "technologies": jd_analysis.technologies,
        },
        indent=2,
    )
    resume_block = _serialize_resume(parsed_resume)

    user_prompt = (
        "<jd_analysis>\n"
        f"{jd_block}\n"
        "</jd_analysis>\n\n"
        "<resume_data>\n"
        f"{resume_block}\n"
        "</resume_data>"
    )

    logger.info(
        "Selecting content for %s at %s …",
        jd_analysis.role,
        jd_analysis.company,
    )
    logger.debug(
        "Selector prompt built (jd_chars=%d, resume_chars=%d)",
        len(jd_block),
        len(resume_block),
    )

    raw = client.chat_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.1,
    )

    selection = ContentSelection.from_dict(raw)

    # Log summary
    included_items = sum(
        1
        for sec in selection.sections
        for it in sec.items
        if it.include
    )
    total_items = sum(len(sec.items) for sec in selection.sections)
    logger.info(
        "Content selection: %d/%d optional items included, %d skill categories",
        included_items,
        total_items,
        len(selection.skill_categories),
    )

    return selection
