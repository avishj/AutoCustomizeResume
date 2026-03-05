"""Content selector: decides which optional items to include.

Uses LLM to score optional resume items against the JD analysis and
pick the best set.  Can do minor rephrasing of bullets to better match
JD terminology while preserving core meaning.  Reorders skills within
each subcategory to front-load the most relevant ones.
"""

from __future__ import annotations

import json
import logging

from autocustomizeresume.config import Config
from autocustomizeresume.llm_client import LLMClient
from autocustomizeresume.models import (
    ParsedResume,
    ResumeSection,
    SkillsSection,
)
from autocustomizeresume.schemas import ContentSelection, JDAnalysis
from autocustomizeresume.utils import latex_preview

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a resume content-selection assistant.  Your goal is to produce a
tightly tailored one-page resume by choosing the optional content that best
matches the target job.  The candidate is already a software engineer —
do not reward items simply for being "software engineering."  Instead,
prioritize items that demonstrate the specific technologies, domain
experience, and competencies that distinguish THIS role.

You will receive two inputs wrapped in XML tags:
1. **<jd_analysis>** — structured metadata about the target job, including
   a "priority_keywords" list of the 3-5 most differentiating requirements.
   Use these as your primary selection signal.
2. **<resume_data>** — the candidate's resume broken into sections, items,
   bullets, and skill categories.  Each element is marked as either
   "pinned" (always included) or "optional" (you decide).

Return a single JSON object (no markdown, no commentary):

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
              "relevance_score": <0-100>,
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

Selection rules:
- Pinned sections, items, and bullets are always included automatically —
  do NOT list them.  However, if a pinned section contains optional items
  or bullets, you MUST still include that section in your output (with
  "include": true) so you can list the optional elements within it.
- Every optional section, item, and bullet from the input MUST appear in
  your output with an explicit include decision.
- CRITICAL: Your goal is to FILL a full one-page resume, not to minimize
  content.  Include as much relevant content as possible.  A resume that
  is too short is WORSE than one that is slightly too long — the system
  will automatically trim overflow, but it CANNOT add content back.
- When in doubt, INCLUDE the item or bullet.  Err heavily on the side of
  inclusion.  Only exclude items that are truly irrelevant to the role.

Scoring guidance:
- "relevance_score" applies to BOTH items and bullets.  It reflects how
  well the element matches THIS specific role, not software engineering
  in general.
- Score 80-100: directly demonstrates a priority_keyword or core JD requirement.
- Score 50-79: relevant technology or transferable domain experience.
- Score 20-49: tangentially related or shows general engineering strength.
- Score 0-19: no meaningful connection to the role's distinguishing needs.
- For bullets, score each independently — a high-relevance bullet within a
  low-relevance item (or vice versa) is perfectly fine.
- Include ALL items scoring 20+.  Only exclude items scoring below 20.

Bullet editing ("edited_text"):
- Set to "" (empty string) to keep original text verbatim — this is the default.
- Use ONLY to incorporate JD-specific terminology where the original bullet
  reasonably implies it.  Slight contextual inference is fine — bullets are
  summaries that don't capture full detail.
- Do NOT change metrics, numbers, or quantified outcomes.
- Do NOT fabricate entirely new skills or experiences.
- If you are unsure whether an edit crosses the line from reasonable
  inference to fabrication, set edited_text to "" and flag it by giving
  the bullet a lower relevance context — the user will handle it manually.
- Example — GOOD: "managed cloud infrastructure" → "managed AWS cloud
  infrastructure" (reasonable if the role/company context implies AWS).
- Example — GOOD: "built data pipelines" → "built real-time data pipelines
  using Kafka" (if the item's context involves streaming).
- Example — BAD: "fixed frontend bugs" → "architected a distributed
  microservices platform" (completely different scope and meaning).

Skill ordering:
- Include only skills from the original list.  Order by relevance to JD
  (most relevant first).  You may drop clearly irrelevant skills, but
  err on the side of inclusion.

Compact items:
- Items marked "has_compact=yes" have a compact one-liner fallback.  You
  may safely exclude ALL their bullets — the item will still appear as a
  single-line entry.  For items WITHOUT has_compact, excluding all bullets
  will drop the item entirely.

Return ONLY the JSON object.  No explanation, no markdown fences.\
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
    lines: list[str] = [f"SECTION: id={section.id}, tag={section.tag_type}"]

    for item in section.items:
        compact_flag = ", has_compact=yes" if item.compact_heading else ""
        lines.append(f"  ITEM: id={item.id}, tag={item.tag_type}{compact_flag}")
        # Include a brief summary from heading lines (strip LaTeX noise)
        heading_preview = latex_preview(item.heading_lines)
        if heading_preview:
            lines.append(f"    heading: {heading_preview}")

        for bullet in item.bullets:
            bullet_text = latex_preview(bullet.text)
            lines.append(f"    BULLET: id={bullet.id}, tag={bullet.tag_type}")
            if bullet_text:
                lines.append(f"      text: {bullet_text}")

    return "\n".join(lines)


def _serialize_skills_section(section: SkillsSection) -> str:
    """Serialize the skills section."""
    lines: list[str] = [f"SKILLS SECTION: id={section.id}, tag={section.tag_type}"]

    for cat in section.categories:
        skills_str = ", ".join(cat.skills)
        lines.append(
            f"  CATEGORY: name={cat.name}, "
            f"display={cat.display_name}, "
            f"skills=[{skills_str}]"
        )

    return "\n".join(lines)


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
            "priority_keywords": jd_analysis.priority_keywords,
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

    raw = client.chat(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.1,
    )

    selection = ContentSelection.from_dict(raw)

    # Log summary
    included_items = sum(
        1 for sec in selection.sections for it in sec.items if it.include
    )
    total_items = sum(len(sec.items) for sec in selection.sections)
    logger.info(
        "Content selection: %d/%d optional items included, %d skill categories",
        included_items,
        total_items,
        len(selection.skill_categories),
    )

    return selection
