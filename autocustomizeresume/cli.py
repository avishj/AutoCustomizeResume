"""CLI entry point: watch mode and one-shot mode.

Handles argument parsing, dispatches to pipeline or watcher.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from autocustomizeresume import status
from autocustomizeresume.config import ConfigError, load_config
from autocustomizeresume.namer import handle_output
from autocustomizeresume.pipeline import run_pipeline
from autocustomizeresume.watcher import watch


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autocustomizeresume",
        description="Auto-customize a tagged LaTeX resume for a job description.",
    )
    parser.add_argument(
        "--jd",
        metavar="PATH",
        help="Path to JD text file (one-shot mode). Omit for watch mode.",
    )
    parser.add_argument(
        "--company",
        metavar="NAME",
        help="Override LLM-extracted company name.",
    )
    parser.add_argument(
        "--role",
        metavar="TITLE",
        help="Override LLM-extracted role title.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )
    parser.add_argument(
        "--keep-dir",
        metavar="PATH",
        help="Keep build artifacts (tex, pdf) in this directory.",
    )
    return parser


def _run_oneshot(
    jd_path: str, *, company: str | None, role: str | None, keep_dir: Path | None
) -> None:
    """Execute a single pipeline run."""
    jd_file = Path(jd_path)
    if not jd_file.is_file():
        status.error(f"JD file not found: {jd_path}")
        sys.exit(1)

    jd_text = jd_file.read_text(encoding="utf-8").strip()
    if not jd_text:
        status.error(f"JD file is empty: {jd_path}")
        sys.exit(1)

    config = load_config()
    result = run_pipeline(
        jd_text, config, company=company, role=role, keep_dir=keep_dir
    )
    handle_output(result, config)
    status.success(f"Output → {config.paths.output_dir}/")


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%H:%M:%S",
        )

    try:
        if args.jd:
            keep_dir = Path(args.keep_dir) if args.keep_dir else None
            _run_oneshot(
                args.jd, company=args.company, role=args.role, keep_dir=keep_dir
            )
        else:
            config = load_config()
            watch(config, company=args.company, role=args.role)
    except ConfigError as exc:
        status.error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(0)
    except Exception as exc:
        status.error(f"Pipeline failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
