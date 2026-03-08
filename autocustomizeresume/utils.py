"""Shared utility helpers."""

from __future__ import annotations

import re

# LaTeX special chars that should be escaped when they appear unescaped
# in LLM-returned LaTeX text.  We match a special char preceded by an
# even number of backslashes (including zero) — that means the char
# itself is NOT escaped.  An odd count means the last backslash escapes
# the special char, so we leave it alone.
_UNESCAPED_SPECIAL = re.compile(r"(?<!\\)((?:\\\\)*)([#&%\$])")


def escape_latex_special(text: str) -> str:
    r"""Escape unescaped LaTeX special characters in LLM-returned text.

    Handles characters like ``#`` in "C#" or ``&`` that the LLM may
    return without proper escaping.  Already-escaped sequences (e.g.
    ``\#``, ``\&``) are left untouched.  Correctly handles even runs
    of backslashes (e.g. ``\\#`` where ``\\`` is a line break and
    ``#`` is unescaped).
    """
    return _UNESCAPED_SPECIAL.sub(r"\1\\\2", text)


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
