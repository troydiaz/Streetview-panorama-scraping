#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=ROOT)


def newest_raw_panoids_file() -> Path:
    candidates = sorted(ROOT.glob("panoids_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        candidates = sorted(ROOT.glob("panoids*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError("No panoids*.json found after running 1_get_panoid_info.py")
    return candidates[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the Street View pipeline (with optional date filtering and streaming projection).")
    ap.add_argument("--from-scratch", action="store_true", help="Run 1_get_panoid_info.py then filter to dates-only JSON.")
    ap.add_argument("--raw-panoids", default=None, help="Raw panoids JSON input for filtering (defaults to newest panoids_*.json).")
    ap.add_argument("--clean-panoids", default="panoids_with_dates.json", help="Output cleaned JSON path.")
    ap.add_argument("--use-clean", default=None, help="Use an existing cleaned JSON (skips steps 1+2).")
    ap.add_argument("--download-only", action="store_true", help="Only download panoramas (do not project).")
    ap.add_argument("--project-after", action="store_true", help="Run 3_project_panoramas.py after downloading.")
    ap.add_argument("--delete-panos", action="store_true", help="When projecting, delete panorama JPGs to save disk.")
    args = ap.parse_args()

    if args.from_scratch:
        run([str(ROOT / "1_get_panoid_info.py")])

        raw = Path(args.raw_panoids) if args.raw_panoids else newest_raw_panoids_file()
        clean = Path(args.clean_panoids)

        run([str(ROOT / "filter_panoids_by_date.py"), "--in", str(raw), "--out", str(clean)])
        panoids_file = clean

    else:
        panoids_file = Path(args.use_clean) if args.use_clean else Path(args.clean_panoids)
        if not panoids_file.is_file():
            raise FileNotFoundError(
                f"Clean panoids file not found: {panoids_file}. "
                f"Either pass --use-clean <file> or use --from-scratch."
            )

    if args.download_only:
        run([str(ROOT / "2_download_panoramas.py"), "--panoids", str(panoids_file), "--require-year"])
        return

    run_args = [str(ROOT / "2_download_panoramas.py"), "--panoids", str(panoids_file), "--require-year", "--project"]
    if args.delete_panos:
        run_args.append("--delete-pano")
    run(run_args)

    if args.project_after:
        proj_args = [str(ROOT / "3_project_panoramas.py"), "--panoids", str(panoids_file)]
        if args.delete_panos:
            proj_args.append("--delete")
        run(proj_args)


if __name__ == "__main__":
    main()
