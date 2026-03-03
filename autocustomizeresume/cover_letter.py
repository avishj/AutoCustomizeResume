"""Cover letter generator: produces a cover letter PDF.

Uses LLM to generate body text from JD + selected resume content,
injects it into the LaTeX template, and compiles to PDF.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

from autocustomizeresume.compiler import compile_tex
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
# LaTeX escaping — makes plain text safe for injection into LaTeX
# ---------------------------------------------------------------------------

# Characters that have special meaning in LaTeX and must be escaped.
_LATEX_SPECIAL_CHARS: dict[str, str] = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain text.

    Converts characters that have special meaning in LaTeX into their
    safe escaped equivalents.  Handles backslash and braces carefully
    to avoid double-escaping.
    """
    # Backslash must be handled first and specially — we replace it
    # with a placeholder, then handle braces, then swap placeholder.
    placeholder = "\x00BACKSLASH\x00"
    text = text.replace("\\", placeholder)

    # Braces next (before other chars, since replacements contain braces)
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")

    # Now the remaining special chars
    for char, replacement in _LATEX_SPECIAL_CHARS.items():
        text = text.replace(char, replacement)

    # Replace placeholder with the proper LaTeX command
    text = text.replace(placeholder, r"\textbackslash{}")

    return text


def _plain_text_to_latex(text: str) -> str:
    """Convert plain text (from LLM) to LaTeX-safe body content.

    1. Escapes LaTeX special characters.
    2. Converts blank-line-separated paragraphs to ``\\par`` separators.
    """
    escaped = _escape_latex(text)

    # Split on blank lines (one or more empty lines between paragraphs)
    paragraphs = re.split(r"\n\s*\n", escaped)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    return "\n\n\\par\n\n".join(paragraphs)


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
                bd = next((b for b in item_dec.bullets if b.id == bullet.id), None)
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
        stream=True,
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )

    logger.info("Cover letter body generated (%d chars)", len(body))
    return body.strip()


# ---------------------------------------------------------------------------
# Template injection — replace placeholders with values
# ---------------------------------------------------------------------------

_SIGNATURE_LATEX = (
    r"\hspace{-0.5cm}"
    r"\includegraphics[width=0.2\textwidth]"
)


def _build_signature_block(signature_path: str) -> str:
    """Build the LaTeX for the signature, or empty string if no path.

    Uses only the filename since the image is copied to the compile
    directory alongside the .tex file.  The filename is wrapped in
    ``\\detokenize`` so that characters like ``_`` are passed through
    literally rather than being interpreted as LaTeX commands.
    """
    if not signature_path.strip():
        return ""
    filename = Path(signature_path).name
    return _SIGNATURE_LATEX + r"{\detokenize{" + filename + "}}"


def _format_date() -> str:
    """Return today's date in 'Month DD, YYYY' format."""
    return date.today().strftime("%B %d, %Y")


def inject_template(
    template_tex: str,
    *,
    config: Config,
    body_text: str,
) -> str:
    """Replace all ``{{PLACEHOLDER}}`` tokens in the cover letter template.

    Parameters
    ----------
    template_tex:
        The raw LaTeX template string with ``{{...}}`` placeholders.
    config:
        Application config (user info, cover letter settings).
    body_text:
        The LLM-generated body text (already LaTeX-escaped via
        :func:`_plain_text_to_latex`).

    Returns
    -------
    str
        The filled-in LaTeX document ready for compilation.
    """
    esc = _escape_latex

    replacements: dict[str, str] = {
        "{{FIRST_NAME}}": esc(config.user.first_name),
        "{{LAST_NAME}}": esc(config.user.last_name),
        "{{PHONE}}": esc(config.user.phone),
        "{{EMAIL}}": esc(config.user.email),
        "{{LINKEDIN}}": esc(config.user.linkedin),
        "{{WEBSITE}}": esc(config.user.website),
        "{{DEGREE}}": esc(config.user.degree),
        "{{UNIVERSITY}}": esc(config.user.university),
        "{{DATE}}": esc(_format_date()),
        "{{BODY}}": body_text,  # already escaped by _plain_text_to_latex
        "{{SIGNATURE_BLOCK}}": _build_signature_block(
            config.cover_letter.signature_path
        ),
    }

    result = template_tex
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    # Warn about any remaining unreplaced placeholders
    remaining = re.findall(r"\{\{[A-Z_]+\}\}", result)
    if remaining:
        logger.warning(
            "Unreplaced placeholders in cover letter template: %s",
            ", ".join(remaining),
        )

    logger.info("Template injection complete")
    return result


# ---------------------------------------------------------------------------
# Cover letter compilation
# ---------------------------------------------------------------------------


def compile_cover_letter(
    filled_tex: str,
    *,
    config: Config,
    keep_dir: Path | None = None,
) -> Path:
    """Compile a filled-in cover letter .tex to PDF.

    Copies the template's font directory (and signature image if
    configured) into the compilation directory so tectonic can
    resolve all referenced files.

    Parameters
    ----------
    filled_tex:
        The complete LaTeX document after placeholder injection.
    config:
        Application config (for locating fonts and signature).
    keep_dir:
        If provided, write build artifacts here.  Otherwise a
        temporary directory is created; the caller owns cleanup.

    Returns
    -------
    Path
        Path to the generated PDF file.

    Raises
    ------
    CompileError
        If compilation fails.
    """
    template_path = Path(config.cover_letter.template)
    template_dir = template_path.parent
    fonts_src = template_dir / "fonts"

    if keep_dir is not None:
        work = keep_dir
        work.mkdir(parents=True, exist_ok=True)
        owns_dir = False
    else:
        work = Path(tempfile.mkdtemp(prefix="acr_cl_"))
        owns_dir = True

    try:
        # Copy fonts directory
        fonts_dst = work / "fonts"
        if fonts_src.is_dir() and not fonts_dst.exists():
            shutil.copytree(fonts_src, fonts_dst)
            logger.debug("Copied fonts to %s", fonts_dst)

        # Copy signature image if configured
        sig_path = config.cover_letter.signature_path
        if sig_path and sig_path.strip():
            sig_src = Path(sig_path)
            if sig_src.exists():
                sig_dst = work / sig_src.name
                if not sig_dst.exists():
                    shutil.copy2(sig_src, sig_dst)
                logger.debug("Copied signature to %s", sig_dst)
            else:
                logger.warning("Signature file not found: %s — skipping", sig_path)

        # Compile (compile_tex handles writing the .tex and invoking tectonic)
        pdf_path = compile_tex(filled_tex, keep_dir=work)

        logger.info("Cover letter compiled: %s", pdf_path)
        return pdf_path
    except Exception:
        if owns_dir:
            shutil.rmtree(work, ignore_errors=True)
        raise


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def build_cover_letter(
    jd_analysis: JDAnalysis,
    parsed_resume: ParsedResume,
    selection: ContentSelection,
    *,
    config: Config,
    client: LLMClient | None = None,
    keep_dir: Path | None = None,
) -> Path | None:
    """Generate and compile a cover letter PDF end-to-end.

    Checks ``config.cover_letter.enabled`` and returns *None* if
    cover letter generation is disabled.

    Parameters
    ----------
    jd_analysis:
        Structured metadata from the job description.
    parsed_resume:
        The fully parsed tagged resume.
    selection:
        The content selection decisions.
    config:
        Application config.
    client:
        Optional pre-built LLM client.
    keep_dir:
        If provided, write build artifacts here.

    Returns
    -------
    Path or None
        Path to the generated PDF, or *None* if disabled.

    Raises
    ------
    CompileError
        If compilation fails.
    FileNotFoundError
        If the template file does not exist.
    """
    if not config.cover_letter.enabled:
        logger.info("Cover letter generation disabled — skipping")
        return None

    # Validate template exists
    template_path = Path(config.cover_letter.template)
    if not template_path.exists():
        raise FileNotFoundError(f"Cover letter template not found: {template_path}")

    # 1. Generate body text via LLM
    body_plain = generate_cover_letter_body(
        jd_analysis,
        parsed_resume,
        selection,
        config=config,
        client=client,
    )

    # 2. Post-process: escape special chars + convert paragraphs
    body_latex = _plain_text_to_latex(body_plain)

    # 3. Inject into template
    template_tex = template_path.read_text(encoding="utf-8")
    filled_tex = inject_template(
        template_tex,
        config=config,
        body_text=body_latex,
    )

    # 4. Compile to PDF
    pdf_path = compile_cover_letter(
        filled_tex,
        config=config,
        keep_dir=keep_dir,
    )

    logger.info("Cover letter build complete: %s", pdf_path)
    return pdf_path
