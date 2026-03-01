"""File namer: applies naming templates and manages output/history.

Copies compiled PDFs to output/ (overwritten each run) and
history/ (permanent archive with timestamps).
"""

from __future__ import annotations

from datetime import datetime

from autocustomizeresume.config import Config
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
    return template.format(**variables)
