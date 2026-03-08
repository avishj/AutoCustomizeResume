"""Pipeline orchestrator: runs the full resume customization pipeline.

Reads the master resume and JD, calls each module in sequence
(parse → analyze → select → assemble → compile), and returns
the result with PDF paths.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from autocustomizeresume import status
from autocustomizeresume.analyzer import analyze_jd
from autocustomizeresume.compiler import compile_with_enforcement
from autocustomizeresume.config import Config
from autocustomizeresume.cover_letter import build_cover_letter
from autocustomizeresume.llm_client import LLMClient
from autocustomizeresume.parser import parse_resume
from autocustomizeresume.schemas import ContentSelection, JDAnalysis
from autocustomizeresume.selector import select_content

_STEPS_BASE = 5
_STEPS_WITH_CL = 6


@dataclass
class PipelineResult:
    """Output of a single pipeline run."""

    resume_pdf: Path
    analysis: JDAnalysis
    selection: ContentSelection | None = None
    cover_letter_pdf: Path | None = None


def run_pipeline(
    jd_text: str,
    config: Config,
    *,
    company: str | None = None,
    role: str | None = None,
    keep_dir: Path | None = None,
) -> PipelineResult:
    """Run the full resume customization pipeline.

    Parameters
    ----------
    jd_text:
        Raw text of the job description.
    config:
        Application configuration.
    company:
        Override the LLM-extracted company name.
    role:
        Override the LLM-extracted role title.
    keep_dir:
        If provided, keep build artifacts (tex, pdf) in this directory.

    Returns
    -------
    PipelineResult
        Contains resume PDF path, JD analysis, and content selection.
    """
    total = _STEPS_WITH_CL if config.cover_letter.enabled else _STEPS_BASE

    # 1. Parse master resume
    status.step(1, total, "Parsing master resume…")
    resume_path = Path(config.paths.master_resume)
    tex_content = resume_path.read_text(encoding="utf-8")
    parsed = parse_resume(tex_content)

    # 2. Analyze JD
    status.step(2, total, "Analyzing job description…")
    client = LLMClient(config)
    analysis = analyze_jd(jd_text, config=config, client=client)

    # Apply company/role overrides
    overrides: dict[str, str] = {}
    if company is not None:
        overrides["company"] = company
    if role is not None:
        overrides["role"] = role
    if overrides:
        analysis = replace(analysis, **overrides)

    status.info(f"Target: {analysis.role} at {analysis.company}")

    # 3. Select content
    status.step(3, total, "Selecting resume content…")
    selection = select_content(
        analysis,
        parsed,
        config=config,
        client=client,
    )

    # 4. Compile with 1-page enforcement
    status.step(4, total, "Compiling resume PDF…")
    resume_pdf, selection = compile_with_enforcement(
        parsed, selection, keep_dir=keep_dir
    )

    # 5. Cover letter (if enabled)
    cover_letter_pdf: Path | None = None
    if config.cover_letter.enabled:
        status.step(5, total, "Generating cover letter…")
        cover_letter_pdf = build_cover_letter(
            analysis,
            parsed,
            selection,
            config=config,
            client=client,
        )

    # Final step
    status.step(total, total, "Done.")

    return PipelineResult(
        resume_pdf=resume_pdf,
        analysis=analysis,
        selection=selection,
        cover_letter_pdf=cover_letter_pdf,
    )
