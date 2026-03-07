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

import logging
import re
import warnings
from collections.abc import Callable
from typing import TypeVar, cast

from autocustomizeresume.models import (
    Bullet,
    ParsedResume,
    ResumeItem,
    ResumeSection,
    SkillCategory,
    SkillsSection,
    TagType,
)

logger = logging.getLogger(__name__)

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
TAG_BEGIN_RE = re.compile(r"^%%% BEGIN:(pinned|optional):(\S+)\s*$")

# Matches: %%% END:pinned:section-id  or  %%% END:optional:item-id
# Groups:  (1) type = pinned|optional   (2) id = identifier
TAG_END_RE = re.compile(r"^%%% END:(pinned|optional):(\S+)\s*$")

# Matches: %%% SKILLS:category-name
# Groups:  (1) category name
SKILLS_BEGIN_RE = re.compile(r"^%%% SKILLS:(\S+)\s*$")

# Matches: %%% END:SKILLS:category-name
# Groups:  (1) category name
SKILLS_END_RE = re.compile(r"^%%% END:SKILLS:(\S+)\s*$")

# Matches: %%% COMPACT: <LaTeX one-liner>
# Groups:  (1) the compact heading content (everything after "%%% COMPACT: ")
COMPACT_RE = re.compile(r"^%%% COMPACT:\s*(.+)$")

# Catches any line that looks like a tag directive (starts with %%% followed
# by a keyword) but doesn't match any of the valid tag patterns above.
# Used to warn about typos in tag markup.
_TAG_LIKE_RE = re.compile(r"^%%% (?:BEGIN|END|SKILLS|COMPACT)\b")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ParseError(Exception):
    """Raised when the tagged resume has structural errors."""


# ---------------------------------------------------------------------------
# Tag validation helpers
# ---------------------------------------------------------------------------

_VALID_TAG_RES = (TAG_BEGIN_RE, TAG_END_RE, SKILLS_BEGIN_RE, SKILLS_END_RE, COMPACT_RE)


def _warn_malformed_tags(tex_content: str) -> None:
    """Emit warnings for lines that look like tags but don't match any pattern.

    This catches typos like ``%%% BEGIN:invalid:foo``, ``%%% BEGIN:pinned``
    (missing ID), ``%%% END:SKILLS`` (missing category), etc.
    """
    for lineno, line in enumerate(tex_content.split("\n"), start=1):
        stripped = line.strip()
        if not _TAG_LIKE_RE.match(stripped):
            continue
        # It looks like a tag — does it match a valid pattern?
        if any(r.match(stripped) for r in _VALID_TAG_RES):
            continue
        warnings.warn(
            f"Line {lineno}: malformed tag-like comment ignored: {stripped!r}",
            stacklevel=2,
        )


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
    # --- 0. Warn about malformed tag-like lines ---
    _warn_malformed_tags(tex_content)

    # --- 1. Split preamble from body at \begin{document} ---
    marker = r"\begin{document}"
    idx = tex_content.find(marker)
    if idx == -1:
        raise ParseError(r"No \begin{document} found in resume")

    preamble = tex_content[: idx + len(marker)]
    body = tex_content[idx + len(marker) :]

    # --- 2. Walk lines, split into header / sections / postamble ---
    lines = body.split("\n")
    header_lines: list[str] = []
    section_chunks: list[dict] = []  # each: {type, id, lines}
    postamble_lines: list[str] = []
    interstitial_lines: list[str] = []  # between sections

    # Top-level interstitial tracking
    top_interstitial: list[tuple[int, str]] = []

    in_section = False
    section_depth_type: TagType | None = None
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
                section_depth_type = cast(TagType, m.group(1))
                section_depth_id = m.group(2)
                section_chunks.append(
                    {
                        "type": section_depth_type,
                        "id": section_depth_id,
                        "lines": [],
                    }
                )
                i += 1
                continue
            # Reject stray END tags before any section opens
            if TAG_END_RE.match(stripped):
                raise ParseError(f"Unexpected END tag before any section: {stripped}")
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
                section_depth_type = cast(TagType, m.group(1))
                section_depth_id = m.group(2)
                section_chunks.append(
                    {
                        "type": section_depth_type,
                        "id": section_depth_id,
                        "lines": [],
                    }
                )
                i += 1
                continue
            # Reject stray END tags between sections
            if TAG_END_RE.match(stripped):
                raise ParseError(f"Unexpected END tag between sections: {stripped}")
            interstitial_lines.append(line)
            i += 1
            continue

        # Inside a section — look for the matching END
        m_end = TAG_END_RE.match(stripped)
        if (
            m_end
            and m_end.group(1) == section_depth_type
            and m_end.group(2) == section_depth_id
        ):
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
        section = _parse_section(
            cast(TagType, chunk["type"]), chunk["id"], chunk["lines"]
        )
        sections.append(section)

    # --- 4. Validate ID uniqueness across the entire resume ---
    _validate_unique_ids(sections)

    return ParsedResume(
        preamble=preamble,
        header="\n".join(header_lines),
        sections=sections,
        interstitial=top_interstitial,
        postamble="\n".join(postamble_lines),
    )


def _validate_unique_ids(
    sections: list[ResumeSection | SkillsSection],
) -> None:
    """Raise ParseError if any tag ID appears more than once.

    Checks section IDs, item IDs, and bullet IDs across the entire resume.
    Skill category names are also checked.
    """
    seen: dict[str, str] = {}  # id -> context description

    def _check(tag_id: str, context: str) -> None:
        if tag_id in seen:
            raise ParseError(
                f"Duplicate ID '{tag_id}' — first seen in {seen[tag_id]}, "
                f"also found in {context}"
            )
        seen[tag_id] = context

    for section in sections:
        _check(section.id, f"section '{section.id}'")

        if isinstance(section, SkillsSection):
            for cat in section.categories:
                _check(
                    cat.name, f"skill category '{cat.name}' in section '{section.id}'"
                )
        else:
            for item in section.items:
                _check(item.id, f"item '{item.id}' in section '{section.id}'")
                for bullet in item.bullets:
                    _check(
                        bullet.id,
                        f"bullet '{bullet.id}' in item '{item.id}'",
                    )


def _parse_section(
    tag_type: TagType, tag_id: str, lines: list[str]
) -> ResumeSection | SkillsSection:
    """Parse the body lines of a section into items or skill categories.

    Detects whether this is a skills section (contains SKILLS: tags) or
    a regular section (contains BEGIN/END item tags).
    """
    # Check if any line is a SKILLS tag
    has_skills = any(SKILLS_BEGIN_RE.match(line.strip()) for line in lines)

    if has_skills:
        return _parse_skills_section(tag_type, tag_id, lines)
    return _parse_regular_section(tag_type, tag_id, lines)


_TChild = TypeVar("_TChild")
_TIdent = TypeVar("_TIdent", bound=tuple)


def _collect_tagged_children(
    lines: list[str],
    *,
    begin_re: re.Pattern[str],
    end_re: re.Pattern[str],
    begin_identity: Callable[[re.Match[str]], _TIdent],
    end_identity: Callable[[re.Match[str]], _TIdent],
    build_child: Callable[[_TIdent, list[str]], _TChild],
    unexpected_end_error: Callable[[str], ParseError],
    unclosed_error: Callable[[_TIdent], ParseError],
) -> tuple[list[_TChild], list[tuple[int, str]]]:
    """Collect tagged child blocks with interstitial content.

    Generic state-machine shared by regular sections (items) and skills
    sections (categories).  Iterates *lines*, matching begin/end regex
    pairs, accumulating child content and interstitial buffers.

    Returns ``(children, interstitial)`` where interstitial entries are
    ``(child_index, text)`` pairs.
    """
    children: list[_TChild] = []
    interstitial: list[tuple[int, str]] = []
    buffer: list[str] = []

    in_child = False
    cur_ident: _TIdent | None = None
    child_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not in_child:
            m = begin_re.match(stripped)
            if m:
                if buffer:
                    interstitial.append((len(children), "\n".join(buffer)))
                    buffer = []
                in_child = True
                cur_ident = begin_identity(m)
                child_lines = []
                continue
            if end_re.match(stripped):
                raise unexpected_end_error(stripped)
            buffer.append(line)
            continue

        m_end = end_re.match(stripped)
        if m_end and end_identity(m_end) == cur_ident:
            children.append(build_child(cur_ident, child_lines))
            in_child = False
            cur_ident = None
            child_lines = []
            continue

        child_lines.append(line)

    if in_child:
        assert cur_ident is not None
        raise unclosed_error(cur_ident)

    if buffer:
        interstitial.append((len(children), "\n".join(buffer)))

    return children, interstitial


def _parse_regular_section(
    tag_type: TagType, tag_id: str, lines: list[str]
) -> ResumeSection:
    """Parse a regular section (Education, Experience, Projects, etc.)."""
    items, interstitial = _collect_tagged_children(
        lines,
        begin_re=TAG_BEGIN_RE,
        end_re=TAG_END_RE,
        begin_identity=lambda m: (cast(TagType, m.group(1)), m.group(2)),
        end_identity=lambda m: (cast(TagType, m.group(1)), m.group(2)),
        build_child=lambda ident, child_lines: _parse_item(
            cast(TagType, ident[0]), cast(str, ident[1]), child_lines
        ),
        unexpected_end_error=lambda stripped: ParseError(
            f"Unexpected END tag outside any item in section '{tag_id}': {stripped}"
        ),
        unclosed_error=lambda ident: ParseError(
            f"Unclosed item tag: %%% BEGIN:{ident[0]}:{ident[1]}"
        ),
    )

    return ResumeSection(
        tag_type=tag_type,
        id=tag_id,
        items=items,
        interstitial=interstitial,
    )


def _parse_item(tag_type: TagType, tag_id: str, lines: list[str]) -> ResumeItem:
    """Parse a single item's lines into heading + bullets."""
    bullets: list[Bullet] = []
    interstitial: list[tuple[int, str]] = []
    heading_lines: list[str] = []
    buffer: list[str] = []  # interstitial between bullets
    compact_heading: str | None = None

    in_bullet = False
    bullet_type: TagType | None = None
    bullet_id: str | None = None
    bullet_lines: list[str] = []
    found_first_bullet_tag = False

    for line in lines:
        stripped = line.strip()

        if not in_bullet:
            # Check for %%% COMPACT: tag (must appear before first bullet)
            m_compact = COMPACT_RE.match(stripped)
            if m_compact:
                if not found_first_bullet_tag:
                    compact_heading = m_compact.group(1)
                else:
                    logger.warning(
                        "Ignoring misplaced %%% COMPACT: tag after first "
                        "bullet in item '%s'",
                        tag_id,
                    )
                continue

            m = TAG_BEGIN_RE.match(stripped)
            if m:
                found_first_bullet_tag = True
                # Flush buffer as interstitial
                if buffer:
                    interstitial.append((len(bullets), "\n".join(buffer)))
                    buffer = []
                in_bullet = True
                bullet_type = cast(TagType, m.group(1))
                bullet_id = m.group(2)
                bullet_lines = []
                continue

            # Reject stray END tags outside any bullet
            if TAG_END_RE.match(stripped):
                raise ParseError(
                    f"Unexpected END tag outside any bullet in item "
                    f"'{tag_id}': {stripped}"
                )

            if not found_first_bullet_tag:
                heading_lines.append(line)
            else:
                buffer.append(line)
            continue

        # Inside a bullet tag
        m_end = TAG_END_RE.match(stripped)
        if m_end and m_end.group(1) == bullet_type and m_end.group(2) == bullet_id:
            bullets.append(
                Bullet(
                    tag_type=bullet_type,
                    id=bullet_id,
                    text="\n".join(bullet_lines),
                )
            )
            in_bullet = False
            bullet_type = None
            bullet_id = None
            bullet_lines = []
            continue

        bullet_lines.append(line)

    if in_bullet:
        raise ParseError(f"Unclosed bullet tag: %%% BEGIN:{bullet_type}:{bullet_id}")

    # Trailing interstitial
    if buffer:
        interstitial.append((len(bullets), "\n".join(buffer)))

    return ResumeItem(
        tag_type=tag_type,
        id=tag_id,
        heading_lines="\n".join(heading_lines),
        bullets=bullets,
        interstitial=interstitial,
        compact_heading=compact_heading,
    )


def _parse_skills_section(
    tag_type: TagType, tag_id: str, lines: list[str]
) -> SkillsSection:
    """Parse a skills section with SKILLS category tags.

    Each category is delimited by %%% SKILLS:<name> / %%% END:SKILLS:<name>
    and contains a single \\textbf{DisplayName}{: skill1, skill2, ...} line.
    """
    categories, interstitial = _collect_tagged_children(
        lines,
        begin_re=SKILLS_BEGIN_RE,
        end_re=SKILLS_END_RE,
        begin_identity=lambda m: (m.group(1),),
        end_identity=lambda m: (m.group(1),),
        build_child=lambda ident, child_lines: _parse_skill_line(
            cast(str, ident[0]), child_lines
        ),
        unexpected_end_error=lambda stripped: ParseError(
            f"Unexpected END:SKILLS tag outside any category in "
            f"section '{tag_id}': {stripped}"
        ),
        unclosed_error=lambda ident: ParseError(
            f"Unclosed skills tag: %%% SKILLS:{ident[0]}"
        ),
    )

    return SkillsSection(
        tag_type=tag_type,
        id=tag_id,
        categories=categories,
        interstitial=interstitial,
    )


# Regex to parse: \textbf{DisplayName}{: skill1, skill2, ...}
# with optional trailing period, closing brace, and \\
# Groups: (1) full prefix up to and including "{: "
#         (2) display name inside \textbf{...}  (nested in group 1)
#         (3) the comma-separated skills
#         (4) trailing suffix (e.g. ".} \\" or "}")
_SKILL_LINE_RE = re.compile(
    r"^(.*\\textbf\{([^}]+)\}\{:\s*)"  # prefix + display name
    r"(.+?)"  # skills (greedy-minimal)
    r"(\.\}.*|\}.*)$",  # suffix: ".} \\" or "} \\" or "}"
    re.DOTALL,
)


def _parse_skill_line(cat_name: str, lines: list[str]) -> SkillCategory:
    """Parse the content lines of a single SKILLS category tag.

    Expects a single logical line (possibly spread across multiple lines)
    of the form: \\textbf{Display}{: A, B, C.} \\\\
    """
    # Join all content lines into one string for matching
    content = "\n".join(lines).strip()

    m = _SKILL_LINE_RE.match(content)
    if not m:
        raise ParseError(
            f"Could not parse skills line for category '{cat_name}': {content!r}"
        )

    prefix = m.group(1)
    display_name = m.group(2)
    raw_skills = m.group(3)
    suffix = m.group(4)

    # Split on commas that are NOT inside parentheses, so grouped
    # skills like "AWS (EC2, S3, EKS)" stay as a single token.
    skills = [s.strip() for s in re.split(r",\s*(?![^()]*\))", raw_skills) if s.strip()]

    return SkillCategory(
        name=cat_name,
        display_name=display_name,
        skills=skills,
        prefix=prefix,
        suffix=suffix,
    )
