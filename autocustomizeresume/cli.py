"""CLI entry point: watch mode and one-shot mode.

Handles argument parsing, dispatches to pipeline or watcher.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from autocustomizeresume import __version__, status
from autocustomizeresume.config import ConfigError, load_config
from autocustomizeresume.namer import handle_output
from autocustomizeresume.pipeline import run_pipeline
from autocustomizeresume.watcher import watch

app = typer.Typer(
    name="autocustomizeresume",
    help="Auto-customize a tagged LaTeX resume for a job description.",
    rich_markup_mode="rich",
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:  # noqa: FBT001
    """Print version and exit."""
    if value:
        console.print(f"autocustomizeresume {__version__}")
        raise typer.Exit


def _run_oneshot(
    jd_path: Path, *, company: str | None, role: str | None, keep_dir: Path | None
) -> None:
    """Execute a single pipeline run."""
    if not jd_path.is_file():
        status.error(f"JD file not found: {jd_path}")
        sys.exit(1)

    jd_text = jd_path.read_text(encoding="utf-8").strip()
    if not jd_text:
        status.error(f"JD file is empty: {jd_path}")
        sys.exit(1)

    config = load_config()
    result = run_pipeline(
        jd_text, config, company=company, role=role, keep_dir=keep_dir
    )
    handle_output(result, config)
    status.success(f"Output → {config.paths.output_dir}/")


@app.callback(invoke_without_command=True)
def main(
    jd: Annotated[
        Path | None,
        typer.Option(help="Path to JD text file (one-shot mode). Omit for watch mode."),
    ] = None,
    company: Annotated[
        str | None,
        typer.Option(help="Override LLM-extracted company name."),
    ] = None,
    role: Annotated[
        str | None,
        typer.Option(help="Override LLM-extracted role title."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose debug logging."),
    ] = False,
    keep_dir: Annotated[
        Path | None,
        typer.Option(help="Keep build artifacts (tex, pdf) in this directory."),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Auto-customize a tagged LaTeX resume for a job description."""
    if verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )

    try:
        if jd:
            _run_oneshot(jd, company=company, role=role, keep_dir=keep_dir)
        else:
            config = load_config()
            watch(config, company=company, role=role)
    except ConfigError as exc:
        status.error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        console.print()
        sys.exit(0)
    except Exception as exc:
        status.error(f"Pipeline failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    app()
