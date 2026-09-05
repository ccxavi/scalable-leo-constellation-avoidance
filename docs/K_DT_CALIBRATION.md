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
`data/tle/`. Input existence is checked when catalog loading is implemented;
configuration validation checks only the schema and internal consistency.

## Propagation start

`start_epoch_mode` is `latest_tle_epoch`. The future catalog loader will find
the latest epoch among accepted TLE records and use it as the common propagation
start. The exact resolved UTC timestamp must be stored with the run outputs.
This keeps the checked-in configuration usable with different frozen catalog
snapshots without making the start time ambiguous within a run.

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

```python
from orbitzoo.thesis.calibration import CalibrationConfig

path = "configs/k_dt_calibration.json"
config = CalibrationConfig.load(path)
tle_path, metadata_path = config.resolve_catalog_paths(path)
```

Saving a configuration validates it and emits deterministic, sorted JSON. The
schema version is currently `1`; unsupported versions are rejected rather than
silently interpreted.
