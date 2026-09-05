from pathlib import Path

import pytest

from orbitzoo.cli import build_parser


VALID_LINE_1 = (
    "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
)
VALID_LINE_2 = (
    "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"
)


def _write_catalog_fixture(tmp_path: Path) -> Path:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "catalog.tle").write_text(
        f"ISS (ZARYA)\n{VALID_LINE_1}\n{VALID_LINE_2}\n"
    )
    (data_directory / "objects.csv").write_text(
        "norad_id,object_type,is_agent_candidate,name,radius_meters,constellation\n"
        "25544,payload,true,ISS,50,station\n"
    )
    config_path = tmp_path / "calibration.json"
    config_path.write_text(
        """{
  "catalog": {
    "tle_path": "data/catalog.tle",
    "metadata_path": "data/objects.csv",
    "minimum_altitude_meters": 200000.0,
    "maximum_altitude_meters": 2000000.0,
    "maximum_tle_age_days": 14.0,
    "default_radius_meters": 1.0
  },
  "propagation": {
    "start_epoch_mode": "latest_tle_epoch",
    "duration_seconds": 86400,
    "reference_step_seconds": 10
  },
  "safety": {
    "safe_separation_meters": 1000.0,
    "screening_horizon_seconds": 1800.0
  },
  "sweep": {
    "agent_counts": [16],
    "neighborhood_sizes": [1],
    "decision_intervals_seconds": [60],
    "calibration_seeds": [0],
    "validation_seeds": [100]
  },
  "passing_thresholds": {
    "minimum_threat_recall": 0.999,
    "minimum_timely_detection_fraction": 0.99,
    "minimum_decisions_before_tca": 3
  },
  "schema_version": 1
}
"""
    )
    return config_path


def test_catalog_command_validates_and_summarizes_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = _write_catalog_fixture(tmp_path)
    args = build_parser().parse_args(
        ["catalog", "--config", str(config_path), "--limit", "1"]
    )

    args.handler(args)

    output = capsys.readouterr().out
    assert "Catalog valid" in output
    assert "Source records: 1" in output
    assert "Retained records: 1" in output
    assert "Agent candidates: 1" in output
    assert "25544 | ISS | payload | agent=true" in output


def test_catalog_command_reports_validation_failure(tmp_path: Path) -> None:
    args = build_parser().parse_args(
        ["catalog", "--config", str(tmp_path / "missing.json")]
    )

    with pytest.raises(SystemExit, match="catalog validation failed"):
        args.handler(args)
