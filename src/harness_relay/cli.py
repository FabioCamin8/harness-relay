"""Command-line entry point for the HarnessRelay package foundation."""

from __future__ import annotations

import argparse
from typing import Sequence

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for the currently supported public CLI surface."""
    parser = argparse.ArgumentParser(
        prog="harness-relay",
        description="Portable public foundation for HarnessRelay.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the supported command-line surface."""
    build_parser().parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
