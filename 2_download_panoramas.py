#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import streetview


def load_panoids(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    # tolerate wrapped shapes like {"panoids":[...]}
    if isinstance(data, dict):
        for k in ("panoids", "data", "items", "records"):
            if k in data and isinstance(data[k], list):
                return data[k]
    raise ValueError(f"Unsupported JSON shape in {path} (expected a list).")


def pano_jpg_path(panoid: Dict[str, Any], pano_dir: str) -> str:
    # Must match streetview.stich_tiles naming convention used by panoid_created in the original script.
    fname = f"{panoid['lat']}_{panoid['lon']}_{panoid['panoid']}.jpg"
    return os.path.join(pano_dir, fname)


def ensure_dirs(*dirs: str) -> None:
    for d in dirs:
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)


async def download_tiles_async(tiles, directory: str, session: aiohttp.ClientSession) -> None:
    """Downloads all tiles for a panorama into `directory`."""
    for (x, y, fname, url) in tiles:
        url = url.replace("http://", "https://")
        while True:
            try:
                async with session.get(url) as response:
                    content = await response.read()
                with open(os.path.join(directory, fname), "wb") as out_file:
                    out_file.write(content)
                break
            except Exception:
                print(traceback.format_exc())


def load_projection_settings(config_path: Path) -> Tuple[int, Dict[str, bool]]:
    import yaml  # lazy import

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    size = int(cfg["projected_resolution"])
    sides_cfg = cfg.get("sides", {}) or {}
    sides_enabled = {
        "left": bool(sides_cfg.get("left", True)),
        "front": bool(sides_cfg.get("front", True)),
        "right": bool(sides_cfg.get("right", True)),
        "back": bool(sides_cfg.get("back", True)),
    }
    if not any(sides_enabled.values()):
        raise ValueError("config.yaml sides: at least one side must be true")
    return size, sides_enabled


def month_str_from_meta(meta: Dict[str, Any]) -> str:
    m = meta.get("month", None)
    if m is None:
        return "00"  # unknown month
    try:
        mi = int(m)
    except Exception:
        return "00"
    return f"{mi:02d}" if 1 <= mi <= 12 else "00"


def projected_outputs_exist(panoid: Dict[str, Any], cube_dir: str, sides_enabled: Dict[str, bool]) -> bool:
    """
    If projecting+deleting, the panorama JPG won't exist anymore.
    This checks whether projected faces already exist (so you can resume safely).
    """
    year = panoid.get("year", None)
    if year is None:
        return False

    y = str(int(year))
    m = month_str_from_meta(panoid)
    base = f"{y}_{m}_{panoid['lat']}_{panoid['lon']}_{panoid['panoid']}"
    out_dir = os.path.join(cube_dir, y, m)

    for side, enabled in sides_enabled.items():
        if not enabled:
            continue
        out_path = os.path.join(out_dir, f"{base}_{side}.jpg")
        if not os.path.isfile(out_path):
            return False
    return True


def project_panorama_file(
    pano_jpg: str,
    panoid: Dict[str, Any],
    cube_dir: str,
    face_w: int,
    sides_enabled: Dict[str, bool],
) -> None:
    """
    Converts equirectangular panorama into 4 cube faces (left/front/right/back),
    and writes them to: cube_dir/<year>/<month>/...
    """
    import numpy as np  # lazy import
    from PIL import Image  # lazy import
    import py360convert  # lazy import

    year = panoid.get("year", None)
    if year is None:
        raise ValueError(f"Missing year for panoid {panoid.get('panoid')}")

    y = str(int(year))
    m = month_str_from_meta(panoid)

    out_dir = os.path.join(cube_dir, y, m)
    os.makedirs(out_dir, exist_ok=True)

    base = f"{y}_{m}_{panoid['lat']}_{panoid['lon']}_{panoid['panoid']}"

    cube_dice = np.array(Image.open(pano_jpg))
    cube_h = py360convert.e2c(cube_dice, face_w=face_w)
    faces = {
        "left":  cube_h[face_w:face_w * 2, 0 * face_w:1 * face_w, :],
        "front": cube_h[face_w:face_w * 2, 1 * face_w:2 * face_w, :],
        "right": cube_h[face_w:face_w * 2, 2 * face_w:3 * face_w, :],
        "back":  cube_h[face_w:face_w * 2, 3 * face_w:4 * face_w, :],
    }

    for side, img in faces.items():
        if not sides_enabled.get(side, True):
            continue
        out_path = os.path.join(out_dir, f"{base}_{side}.jpg")
        Image.fromarray(img).save(out_path)


async def download_one(
    panoid: Dict[str, Any],
    session: aiohttp.ClientSession,
    tile_dir: str,
    pano_dir: str,
    *,
    project: bool,
    delete_pano_after_project: bool,
    cube_dir: str,
    face_w: Optional[int],
    sides_enabled: Optional[Dict[str, bool]],
) -> None:
    ensure_dirs(tile_dir, pano_dir)

    try:
        tiles = streetview.tiles_info(panoid["panoid"])
        await download_tiles_async(tiles, tile_dir, session)

        # stitch into panorama jpg
        streetview.stich_tiles(
            panoid["panoid"],
            tiles,
            tile_dir,
            pano_dir,
            point=(panoid["lat"], panoid["lon"]),
        )
        streetview.delete_tiles(tiles, tile_dir)

        pano_path = pano_jpg_path(panoid, pano_dir)

        if project:
            assert face_w is not None and sides_enabled is not None
            project_panorama_file(pano_path, panoid, cube_dir, face_w, sides_enabled)
            if delete_pano_after_project:
                try:
                    os.remove(pano_path)
                except FileNotFoundError:
                    pass

    except Exception:
        print(f"Failed for panoid={panoid.get('panoid')}\n{traceback.format_exc()}")


async def run_batches(
    panoids: List[Dict[str, Any]],
    *,
    batch_size: int,
    conn_limit: int,
    tile_dir: str,
    pano_dir: str,
    project: bool,
    delete_pano_after_project: bool,
    cube_dir: str,
    face_w: Optional[int],
    sides_enabled: Optional[Dict[str, bool]],
    max_items: Optional[int],
) -> None:
    if max_items is not None:
        panoids = panoids[:max_items]

    conn = aiohttp.TCPConnector(limit=conn_limit)
    async with aiohttp.ClientSession(connector=conn, auto_decompress=False) as session:
        for start in range(0, len(panoids), batch_size):
            chunk = panoids[start : start + batch_size]
            await asyncio.gather(
                *[
                    download_one(
                        p,
                        session,
                        tile_dir,
                        pano_dir,
                        project=project,
                        delete_pano_after_project=delete_pano_after_project,
                        cube_dir=cube_dir,
                        face_w=face_w,
                        sides_enabled=sides_enabled,
                    )
                    for p in chunk
                ]
            )
            print(f"Completed batch {start+1} → {min(start+batch_size, len(panoids))} / {len(panoids)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Download Street View panoramas from a panoids JSON file.")
    ap.add_argument("--panoids", default=None, help="Path to panoids JSON (preferably the cleaned dates-only file).")
    ap.add_argument("--config", default="config.yaml", help="Path to config.yaml (used for projection settings).")
    ap.add_argument("--tile-dir", default="tiles", help="Temp tile directory.")
    ap.add_argument("--pano-dir", default="panoramas", help="Panorama JPG output directory.")
    ap.add_argument("--cube-dir", default="cube_pano", help="Cube face output directory (only if --project).")
    ap.add_argument("--batch-size", type=int, default=100, help="How many panoids to process per asyncio batch.")
    ap.add_argument("--conn-limit", type=int, default=100, help="aiohttp connector limit.")
    ap.add_argument("--max", type=int, default=None, help="Only process first N panoids.")
    ap.add_argument("--project", action="store_true", help="Project each panorama into cube faces after download.")
    ap.add_argument("--delete-pano", action="store_true", help="Delete panorama JPG after projecting (saves disk).")
    ap.add_argument(
        "--require-year",
        action="store_true",
        help="Skip panoids that don't have a 'year' field (recommended when using cleaned dates-only JSON).",
    )
    args = ap.parse_args()

    # Pick default panoids file if not provided
    panoids_path: Optional[Path] = Path(args.panoids) if args.panoids else None
    if panoids_path is None:
        candidate = Path("panoids_with_dates.json")
        if candidate.is_file():
            panoids_path = candidate
        else:
            matches = sorted(Path(".").glob("panoids*.json"))
            if len(matches) == 1:
                panoids_path = matches[0]
            else:
                raise SystemExit("Please pass --panoids <file>. (Multiple panoids*.json exist.)")

    panoids = load_panoids(panoids_path)
    print(f"Loaded {len(panoids)} panoids from {panoids_path}")

    if args.require_year:
        before = len(panoids)
        panoids = [p for p in panoids if p.get("year") is not None]
        print(f"Filtered to {len(panoids)} with year (dropped {before - len(panoids)})")

    face_w = None
    sides_enabled = None
    if args.project:
        face_w, sides_enabled = load_projection_settings(Path(args.config))

        # If projecting+deleting, skip ones already projected so you can resume safely.
        if args.delete_pano:
            before = len(panoids)
            panoids = [p for p in panoids if not projected_outputs_exist(p, args.cube_dir, sides_enabled)]
            print(f"Skipping already-projected panoids: {before - len(panoids)}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(
            run_batches(
                panoids,
                batch_size=args.batch_size,
                conn_limit=args.conn_limit,
                tile_dir=args.tile_dir,
                pano_dir=args.pano_dir,
                project=args.project,
                delete_pano_after_project=args.delete_pano and args.project,
                cube_dir=args.cube_dir,
                face_w=face_w,
                sides_enabled=sides_enabled,
                max_items=args.max,
            )
        )
    finally:
        loop.close()


if __name__ == "__main__":
    main()
