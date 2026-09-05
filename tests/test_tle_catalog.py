from datetime import timedelta, timezone
from pathlib import Path

import pytest
from sgp4.io import fix_checksum

from orbitzoo.thesis.calibration import (
    CalibrationConfig,
    CatalogConfig,
    CatalogLoadError,
    ObjectType,
    load_catalog,
)


BASE_LINE_1 = (
    "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
)
BASE_LINE_2 = (
    "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"
)
METADATA_HEADER = (
    "norad_id,object_type,is_agent_candidate,name,radius_meters,constellation\n"
)


def _tle_lines(
    catalog_field: str = "25544",
    epoch: str = "19343.69339541",
) -> tuple[str, str]:
    line1 = BASE_LINE_1[:2] + catalog_field + BASE_LINE_1[7:18] + epoch + BASE_LINE_1[32:]
    line2 = BASE_LINE_2[:2] + catalog_field + BASE_LINE_2[7:]
    return fix_checksum(line1[:68]), fix_checksum(line2[:68])


def _write_inputs(
    tmp_path: Path,
    tle_text: str,
    metadata_text: str = METADATA_HEADER,
    **catalog_overrides: object,
) -> tuple[CalibrationConfig, Path]:
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    (data_directory / "catalog.tle").write_text(tle_text)
    (data_directory / "objects.csv").write_text(metadata_text)
    config_path = tmp_path / "configs" / "calibration.json"
    config = CalibrationConfig(
        catalog=CatalogConfig(
            tle_path="../data/catalog.tle",
            metadata_path="../data/objects.csv",
            **catalog_overrides,
        )
    )
    return config, config_path


def test_loads_mixed_two_and_three_line_records_in_source_order(tmp_path: Path) -> None:
    line1_a, line2_a = _tle_lines("25544")
    line1_b, line2_b = _tle_lines("40909")
    config, config_path = _write_inputs(
        tmp_path,
        f"0 ISS (ZARYA)\n{line1_a}\n{line2_a}\n{line1_b}\n{line2_b}\n",
        METADATA_HEADER + "25544,payload,true,Metadata Name,2.5,station\n",
    )

    catalog = load_catalog(config, config_path)

    assert [item.norad_id for item in catalog.objects] == [25544, 40909]
    first, second = catalog.objects
    assert first.name == "Metadata Name"
    assert first.tle_name == "ISS (ZARYA)"
    assert first.object_type is ObjectType.PAYLOAD
    assert first.is_agent_candidate is True
    assert first.radius_meters == 2.5
    assert first.constellation == "station"
    assert first.has_metadata is True
    assert second.name == "NORAD-40909"
    assert second.object_type is ObjectType.UNKNOWN
    assert second.is_agent_candidate is False
    assert second.radius_meters == 1.0
    assert second.has_metadata is False
    assert first.tle_epoch_utc.tzinfo is timezone.utc
    assert catalog.source_record_count == 2
    assert catalog.stale_filtered_norad_ids == ()


def test_supports_alpha_5_catalog_ids(tmp_path: Path) -> None:
    line1, line2 = _tle_lines("E8493")
    config, config_path = _write_inputs(tmp_path, f"ALPHA-5 OBJECT\n{line1}\n{line2}\n")

    catalog = load_catalog(config, config_path)

    assert catalog.objects[0].norad_id == 148493
    assert catalog.objects[0].name == "ALPHA-5 OBJECT"


def test_filters_records_older_than_latest_catalog_epoch(tmp_path: Path) -> None:
    newest = _tle_lines("25544", "19350.00000000")
    boundary = _tle_lines("40909", "19336.00000000")
    stale = _tle_lines("43013", "19335.99999999")
    tle_text = "\n".join((*boundary, *stale, *newest)) + "\n"
    config, config_path = _write_inputs(
        tmp_path,
        tle_text,
        maximum_tle_age_days=14.0,
    )

    catalog = load_catalog(config, config_path)

    assert [item.norad_id for item in catalog.objects] == [40909, 25544]
    assert catalog.stale_filtered_norad_ids == (43013,)
    assert catalog.source_record_count == 3
    assert catalog.objects[0].tle_epoch_utc == catalog.latest_epoch_utc - timedelta(days=14)


@pytest.mark.parametrize(
    ("tle_text", "message"),
    [
        (BASE_LINE_1 + "\n", "not followed by line 2"),
        (BASE_LINE_1[:-1] + "0\n" + BASE_LINE_2 + "\n", "checksum"),
        (
            _tle_lines("25544")[0] + "\n" + _tle_lines("40909")[1] + "\n",
            "different catalog IDs",
        ),
    ],
)
def test_rejects_malformed_tle_records(
    tmp_path: Path,
    tle_text: str,
    message: str,
) -> None:
    config, config_path = _write_inputs(tmp_path, tle_text)

    with pytest.raises(CatalogLoadError, match=message):
        load_catalog(config, config_path)


def test_rejects_duplicate_tle_ids(tmp_path: Path) -> None:
    lines = _tle_lines()
    config, config_path = _write_inputs(tmp_path, "\n".join((*lines, *lines)) + "\n")

    with pytest.raises(CatalogLoadError, match="duplicate NORAD ID 25544"):
        load_catalog(config, config_path)


@pytest.mark.parametrize(
    ("metadata_row", "message"),
    [
        ("25544,satellite,false,,,\n", "invalid object_type"),
        ("25544,payload,yes,,,\n", "expected true or false"),
        ("25544,debris,true,,,\n", "only payloads"),
        ("25544,payload,false,,0,\n", "radius_meters must be"),
        ("40909,payload,false,,,\n", "absent from the TLE catalog"),
    ],
)
def test_rejects_invalid_metadata(
    tmp_path: Path,
    metadata_row: str,
    message: str,
) -> None:
    line1, line2 = _tle_lines()
    config, config_path = _write_inputs(
        tmp_path,
        f"{line1}\n{line2}\n",
        METADATA_HEADER + metadata_row,
    )

    with pytest.raises(CatalogLoadError, match=message):
        load_catalog(config, config_path)


def test_rejects_duplicate_metadata_ids(tmp_path: Path) -> None:
    line1, line2 = _tle_lines()
    row = "25544,payload,false,,,\n"
    config, config_path = _write_inputs(
        tmp_path,
        f"{line1}\n{line2}\n",
        METADATA_HEADER + row + row,
    )

    with pytest.raises(CatalogLoadError, match="duplicate metadata NORAD ID"):
        load_catalog(config, config_path)


def test_missing_catalog_file_is_reported_as_a_catalog_error(tmp_path: Path) -> None:
    config = CalibrationConfig(
        catalog=CatalogConfig(
            tle_path="missing.tle",
            metadata_path="missing.csv",
        )
    )

    with pytest.raises(CatalogLoadError, match="missing.tle"):
        load_catalog(config, tmp_path / "calibration.json")


def test_repeated_loads_are_deterministic(tmp_path: Path) -> None:
    line1, line2 = _tle_lines()
    config, config_path = _write_inputs(tmp_path, f"ISS\n{line1}\n{line2}\n")

    assert load_catalog(config, config_path) == load_catalog(config, config_path)
