"""
scrape_tle.py
=============
Fetches Two-Line Element (TLE / OMM) data from CelesTrak for LEO satellite
constellation research.

Context
-------
This script supports the thesis:
  "Scalable Shared-Policy MARL with Locality-Constrained Coordination for
   Autonomous Collision Avoidance in Large LEO Satellite Constellations"

The thesis uses publicly available TLE datasets from CelesTrak to initialize
satellite orbital states in the OrbitZoo digital twin environment.

Data sources
------------
All data is fetched from CelesTrak's GP query API:
  https://celestrak.org/NORAD/elements/gp.php?GROUP=<group>&FORMAT=<fmt>

IMPORTANT: CelesTrak now recommends using the OMM JSON format (FORMAT=json)
over the legacy TLE text format, because NORAD catalog numbers exceeded 99999
on 2026-07-11. Objects with catalog numbers >= 100000 cannot be represented
in the fixed-field TLE format. Always prefer JSON/OMM for new code.

Usage
-----
  python3 scrape_tle.py               # Fetch all configured groups
  python3 scrape_tle.py --group active  # Fetch a specific group only
  python3 scrape_tle.py --list          # List available groups and exit
  python3 scrape_tle.py --leo-only      # Fetch only LEO-relevant groups

Output
------
  data/
    tle_<group>_<timestamp>.json      -- OMM JSON (primary, supports 6-digit IDs)
    tle_<group>_<timestamp>.tle       -- Legacy TLE text (objects < 100000 only)
    tle_<group>_latest.json           -- Latest fetch copy (easy access)
    tle_<group>_latest.tle            -- Latest fetch copy (easy access)
    metadata.json                     -- Fetch log / manifest
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"

# All groups relevant to LEO constellation research (thesis scope).
# Ordered from highest-priority (most relevant) to lowest.
LEO_GROUPS = [
    # General LEO active population — primary dataset for training initialization
    ("active",              "Active Satellites (all)"),
    # Mega-constellations — the main collision risk environment studied
    ("starlink",            "Starlink"),
    ("oneweb",              "OneWeb"),
    ("kuiper",              "Amazon Kuiper"),
    ("qianfan",             "Qianfan (SpaceSail)"),
    # Debris fields — relevant for realistic conjunction scenarios
    ("fengyun-1c-debris",   "Fengyun 1C Debris (Chinese ASAT test)"),
    ("iridium-33-debris",   "Iridium 33 Debris"),
    ("cosmos-2251-debris",  "Cosmos 2251 Debris"),
    # Other LEO populations
    ("cubesat",             "CubeSats"),
    ("amateur",             "Amateur Radio Satellites"),
    ("science",             "Space & Earth Science Satellites"),
    ("planet",              "Planet Labs"),
    ("spire",               "Spire"),
]

# Groups NOT included by default (non-LEO / out of thesis scope):
#   geo, gps-ops, glo-ops, galileo, beidou, gnss, tdrss, intelsat, ses, ...

ALL_GROUPS = LEO_GROUPS + [
    ("stations",        "Space Stations"),
    ("visual",          "100 Brightest"),
    ("last-30-days",    "Last 30 Days' Launches"),
    ("analyst",         "Analyst Satellites"),
    ("weather",         "Weather"),
    ("resource",        "Earth Resources"),
    ("sar",             "Synthetic Aperture Radar"),
    ("military",        "Miscellaneous Military"),
    ("radar",           "Radar Calibration"),
]

DATA_DIR = Path(__file__).parent.parent / "data"

# CelesTrak usage policy: cache data, don't hammer the endpoint.
REQUEST_DELAY_SECONDS = 2.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    """Return current UTC timestamp as ISO-8601 compact string."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_group(group: str, fmt: str = "json", retries: int = 3) -> bytes:
    """
    Fetch TLE/OMM data for a group from CelesTrak.

    Parameters
    ----------
    group : str
        CelesTrak GROUP parameter value (e.g. 'active', 'starlink').
    fmt : str
        FORMAT parameter: 'json' (OMM JSON) or 'tle' (legacy TLE text).
    retries : int
        Number of retry attempts on transient errors.

    Returns
    -------
    bytes
        Raw response body.
    """
    url = f"{BASE_URL}?GROUP={group}&FORMAT={fmt}"
    headers = {
        "User-Agent": (
            "thesis-tle-scraper/1.0 "
            "(LEO constellation research; "
            "contact: ccxavillarin@gmail.com)"
        )
    }

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if not data:
                    raise ValueError(f"Empty response from {url}")
                return data
        except urllib.error.HTTPError as e:
            print(f"    [!] HTTP {e.code} for {url} (attempt {attempt}/{retries})")
            if e.code in (429, 503) and attempt < retries:
                wait = 10 * attempt
                print(f"    ... Rate limited. Waiting {wait}s before retry.")
                time.sleep(wait)
            elif attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"    [!] Network error for {url}: {e} (attempt {attempt}/{retries})")
            if attempt < retries:
                time.sleep(5 * attempt)
            else:
                raise


def save_json(data: bytes, path: Path) -> int:
    """
    Parse and pretty-save OMM JSON data.

    Returns
    -------
    int
        Number of satellite records saved.
    """
    records = json.loads(data.decode("utf-8"))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    return len(records) if isinstance(records, list) else 1


def save_tle(data: bytes, path: Path) -> int:
    """
    Save legacy TLE text data and return the number of TLE sets found.
    Only valid 3LE sets (name + line1 + line2) are kept.
    """
    text = data.decode("utf-8", errors="replace")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]

    sets_saved = 0
    valid_lines = []
    i = 0
    while i < len(lines):
        if i + 2 < len(lines):
            name  = lines[i]
            line1 = lines[i + 1]
            line2 = lines[i + 2]
            if line1.startswith("1 ") and line2.startswith("2 "):
                valid_lines += [name, line1, line2]
                sets_saved += 1
                i += 3
                continue
        i += 1

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(valid_lines))
        if valid_lines:
            f.write("\n")

    return sets_saved


def load_metadata(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"fetches": []}


def save_metadata(meta: dict, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------


def scrape_group(group: str, label: str, timestamp: str) -> dict:
    """
    Fetch both JSON (OMM) and TLE formats for a group and save to data/.

    Returns
    -------
    dict
        Fetch result record for the manifest.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    result = {
        "group": group,
        "label": label,
        "timestamp": timestamp,
        "json_file": None,
        "tle_file": None,
        "records_json": 0,
        "records_tle": 0,
        "errors": [],
    }

    # -- JSON (OMM) ----------------------------------------------------------
    json_path   = DATA_DIR / f"tle_{group}_{timestamp}.json"
    latest_json = DATA_DIR / f"tle_{group}_latest.json"
    try:
        print(f"  Fetching JSON (OMM): {group} ...", end=" ", flush=True)
        raw = fetch_group(group, fmt="json")
        count = save_json(raw, json_path)
        save_json(raw, latest_json)
        result["json_file"] = json_path.name
        result["records_json"] = count
        print(f"OK ({count:,} records)")
    except Exception as e:
        result["errors"].append(f"JSON fetch failed: {e}")
        print(f"FAILED: {e}")

    time.sleep(REQUEST_DELAY_SECONDS)

    # -- TLE text (legacy) ---------------------------------------------------
    tle_path   = DATA_DIR / f"tle_{group}_{timestamp}.tle"
    latest_tle = DATA_DIR / f"tle_{group}_latest.tle"
    try:
        print(f"  Fetching TLE (text): {group} ...", end=" ", flush=True)
        raw = fetch_group(group, fmt="tle")
        count = save_tle(raw, tle_path)
        save_tle(raw, latest_tle)
        result["tle_file"] = tle_path.name
        result["records_tle"] = count
        print(f"OK ({count:,} TLE sets)")
    except Exception as e:
        result["errors"].append(f"TLE fetch failed: {e}")
        print(f"FAILED: {e}")

    time.sleep(REQUEST_DELAY_SECONDS)

    return result


def scrape_groups(groups: list) -> None:
    """
    Scrape a list of (group, label) pairs and write metadata manifest.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = DATA_DIR / "metadata.json"
    meta = load_metadata(meta_path)

    timestamp = utc_now()
    print(f"\n{'='*60}")
    print(f"  CelesTrak TLE Scraper — {timestamp}")
    print(f"  Fetching {len(groups)} group(s) to: {DATA_DIR}")
    print(f"{'='*60}\n")

    session_results = []
    for group, label in groups:
        print(f"[{group}] {label}")
        result = scrape_group(group, label, timestamp)
        session_results.append(result)
        print()

    # Update manifest
    meta["fetches"].append({
        "session_timestamp": timestamp,
        "groups_fetched": len(groups),
        "results": session_results,
    })
    save_metadata(meta, meta_path)

    # Summary
    total_json   = sum(r["records_json"] for r in session_results)
    total_tle    = sum(r["records_tle"]  for r in session_results)
    json_errors  = sum(1 for r in session_results if any("JSON" in e for e in r["errors"]))
    tle_warnings = sum(1 for r in session_results if any("TLE"  in e for e in r["errors"]))

    print(f"{'='*60}")
    print(f"  Done.")
    print(f"    Groups fetched      : {len(groups)}")
    print(f"    JSON records (OMM)  : {total_json:,}  [primary format]")
    print(f"    TLE sets (legacy)   : {total_tle:,}")
    if tle_warnings:
        print(f"    TLE warnings        : {tle_warnings} "
              f"(CelesTrak is retiring the TLE text endpoint for large groups)")
    if json_errors:
        print(f"    JSON errors         : {json_errors}  [!]")
    print(f"    Manifest            : {meta_path}")
    print(f"{'='*60}\n")

    # Only exit with error if JSON (primary) fetches failed
    if json_errors:
        print("  [!] Some JSON fetches failed. Check data/metadata.json for details.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch TLE/OMM data from CelesTrak for LEO satellite research.\n"
            "Saves both OMM JSON (primary) and legacy TLE text formats."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--group", "-g",
        metavar="GROUP",
        help="Fetch a specific group only (e.g. active, starlink, oneweb).",
    )
    parser.add_argument(
        "--leo-only",
        action="store_true",
        default=True,
        help="Fetch only LEO-relevant groups (default).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Fetch ALL available groups (including GEO, GPS, etc.).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available groups and exit.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list:
        print("\nLEO groups (fetched by default):")
        for g, label in LEO_GROUPS:
            print(f"  {g:<30}  {label}")
        print("\nAdditional groups (use --all to include):")
        for g, label in ALL_GROUPS:
            if (g, label) not in LEO_GROUPS:
                print(f"  {g:<30}  {label}")
        print()
        return

    if args.group:
        all_map = {g: l for g, l in ALL_GROUPS}
        label = all_map.get(args.group, args.group)
        groups = [(args.group, label)]
    elif args.all:
        groups = ALL_GROUPS
    else:
        groups = LEO_GROUPS

    scrape_groups(groups)


if __name__ == "__main__":
    main()
