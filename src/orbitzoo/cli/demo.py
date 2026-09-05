"""Standard OrbitZoo demo command."""

import argparse


def run_demo(_args: argparse.Namespace) -> None:
    from orbitzoo.env import main as demo_main

    demo_main()


def add_demo_parser(subparsers: argparse._SubParsersAction) -> None:
    demo = subparsers.add_parser("demo", help="run the standard OrbitZoo demo")
    demo.set_defaults(handler=run_demo)
