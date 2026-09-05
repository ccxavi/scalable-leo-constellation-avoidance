"""Catalog validation command."""

import argparse
from pathlib import Path


def check_catalog(args: argparse.Namespace) -> None:
    from orbitzoo.thesis.calibration import CalibrationConfig, load_catalog

    config_path = Path(args.config).expanduser()
    try:
        config = CalibrationConfig.load(config_path)
        catalog = load_catalog(config, config_path)
    except (KeyError, OSError, ValueError) as error:
        raise SystemExit(f"oz: catalog validation failed: {error}") from error

    agent_count = sum(item.is_agent_candidate for item in catalog.objects)
    print("Catalog valid")
    print(f"Config: {config_path.resolve()}")
    print(f"Source records: {catalog.source_record_count}")
    print(f"Retained records: {len(catalog.objects)}")
    print(f"Stale filtered: {len(catalog.stale_filtered_norad_ids)}")
    print(f"Agent candidates: {agent_count}")
    print(f"Latest epoch UTC: {catalog.latest_epoch_utc.isoformat()}")
    if args.limit:
        print("Objects:")
        for item in catalog.objects[: args.limit]:
            print(
                f"  {item.norad_id} | {item.name} | {item.object_type.value} | "
                f"agent={str(item.is_agent_candidate).lower()} | "
                f"epoch={item.tle_epoch_utc.isoformat()}"
            )


def add_catalog_parser(subparsers: argparse._SubParsersAction) -> None:
    catalog = subparsers.add_parser(
        "catalog",
        help="validate and summarize a calibration TLE catalog",
    )
    catalog.add_argument(
        "--config",
        default="configs/k_dt_calibration.json",
        help="calibration configuration path (default: %(default)s)",
    )
    catalog.add_argument(
        "--limit",
        type=int,
        default=10,
        choices=range(0, 101),
        metavar="0..100",
        help="number of retained objects to display (default: %(default)s)",
    )
    catalog.set_defaults(handler=check_catalog)
