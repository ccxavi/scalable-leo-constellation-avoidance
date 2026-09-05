# Neighborhood and decision-interval calibration

Before MAPPO training, an offline TLE calibration will select the neighborhood
size `k` and decision interval `delta t`. The calibration uses propagated orbit
states and conjunction timing only; it does not execute maneuvers or train a
policy.

## Versioned configuration

The initial configuration is
[`configs/k_dt_calibration.json`](../configs/k_dt_calibration.json). It defines:

- paths to one frozen TLE catalog and its object metadata;
- the propagation time model and LEO altitude filter;
- conjunction-screening thresholds;
- agent counts, candidate values, and deterministic seeds;
- the passing thresholds used to choose a parameter pair.

Catalog paths are resolved relative to the configuration file, not the process
working directory. The checked-in paths therefore resolve to files under
`data/tle/`. Configuration validation checks the schema and internal
consistency; `load_catalog` reports missing or unreadable input files.

## TLE catalog input

The loader accepts ordinary two-line records and three-line records with a name
above the element lines. Blank lines are ignored, and a leading `0 ` on a name
line is removed. Each element line must be exactly 69 ASCII characters with a
valid checksum. The two lines must contain the same catalog ID. Both numeric
NORAD IDs and the Space-Track Alpha-5 representation are supported.

Loading fails on malformed element fields, duplicate NORAD IDs, duplicate
metadata IDs, or metadata rows for IDs absent from the TLE file. Every accepted
epoch is returned as a timezone-aware UTC value. Records more than
`maximum_tle_age_days` older than the latest epoch in that frozen catalog are
excluded; a record exactly on the cutoff is retained. The original TLE order is
preserved. LEO altitude filtering is intentionally deferred until propagation,
when an actual state vector exists.

Metadata is UTF-8 CSV. These columns are required:

- `norad_id`: positive decoded NORAD integer;
- `object_type`: `payload`, `rocket_body`, `debris`, or `unknown` (case,
  spaces, and hyphens are normalized);
- `is_agent_candidate`: exactly `true` or `false`, case-insensitive.

The optional columns are `name`, `radius_meters`, and `constellation`; other
named columns are ignored. Radius values must be finite and positive. Only a
payload may be an agent candidate. A TLE without metadata is retained as an
unknown, non-agent object with `default_radius_meters`. Display names use
metadata first, then the TLE name, then `NORAD-<id>`.

## Propagation start

`start_epoch_mode` is `latest_tle_epoch`. The catalog loader exposes the latest
epoch among all validated TLE records as the common propagation start, including
the epoch used to establish the freshness cutoff. The exact resolved UTC
timestamp must be stored with the run outputs. This keeps the checked-in
configuration usable with different frozen catalog snapshots without making the
start time ambiguous within a run.

## Default sweep

The first calibration evaluates agent populations of 16, 64, and 256; neighbor
counts of 1, 2, 4, 8, and 16; and decision intervals of 60, 120, 300, and 600
seconds. Seeds 0 through 9 are reserved for selection, while seeds 100 through
104 are held out for validation.

The selected pair must achieve at least 99.9% threat recall. At least 99% of
reference threats must be detected with three or more decision opportunities
remaining before time of closest approach. Among passing pairs, the later
calibration runner will choose the smallest `k` and then the largest decision
interval.

## Python API

From the repository root, validate and summarize the configured real-data
catalog with one command:

```sh
oz catalog
```

Use `oz catalog --config path/to/calibration.json --limit 20` for another
configuration or a longer object preview. Set `--limit 0` for summary-only
output. The command exits unsuccessfully and prints the input location when
validation fails.

The equivalent Python API is:

```python
from orbitzoo.thesis.calibration import CalibrationConfig, load_catalog

path = "configs/k_dt_calibration.json"
config = CalibrationConfig.load(path)
catalog = load_catalog(config, path)

for object_record in catalog.objects:
    print(object_record.norad_id, object_record.tle_epoch_utc)
```

Saving a configuration validates it and emits deterministic, sorted JSON. The
schema version is currently `1`; unsupported versions are rejected rather than
silently interpreted.
