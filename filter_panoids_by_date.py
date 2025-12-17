#!/usr/bin/env python3
"""
Filter Street View panoid JSON entries by date fields.

Rules:
- If an entry has NO "year" -> do NOT copy it.
- If an entry has "month" but NO "year" -> do NOT copy it. (covered by rule above)
- If an entry has "year" and "month" -> copy it.
- If an entry has "year" but NO "month" -> copy it.

Output records contain: panoid, lat, lon, year, and (optionally) month.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _to_int(x: Any) -> int | None:
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float) and x.is_integer():
        return int(x)
    if isinstance(x, str):
        s = x.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            try:
                return int(s)
            except ValueError:
                return None
    return None


def filter_pano_json(records: List[Dict[str, Any]], drop_invalid_month: bool = True) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    out: List[Dict[str, Any]] = []
    stats = {
        "input": 0,
        "kept": 0,
        "skipped_no_year": 0,
        "skipped_missing_fields": 0,
        "skipped_invalid_year": 0,
        "skipped_invalid_month": 0,
        "kept_year_only": 0,
        "kept_year_month": 0,
        "dropped_bad_month_but_kept_year": 0,
    }

    for item in records:
        stats["input"] += 1
        if not isinstance(item, dict):
            stats["skipped_missing_fields"] += 1
            continue

        panoid = item.get("panoid")
        lat = item.get("lat")
        lon = item.get("lon")

        # Require core fields
        if panoid is None or lat is None or lon is None:
            stats["skipped_missing_fields"] += 1
            continue

        year_raw = item.get("year", None)
        month_raw = item.get("month", None)

        # Year is required to keep the record
        if year_raw is None:
            stats["skipped_no_year"] += 1
            continue

        year = _to_int(year_raw)
        if year is None:
            stats["skipped_invalid_year"] += 1
            continue

        month = _to_int(month_raw)
        month_present = "month" in item and month_raw is not None

        if month_present:
            # If month is present, validate it
            if month is None or not (1 <= month <= 12):
                if drop_invalid_month:
                    # Treat as "year but not month" and keep
                    stats["dropped_bad_month_but_kept_year"] += 1
                    month = None
                else:
                    stats["skipped_invalid_month"] += 1
                    continue

        rec: Dict[str, Any] = {
            "panoid": panoid,
            "lat": lat,
            "lon": lon,
            "year": year,
        }
        if month is not None:
            rec["month"] = month

        out.append(rec)
        stats["kept"] += 1
        if "month" in rec:
            stats["kept_year_month"] += 1
        else:
            stats["kept_year_only"] += 1

    return out, stats


def load_json(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data  # type: ignore[return-value]
    if isinstance(data, dict):
        # If your JSON is wrapped (e.g., {"panoids": [...]})
        for k in ("panoids", "data", "items", "records"):
            if k in data and isinstance(data[k], list):
                return data[k]  # type: ignore[return-value]
    raise ValueError("Input JSON must be a list (or a dict containing a list under a common key).")


def main() -> None:
    p = argparse.ArgumentParser(description="Create a filtered panoid JSON containing only entries with a year (and optional month).")
    p.add_argument("--in", dest="in_path", required=True, help="Input JSON path (array of pano objects).")
    p.add_argument("--out", dest="out_path", required=True, help="Output JSON path.")
    p.add_argument(
        "--keep-invalid-month",
        action="store_true",
        help="Do NOT drop invalid months; instead skip those records entirely.",
    )
    args = p.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out_path)

    records = load_json(in_path)
    filtered, stats = filter_pano_json(records, drop_invalid_month=not args.keep_invalid_month)

    out_path.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Done.")
    print(f"Input records:   {stats['input']}")
    print(f"Kept records:    {stats['kept']}")
    print(f"  - year+month:  {stats['kept_year_month']}")
    print(f"  - year only:   {stats['kept_year_only']}")
    print(f"Skipped (no year):           {stats['skipped_no_year']}")
    print(f"Skipped (missing fields):    {stats['skipped_missing_fields']}")
    print(f"Skipped (invalid year):      {stats['skipped_invalid_year']}")
    if args.keep_invalid_month:
        print(f"Skipped (invalid month):     {stats['skipped_invalid_month']}")
    else:
        print(f"Dropped bad month, kept year:{stats['dropped_bad_month_but_kept_year']}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
