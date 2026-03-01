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
from autocustomizeresume.llm_client import LLMClient
from autocustomizeresume.parser import parse_resume
from autocustomizeresume.schemas import ContentSelection, JDAnalysis
from autocustomizeresume.selector import select_content

_TOTAL_STEPS = 5


@dataclass
class PipelineResult:
    """Output of a single pipeline run."""

    resume_pdf: Path
    analysis: JDAnalysis
    selection: ContentSelection
    cover_letter_pdf: Path | None = None


def run_pipeline(
    jd_text: str,
    config: Config,
    *,
    company: str | None = None,
    role: str | None = None,
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

    Returns
    -------
    PipelineResult
        Contains resume PDF path, JD analysis, and content selection.
    """
    # 1. Parse master resume
    status.step(1, _TOTAL_STEPS, "Parsing master resume…")
    resume_path = Path(config.paths.master_resume)
    tex_content = resume_path.read_text(encoding="utf-8")
    parsed = parse_resume(tex_content)

    # 2. Analyze JD
    status.step(2, _TOTAL_STEPS, "Analyzing job description…")
    client = LLMClient(config)
    analysis = analyze_jd(jd_text, config=config, client=client)

    # Apply company/role overrides
    overrides: dict[str, str] = {}
    if company:
        overrides["company"] = company
    if role:
        overrides["role"] = role
    if overrides:
        analysis = replace(analysis, **overrides)

    status.info(f"Target: {analysis.role} at {analysis.company}")

    # 3. Select content
    status.step(3, _TOTAL_STEPS, "Selecting resume content…")
    selection = select_content(
        analysis, parsed, config=config, client=client,
    )

    # 4. Compile with 1-page enforcement
    status.step(4, _TOTAL_STEPS, "Compiling resume PDF…")
    resume_pdf, selection = compile_with_enforcement(parsed, selection)

    # 5. Done (cover letter is added in a separate step)
    status.step(5, _TOTAL_STEPS, "Resume complete.")

    return PipelineResult(
        resume_pdf=resume_pdf,
        analysis=analysis,
        selection=selection,
    )
