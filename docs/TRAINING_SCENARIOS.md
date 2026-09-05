# Training scenarios

`data/training_scenarios.json` records the top candidate orbital bands for
thesis training scenarios, ranked by real-world satellite density. It is
produced by [`utils/identify_training_scenarios.py`](../utils/identify_training_scenarios.py)
from TLE/OMM data fetched with [`utils/scrape_tle.py`](../utils/scrape_tle.py).

## Regenerating the data

```sh
# 1. Fetch fresh TLE data from CelesTrak
python3 utils/scrape_tle.py

# 2. Recompute the ranked scenario list
python3 utils/identify_training_scenarios.py --top 15

# 3. Build the frozen catalog for calibration (rank-1 band by default)
python3 utils/build_catalog.py
```

Step 3 writes `data/tle/catalog.tle` and `data/tle/objects.csv` — the exact
paths expected by `configs/k_dt_calibration.json`. Use `--rank N` to target
a different scenario band.

Results are written to `data/training_scenarios.json`. The `data/` directory
is gitignored; only the scripts and this doc are version-controlled.

---

## `training_scenarios.json` — Field Reference & Ranking Methodology

### Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `sources` | `string[]` | The CelesTrak data groups that were loaded and analyzed (e.g. `starlink`, `kuiper`, `active`, debris catalogs, etc.) |
| `alt_bin_km` | `float` | Altitude bin width in km used for discretization (default: **50 km**) |
| `inc_bin_deg` | `float` | Inclination bin width in degrees used for discretization (default: **5°**) |
| `total_leo_sats` | `int` | Total number of unique LEO satellites analyzed across all sources (200–2000 km) |
| `total_bins` | `int` | Total number of distinct (altitude × inclination) cells that contained at least one satellite |
| `top_scenarios` | `object[]` | Ordered list of the top-N densest orbital bands, ranked #1 = most satellites |

---

### Per-Scenario Fields (`top_scenarios[i]`)

| Field | Type | Description |
|---|---|---|
| `rank` | `int` | Density rank — **1 = the most populated orbital band** |
| `alt_lo_km` | `float` | Lower altitude edge of the bin (km) |
| `alt_hi_km` | `float` | Upper altitude edge of the bin (km) |
| `alt_center_km` | `float` | Midpoint altitude of the bin — `(alt_lo + alt_hi) / 2` (km) |
| `inc_lo_deg` | `float` | Lower inclination edge of the bin (degrees) |
| `inc_hi_deg` | `float` | Upper inclination edge of the bin (degrees) |
| `inc_center_deg` | `float` | Midpoint inclination of the bin — `(inc_lo + inc_hi) / 2` (degrees) |
| `satellite_count` | `int` | Number of real satellites currently occupying this orbital band |
| `known_label` | `string` | Human-readable constellation label if this band matches a known shell (e.g. `"Starlink Shell 1 (550 km, 53°)"`), empty string `""` otherwise |
| `satellites` | `string[]` | Alphabetically sorted list of all `OBJECT_NAME` values (satellite names) found in this band |

---

## Ranking Methodology

The script computes **satellite density per (altitude × inclination) bin** —
a 2-D histogram over LEO orbital space:

```
1. Load OMM records from all CelesTrak sources
2. Convert MEAN_MOTION (rev/day) → altitude (km) via Kepler's 3rd law:
     n (rad/s) = mean_motion × 2π / 86400
     a   (m)   = (GM / n²)^(1/3)
     alt (km)  = a/1000 − R_earth
3. Filter: keep only LEO objects (200 km ≤ alt ≤ 2000 km)
4. Assign each satellite to a cell:
     alt_lo  = floor(alt / 50)  × 50
     inc_lo  = floor(inc /  5)  × 5
     cell_id = (alt_lo, inc_lo)
5. Count satellites per cell
6. Sort cells descending by count  →  Rank 1 = highest count
```

### Rank 1 in the current dataset (fetched 2026-08-28)

| Field | Value |
|---|---|
| Altitude band | **450 – 500 km** (center: 475 km) |
| Inclination band | **50° – 55°** (center: 52.5°) |
| Satellite count | **4,337 satellites** |
| `known_label` | *(none — mixed constellation band)* |

This band tops the ranking because it contains a high-density mix of
**Starlink** (early-generation parking orbits), **Amazon Kuiper** (transit
at ~480 km before raising to 590–630 km), and **Guowang / Qianfan** test
objects. The 450–500 km / 50–55° cell captures a transit-and-operational
overlap zone where multiple large constellations co-exist, making it the
conjunction-richest bin in LEO and thus the most realistic starting point
for training autonomous collision-avoidance agents.

> **Thesis relevance:** The simulation initializes satellite agents in the
> top-ranked band so the environment is populated with real-world density.
> Training in a sparse region would produce agents that do not generalize
> to the actual crowded LEO environment.

---

## Altitude ↔ Mean Motion Conversion

The script never reads altitude directly from TLE records. It derives it from
`MEAN_MOTION` (revolutions/day) using Kepler's Third Law:

$$a = \left(\frac{GM}{n^2}\right)^{1/3}, \quad \text{alt} = \frac{a}{1000} - R_\oplus$$

| Constant | Value |
|---|---|
| `GM` (gravitational parameter) | 3.986004418 × 10¹⁴ m³/s² |
| `R_EARTH` (mean radius) | 6371.0 km |

---

## Known Shell Labels

[`identify_training_scenarios.py`](../utils/identify_training_scenarios.py)
pattern-matches bins against hardcoded known shells:

| Altitude (km) | Inclination (°) | Label |
|---|---|---|
| 540–570 | 52–55 | Starlink Shell 1 (550 km, 53°) |
| 560–590 | 97–98 | Starlink Shell 2 (570 km, 97.6° SSO) |
| 330–360 | 52–54 | Starlink Shell 3 (340 km, 53°) |
| 345–360 | 97–98 | Starlink Shell 4 (350 km, 97.6°) |
| 500–530 | 87–88 | Starlink Shell 5 (510 km, 87.9°) |
| 590–620 | 97–98 | OneWeb (600 km, 87.9°) |
| 590–620 | 87–89 | OneWeb (600 km, 87.9°) |
| 200–450 | 96–99 | Sun-Synchronous Orbit (SSO) band |
| 400–430 | 51–52 | ISS vicinity (408 km, 51.6°) |

Bins that do not match any shell get `known_label: ""`.
