#!/usr/bin/env python3
"""
Delete panoramas/*.jpg that are NOT in your cleaned panoids_with_dates.json.
Useful if you started downloading from the uncleaned panoids JSON and want to reclaim disk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set


def load_panoids(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("panoids", "data", "items", "records"):
            if k in data and isinstance(data[k], list):
                return data[k]
    raise ValueError(f"Unsupported JSON shape in {path} (expected a list).")


def panoid_from_panorama_filename(p: Path) -> str | None:
    parts = p.stem.split("_")
    if len(parts) < 3:
        return None
    return "_".join(parts[2:])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panoids", default="panoids_with_dates.json", help="Cleaned panoids JSON (dates-only).")
    ap.add_argument("--pano-dir", default="panoramas", help="Directory containing panorama JPGs.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be deleted without deleting.")
    args = ap.parse_args()

    panoids = load_panoids(Path(args.panoids))
    keep: Set[str] = {p["panoid"] for p in panoids if isinstance(p, dict) and p.get("year") is not None and "panoid" in p}

    pano_dir = Path(args.pano_dir)
    files = sorted(pano_dir.glob("*.jpg"))

    deleted = 0
    kept = 0
    unknown = 0

    for f in files:
        pid = panoid_from_panorama_filename(f)
        if pid is None:
            unknown += 1
            continue
        if pid in keep:
            kept += 1
            continue

        deleted += 1
        if args.dry_run:
            print(f"DELETE {f}")
        else:
            f.unlink(missing_ok=True)

    print(f"Panoramas scanned: {len(files)}")
    print(f"Kept (in dates-only json): {kept}")
    print(f"Deleted: {deleted}")
    print(f"Skipped (unparseable): {unknown}")


if __name__ == "__main__":
    main()
