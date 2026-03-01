"""File namer: applies naming templates and manages output/history.

Copies compiled PDFs to output/ (overwritten each run) and
history/ (permanent archive with timestamps).
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from autocustomizeresume.config import Config
from autocustomizeresume.pipeline import PipelineResult
from autocustomizeresume.schemas import JDAnalysis


def build_variables(config: Config, analysis: JDAnalysis) -> dict[str, str]:
    """Build the template variable mapping from config and JD analysis.

    Returns
    -------
    dict[str, str]
        Keys are template variable names (without braces),
        values are the resolved strings.
    """
    now = datetime.now()
    return {
        "first": config.user.first_name,
        "last": config.user.last_name,
        "company": analysis.company,
        "role": analysis.role,
        "date": now.strftime("%Y-%m-%d"),
        "timestamp": now.strftime("%Y-%m-%d_%H%M%S"),
    }


def build_name(template: str, variables: dict[str, str]) -> str:
    """Substitute template variables into a naming template.

    Parameters
    ----------
    template:
        A naming template string, e.g. ``"{last}, {first} - Resume.pdf"``.
    variables:
        Variable mapping from :func:`build_variables`.

    Returns
    -------
    str
        The resolved filename.

    Raises
    ------
    KeyError
        If the template references a variable not present in *variables*.
    """
    result = template.format(**variables)
    return _sanitize_filename(result)


_INVALID_CHARS = frozenset('\\/:*?"<>|')


def _sanitize_filename(name: str) -> str:
    """Replace invalid filename characters with underscores."""
    return "".join("_" if c in _INVALID_CHARS else c for c in name)


def _copy(src: Path, dest_dir: Path, filename: str) -> Path:
    """Copy *src* to *dest_dir/filename*, creating dirs as needed."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copy2(src, dest)
    return dest


def handle_output(result: PipelineResult, config: Config) -> None:
    """Copy pipeline PDFs to output/ and history/ with configured names.

    Parameters
    ----------
    result:
        The completed pipeline result with PDF paths.
    config:
        Application configuration with naming templates and paths.
    """
    variables = build_variables(config, result.analysis)
    output_dir = Path(config.paths.output_dir)
    history_dir = Path(config.paths.history_dir)

    # Resume
    resume_out = build_name(config.naming.output_resume, variables)
    resume_hist = build_name(config.naming.history_resume, variables)
    _copy(result.resume_pdf, output_dir, resume_out)
    _copy(result.resume_pdf, history_dir, resume_hist)

    # Cover letter (if generated)
    if result.cover_letter_pdf is not None:
        cl_out = build_name(config.naming.output_cover, variables)
        cl_hist = build_name(config.naming.history_cover, variables)
        _copy(result.cover_letter_pdf, output_dir, cl_out)
        _copy(result.cover_letter_pdf, history_dir, cl_hist)
