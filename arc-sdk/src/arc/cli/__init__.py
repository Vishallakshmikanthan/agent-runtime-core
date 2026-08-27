"""ARC command-line interface (structure only).

Declares the ``arc`` console-script surface. Argument parsing is defined here;
command handlers delegate to the :class:`arc.ARC` facade, whose runtime is not
implemented in this scaffold, so subcommands report that explicitly.
"""

from __future__ import annotations

import argparse
from typing import List, Optional, Sequence

from ..version import __version__

_COMMANDS: Sequence[str] = ("trace", "replay", "verify", "recover", "inspect")


def build_parser() -> argparse.ArgumentParser:
    """Construct the top-level ``arc`` argument parser."""
    parser = argparse.ArgumentParser(prog="arc", description="Agent Runtime Core CLI")
    parser.add_argument("--version", action="version", version=f"arc {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name in _COMMANDS:
        cmd = sub.add_parser(name, help=f"{name} a session")
        cmd.add_argument("session_id", help="Target session identifier")
        cmd.add_argument("--server-url", default=None, help="ARC control-plane URL")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Console-script entrypoint for the ``arc`` command."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    # Runtime dispatch is not wired in this scaffold.
    parser.exit(
        status=2,
        message=f"arc {args.command}: runtime not implemented in this scaffold\n",
    )
    return 2


__all__ = ["main", "build_parser"]
