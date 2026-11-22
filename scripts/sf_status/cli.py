"""Command line entry point; each subcommand registers itself in COMMANDS."""
import argparse
import sys
from dataclasses import fields
from typing import Callable

from .config import ServerConfig, load_server_config


def _add_config(sub) -> None:
    p = sub.add_parser("config", help="print one server setting")
    p.add_argument("key", choices=[f.name for f in fields(ServerConfig)])


def _run_config(args: argparse.Namespace) -> int:
    value = getattr(load_server_config(), args.key)
    print(str(value).lower() if isinstance(value, bool) else value)
    return 0


# name -> (function adding the subparser, function running it with parsed args)
# Later tasks append their own entries here.
COMMANDS: dict[str, tuple[Callable, Callable[[argparse.Namespace], int]]] = {
    "config": (_add_config, _run_config),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sf-status")
    sub = parser.add_subparsers(dest="command", required=True)
    for add, _ in COMMANDS.values():
        add(sub)
    return parser


def main(argv: list[str]) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    return COMMANDS[args.command][1](args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
