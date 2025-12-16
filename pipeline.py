from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=ROOT)

def ensure_single_panoids_file() -> None:
    files = sorted(ROOT.glob("panoids*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if len(files) <= 1:
        return
    archive = ROOT / "panoids_archive"
    archive.mkdir(exist_ok=True)
    keep = files[0]
    for f in files[1:]:
        shutil.move(str(f), str(archive / f.name))
    print(f"Moved {len(files)-1} old panoids files to {archive.name} (kept {keep.name})")

if __name__ == "__main__":
    run("1_get_panoid_info.py")          # writes panoids_*.json
    ensure_single_panoids_file()         # because downloader requires exactly one panoids*.json
    run("2_download_panoramas.py")       # downloads to panoramas/ 
    run("3_project_panoramas.py")        # writes cube faces to cube_pano/ 
