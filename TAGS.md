# Resume Tag Format Specification

This document describes the LaTeX comment tags used to mark sections, items,
bullets, and skills in your `resume.tex` so the parser can extract structured
data for LLM-powered customization.

---

## What the LLM Can Do

| Level    | Include/Exclude | Reorder | Add/Remove | Tweak Text |
|----------|:-:|:-:|:-:|:-:|
| Section  | yes | no  | no  | no  |
| Item     | yes | no  | no  | no  |
| Bullet   | yes | no  | no  | yes (minor keyword edits) |
| Skill    | —   | yes | yes | no  |

---

## Tag Types

| Type       | Purpose                                    |
|------------|--------------------------------------------|
| `pinned`   | Always included — never dropped by the LLM |
| `optional` | LLM may include or exclude per job fit     |
| `SKILLS`   | Special tag for skill subcategories        |

---

## Section Tags

Wrap an entire resume section (e.g. Education, Experience).

```latex
%%% BEGIN:pinned:education
\section{Education}
    ...
%%% END:pinned:education

%%% BEGIN:optional:projects
\section{Projects}
    ...
%%% END:optional:projects
```

- **ID** must be unique across the resume (e.g. `education`, `experience`,
  `projects`, `research`).
- Sections can be `pinned` (always shown) or `optional` (LLM decides).

---

## Item Tags

Wrap individual entries **inside** a section (e.g. a single job, project, or
publication). Item tags nest inside section tags.

```latex
%%% BEGIN:optional:experience
\section{Industry Experience}
  \resumeSubHeadingListStart

    %%% BEGIN:pinned:snap
    \resumeSubheading{Snap Inc.}{Aug 2025 -- Dec 2025}
      {Software Engineering Intern}{Pittsburgh, PA}
      ...
    %%% END:pinned:snap

    %%% BEGIN:optional:addverb
    \resumeSubheading{Addverb Technologies}{Jan 2023 -- Jul 2024}
      {Software Engineer}{Delhi NCR, India}
      ...
    %%% END:optional:addverb

  \resumeSubHeadingListEnd
%%% END:optional:experience
```

- Item IDs must be unique within the resume (e.g. `snap`, `siemens`,
  `addverb`).
- Only `optional` items can be dropped. `pinned` items always appear.

---

## Bullet Tags

Wrap individual `\resumeItem{...}` bullets **inside** an item. This gives
the LLM per-bullet include/exclude control and the ability to make minor
keyword tweaks to the text.

```latex
%%% BEGIN:optional:snap
\resumeSubheading{Snap Inc.}{Aug 2025 -- Dec 2025}
  {Software Engineering Intern}{Pittsburgh, PA}
\resumeItemListStart
    %%% BEGIN:optional:snap-1
    \resumeItem{Tech lead of a CMU team building an XR remote desktop PoC...}
    %%% END:optional:snap-1
    %%% BEGIN:optional:snap-2
    \resumeItem{Cut streaming bandwidth for 4K by 97\%...}
    %%% END:optional:snap-2
    %%% BEGIN:optional:snap-3
    \resumeItem{Built a controller-free interaction layer...}
    %%% END:optional:snap-3
\resumeItemListEnd
%%% END:optional:snap
```

- Bullet IDs follow the pattern `<item-id>-<n>` (e.g. `snap-1`, `snap-2`).
- Bullets are typically `optional`. Use `pinned` for a bullet that must
  always appear when its parent item is included.
- The LLM can make **minor text edits** to optional bullets (swapping
  synonyms, adding JD keywords) but should not fully rewrite them.

---

## Skills Tags

The skills section uses a special tag format. Skills are comma-separated
within a `\textbf{Category}{: skill1, skill2, ...}` line. The parser splits
individual skills so the LLM can **reorder, add, and remove** them.

```latex
%%% BEGIN:pinned:skills
\section{Skills, Awards \& Roles}
\vspace{-1pt}
 \begin{itemize}[leftmargin=0in, label={}]
    \small{\item{

     %%% SKILLS:languages
     \textbf{Languages}{: Java, Python, C++, Rust, Go, C\#, TypeScript, JavaScript, C, SQL, HTML/CSS.} \\
     %%% END:SKILLS:languages

     %%% SKILLS:cloud-infra
     \textbf{Cloud \& Infra}{: AWS, GCP, Azure, Docker, Kubernetes, Kafka, Redis, MongoDB, Linux, Git.} \\
     %%% END:SKILLS:cloud-infra

     %%% SKILLS:frameworks-tools
     \textbf{Frameworks \& Tools}{: Spring Boot, OpenTelemetry, Grafana, React, Astro, TensorFlow, Playwright.} \\
     %%% END:SKILLS:frameworks-tools

     %%% SKILLS:awards-roles
     \textbf{Awards \& Roles}{: Special Achiever's Award at VIT, Treasurer at MSE Leadership Initiative at CMU.}
     %%% END:SKILLS:awards-roles

    }}
 \end{itemize}
%%% END:pinned:skills
```

- Each `%%% SKILLS:category-name` / `%%% END:SKILLS:category-name` pair
  wraps exactly one `\textbf{...}{: ...}` line.
- The LLM can **add** new relevant skills, **remove** less relevant ones,
  and **reorder** skills within each category (most relevant first).

---

## Tag Hierarchy

```text
section (pinned|optional)
├── item (pinned|optional)
│   ├── bullet (pinned|optional)   ← LLM can tweak text
│   └── bullet ...
├── SKILLS category
│   └── individual skills          ← LLM can add/remove/reorder
└── untagged content               ← preserved as-is
```

---

## Rules

1. **Every `BEGIN` must have a matching `END`** with the same type and ID.
2. **IDs use lowercase kebab-case**: `snap`, `cloud-infra`, `snap-1`.
3. **Nesting**: sections contain items or SKILLS; items contain bullets.
   No deeper nesting.
4. **Untagged content** between tags is preserved as-is (e.g. `\vspace`,
   list start/end commands).
5. **The preamble** (everything before `\begin{document}`) is never tagged
   and always preserved verbatim.
6. **The header** (content between `\begin{document}` and the first
   `%%% BEGIN:(pinned|optional):` tag) is never tagged and always preserved
   verbatim.
