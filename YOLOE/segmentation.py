from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple

import torch
import cv2
from ultralytics import YOLOE


def iter_images(root: Path) -> Iterable[Path]:
    exts = {".jpg", ".jpeg", ".png"}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def fmt_hms(seconds: float) -> str:
    s = max(0, int(seconds))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def parse_meta_from_filename(img_path: Path) -> Optional[Tuple[str, str, str, str]]:
    """
    year_month_lat_lon_panoid_side.jpg
    Example:
      2025_05_21.876..._-159.45..._Y9OU..._back.jpg
    """
    parts = img_path.stem.split("_")
    if len(parts) < 6:
        return None

    year, month, lat_s, lon_s = parts[0], parts[1], parts[2], parts[3]

    if not (len(year) == 4 and year.isdigit()):
        return None
    if not (month.isdigit() and 1 <= int(month) <= 12):
        return None

    try:
        lat = str(float(lat_s))
        lon = str(float(lon_s))
    except Exception:
        return None

    return year, f"{int(month):02d}", lat, lon


def has_any_detection(result) -> bool:
    try:
        return getattr(result, "boxes", None) is not None and len(result.boxes) > 0
    except Exception:
        return False


def safe_relpath(p: Path, root: Path) -> Path:
    try:
        return p.relative_to(root)
    except Exception:
        return Path(p.name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--root",
        default=r"C:\Users\tdiaz\Desktop\Streetview-panorama-scraping\cube_pano\2025",
        help="Root folder to scan (recursively).",
    )
    ap.add_argument("--out", default="hits.csv", help="Output CSV path.")
    ap.add_argument("--conf", type=float, default=0.30, help="Confidence threshold.")
    ap.add_argument("--iou", type=float, default=0.60, help="IOU threshold.")
    ap.add_argument("--imgsz", type=int, default=1024, help="Inference image size.")
    ap.add_argument("--batch", type=int, default=16, help="Batch size.")
    ap.add_argument("--print-every", type=int, default=250, help="Progress print frequency.")
    ap.add_argument("--allow-cpu", action="store_true", help="Allow CPU fallback (otherwise exits if no CUDA).")

    # NEW: text prompts/classes (one or more). Use quotes for multi-word classes.
    ap.add_argument(
        "--classes",
        nargs="+",
        default=["manhole"],
        help='One or more class prompts, e.g. --classes "fire hydrant" or --classes "stop sign"',
    )

    # visualization saving
    ap.add_argument("--save-vis", action="store_true", help="Save annotated images with segmentation overlay.")
    ap.add_argument("--vis-dir", default="vis", help="Folder to save annotated images into.")
    ap.add_argument(
        "--vis-only-hits",
        action="store_true",
        default=True,
        help="(default True) Only save visualization images when there is a hit.",
    )
    ap.add_argument(
        "--max-vis",
        type=int,
        default=None,
        help="Optional cap on number of visualization images saved (useful for testing).",
    )

    args = ap.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Root path does not exist: {root}")

    cuda_ok = torch.cuda.is_available() and torch.cuda.device_count() > 0
    if not cuda_ok and not args.allow_cpu:
        raise SystemExit(
            "CUDA GPU not available. Exiting (use --allow-cpu to override). "
            "Tip: install a CUDA-enabled PyTorch build and confirm NVIDIA drivers."
        )

    device = 0 if cuda_ok else "cpu"
    if cuda_ok:
        print(f"Using CUDA device {device}: {torch.cuda.get_device_name(device)}")
    else:
        print("Using device: cpu (override enabled)")

    MODEL_PATH = Path(__file__).with_name("yoloe-11l-seg.pt")
    if not MODEL_PATH.is_file():
        raise SystemExit(f"Model weights not found: {MODEL_PATH}")

    model = YOLOE(str(MODEL_PATH))

    # Apply YOLOE text prompt(s)
    names = args.classes
    print(f"Using classes/prompts: {names}")
    model.set_classes(names, model.get_text_pe(names))

    images = list(iter_images(root))
    n_images = len(images)
    print(f"Found {n_images} images under: {root}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    vis_dir = Path(args.vis_dir)
    if args.save_vis:
        vis_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    kept = 0
    vis_saved = 0
    t0 = time.perf_counter()
    last_name = ""

    def log_progress() -> None:
        now = datetime.now().strftime("%H:%M:%S")
        elapsed = time.perf_counter() - t0
        rate = (total / elapsed) if elapsed > 0 else 0.0
        remaining = max(0, n_images - total)
        eta = (remaining / rate) if rate > 0 else 0.0
        extra = f" | vis saved: {vis_saved}" if args.save_vis else ""
        print(
            f"[{now}] Processed {total}/{n_images} | hits written: {kept}{extra} | "
            f"elapsed {fmt_hms(elapsed)} | {rate:.2f} img/s | ETA {fmt_hms(eta)} | last: {last_name}"
        )

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "month", "lat", "lon"])

        with torch.inference_mode():
            batch_paths: list[str] = []

            def process_batch(paths: list[str]) -> None:
                nonlocal total, kept, last_name, vis_saved
                if not paths:
                    return

                # Ultralytics predict supports common args like conf/iou/imgsz/batch. :contentReference[oaicite:2]{index=2}
                results = model.predict(
                    paths,
                    device=device,
                    conf=args.conf,
                    iou=args.iou,
                    imgsz=args.imgsz,
                    verbose=False,
                    save=False,
                )

                for r in results:
                    total += 1
                    r_path = Path(r.path)
                    last_name = r_path.name

                    if total % args.print_every == 0:
                        log_progress()

                    hit = has_any_detection(r)
                    if not hit:
                        continue

                    meta = parse_meta_from_filename(r_path)
                    if meta:
                        year, month, lat, lon = meta
                        w.writerow([year, month, lat, lon])
                        kept += 1

                    if args.save_vis:
                        if args.max_vis is not None and vis_saved >= args.max_vis:
                            continue

                        rel = safe_relpath(r_path, root)
                        out_img = (vis_dir / rel).with_suffix(".jpg")
                        out_img.parent.mkdir(parents=True, exist_ok=True)

                        annotated = r.plot()
                        cv2.imwrite(str(out_img), annotated)
                        vis_saved += 1

            for img_path in images:
                batch_paths.append(str(img_path))
                if len(batch_paths) >= args.batch:
                    process_batch(batch_paths)
                    batch_paths = []

            process_batch(batch_paths)

    log_progress()
    print(f"Done. Wrote {kept} hit-rows to: {out_path}")
    if args.save_vis:
        print(f"Saved {vis_saved} annotated images under: {vis_dir.resolve()}")


if __name__ == "__main__":
    main()
