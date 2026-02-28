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

from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillsSection,
)

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


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when the tagged resume has structural errors."""


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def parse_resume(tex_content: str) -> ParsedResume:
    """Parse a tagged LaTeX resume into structured data.

    Args:
        tex_content: Full content of the tagged resume.tex file.

    Returns:
        A ParsedResume with all sections, items, bullets, and skills
        extracted and structured.

    Raises:
        ParseError: If tags are malformed, mismatched, or improperly nested.
    """
    # --- 1. Split preamble from body at \begin{document} ---
    marker = r"\begin{document}"
    idx = tex_content.find(marker)
    if idx == -1:
        raise ParseError(r"No \begin{document} found in resume")

    preamble = tex_content[:idx + len(marker)]
    body = tex_content[idx + len(marker):]

    # --- 2. Walk lines, split into header / sections / postamble ---
    lines = body.split("\n")
    header_lines: list[str] = []
    section_chunks: list[dict] = []  # each: {type, id, lines}
    postamble_lines: list[str] = []
    interstitial_lines: list[str] = []  # between sections

    # Top-level interstitial tracking
    top_interstitial: list[tuple[int, str]] = []

    in_section = False
    section_depth_type: str | None = None
    section_depth_id: str | None = None
    found_first_section = False

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not found_first_section:
            # Looking for the first section-level BEGIN tag
            m = TAG_BEGIN_RE.match(stripped)
            if m:
                found_first_section = True
                in_section = True
                section_depth_type = m.group(1)
                section_depth_id = m.group(2)
                section_chunks.append({
                    "type": section_depth_type,
                    "id": section_depth_id,
                    "lines": [],
                })
                i += 1
                continue
            header_lines.append(line)
            i += 1
            continue

        if not in_section:
            # Between sections — check for next section or end of content
            m = TAG_BEGIN_RE.match(stripped)
            if m:
                # Flush interstitial
                if interstitial_lines:
                    top_interstitial.append(
                        (len(section_chunks), "\n".join(interstitial_lines))
                    )
                    interstitial_lines = []
                in_section = True
                section_depth_type = m.group(1)
                section_depth_id = m.group(2)
                section_chunks.append({
                    "type": section_depth_type,
                    "id": section_depth_id,
                    "lines": [],
                })
                i += 1
                continue
            interstitial_lines.append(line)
            i += 1
            continue

        # Inside a section — look for the matching END
        m_end = TAG_END_RE.match(stripped)
        if m_end and m_end.group(1) == section_depth_type and m_end.group(2) == section_depth_id:
            in_section = False
            section_depth_type = None
            section_depth_id = None
            interstitial_lines = []
            i += 1
            continue

        # Accumulate section body lines
        section_chunks[-1]["lines"].append(line)
        i += 1

    if in_section:
        raise ParseError(
            f"Unclosed section tag: %%% BEGIN:{section_depth_type}:{section_depth_id}"
        )

    # Remaining interstitial after last section = postamble
    if interstitial_lines:
        postamble_lines = interstitial_lines

    # --- 3. Parse each section chunk ---
    sections: list[ResumeSection | SkillsSection] = []
    for chunk in section_chunks:
        section = _parse_section(chunk["type"], chunk["id"], chunk["lines"])
        sections.append(section)

    return ParsedResume(
        preamble=preamble,
        header="\n".join(header_lines),
        sections=sections,
        interstitial=top_interstitial,
        postamble="\n".join(postamble_lines),
    )


def _parse_section(
    tag_type: str, tag_id: str, lines: list[str]
) -> ResumeSection | SkillsSection:
    """Parse the body lines of a section into items or skill categories.

    Detects whether this is a skills section (contains SKILLS: tags) or
    a regular section (contains BEGIN/END item tags).
    """
    # Check if any line is a SKILLS tag
    has_skills = any(SKILLS_BEGIN_RE.match(l.strip()) for l in lines)

    if has_skills:
        return _parse_skills_section(tag_type, tag_id, lines)
    return _parse_regular_section(tag_type, tag_id, lines)


def _parse_regular_section(
    tag_type: str, tag_id: str, lines: list[str]
) -> ResumeSection:
    """Parse a regular section (Education, Experience, Projects, etc.)."""
    items: list[ResumeItem] = []
    interstitial: list[tuple[int, str]] = []
    buffer: list[str] = []  # accumulates interstitial between items

    in_item = False
    item_type: str | None = None
    item_id: str | None = None
    item_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not in_item:
            m = TAG_BEGIN_RE.match(stripped)
            if m:
                # Flush interstitial buffer
                if buffer:
                    interstitial.append((len(items), "\n".join(buffer)))
                    buffer = []
                in_item = True
                item_type = m.group(1)
                item_id = m.group(2)
                item_lines = []
                continue
            buffer.append(line)
            continue

        # Inside an item — look for matching END
        m_end = TAG_END_RE.match(stripped)
        if m_end and m_end.group(1) == item_type and m_end.group(2) == item_id:
            assert item_type is not None and item_id is not None
            item = _parse_item(item_type, item_id, item_lines)
            items.append(item)
            in_item = False
            item_type = None
            item_id = None
            item_lines = []
            continue

        item_lines.append(line)

    if in_item:
        raise ParseError(
            f"Unclosed item tag: %%% BEGIN:{item_type}:{item_id}"
        )

    # Trailing interstitial
    if buffer:
        interstitial.append((len(items), "\n".join(buffer)))

    return ResumeSection(
        tag_type=tag_type,
        id=tag_id,
        items=items,
        interstitial=interstitial,
    )


def _parse_item(
    tag_type: str, tag_id: str, lines: list[str]
) -> ResumeItem:
    """Parse a single item's lines into heading + bullets."""
    bullets: list[Bullet] = []
    interstitial: list[tuple[int, str]] = []
    heading_lines: list[str] = []
    buffer: list[str] = []  # interstitial between bullets

    in_bullet = False
    bullet_type: str | None = None
    bullet_id: str | None = None
    bullet_lines: list[str] = []
    found_first_bullet_tag = False

    for line in lines:
        stripped = line.strip()

        if not in_bullet:
            m = TAG_BEGIN_RE.match(stripped)
            if m:
                found_first_bullet_tag = True
                # Flush buffer as interstitial
                if buffer:
                    interstitial.append((len(bullets), "\n".join(buffer)))
                    buffer = []
                in_bullet = True
                bullet_type = m.group(1)
                bullet_id = m.group(2)
                bullet_lines = []
                continue

            if not found_first_bullet_tag:
                heading_lines.append(line)
            else:
                buffer.append(line)
            continue

        # Inside a bullet tag
        m_end = TAG_END_RE.match(stripped)
        if m_end and m_end.group(1) == bullet_type and m_end.group(2) == bullet_id:
            assert bullet_type is not None and bullet_id is not None
            bullets.append(Bullet(
                tag_type=bullet_type,
                id=bullet_id,
                text="\n".join(bullet_lines),
            ))
            in_bullet = False
            bullet_type = None
            bullet_id = None
            bullet_lines = []
            continue

        bullet_lines.append(line)

    if in_bullet:
        raise ParseError(
            f"Unclosed bullet tag: %%% BEGIN:{bullet_type}:{bullet_id}"
        )

    # Trailing interstitial
    if buffer:
        interstitial.append((len(bullets), "\n".join(buffer)))

    return ResumeItem(
        tag_type=tag_type,
        id=tag_id,
        heading_lines="\n".join(heading_lines),
        bullets=bullets,
        interstitial=interstitial,
    )


def _parse_skills_section(
    tag_type: str, tag_id: str, lines: list[str]
) -> SkillsSection:
    """Parse a skills section with SKILLS category tags.

    Placeholder — full implementation in commit 2.4.
    """
    return SkillsSection(
        tag_type=tag_type,
        id=tag_id,
        categories=[],
        interstitial=[(0, "\n".join(lines))],
    )
