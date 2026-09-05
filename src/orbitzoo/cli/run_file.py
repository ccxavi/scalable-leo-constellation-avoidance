"""External Python mission-file command."""

import argparse
from pathlib import Path
import runpy
import sys


def run_file(args: argparse.Namespace) -> None:
    script = Path(args.file).expanduser()
    if not script.is_file():
        raise SystemExit(f"oz: script not found: {script}")

    sys.argv = [str(script), *args.script_args]
    runpy.run_path(str(script), run_name="__main__")


def add_run_parser(subparsers: argparse._SubParsersAction) -> None:
    run = subparsers.add_parser("run", help="run a Python mission file")
    run.add_argument("file", help="path to the Python script")
    run.add_argument(
        "script_args",
        nargs=argparse.REMAINDER,
        help="script arguments",
    )
    run.set_defaults(handler=run_file)
