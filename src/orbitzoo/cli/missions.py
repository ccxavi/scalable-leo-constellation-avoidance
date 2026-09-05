"""Bundled mission discovery and execution commands."""

import argparse
import pkgutil
import runpy
import sys


def mission_modules() -> list[str]:
    from orbitzoo import scripts

    return sorted(
        module.name
        for module in pkgutil.iter_modules(scripts.__path__)
        if module.name != "__init__"
    )


def mission_name(module_name: str) -> str:
    return module_name.removeprefix("env_")


def list_missions(_args: argparse.Namespace) -> None:
    for module_name in mission_modules():
        print(mission_name(module_name))


def run_mission(args: argparse.Namespace) -> None:
    modules = mission_modules()
    candidates = (args.name, f"env_{args.name}")
    module_name = next((name for name in candidates if name in modules), None)
    if module_name is None:
        available = ", ".join(mission_name(name) for name in modules)
        raise SystemExit(
            f"oz: unknown mission {args.name!r}\nAvailable missions: {available}"
        )

    sys.argv = [f"oz mission {args.name}", *args.mission_args]
    runpy.run_module(f"orbitzoo.scripts.{module_name}", run_name="__main__")


def add_mission_parsers(subparsers: argparse._SubParsersAction) -> None:
    missions = subparsers.add_parser("missions", help="list bundled missions")
    missions.set_defaults(handler=list_missions)

    mission = subparsers.add_parser("mission", help="run a bundled mission")
    mission.add_argument("name", help="mission name shown by 'oz missions'")
    mission.add_argument(
        "mission_args",
        nargs=argparse.REMAINDER,
        help="mission arguments",
    )
    mission.set_defaults(handler=run_mission)
