#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from PIL import Image
import py360convert
import yaml


def load_panoids(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("panoids", "data", "items", "records"):
            if k in data and isinstance(data[k], list):
                return data[k]
    raise ValueError(f"Unsupported JSON shape in {path} (expected a list).")


def month_str(meta: Dict[str, Any]) -> str:
    m = meta.get("month", None)
    if m is None:
        return "00"
    try:
        mi = int(m)
    except Exception:
        return "00"
    return f"{mi:02d}" if 1 <= mi <= 12 else "00"


def parse_panorama_filename(pano_path: Path) -> Dict[str, Any]:
    """
    Expected panorama filename: <lat>_<lon>_<panoid>.jpg
    (panoid may contain underscores, so we join the remaining parts)
    """
    parts = pano_path.stem.split("_")
    if len(parts) < 3:
        raise ValueError(f"Unexpected panorama filename format: {pano_path.name}")
    lat = parts[0]
    lon = parts[1]
    panoid = "_".join(parts[2:])
    return {"lat": lat, "lon": lon, "panoid": panoid}


def project_one(
    pano_jpg: Path,
    meta: Dict[str, Any],
    out_root: Path,
    face_w: int,
    sides_enabled: Dict[str, bool],
) -> None:
    y = str(int(meta["year"]))
    m = month_str(meta)

    out_dir = out_root / y / m
    out_dir.mkdir(parents=True, exist_ok=True)

    name_bits = parse_panorama_filename(pano_jpg)
    base = f"{y}_{m}_{name_bits['lat']}_{name_bits['lon']}_{name_bits['panoid']}"

    cube_dice = np.array(Image.open(pano_jpg))
    cube_h = py360convert.e2c(cube_dice, face_w=face_w)
    faces = {
        "left":  cube_h[face_w:face_w * 2, 0 * face_w:1 * face_w, :],
        "front": cube_h[face_w:face_w * 2, 1 * face_w:2 * face_w, :],
        "right": cube_h[face_w:face_w * 2, 2 * face_w:3 * face_w, :],
        "back":  cube_h[face_w:face_w * 2, 3 * face_w:4 * face_w, :],
    }

    for side, arr in faces.items():
        if not sides_enabled.get(side, True):
            continue
        Image.fromarray(arr).save(out_dir / f"{base}_{side}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser(description="Project panoramas/*.jpg into cube faces, optionally deleting the pano JPGs.")
    ap.add_argument("--pano-dir", default="panoramas", help="Directory containing panorama JPGs.")
    ap.add_argument("--out-dir", default="cube_pano", help="Output directory for cube faces.")
    ap.add_argument("--panoids", default="panoids_with_dates.json", help="Cleaned panoids JSON (used for year/month).")
    ap.add_argument("--config", default="config.yaml", help="config.yaml for projected_resolution + sides.")
    ap.add_argument("--delete", action="store_true", help="Delete each panorama JPG after projecting it.")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    face_w = int(cfg["projected_resolution"])
    sides_cfg = cfg.get("sides", {}) or {}
    sides_enabled = {
        "left": bool(sides_cfg.get("left", True)),
        "front": bool(sides_cfg.get("front", True)),
        "right": bool(sides_cfg.get("right", True)),
        "back": bool(sides_cfg.get("back", True)),
    }

    panoids = load_panoids(Path(args.panoids))
    meta_by_id: Dict[str, Dict[str, Any]] = {p["panoid"]: p for p in panoids if isinstance(p, dict) and "panoid" in p}

    pano_dir = Path(args.pano_dir)
    out_dir = Path(args.out_dir)

    panos = sorted(pano_dir.glob("*.jpg"))
    print(f"Loaded {len(panos)} panoramas from {pano_dir}/")

    projected = 0
    skipped_no_meta = 0
    for pano_jpg in panos:
        try:
            bits = parse_panorama_filename(pano_jpg)
            meta = meta_by_id.get(bits["panoid"])
            if not meta or meta.get("year") is None:
                skipped_no_meta += 1
                continue

            project_one(pano_jpg, meta, out_dir, face_w, sides_enabled)
            projected += 1

            if args.delete:
                pano_jpg.unlink(missing_ok=True)

        except Exception as e:
            print(f"Failed on {pano_jpg.name}: {e}")

    print(f"Projected: {projected}")
    print(f"Skipped (no year/month meta): {skipped_no_meta}")


if __name__ == "__main__":
    main()
