"""Cover letter generator: produces a cover letter PDF.

Uses LLM to generate body text from JD + selected resume content,
injects it into the LaTeX template, and compiles to PDF.
"""

from __future__ import annotations

import json
import logging

from autocustomizeresume.config import Config
from autocustomizeresume.llm_client import LLMClient
from autocustomizeresume.models import (
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillsSection,
)
from autocustomizeresume.schemas import (
    ContentSelection,
    ItemDecision,
    JDAnalysis,
    SectionDecision,
    SkillCategoryDecision,
)
from autocustomizeresume.selector import _latex_preview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt for body generation
# ---------------------------------------------------------------------------

_BODY_SYSTEM_PROMPT = """\
You are a cover letter writing assistant.

You will receive three inputs wrapped in XML tags:
1. **<jd_analysis>** — structured metadata about the target job (company, \
role, seniority, domain, key skills, technologies).
2. **<resume_summary>** — a summary of the candidate's resume content that \
will appear in their final resume for this application.
3. **<style>** — the user's style preferences for the cover letter tone.

Your job is to write the **body text** of a cover letter.

Rules:
- Write 3-4 paragraphs of plain text.
- Reference specific experiences, projects, or skills from the resume \
summary that are relevant to the job.
- Tailor the letter to the specific company and role.
- Match the style preferences provided.
- Do NOT fabricate experiences, skills, or qualifications not present in \
the resume summary.
- Do NOT include a greeting/salutation (e.g. "Dear Hiring Manager") — \
the template already has one.
- Do NOT include a closing (e.g. "Sincerely") — the template handles that.
- Do NOT use any LaTeX commands or formatting.  Output plain text only.
- Separate paragraphs with a blank line.
- Be concise and direct.  Avoid generic filler phrases.
- Return ONLY the body text.  No commentary, no markdown.\
"""


# ---------------------------------------------------------------------------
# Resume context serializer — builds a text summary of selected content
# ---------------------------------------------------------------------------

def _summarize_selected_content(
    parsed: ParsedResume,
    selection: ContentSelection,
) -> str:
    """Build a human-readable summary of the selected resume content.

    Includes pinned content (always present) and optional content that
    was included by the LLM selection.  This gives the cover letter
    generator full context about what appears in the final resume.
    """
    parts: list[str] = []

    for section in parsed.sections:
        if isinstance(section, SkillsSection):
            block = _summarize_skills_section(section, selection)
        elif isinstance(section, ResumeSection):
            block = _summarize_regular_section(section, selection)
        else:
            continue

        if block:
            parts.append(block)

    return "\n\n".join(parts)


def _find_section_decision(
    selection: ContentSelection, section_id: str
) -> SectionDecision | None:
    return next((sd for sd in selection.sections if sd.id == section_id), None)


def _find_item_decision(
    section_dec: SectionDecision, item_id: str
) -> ItemDecision | None:
    return next((itd for itd in section_dec.items if itd.id == item_id), None)


def _find_skill_cat_decision(
    selection: ContentSelection, cat_name: str
) -> SkillCategoryDecision | None:
    return next(
        (scd for scd in selection.skill_categories if scd.name == cat_name),
        None,
    )


def _is_item_included(item: ResumeItem, item_dec: ItemDecision | None) -> bool:
    """Determine if an item is included in the final resume."""
    if item.tag_type == "pinned":
        return True
    if item_dec is None or not item_dec.include:
        return False
    return True


def _summarize_regular_section(
    section: ResumeSection,
    selection: ContentSelection,
) -> str:
    """Summarize a regular section's selected content."""
    sec_dec = _find_section_decision(selection, section.id)

    # Optional section excluded
    if section.tag_type == "optional" and (sec_dec is None or not sec_dec.include):
        return ""

    lines: list[str] = [f"## {section.id.replace('-', ' ').title()}"]

    for item in section.items:
        item_dec = _find_item_decision(sec_dec, item.id) if sec_dec else None

        if not _is_item_included(item, item_dec):
            continue

        heading = _latex_preview(item.heading_lines)
        if heading:
            lines.append(f"- {heading}")

        # Include selected bullet text
        for bullet in item.bullets:
            # Pinned bullets always included
            if bullet.tag_type == "pinned":
                text = _latex_preview(bullet.text)
                if text:
                    lines.append(f"  * {text}")
            elif item_dec is not None:
                # Check if this optional bullet is included
                bd = next(
                    (b for b in item_dec.bullets if b.id == bullet.id), None
                )
                if bd is not None and bd.include:
                    # Use edited text if present
                    raw = bd.edited_text if bd.edited_text else bullet.text
                    text = _latex_preview(raw)
                    if text:
                        lines.append(f"  * {text}")

    # If only the header line, section had no included items
    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


def _summarize_skills_section(
    section: SkillsSection,
    selection: ContentSelection,
) -> str:
    """Summarize the skills section's selected content."""
    if section.tag_type == "optional":
        sd = _find_section_decision(selection, section.id)
        if sd is None or not sd.include:
            return ""

    lines: list[str] = [f"## {section.id.replace('-', ' ').title()}"]

    for cat in section.categories:
        cat_dec = _find_skill_cat_decision(selection, cat.name)
        skills = cat_dec.skills if cat_dec is not None else cat.skills

        if skills:
            lines.append(f"- {cat.display_name}: {', '.join(skills)}")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Body generation via LLM
# ---------------------------------------------------------------------------

def generate_cover_letter_body(
    jd_analysis: JDAnalysis,
    parsed_resume: ParsedResume,
    selection: ContentSelection,
    *,
    config: Config,
    client: LLMClient | None = None,
) -> str:
    """Generate cover letter body text via LLM.

    Parameters
    ----------
    jd_analysis:
        Structured metadata from the job description.
    parsed_resume:
        The fully parsed tagged resume.
    selection:
        The content selection decisions (determines what's in the
        final resume).
    config:
        Application config (style preferences + LLM settings).
    client:
        Optional pre-built LLM client.

    Returns
    -------
    str
        Plain text body (paragraphs separated by blank lines).
    """
    if client is None:
        client = LLMClient(config)

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

    resume_summary = _summarize_selected_content(parsed_resume, selection)
    style = config.cover_letter.style or "Professional, concise."

    user_prompt = (
        "<jd_analysis>\n"
        f"{jd_block}\n"
        "</jd_analysis>\n\n"
        "<resume_summary>\n"
        f"{resume_summary}\n"
        "</resume_summary>\n\n"
        "<style>\n"
        f"{style}\n"
        "</style>"
    )

    logger.info(
        "Generating cover letter body for %s at %s",
        jd_analysis.role,
        jd_analysis.company,
    )

    body = client.chat(
        system=_BODY_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.4,
    )

    logger.info("Cover letter body generated (%d chars)", len(body))
    return body.strip()
