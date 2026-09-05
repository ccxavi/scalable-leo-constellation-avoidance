"""
identify_training_scenarios.py
===============================
Analyzes scraped CelesTrak TLE/OMM data to identify candidate orbital bands
for training scenario initialization.

Context
-------
The thesis trains N=50 satellite agents within a "constrained altitude and
inclination band" (Section 4.1.2). This script identifies which altitude ×
inclination bands have the highest real-world satellite density, so the
training constellation is initialized in a realistic, conjunction-rich region.

Methodology
-----------
1. Load OMM JSON data from data/tle_*_latest.json
2. Convert mean motion → altitude using Kepler's 3rd law
3. Filter to LEO (200–2000 km)
4. Bin satellites by altitude (50 km bins) and inclination (5° bins)
5. Rank by density → top bins = candidate training scenarios
6. Export results to data/training_scenarios.json + print summary

Usage
-----
  python3 identify_training_scenarios.py
  python3 identify_training_scenarios.py --alt-bin 25 --inc-bin 2
  python3 identify_training_scenarios.py --source active starlink
  python3 identify_training_scenarios.py --top 20
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GM       = 3.986004418e14   # Earth gravitational parameter, m³/s²
R_EARTH  = 6371.0           # Earth mean radius, km

LEO_ALT_MIN_KM = 200.0      # LEO lower bound
LEO_ALT_MAX_KM = 2000.0     # LEO upper bound (thesis scope)

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Orbital mechanics helpers
# ---------------------------------------------------------------------------


def mean_motion_to_altitude_km(mean_motion_rev_per_day: float) -> float:
    """
    Convert TLE mean motion (rev/day) to altitude above Earth's surface (km).

    Steps:
      n (rad/s) = mean_motion * 2π / 86400
      a (m)     = (GM / n²)^(1/3)    [Kepler 3rd law]
      alt (km)  = (a - R_earth*1000) / 1000
    """
    n_rad_s = mean_motion_rev_per_day * 2.0 * math.pi / 86400.0
    a_m     = (GM / (n_rad_s ** 2)) ** (1.0 / 3.0)
    alt_km  = (a_m / 1000.0) - R_EARTH
    return alt_km


def bin_value(value: float, bin_size: float) -> float:
    """Return the lower edge of the bin containing value."""
    return math.floor(value / bin_size) * bin_size


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_sources(source_names: list[str]) -> list[dict]:
    """
    Load OMM records from the specified source groups.
    Deduplicates by NORAD_CAT_ID (some objects appear in multiple groups).
    """
    seen_ids = set()
    records  = []

    for name in source_names:
        path = DATA_DIR / f"tle_{name}_latest.json"
        if not path.exists():
            print(f"  [!] {path.name} not found — skipping. Run scrape_tle.py first.")
            continue

        with open(path, "r", encoding="utf-8") as f:
            group_records = json.load(f)

        added = 0
        for rec in group_records:
            cat_id = rec.get("NORAD_CAT_ID")
            if cat_id not in seen_ids:
                seen_ids.add(cat_id)
                records.append(rec)
                added += 1

        print(f"  Loaded {added:>6,} records from {name} ({len(group_records):,} total, {len(group_records)-added:,} duplicates skipped)")

    return records


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze(
    records:    list[dict],
    alt_bin_km: float,
    inc_bin_deg: float,
) -> tuple[list[dict], list[dict]]:
    """
    Compute satellite density per (altitude_band × inclination_band) cell.

    Returns
    -------
    leo_records : list[dict]
        All records that fall within LEO, with altitude added.
    bins : list[dict]
        Sorted list of bins (densest first), each containing:
        - alt_lo, alt_hi   : altitude band edges (km)
        - inc_lo, inc_hi   : inclination band edges (degrees)
        - count            : number of satellites in this cell
        - satellites        : list of OBJECT_NAME strings in this cell
    """
    # Accumulate per-cell
    cell_counts     = defaultdict(int)
    cell_satellites = defaultdict(list)
    leo_records     = []

    skipped_non_leo = 0
    skipped_no_mm   = 0

    for rec in records:
        mm = rec.get("MEAN_MOTION")
        if mm is None or mm <= 0:
            skipped_no_mm += 1
            continue

        alt = mean_motion_to_altitude_km(mm)
        inc = rec.get("INCLINATION", 0.0)

        if not (LEO_ALT_MIN_KM <= alt <= LEO_ALT_MAX_KM):
            skipped_non_leo += 1
            continue

        rec["_altitude_km"]    = round(alt, 2)
        rec["_inclination_deg"] = inc
        leo_records.append(rec)

        alt_lo  = bin_value(alt, alt_bin_km)
        inc_lo  = bin_value(inc, inc_bin_deg)
        cell_id = (alt_lo, inc_lo)

        cell_counts[cell_id]     += 1
        cell_satellites[cell_id].append(rec.get("OBJECT_NAME", "UNKNOWN"))

    print(f"\n  Total records        : {len(records):,}")
    print(f"  LEO (within scope)   : {len(leo_records):,}")
    print(f"  Non-LEO (filtered)   : {skipped_non_leo:,}")
    print(f"  Missing mean motion  : {skipped_no_mm:,}")

    # Build sorted bin list
    bins = []
    for (alt_lo, inc_lo), count in sorted(cell_counts.items(), key=lambda x: -x[1]):
        bins.append({
            "alt_lo_km":    alt_lo,
            "alt_hi_km":    alt_lo + alt_bin_km,
            "inc_lo_deg":   inc_lo,
            "inc_hi_deg":   inc_lo + inc_bin_deg,
            "count":        count,
            "satellites":   sorted(cell_satellites[(alt_lo, inc_lo)]),
        })

    return leo_records, bins


# ---------------------------------------------------------------------------
# Training scenario labeling
# ---------------------------------------------------------------------------

KNOWN_SHELLS = [
    # (alt_lo, alt_hi, inc_lo, inc_hi, label)
    (540, 570,  52, 54,  "Starlink Shell 1 (550 km, 53°)"),
    (540, 570,  53, 55,  "Starlink Shell 1 (550 km, 53°)"),
    (560, 590,  97, 98,  "Starlink Shell 2 (570 km, 97.6° SSO)"),
    (330, 360,  52, 54,  "Starlink Shell 3 (340 km, 53°)"),
    (345, 360,  97, 98,  "Starlink Shell 4 (350 km, 97.6°)"),
    (500, 530,  87, 88,  "Starlink Shell 5 (510 km, 87.9°)"),
    (590, 620,  97, 98,  "OneWeb (600 km, 87.9°)"),
    (590, 620,  87, 89,  "OneWeb (600 km, 87.9°)"),
    (200, 450,  96, 99,  "Sun-Synchronous Orbit (SSO) band"),
    (400, 430,  51, 52,  "ISS vicinity (408 km, 51.6°)"),
]


def label_bin(b: dict) -> str:
    for alt_lo, alt_hi, inc_lo, inc_hi, label in KNOWN_SHELLS:
        if (alt_lo <= b["alt_lo_km"] < alt_hi and
                inc_lo <= b["inc_lo_deg"] < inc_hi):
            return label
    return ""


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_top_bins(bins: list[dict], top_n: int, alt_bin_km: float, inc_bin_deg: float):
    print(f"\n{'='*72}")
    print(f"  Top {top_n} Candidate Training Scenario Orbital Bands")
    print(f"  (alt bin={alt_bin_km} km, inc bin={inc_bin_deg}°)")
    print(f"{'='*72}")
    print(f"  {'#':<4} {'Alt range (km)':<22} {'Inc range (°)':<18} {'Sats':>6}  Label")
    print(f"  {'-'*4} {'-'*22} {'-'*18} {'-'*6}  {'-'*30}")
    for i, b in enumerate(bins[:top_n], 1):
        alt_range = f"{b['alt_lo_km']:.0f}–{b['alt_hi_km']:.0f}"
        inc_range = f"{b['inc_lo_deg']:.0f}–{b['inc_hi_deg']:.0f}"
        label = label_bin(b)
        print(f"  {i:<4} {alt_range:<22} {inc_range:<18} {b['count']:>6}  {label}")
    print(f"{'='*72}\n")


def build_output(bins: list[dict], top_n: int, sources: list[str], alt_bin_km: float, inc_bin_deg: float) -> dict:
    top_bins = bins[:top_n]
    scenarios = []
    for rank, b in enumerate(top_bins, 1):
        scenarios.append({
            "rank":            rank,
            "alt_lo_km":       b["alt_lo_km"],
            "alt_hi_km":       b["alt_hi_km"],
            "alt_center_km":   round((b["alt_lo_km"] + b["alt_hi_km"]) / 2, 1),
            "inc_lo_deg":      b["inc_lo_deg"],
            "inc_hi_deg":      b["inc_hi_deg"],
            "inc_center_deg":  round((b["inc_lo_deg"] + b["inc_hi_deg"]) / 2, 1),
            "satellite_count": b["count"],
            "known_label":     label_bin(b),
        })
    return {
        "sources":         sources,
        "alt_bin_km":      alt_bin_km,
        "inc_bin_deg":     inc_bin_deg,
        "total_leo_sats":  sum(b["count"] for b in bins),
        "total_bins":      len(bins),
        "top_scenarios":   scenarios,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEFAULT_SOURCES = [
    "active",
    "starlink",
    "oneweb",
    "kuiper",
    "qianfan",
    "fengyun-1c-debris",
    "iridium-33-debris",
    "cosmos-2251-debris",
    "cubesat",
    "planet",
    "spire",
    "science",
    "amateur",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Identify candidate training scenario orbital bands from TLE data."
    )
    parser.add_argument(
        "--source", "-s",
        nargs="+",
        default=DEFAULT_SOURCES,
        metavar="GROUP",
        help="Which scraped groups to analyze (default: all LEO groups).",
    )
    parser.add_argument(
        "--alt-bin",
        type=float,
        default=50.0,
        metavar="KM",
        help="Altitude bin size in km (default: 50).",
    )
    parser.add_argument(
        "--inc-bin",
        type=float,
        default=5.0,
        metavar="DEG",
        help="Inclination bin size in degrees (default: 5).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        metavar="N",
        help="Number of top scenarios to display/export (default: 15).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"\n{'='*72}")
    print(f"  Training Scenario Identifier — Loading TLE data")
    print(f"{'='*72}")

    records = load_sources(args.source)
    if not records:
        print("\n[!] No records loaded. Run scrape_tle.py first.")
        return

    leo_records, bins = analyze(records, args.alt_bin, args.inc_bin)

    if not bins:
        print("[!] No LEO satellites found in the data.")
        return

    print_top_bins(bins, args.top, args.alt_bin, args.inc_bin)

    # Save results
    output = build_output(bins, args.top, args.source, args.alt_bin, args.inc_bin)
    out_path = DATA_DIR / "training_scenarios.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"  Results saved to: {out_path}")
    print(f"  Total LEO satellites analyzed: {output['total_leo_sats']:,}")
    print(f"  Total distinct bins found: {output['total_bins']:,}\n")


if __name__ == "__main__":
    main()
