#!/usr/bin/env python3
"""
Filter a panoids-with-dates JSON file down to a single year (default: 2025).

Supports input JSON shaped as:
1) List[dict]  (your example)
2) Dict with list under common keys: "panoids", "items", "data"

Writes a JSON list of panoid records that match the year.
"""

import argparse
import json
from pathlib import Path
from typing import Any, List, Dict


def extract_records(obj: Any) -> List[Dict[str, Any]]:
    """Return a list of panoid records from various possible JSON shapes."""
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]

    if isinstance(obj, dict):
        for key in ("panoids", "items", "data", "records"):
            v = obj.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]

    raise ValueError(
        "Unsupported JSON format. Expected a list of dicts or a dict containing a list "
        "under one of: panoids/items/data/records."
    )


def parse_year(v: Any) -> int | None:
    """Convert year field to int if possible."""
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input panoids JSON (with year/month fields)")
    ap.add_argument("--out", dest="out", required=True, help="Output JSON (filtered list)")
    ap.add_argument("--year", type=int, default=2025, help="Year to keep (default: 2025)")
    ap.add_argument("--drop-no-year", action="store_true", help="Drop items missing/invalid year (default behavior)")
    args = ap.parse_args()

    inp_path = Path(args.inp)
    out_path = Path(args.out)

    data = json.loads(inp_path.read_text(encoding="utf-8"))
    records = extract_records(data)

    kept = []
    dropped_no_year = 0

    for r in records:
        y = parse_year(r.get("year"))
        if y is None:
            dropped_no_year += 1
            continue  # always drop missing/invalid year
        if y == args.year:
            kept.append(r)

    out_path.write_text(json.dumps(kept, indent=2), encoding="utf-8")

    print(f"Input records: {len(records)}")
    print(f"Kept year {args.year}: {len(kept)}")
    print(f"Dropped missing/invalid year: {dropped_no_year}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
