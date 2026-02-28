"""Resume parser: extracts tagged blocks from master resume.tex.

Reads LaTeX comment tags (%%% BEGIN/END) and produces structured
data models representing sections, items, bullets, and skills.

Tag hierarchy (outermost to innermost):
  section  >  item  >  bullet
  section  >  SKILLS category

The LLM can:
  - Include/exclude optional sections and items
  - Include/exclude individual bullets within an item
  - Tweak bullet text to incorporate JD keywords
  - Add, remove, and reorder skills within each category
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Tag format constants
# ---------------------------------------------------------------------------

# Tag types
PINNED = "pinned"
OPTIONAL = "optional"
SKILLS = "SKILLS"

TAG_TYPES = {PINNED, OPTIONAL}

# ---------------------------------------------------------------------------
# Regex patterns for tag detection
# ---------------------------------------------------------------------------

# Matches: %%% BEGIN:pinned:section-id  or  %%% BEGIN:optional:item-id
# Groups:  (1) type = pinned|optional   (2) id = identifier
TAG_BEGIN_RE = re.compile(
    r"^%%% BEGIN:(pinned|optional):(\S+)\s*$"
)

# Matches: %%% END:pinned:section-id  or  %%% END:optional:item-id
# Groups:  (1) type = pinned|optional   (2) id = identifier
TAG_END_RE = re.compile(
    r"^%%% END:(pinned|optional):(\S+)\s*$"
)

# Matches: %%% SKILLS:category-name
# Groups:  (1) category name
SKILLS_BEGIN_RE = re.compile(
    r"^%%% SKILLS:(\S+)\s*$"
)

# Matches: %%% END:SKILLS:category-name
# Groups:  (1) category name
SKILLS_END_RE = re.compile(
    r"^%%% END:SKILLS:(\S+)\s*$"
)
