"""Shared utility helpers."""

from __future__ import annotations

import re


def latex_preview(text: str) -> str:
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
