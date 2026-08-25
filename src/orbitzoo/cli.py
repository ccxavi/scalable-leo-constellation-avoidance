"""Command-line interface for OrbitZoo."""

import argparse
import pkgutil
import runpy
import sys
from pathlib import Path


def _mission_modules():
    from orbitzoo import scripts

    return sorted(
        module.name
        for module in pkgutil.iter_modules(scripts.__path__)
        if module.name != "__init__"
    )


def _mission_name(module_name):
    return module_name.removeprefix("env_")


def _run_demo(_args):
    from orbitzoo.env import main as demo_main

    demo_main()


def _run_file(args):
    script = Path(args.file).expanduser()
    if not script.is_file():
        raise SystemExit(f"oz: script not found: {script}")

    sys.argv = [str(script), *args.script_args]
    runpy.run_path(str(script), run_name="__main__")


def _list_missions(_args):
    for module_name in _mission_modules():
        print(_mission_name(module_name))


def _run_mission(args):
    modules = _mission_modules()
    candidates = (args.name, f"env_{args.name}")
    module_name = next((name for name in candidates if name in modules), None)
    if module_name is None:
        available = ", ".join(_mission_name(name) for name in modules)
        raise SystemExit(
            f"oz: unknown mission {args.name!r}\nAvailable missions: {available}"
        )

    sys.argv = [f"oz mission {args.name}", *args.mission_args]
    runpy.run_module(f"orbitzoo.scripts.{module_name}", run_name="__main__")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="oz",
        description="Run OrbitZoo demos and mission scripts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run the standard OrbitZoo demo")
    demo.set_defaults(handler=_run_demo)

    run = subparsers.add_parser("run", help="run a Python mission file")
    run.add_argument("file", help="path to the Python script")
    run.add_argument("script_args", nargs=argparse.REMAINDER, help="script arguments")
    run.set_defaults(handler=_run_file)

    missions = subparsers.add_parser("missions", help="list bundled missions")
    missions.set_defaults(handler=_list_missions)

    mission = subparsers.add_parser("mission", help="run a bundled mission")
    mission.add_argument("name", help="mission name shown by 'oz missions'")
    mission.add_argument("mission_args", nargs=argparse.REMAINDER, help="mission arguments")
    mission.set_defaults(handler=_run_mission)

    return parser


def main():
    args = build_parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
