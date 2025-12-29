from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Dark theme
BG = "#000000"
FG = "#FFFFFF"

# Matches year/month/lat/lon at the start of your filename (extra stuff after lon is OK)
# Examples it supports:
# 2025_04_21.8959_-159.4576_front.jpg
# 2025_04_21.8959_-159.4576_<panoid>_front.jpg
FNAME_META_RE = re.compile(
    r"(?P<year>\d{4})_(?P<month>\d{1,2})_(?P<lat>-?\d+(?:\.\d+)?)_(?P<lon>-?\d+(?:\.\d+)?)"
)

# Extract view suffix like _front/_back/_left/_right right before extension
VIEW_RE = re.compile(r"_(front|back|left|right)(?=\.[^.]+$)", re.IGNORECASE)


def view_from_filename(name: str) -> Optional[str]:
    m = VIEW_RE.search(name)
    return m.group(1).lower() if m else None


# Optional Tk viewer (needs Pillow)
try:
    import tkinter as tk  # type: ignore
    from PIL import Image, ImageTk  # type: ignore

    TK_OK = True
except Exception:
    TK_OK = False
    tk = None
    Image = None
    ImageTk = None

# Windows-only: single keypress without Enter (fallback mode)
try:
    import msvcrt  # type: ignore
except Exception:
    msvcrt = None

# Windows-only: focus console window (fallback mode convenience)
try:
    import ctypes  # type: ignore
except Exception:
    ctypes = None


@dataclass(frozen=True)
class Meta:
    year: int
    month: int
    lat: float
    lon: float


@dataclass
class Action:
    """One TP/FP labeling action that we can undo via Left Arrow."""
    orig_path: Path
    rel_path: str
    label: str  # true_positive / false_positive
    dest_path: Path
    out_row: dict
    moved: bool


def object_name_from_vis_dir(vis_dir: Path) -> str:
    # yoloe_fire_hydrant_vis -> fire_hydrant
    name = vis_dir.name
    name = name.replace("yoloe_", "")
    name = name.replace("_vis", "")
    return name


def meta_from_filename(name: str) -> Optional[Meta]:
    m = FNAME_META_RE.search(name)
    if not m:
        return None
    return Meta(
        year=int(m.group("year")),
        month=int(m.group("month")),
        lat=float(m.group("lat")),
        lon=float(m.group("lon")),
    )


def make_key(meta: Meta, decimals: int = 8) -> str:
    return f"{meta.year:04d}_{meta.month:02d}_{meta.lat:.{decimals}f}_{meta.lon:.{decimals}f}"


def make_raw_key(meta: Meta, view: str, decimals: int) -> str:
    # Key that ignores panoid differences:
    # 2025_04_<lat>_<lon>_front
    return f"{make_key(meta, decimals=decimals)}_{view}"


def read_hits_csv(hits_csv: Path, precision: int) -> Dict[str, Meta]:
    meta_by_key: Dict[str, Meta] = {}
    with hits_csv.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        required = {"year", "month", "lat", "lon"}
        if not required.issubset(set(r.fieldnames or [])):
            raise ValueError(f"CSV missing required headers {required}. Found: {r.fieldnames}")

        for row in r:
            m = Meta(
                year=int(row["year"]),
                month=int(row["month"]),
                lat=float(row["lat"]),
                lon=float(row["lon"]),
            )
            meta_by_key[make_key(m, decimals=precision)] = m
    return meta_by_key


def ensure_csv(path: Path, fieldnames: List[str]) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()


def append_row(path: Path, fieldnames: List[str], row: dict) -> None:
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writerow(row)


def load_done(decisions_csv: Path) -> Dict[str, str]:
    """
    Stores rel_path -> label for y/n ONLY.
    (Skips are NOT persisted, so they show again next session.)
    """
    done: Dict[str, str] = {}
    if not decisions_csv.exists():
        return done
    with decisions_csv.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            done[row["rel_path"]] = row["label"]
    return done


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except Exception:
        return False


def list_images_recursive(vis_dir: Path, ignore_dirs: Set[Path]) -> List[Path]:
    imgs: List[Path] = []
    for p in vis_dir.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() not in IMG_EXTS:
            continue
        if any(is_relative_to(p, d) for d in ignore_dirs):
            continue
        imgs.append(p)
    imgs.sort(key=lambda p: str(p).lower())
    return imgs


def safe_copy_or_move_preserve_tree(src: Path, vis_dir: Path, dst_root: Path, move: bool) -> Path:
    rel = src.relative_to(vis_dir)
    dst = dst_root / rel
    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        stem, suf = dst.stem, dst.suffix
        i = 1
        while True:
            cand = dst.with_name(f"{stem}__{i}{suf}")
            if not cand.exists():
                dst = cand
                break
            i += 1

    if move:
        shutil.move(str(src), str(dst))
    else:
        shutil.copy2(str(src), str(dst))
    return dst


def close_windows_photos_best_effort() -> None:
    for proc in ("Microsoft.Photos.exe", "Photos.exe"):
        subprocess.run(
            ["taskkill", "/IM", proc, "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def focus_console_best_effort() -> None:
    if ctypes is None:
        return
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def flush_key_buffer() -> None:
    if msvcrt is None:
        return
    try:
        while msvcrt.kbhit():
            _ = msvcrt.getch()
    except Exception:
        pass


def get_key_fallback(paused: bool, ignore_until: float) -> tuple[str, bool, float]:
    """
    Fallback console mode (Windows). Returned key values:
      "y", "n", "s", "q", "back"
    """
    if msvcrt is None:
        ch = (input("Key (y/n/s/6/q or LEFT=back): ").strip().lower()[:1] or "")
        return ch, paused, ignore_until

    while True:
        b = msvcrt.getch()

        # Extended keys (arrows)
        if b in (b"\x00", b"\xe0"):
            b2 = msvcrt.getch()
            if b2 == b"K":  # left arrow
                ch = "back"
            else:
                continue
        else:
            ch = b.decode("utf-8", errors="ignore").lower()
            if not ch:
                continue

        if ch == "6":
            paused = not paused
            if not paused:
                ignore_until = time.time() + 0.25
                flush_key_buffer()
            continue

        if paused:
            continue

        if time.time() < ignore_until:
            continue

        if ch in {"y", "n", "s", "q", "back"}:
            return ch, paused, ignore_until


def remove_last_matching_row(csv_path: Path, match: Callable[[dict], bool]) -> bool:
    if not csv_path.exists():
        return False

    with csv_path.open("r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = list(r.fieldnames or [])
        rows = list(r)

    if not fieldnames:
        return False

    idx_to_remove = None
    for i in range(len(rows) - 1, -1, -1):
        if match(rows[i]):
            idx_to_remove = i
            break

    if idx_to_remove is None:
        return False

    del rows[idx_to_remove]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    return True


# ---------------- Tk: RAW zoom window ----------------

class RawZoomWindow:
    """
    Separate zoom/pan viewer for raw (unmasked) image.

    Controls:
      - Mouse wheel: zoom
      - Click+drag: pan
      - 0: reset zoom
    """
    def __init__(self, parent: "tk.Tk", reset_each_image: bool = True) -> None:
        if tk is None:
            raise RuntimeError("tkinter not available")

        self.reset_each_image = reset_each_image

        self.win = tk.Toplevel(parent)
        self.win.title("RAW (zoomable)")
        self.win.geometry("1200x800")
        self.win.configure(bg=BG)

        top = tk.Frame(self.win, bg=BG)
        top.pack(side="top", fill="x")

        self.info_var = tk.StringVar(value="RAW NOT SET")
        tk.Label(
            top,
            textvariable=self.info_var,
            font=("Segoe UI", 10),
            justify="left",
            bg=BG,
            fg=FG,
        ).pack(padx=10, pady=8, anchor="w")

        frame = tk.Frame(self.win, bg=BG)
        frame.pack(side="top", fill="both", expand=True)

        self.canvas = tk.Canvas(frame, highlightthickness=0, bg=BG)
        self.hbar = tk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        self.vbar = tk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self._base_im = None
        self._photo = None
        self._scale = 1.0

        # pan
        self.canvas.bind("<ButtonPress-1>", self._on_pan_start)
        self.canvas.bind("<B1-Motion>", self._on_pan_move)

        # zoom (Windows)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        # reset zoom
        self.win.bind("0", lambda e: self.reset_zoom())

    def set_image(self, img_path: Optional[Path]) -> None:
        if Image is None or ImageTk is None:
            self.info_var.set("Pillow missing: python -m pip install pillow")
            return

        # Reset zoom + pan whenever we load a new image
        if self.reset_each_image:
            self._scale = 1.0
            try:
                self.canvas.xview_moveto(0.0)
                self.canvas.yview_moveto(0.0)
            except Exception:
                pass

        if img_path is None or not img_path.exists():
            self._base_im = None
            self._photo = None
            self.canvas.delete("all")
            self.info_var.set("RAW NOT FOUND (check --raw-root)")
            return

        try:
            self._base_im = Image.open(img_path)
        except Exception as e:
            self._base_im = None
            self.canvas.delete("all")
            self.info_var.set(f"RAW OPEN ERROR: {e}")
            return

        self.info_var.set(f"RAW: {img_path}")
        self._render()

    def reset_zoom(self) -> None:
        self._scale = 1.0
        try:
            self.canvas.xview_moveto(0.0)
            self.canvas.yview_moveto(0.0)
        except Exception:
            pass
        self._render()

    def _on_pan_start(self, event) -> None:
        self.canvas.scan_mark(event.x, event.y)

    def _on_pan_move(self, event) -> None:
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_mousewheel(self, event) -> None:
        if event.delta > 0:
            self._scale *= 1.12
        else:
            self._scale /= 1.12
        self._scale = max(0.1, min(self._scale, 20.0))
        self._render()

    def _render(self) -> None:
        if Image is None or ImageTk is None:
            return
        if self._base_im is None:
            return

        im = self._base_im
        w, h = im.size
        nw, nh = int(w * self._scale), int(h * self._scale)
        if nw <= 0 or nh <= 0:
            return

        rim = im.resize((nw, nh), Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(rim)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, nw, nh))


# ---------------- Tk: main viewer ----------------

class TkViewer:
    def __init__(self, title: str, max_w: int = 1400, max_h: int = 900, enable_raw: bool = False) -> None:
        if not TK_OK or tk is None or Image is None or ImageTk is None:
            raise RuntimeError("TkViewer unavailable (missing tkinter and/or Pillow).")

        self.max_w = max_w
        self.max_h = max_h

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=BG)

        self.info_var = tk.StringVar(value="")
        self.info_label = tk.Label(
            self.root,
            textvariable=self.info_var,
            font=("Segoe UI", 10),
            justify="left",
            bg=BG,
            fg=FG,
        )
        self.info_label.pack(padx=10, pady=(10, 6), anchor="w")

        self.img_label = tk.Label(self.root, bg=BG)
        self.img_label.pack(padx=10, pady=(0, 10))

        self._photo = None
        self._decision = ""
        self._paused = False
        self._ignore_until = 0.0

        self._base_lines: List[str] = []

        self.raw_win: Optional[RawZoomWindow] = RawZoomWindow(self.root, reset_each_image=True) if enable_raw else None

        # Important: bind_all so keys work even if you clicked the raw window
        self.root.bind_all("<Key>", self._on_key)

    def _render_info(self) -> None:
        lines = [ln for ln in self._base_lines if ln]
        if self._paused:
            lines.append("PAUSED — press 6 to resume")
        self.info_var.set("\n".join(lines))

    def _is_pause_key(self, event) -> bool:
        ks = getattr(event, "keysym", "")
        ch = (getattr(event, "char", "") or "")
        # Support top-row 6 + keypad 6
        return ch == "6" or ks in {"6", "KP_6"}

    def _on_key(self, event) -> None:
        now = time.time()

        # Left arrow = go back
        if getattr(event, "keysym", "") == "Left":
            if self._paused:
                return
            if now < self._ignore_until:
                return
            self._decision = "back"
            return

        # Pause toggle
        if self._is_pause_key(event):
            self._paused = not self._paused
            if not self._paused:
                self._ignore_until = now + 0.25
            self._render_info()
            return

        if self._paused:
            return

        if now < self._ignore_until:
            return

        ch = (getattr(event, "char", "") or "").lower()
        if ch in {"y", "n", "s", "q"}:
            self._decision = ch

    def show(self, annotated_path: Path, info_lines: List[str], raw_path: Optional[Path]) -> str:
        self._decision = ""

        self._base_lines = [ln for ln in info_lines if ln and not ln.startswith("PAUSED")]
        self._render_info()

        if self.raw_win is not None:
            try:
                self.raw_win.set_image(raw_path)  # zoom resets each image
            except Exception:
                pass

        im = Image.open(annotated_path)
        w, h = im.size
        scale = min(self.max_w / w, self.max_h / h, 1.0)
        if scale != 1.0:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        self._photo = ImageTk.PhotoImage(im)
        self.img_label.configure(image=self._photo)

        while not self._decision:
            self.root.update()

        return self._decision

    def is_paused(self) -> bool:
        return self._paused

    def close(self) -> None:
        try:
            if self.raw_win is not None:
                self.raw_win.win.destroy()
        except Exception:
            pass
        self.root.destroy()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vis", required=True, help="Path to yoloe_*_vis folder.")
    ap.add_argument("--hits", default="", help="Path to yoloe_*_hits.csv (default inferred).")
    ap.add_argument("--out", default="", help="Output root (default inside vis folder).")
    ap.add_argument("--move", action="store_true", help="Move images instead of copying (default COPY).")
    ap.add_argument("--viewer", choices=["auto", "tk", "fallback"], default="auto")
    ap.add_argument("--precision", type=int, default=8)
    ap.add_argument("--raw-root", default="", help="Root folder containing RAW (unmasked) images (e.g. cube_pano\\2025).")
    ap.add_argument("--no-close", action="store_true", help="Don't try to close Photos after decisions (fallback).")
    ap.add_argument("--no-focus", action="store_true", help="Don't try to refocus terminal after opening Photos.")
    args = ap.parse_args()

    vis_dir = Path(args.vis).expanduser().resolve()
    if not vis_dir.is_dir():
        raise SystemExit(f"Vis folder not found: {vis_dir}")

    hits_csv = (
        Path(args.hits).expanduser().resolve()
        if args.hits
        else vis_dir.parent / vis_dir.name.replace("_vis", "_hits.csv")
    )
    if not hits_csv.exists():
        raise SystemExit(f"Hits CSV not found: {hits_csv}")

    raw_root: Optional[Path] = None
    if args.raw_root.strip():
        raw_root = Path(args.raw_root).expanduser().resolve()
        if not raw_root.exists():
            raise SystemExit(f"--raw-root does not exist: {raw_root}")

    object_name = object_name_from_vis_dir(vis_dir)
    meta_by_key = read_hits_csv(hits_csv, precision=args.precision)

    out_root = Path(args.out).expanduser().resolve() if args.out else vis_dir
    tp_dir = out_root / "true_positive"
    fp_dir = out_root / "false_positive"

    tp_csv = tp_dir / f"true_positive_{object_name}.csv"
    fp_csv = fp_dir / f"false_positive_{object_name}.csv"
    decisions_csv = out_root / "decisions.csv"

    out_fields = ["image", "label", "year", "month", "lat", "lon"]
    decisions_fields = ["rel_path", "label"]

    ensure_csv(tp_csv, out_fields)
    ensure_csv(fp_csv, out_fields)
    ensure_csv(decisions_csv, decisions_fields)

    done = load_done(decisions_csv)

    ignore_dirs = {tp_dir, fp_dir}
    all_imgs = list_images_recursive(vis_dir, ignore_dirs=ignore_dirs)

    pending = [p for p in all_imgs if str(p.relative_to(vis_dir)) not in done]
    total_unique = len(pending)
    if total_unique == 0:
        print("No pending images.")
        return 0

    # Lazy index for raw images by month: {"04": {raw_key: path}, "05": {...}}
    raw_month_index: Dict[str, Dict[str, Path]] = {}

    def ensure_raw_month_index(month_str: str) -> None:
        if raw_root is None:
            return
        if month_str in raw_month_index:
            return

        idx: Dict[str, Path] = {}
        month_dir = raw_root / month_str
        if not month_dir.is_dir():
            raw_month_index[month_str] = idx
            return

        for p in month_dir.rglob("*"):
            if not (p.is_file() and p.suffix.lower() in IMG_EXTS):
                continue
            m = meta_from_filename(p.name)
            v = view_from_filename(p.name)
            if m is None or v is None:
                continue
            k = make_raw_key(m, v, decimals=args.precision)
            idx.setdefault(k, p)

        raw_month_index[month_str] = idx

    def resolve_raw_path(rel_path: str, image_name: str) -> Optional[Path]:
        if raw_root is None:
            return None

        # 1) If raw mirrors the same rel_path (best case)
        cand = raw_root / rel_path
        if cand.exists():
            return cand

        # 2) Robust match by (year,month,lat,lon) + view (ignores panoid)
        m = meta_from_filename(image_name)
        v = view_from_filename(image_name)
        if m is None or v is None:
            return None

        month_str = f"{m.month:02d}"
        ensure_raw_month_index(month_str)
        k = make_raw_key(m, v, decimals=args.precision)
        return raw_month_index.get(month_str, {}).get(k)

    # viewer selection
    use_tk = False
    if args.viewer == "tk":
        if not TK_OK:
            raise SystemExit("Tk viewer needs Pillow. Try: python -m pip install pillow")
        use_tk = True
    elif args.viewer == "fallback":
        use_tk = False
    else:
        use_tk = TK_OK

    viewer = TkViewer(f"TP/FP — {vis_dir.name}", enable_raw=bool(raw_root)) if use_tk else None

    tp_count = sum(1 for v in done.values() if v == "true_positive")
    fp_count = sum(1 for v in done.values() if v == "false_positive")

    skipped_map: Dict[str, int] = {}
    history: List[Action] = []

    queue: List[Path] = pending[:]
    labeled_this_run = 0
    skipped_this_run = 0
    paused = False
    ignore_until = 0.0

    def undo_last_action() -> Optional[Path]:
        nonlocal tp_count, fp_count, labeled_this_run

        if not history:
            return None

        act = history.pop()

        # undo file op
        if act.moved:
            act.orig_path.parent.mkdir(parents=True, exist_ok=True)
            if act.dest_path.exists():
                shutil.move(str(act.dest_path), str(act.orig_path))
        else:
            if act.dest_path.exists():
                try:
                    act.dest_path.unlink()
                except Exception:
                    pass

        # undo done + counters
        if act.rel_path in done:
            del done[act.rel_path]

        if act.label == "true_positive":
            tp_count -= 1
        else:
            fp_count -= 1

        labeled_this_run = max(0, labeled_this_run - 1)

        _ = remove_last_matching_row(
            decisions_csv,
            lambda row: row.get("rel_path") == act.rel_path and row.get("label") == act.label,
        )

        target_csv = tp_csv if act.label == "true_positive" else fp_csv
        removed = remove_last_matching_row(
            target_csv,
            lambda row: (
                row.get("image") == act.out_row.get("image")
                and row.get("label") == act.out_row.get("label")
                and row.get("year") == act.out_row.get("year")
                and row.get("month") == act.out_row.get("month")
                and row.get("lat") == act.out_row.get("lat")
                and row.get("lon") == act.out_row.get("lon")
            ),
        )
        if not removed:
            remove_last_matching_row(target_csv, lambda row: True)

        return act.orig_path

    try:
        while queue:
            img_path = queue.pop(0)
            rel_path = str(img_path.relative_to(vis_dir))
            image_name = img_path.name

            raw_path = resolve_raw_path(rel_path, image_name)

            meta = meta_from_filename(image_name)
            year = month = lat = lon = ""
            if meta is not None:
                key = make_key(meta, decimals=args.precision)
                meta2 = meta_by_key.get(key, meta)
                year = f"{meta2.year:04d}"
                month = f"{meta2.month:02d}"
                lat = str(meta2.lat)
                lon = str(meta2.lon)

            skip_note = "SKIPPED EARLIER (this run)" if skipped_map.get(rel_path, 0) > 0 else ""

            status = (
                f"Labeled {labeled_this_run}/{total_unique} | "
                f"Queue remaining: {len(queue)+1} | TP={tp_count} FP={fp_count} | Skipped(this run)={skipped_this_run}"
            )
            keys = "Keys: y=TP  n=FP  s=skip->end  6=pause-toggle  ←(left)=go back  q=quit"

            if use_tk:
                assert viewer is not None
                info_lines = [status, rel_path]
                if skip_note:
                    info_lines.append(skip_note)
                info_lines.append(keys)

                ch = viewer.show(img_path, info_lines, raw_path=raw_path)
                paused = viewer.is_paused()
                if paused:
                    queue.insert(0, img_path)
                    continue
            else:
                # fallback (Photos)
                print(status)
                print(rel_path)
                if skip_note:
                    print(skip_note)
                print(keys)

                os.startfile(str(img_path))
                time.sleep(0.15)
                if not args.no_focus:
                    focus_console_best_effort()

                ch, paused, ignore_until = get_key_fallback(paused, ignore_until)

                if not args.no_close and ch in {"y", "n", "s", "back"}:
                    close_windows_photos_best_effort()

                if paused:
                    queue.insert(0, img_path)
                    continue

            if ch == "q":
                print("Quit.")
                return 0

            if ch == "back":
                # put current back (not decided yet)
                queue.insert(0, img_path)

                prev_path = undo_last_action()
                if prev_path is None:
                    print("Nothing to go back to (no labeled image yet in this session).")
                    continue

                # show undone image next
                queue.insert(0, prev_path)
                continue

            if ch == "s":
                skipped_map[rel_path] = skipped_map.get(rel_path, 0) + 1
                queue.append(img_path)
                skipped_this_run += 1
                continue

            if ch == "y":
                label = "true_positive"
            elif ch == "n":
                label = "false_positive"
            else:
                continue

            done[rel_path] = label
            append_row(decisions_csv, decisions_fields, {"rel_path": rel_path, "label": label})

            dest_root = tp_dir if label == "true_positive" else fp_dir
            dest_path = safe_copy_or_move_preserve_tree(img_path, vis_dir, dest_root, move=args.move)

            out_row = {"image": image_name, "label": label, "year": year, "month": month, "lat": lat, "lon": lon}
            if label == "true_positive":
                tp_count += 1
                append_row(tp_csv, out_fields, out_row)
            else:
                fp_count += 1
                append_row(fp_csv, out_fields, out_row)

            history.append(
                Action(
                    orig_path=img_path,
                    rel_path=rel_path,
                    label=label,
                    dest_path=dest_path,
                    out_row=out_row,
                    moved=args.move,
                )
            )

            labeled_this_run += 1

    finally:
        if viewer is not None:
            viewer.close()

    print("Done.")
    print(f"Labeled this run: {labeled_this_run}/{total_unique}")
    print(f"Skipped (requeued) this run: {skipped_this_run}")
    print(f"TP CSV: {tp_csv}")
    print(f"FP CSV: {fp_csv}")
    print(f"Decisions: {decisions_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
