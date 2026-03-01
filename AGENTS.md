## Rules

1. NEVER use more than one tool call per response. NEVER ever use parallel/stacked calls.
2. NEVER create a file when edit_file can be used. NEVER use create_file unless file DOES NOT exist. edit_tool is MANDATORY.
3. NEVER make multiple edits to one file unless the edits are unrelated work. Use a single edit_file call.
4. NEVER auto-commit. User always commits. MUST only give a message.
5. NEVER add tech debt or stupid hacks.
6. MUST use uv and uv APIs. ALWAYS use `uv run` instead of raw `python`/`pytest`. ALWAYS use `uv add` instead of `pip install`.
7. NEVER use pip/pip3/conda under any circumstances.
8. MUST divide work into logical chunks, one chunk at a time.
9. MUST give a commit message (MUST use git-committing skill to construct message) after completing each chunk.
10. MUST follow existing codebase patterns. No duplicated spaghetti with minor differences.

## Stack
Python 3.14, uv, pytest, OpenAI SDK, LaTeX (tectonic)

## Project
CLI tool that auto-customizes a tagged LaTeX resume + cover letter for job applications using LLM-powered content selection.
