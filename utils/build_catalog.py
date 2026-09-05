#!/usr/bin/env python3
"""
build_catalog.py — Build a frozen TLE catalog for k/Δt calibration.

Reads the top-ranked (or specified) training scenario from
data/training_scenarios.json, filters all scraped TLE/OMM data to
satellites in that orbital band, and writes:

    data/tle/catalog.tle   -- frozen three-line TLE file
    data/tle/objects.csv   -- object metadata

These files satisfy the paths expected by configs/k_dt_calibration.json.

Usage
-----
    python3 utils/build_catalog.py              # rank-1 scenario (default)
    python3 utils/build_catalog.py --rank 2     # second-densest band
    python3 utils/build_catalog.py --help
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
TLE_DIR = DATA_DIR / "tle"
SCENARIOS_FILE = DATA_DIR / "training_scenarios.json"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GM = 3.986004418e14   # m³/s²  (must match identify_training_scenarios.py)
R_EARTH_KM = 6371.0   # km

# Groups whose satellites are non-maneuvering debris
DEBRIS_GROUPS: set[str] = {
    "fengyun-1c-debris",
    "iridium-33-debris",
    "cosmos-2251-debris",
}

# Canonical constellation labels per scraper group
CONSTELLATION_LABELS: dict[str, str] = {
    "starlink":           "starlink",
    "oneweb":             "oneweb",
    "kuiper":             "kuiper",
    "qianfan":            "qianfan",
    "fengyun-1c-debris":  "fengyun-1c-debris",
    "iridium-33-debris":  "iridium-33-debris",
    "cosmos-2251-debris": "cosmos-2251-debris",
    "planet":             "planet",
    "spire":              "spire",
}

# Load order: debris groups must come before the catch-all 'active' catalog
# so their object type is not overwritten by the payload default.
LOAD_ORDER: list[str] = [
    "fengyun-1c-debris",
    "iridium-33-debris",
    "cosmos-2251-debris",
    "starlink",
    "oneweb",
    "kuiper",
    "qianfan",
    "planet",
    "spire",
    "cubesat",
    "amateur",
    "science",
    "active",   # catch-all: anything not already seen above
]

# Alpha-5 letters for NORAD IDs > 99 999 (I and O are excluded)
_ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"


def norad_to_alpha5(norad: int) -> str:
    """
    Encode a NORAD catalog number as a 5-character Alpha-5 string.

    For IDs ≤ 99 999 this is a zero-padded decimal.  For IDs > 99 999,
    the leading digit is replaced by a letter (A=10 000x, B=11 000x, …)
    using the Space-Track Alpha-5 encoding that skips I and O.
    """
    if norad <= 99999:
        return f"{norad:05d}"
    # Subtract 100 000 to get the offset, then map the leading 'digit'
    offset = norad - 100000
    letter_index, remainder = divmod(offset, 10000)
    if letter_index >= len(_ALPHA5):
        raise ValueError(f"NORAD ID {norad} exceeds Alpha-5 range")
    return f"{_ALPHA5[letter_index]}{remainder:04d}"

# ---------------------------------------------------------------------------
# Orbital mechanics
# ---------------------------------------------------------------------------


def mean_motion_to_altitude_km(mean_motion_revday: float) -> float:
    n = mean_motion_revday * 2 * math.pi / 86400
    a = (GM / n ** 2) ** (1 / 3)
    return a / 1000 - R_EARTH_KM


def in_band(
    rec: dict,
    alt_lo: float,
    alt_hi: float,
    inc_lo: float,
    inc_hi: float,
) -> bool:
    try:
        mm = float(rec["MEAN_MOTION"])
        inc = float(rec["INCLINATION"])
        if mm <= 0:
            return False
    except (KeyError, TypeError, ValueError):
        return False
    alt = mean_motion_to_altitude_km(mm)
    return alt_lo <= alt < alt_hi and inc_lo <= inc < inc_hi


# ---------------------------------------------------------------------------
# TLE checksum
# ---------------------------------------------------------------------------


def tle_checksum(line_68: str) -> int:
    return (
        sum(int(c) if c.isdigit() else (1 if c == "-" else 0) for c in line_68) % 10
    )


# ---------------------------------------------------------------------------
# TLE exponential-notation encoder
# ---------------------------------------------------------------------------


def encode_tle_exp(value: float) -> str:
    """
    Encode a float as an 8-character TLE exponential field.

    TLE format: SMMMMMSE  where
      S     = sign (' ' or '-')
      MMMMM = 5-digit integer mantissa (implied decimal before: 0.MMMMM)
      S     = exponent sign ('+' or '-')
      E     = single exponent digit
    """
    if value == 0.0:
        return " 00000-0"
    sign = "-" if value < 0 else " "
    v = abs(value)
    exp = math.floor(math.log10(v)) + 1
    mantissa = int(round(v / (10 ** exp) * 1e5))
    if mantissa >= 100000:
        mantissa = 99999
    exp_sign = "+" if exp >= 0 else "-"
    return f"{sign}{mantissa:05d}{exp_sign}{abs(exp)}"


# ---------------------------------------------------------------------------
# Epoch conversion
# ---------------------------------------------------------------------------


def epoch_to_tle(epoch_str: str) -> str:
    """
    Convert an ISO-8601 epoch string to TLE epoch YYDDD.DDDDDDDD (14 chars).
    """
    epoch_str = epoch_str.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(epoch_str, fmt)
            break
        except ValueError:
            pass
    else:
        raise ValueError(f"Unrecognised epoch: {epoch_str!r}")
    yy = dt.year % 100
    day_frac = (dt - datetime(dt.year, 1, 1)).total_seconds() / 86400 + 1.0
    return f"{yy:02d}{day_frac:012.8f}"


# ---------------------------------------------------------------------------
# International designator formatter
# ---------------------------------------------------------------------------


def format_intldes(object_id: str) -> str:
    """
    Convert OMM OBJECT_ID (e.g. '2019-074B') to TLE INTLDES (e.g. '19074B  ').

    Strips the century prefix and the first hyphen, then left-justifies to 8.
    """
    oid = (object_id or "").strip()
    # "YYYY-NNNP..." → drop century (first 2 chars) and hyphen at position 4
    if len(oid) >= 5 and oid[4] == "-":
        oid = oid[2:4] + oid[5:]
    return oid.ljust(8)[:8]


# ---------------------------------------------------------------------------
# OMM JSON → TLE three-line set
# ---------------------------------------------------------------------------


def omm_to_tle_lines(rec: dict) -> tuple[str, str, str]:
    """
    Convert one OMM JSON record to (name, line1, line2).

    Raises ValueError when required fields are missing or malformed.
    """
    norad = int(rec["NORAD_CAT_ID"])
    norad_str = norad_to_alpha5(norad)  # 5-char, Alpha-5 for IDs > 99 999
    cls = ((rec.get("CLASSIFICATION_TYPE") or "U")[0]).upper()
    intldes = format_intldes(rec.get("OBJECT_ID") or rec.get("INTLDES") or "")
    epoch = epoch_to_tle(str(rec["EPOCH"]))  # exactly 14 chars

    # First derivative of mean motion: ' .DDDDDDDD' or '-.DDDDDDDD' (10 chars)
    mm_dot = float(rec.get("MEAN_MOTION_DOT") or 0)
    if mm_dot >= 0:
        mm_dot_str = f" {mm_dot:.8f}".replace(" 0.", " .")
    else:
        mm_dot_str = f"{mm_dot:.8f}".replace("-0.", "-.")
    mm_ddot_str = encode_tle_exp(float(rec.get("MEAN_MOTION_DDOT") or 0))
    bstar_str = encode_tle_exp(float(rec.get("BSTAR") or 0))

    eph = int(rec.get("EPHEMERIS_TYPE") or 0)
    elset = int(rec.get("ELEMENT_SET_NO") or 999) % 10000

    # Line 1 body — exactly 68 chars before checksum
    l1 = (
        f"1 {norad_str}{cls} "
        f"{intldes} "
        f"{epoch} "
        f"{mm_dot_str} "
        f"{mm_ddot_str} "
        f"{bstar_str} "
        f"{eph} "
        f"{elset:4d}"
    )
    if len(l1) != 68:
        raise ValueError(f"Line 1 is {len(l1)} chars (expected 68): {l1!r}")
    line1 = l1 + str(tle_checksum(l1))

    inc = float(rec["INCLINATION"])
    raan = float(rec["RA_OF_ASC_NODE"])
    ecc = float(rec["ECCENTRICITY"])
    aop = float(rec["ARG_OF_PERICENTER"])
    ma = float(rec["MEAN_ANOMALY"])
    mm = float(rec["MEAN_MOTION"])
    rev = int(rec.get("REV_AT_EPOCH") or 0) % 100000

    # Eccentricity: strip leading "0." → 7-digit integer string
    ecc_str = f"{ecc:.7f}"[2:]

    # Line 2 body — exactly 68 chars before checksum
    l2 = (
        f"2 {norad_str} "
        f"{inc:8.4f} "
        f"{raan:8.4f} "
        f"{ecc_str} "
        f"{aop:8.4f} "
        f"{ma:8.4f} "
        f"{mm:11.8f}"
        f"{rev:5d}"
    )
    if len(l2) != 68:
        raise ValueError(f"Line 2 is {len(l2)} chars (expected 68): {l2!r}")
    line2 = l2 + str(tle_checksum(l2))

    name = (rec.get("OBJECT_NAME") or f"NORAD-{norad}").strip()[:24]
    return name, line1, line2


# ---------------------------------------------------------------------------
# TLE text file parser
# ---------------------------------------------------------------------------


def parse_tle_file(path: Path) -> dict[int, tuple[str, str, str]]:
    """
    Parse a three-line TLE text file.

    Returns {norad_id: (name, line1, line2)}.
    """
    result: dict[int, tuple[str, str, str]] = {}
    lines = [
        ln.rstrip()
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip()
    ]
    i = 0
    while i < len(lines) - 2:
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if (
            l1.startswith("1 ")
            and l2.startswith("2 ")
            and len(l1) >= 68
            and len(l2) >= 68
        ):
            try:
                norad = int(l1[2:7])
                result[norad] = (name.strip(), l1, l2)
                i += 3
                continue
            except ValueError:
                pass
        i += 1
    return result


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_omm_sources(
    data_dir: Path,
) -> tuple[dict[int, dict], dict[int, str]]:
    """
    Load all tle_*_latest.json OMM files (first-seen NORAD ID wins).

    Debris groups are loaded before the catch-all 'active' catalog so their
    object type is correctly preserved rather than overwritten as payload.

    Returns:
        records : {norad_id: omm_record}
        groups  : {norad_id: group_name}
    """
    records: dict[int, dict] = {}
    groups: dict[int, str] = {}

    # Build ordered file list: LOAD_ORDER first, then anything else alphabetically
    all_paths = {p.name: p for p in data_dir.glob("tle_*_latest.json")}
    ordered: list[Path] = []
    for group in LOAD_ORDER:
        fname = f"tle_{group}_latest.json"
        if fname in all_paths:
            ordered.append(all_paths.pop(fname))
    ordered.extend(sorted(all_paths.values()))  # any groups not in LOAD_ORDER

    for path in ordered:
        group = path.name.removeprefix("tle_").removesuffix("_latest.json")
        try:
            recs: list[dict] = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  [!] Cannot parse {path.name}: {exc}")
            continue

        added = 0
        for rec in recs:
            try:
                norad = int(rec["NORAD_CAT_ID"])
            except (KeyError, TypeError, ValueError):
                continue
            if norad not in records:
                records[norad] = rec
                groups[norad] = group
                added += 1

        print(f"  {added:>6,} new  ← {path.name}  ({len(recs):,} total)")

    return records, groups


def load_tle_text(data_dir: Path) -> dict[int, tuple[str, str, str]]:
    """Load all tle_*_latest.tle files → {norad_id: (name, line1, line2)}."""
    combined: dict[int, tuple[str, str, str]] = {}
    for path in sorted(data_dir.glob("tle_*_latest.tle")):
        for norad, entry in parse_tle_file(path).items():
            if norad not in combined:
                combined[norad] = entry
    return combined


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def determine_object_type(group: str) -> str:
    """Determine canonical object_type from the scraper group name."""
    if group in DEBRIS_GROUPS:
        return "debris"
    # All non-debris groups are active satellite catalogs → payload
    return "payload"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------


def build_catalog(rank: int = 1) -> None:
    sep = "=" * 68
    print(f"\n{sep}")
    print(f"  Catalog Builder — rank {rank} training scenario")
    print(f"{sep}\n")

    # -- Load scenario bands ------------------------------------------------
    if not SCENARIOS_FILE.exists():
        print(f"[!] {SCENARIOS_FILE} not found. Run identify_training_scenarios.py first.")
        return

    top = json.loads(SCENARIOS_FILE.read_text())["top_scenarios"]
    if not (1 <= rank <= len(top)):
        print(f"[!] Rank {rank} out of range (1–{len(top)}).")
        return

    sc = top[rank - 1]
    alt_lo, alt_hi = sc["alt_lo_km"], sc["alt_hi_km"]
    inc_lo, inc_hi = sc["inc_lo_deg"], sc["inc_hi_deg"]
    print(f"  Band : {alt_lo:.0f}–{alt_hi:.0f} km,  {inc_lo:.0f}–{inc_hi:.0f}°")
    print(f"  Known label : {sc['known_label'] or '(mixed)'}")
    print(f"  Expected    : {sc['satellite_count']:,} satellites\n")

    # -- Load OMM JSON -------------------------------------------------------
    print("  Loading OMM JSON ...")
    omm_records, omm_groups = load_omm_sources(DATA_DIR)
    print(f"  Total unique OMM records : {len(omm_records):,}\n")

    # -- Load TLE text -------------------------------------------------------
    print("  Loading TLE text files ...")
    tle_text = load_tle_text(DATA_DIR)
    print(f"  TLE text records : {len(tle_text):,}\n")

    # -- Filter to band ------------------------------------------------------
    in_band_norads = sorted(
        norad for norad, rec in omm_records.items()
        if in_band(rec, alt_lo, alt_hi, inc_lo, inc_hi)
    )
    print(f"  Satellites in band : {len(in_band_norads):,}\n")

    # -- Build catalog entries -----------------------------------------------
    catalog_entries: list[tuple[str, str, str]] = []
    metadata_rows: list[dict] = []
    from_text = from_omm = skipped = 0

    for norad in in_band_norads:
        rec = omm_records[norad]
        group = omm_groups[norad]
        object_type = determine_object_type(group)
        is_agent = object_type == "payload"
        name = (rec.get("OBJECT_NAME") or f"NORAD-{norad}").strip()
        constellation = CONSTELLATION_LABELS.get(group, "")

        if norad in tle_text:
            entry = tle_text[norad]
            from_text += 1
        else:
            try:
                entry = omm_to_tle_lines(rec)
                from_omm += 1
            except (ValueError, KeyError, TypeError) as exc:
                print(f"  [!] Skipping NORAD {norad} ({name}): {exc}")
                skipped += 1
                continue

        catalog_entries.append(entry)
        metadata_rows.append({
            "norad_id":          norad,
            "name":              name,
            "object_type":       object_type,
            "is_agent_candidate": "true" if is_agent else "false",
            "constellation":     constellation,
            "radius_meters":     "",  # not in TLE; loader will use default_radius_meters
        })

    agent_count = sum(1 for r in metadata_rows if r["is_agent_candidate"] == "true")

    print(f"  TLE from text files  : {from_text:,}")
    print(f"  TLE from OMM JSON    : {from_omm:,}")
    print(f"  Skipped (malformed)  : {skipped:,}")
    print(f"  Catalog size         : {len(catalog_entries):,}")
    print(f"  Agent candidates     : {agent_count:,}")
    print(f"  Non-agents (debris)  : {len(catalog_entries) - agent_count:,}\n")

    # -- Write outputs -------------------------------------------------------
    TLE_DIR.mkdir(parents=True, exist_ok=True)

    catalog_path = TLE_DIR / "catalog.tle"
    with open(catalog_path, "w", encoding="ascii") as f:
        for entry_name, line1, line2 in catalog_entries:
            f.write(f"{entry_name}\n{line1}\n{line2}\n")
    print(f"  Written : {catalog_path}")
    print(f"            {len(catalog_entries):,} TLE sets")

    objects_path = TLE_DIR / "objects.csv"
    fieldnames = [
        "norad_id", "name", "object_type",
        "is_agent_candidate", "constellation", "radius_meters",
    ]
    with open(objects_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metadata_rows)
    print(f"  Written : {objects_path}")
    print(f"            {len(metadata_rows):,} rows\n")

    print(f"{sep}")
    print(f"  Done. Run 'oz catalog' to validate.")
    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a frozen TLE catalog for k/Δt calibration.\n\n"
            "Reads the target orbital band from data/training_scenarios.json,\n"
            "filters all scraped TLE/OMM data, and writes:\n"
            "  data/tle/catalog.tle   (input to calibration)\n"
            "  data/tle/objects.csv   (input to calibration)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--rank", "-r",
        type=int,
        default=1,
        metavar="N",
        help="Which training scenario band to use (1 = densest, default: 1).",
    )
    return parser.parse_args()


def main() -> None:
    build_catalog(rank=parse_args().rank)


if __name__ == "__main__":
    main()
