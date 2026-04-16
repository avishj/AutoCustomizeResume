# Rules

1. NEVER create a file when edit_file can be used. NEVER use create_file unless file DOES NOT exist. edit_file is MANDATORY.
2. NEVER make multiple edits to one file unless the edits are unrelated work. Use a single edit_file call.
3. NEVER auto-commit. User always commits. MUST only give a message.
4. NEVER add tech debt or stupid hacks.
5. MUST use uv and uv APIs. ALWAYS use `uv run` instead of raw `python`/`pytest`. ALWAYS use `uv add` instead of `pip install`.
6. NEVER use pip/pip3/conda under any circumstances.
7. MUST divide work into logical chunks, one chunk at a time.
8. MUST give a commit message (MUST use git-committing skill to construct message) after completing each chunk.
9. MUST follow existing codebase patterns. No duplicated spaghetti with minor differences.

## Stack

Python >=3.13, uv, pytest, OpenAI SDK, LaTeX (tectonic)

## Project

CLI tool that auto-customizes a tagged LaTeX resume + cover letter for job applications using LLM-powered content selection.
