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


def _copy_to_dirs(
    src: Path,
    output_dir: Path,
    history_dir: Path,
    output_template: str,
    history_template: str,
    variables: dict[str, str],
) -> None:
    """Copy *src* to both output/ and history/ with template-derived names."""
    _copy(src, output_dir, build_name(output_template, variables))
    _copy(src, history_dir, build_name(history_template, variables))


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

    _copy_to_dirs(
        result.resume_pdf,
        output_dir,
        history_dir,
        config.naming.output_resume,
        config.naming.history_resume,
        variables,
    )

    if result.cover_letter_pdf is not None:
        _copy_to_dirs(
            result.cover_letter_pdf,
            output_dir,
            history_dir,
            config.naming.output_cover,
            config.naming.history_cover,
            variables,
        )
