"""CLI entry-point for the ReFiNe extraction pipeline.

Usage::

    # Extract a single paper
    python -m refine.run extract --paper-id refine_0001

    # Extract multiple papers
    python -m refine.run extract-all --limit 10
"""

# Load .env file from project root so environment variables are available
import os
from pathlib import Path as _Path
_env_path = _Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(str(_env_path), override=True)
    except ImportError:
        pass  # python-dotenv not installed, skip .env loading

import argparse
import logging
import sys
from pathlib import Path

class Console:
    def print(self, *args, **kwargs):
        print(*args)

console = Console()

# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------

# refine/run.py lives at  ReFiNe_starter/refine/run.py
# Project root is two levels up from this file
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _ensure_paths():
    """Create required directories if they don't exist."""
    for d in ["pdfs", "text", "extracted", "logs"]:
        (Path(_PROJECT_ROOT) / "data" / d).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

def _cmd_extract(args: argparse.Namespace) -> None:
    """Handle the 'extract' sub-command."""
    from .extract import extract_paper

    paper_id = args.paper_id
    console.print("ReFiNe Extraction Pipeline")
    console.print(f"  Paper ID: {paper_id}")
    console.print()

    _ensure_paths()
    extract_paper(paper_id)


def _cmd_extract_all(args: argparse.Namespace) -> None:
    """Handle the 'extract-all' sub-command."""
    from .extract import extract_all

    limit = args.limit
    console.print("ReFiNe Extraction Pipeline (batch)")
    console.print(f"  Limit: {limit}")
    console.print()

    _ensure_paths()
    extract_all(limit=limit)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="refine",
        description="ReFiNe: Replication Research Extraction pipeline",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # --- extract ---
    p_extract = sub.add_parser("extract", help="Extract features for a single paper")
    p_extract.add_argument(
        "--paper-id",
        required=True,
        help="Paper ID (e.g. refine_0001)",
    )
    p_extract.set_defaults(handler=_cmd_extract)

    # --- extract-all ---
    p_extract_all = sub.add_parser(
        "extract-all",
        help="Extract features for the first N papers with local PDFs",
    )
    p_extract_all.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of papers to process (default: 10)",
    )
    p_extract_all.set_defaults(handler=_cmd_extract_all)

    return parser


# ---------------------------------------------------------------------------
# Main entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry-point when running ``python -m refine.run``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    # Dispatch to the appropriate handler
    args.handler(args)


if __name__ == "__main__":
    main()