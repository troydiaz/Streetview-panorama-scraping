import json
import math
import asyncio
import itertools
import traceback
import webbrowser
import os
import yaml
import aiohttp
import folium
import csv
from pathlib import Path

import streetview


def distance_km(p1, p2):
    """Haversine formula: returns distance in km for (lat, lon) pairs."""
    R = 6373.0
    lat1 = math.radians(float(p1[0]))
    lon1 = math.radians(float(p1[1]))
    lat2 = math.radians(float(p2[0]))
    lon2 = math.radians(float(p2[1]))

    dlon = lon2 - lon1
    dlat = lat2 - lat1

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def build_points_from_csv(csv_path: str):
    """Read (lat, lon) from CSV columns: latitude / longitude. Dedup by rounding."""
    pts = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fcsv:
        reader = csv.DictReader(fcsv)
        fields = {h.lower(): h for h in (reader.fieldnames or [])}
        lat_col = fields.get("latitude")
        lon_col = fields.get("longitude")
        if not lat_col or not lon_col:
            raise ValueError("CSV must have 'latitude' and 'longitude' columns")

        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except Exception:
                continue
            pts.append((lat, lon))

    # de-dupe points (rounding avoids tiny float differences)
    seen = set()
    out = []
    for lat, lon in pts:
        key = (round(lat, 6), round(lon, 6))
        if key in seen:
            continue
        seen.add(key)
        out.append((lat, lon))
    return out


def build_points_from_grid(center, radius_km, resolution):
    """Fallback grid of points in bounding box, filtered to within radius."""
    top_left = (center[0] - radius_km / 70, center[1] + radius_km / 70)
    bottom_right = (center[0] + radius_km / 70, center[1] - radius_km / 70)

    lat_diff = top_left[0] - bottom_right[0]
    lon_diff = top_left[1] - bottom_right[1]

    grid = list(itertools.product(range(resolution + 1), range(resolution + 1)))
    pts = [
        (bottom_right[0] + x * lat_diff / resolution, bottom_right[1] + y * lon_diff / resolution)
        for (x, y) in grid
    ]
    pts = [p for p in pts if distance_km(p, center) <= radius_km]
    return pts


async def fetch_best_panoid(lat, lon, session, search_radius_m, max_retries=4):
    """
    Call SingleImageSearch and return ONLY the closest panoid dict to (lat, lon).
    Returns None if no panoids found.
    """
    # NOTE: the only change to "reduce surrounding" is this radius: !2d{search_radius_m}
    url = (
        "https://maps.googleapis.com/maps/api/js/GeoPhotoService.SingleImageSearch?pb="
        f"!1m5!1sapiv3!5sUS!11m2!1m1!1b0!2m4!1m2!3d{lat}!4d{lon}!2d{search_radius_m}"
        "!3m10!2m2!1sen!2sGB!9m1!1e2!11m4!1m3!1e2!2b1!3e2!"
        "4m10!1e1!1e2!1e3!1e4!1e8!1e6!5m1!1e2!6m1!1e2&callback=_xdc_._v2mub5"
    )

    delay = 1.0
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                text = await resp.text()

            panoids = streetview.panoids_from_response(text)
            if not panoids:
                return None

            # Choose nearest pano to the query point
            def d_km(p):
                try:
                    return distance_km((lat, lon), (float(p["lat"]), float(p["lon"])))
                except Exception:
                    return float("inf")

            best = min(panoids, key=d_km)
            return best

        except Exception:
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 10.0)


async def worker(name, queue, session, search_radius_m, seen_panoids, unique_panoids, stats, lock):
    """Queue worker: gets points, fetches best panoid, dedupes by panoid id."""
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break

        lat, lon = item
        best = await fetch_best_panoid(lat, lon, session, search_radius_m)

        async with lock:
            stats["processed"] += 1

        if best and isinstance(best, dict):
            pid = best.get("panoid")
            if pid:
                async with lock:
                    if pid not in seen_panoids:
                        seen_panoids.add(pid)
                        unique_panoids.append(best)
                        stats["unique"] += 1

        queue.task_done()


async def run_requests(points, concurrency, search_radius_m, print_every):
    """
    Process all points with a bounded concurrency worker pool.
    Returns list of unique panoid dicts.
    """
    queue = asyncio.Queue()
    for p in points:
        queue.put_nowait(p)

    seen_panoids = set()
    unique_panoids = []
    stats = {"processed": 0, "unique": 0}
    lock = asyncio.Lock()

    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        workers = [
            asyncio.create_task(
                worker(f"W{i+1}", queue, session, search_radius_m, seen_panoids, unique_panoids, stats, lock)
            )
            for i in range(concurrency)
        ]

        # progress printer
        while True:
            await asyncio.sleep(1.0)
            async with lock:
                processed = stats["processed"]
                unique = stats["unique"]
            if processed and (processed % print_every == 0):
                if os.name == "nt":
                    os.system("cls")
                print(f"Processed points: {processed}/{len(points)} | Unique panoids: {unique}")
            if processed >= len(points):
                break

        # stop workers
        for _ in workers:
            queue.put_nowait(None)
        await queue.join()
        await asyncio.gather(*workers, return_exceptions=True)

    return unique_panoids


if __name__ == "__main__":
    # Output files
    file = "Result.html"
    zoom_start = 12

    # Read configuration
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    center = config.get("center", [0, 0])
    radius = config.get("radius", 1.0)          # km (your existing config meaning)
    resolution = config.get("resolution", 50)

    # New knobs (optional in config.yaml)
    search_radius_m = int(config.get("search_radius_m", 10))     # <-- key change vs 50
    concurrency = int(config.get("concurrency", 50))
    print_every = int(config.get("print_every", 500))

    # Create map
    M = folium.Map(location=center, tiles="OpenStreetMap", zoom_start=zoom_start)
    M.add_child(folium.LatLngPopup())
    folium.Circle(location=center, radius=radius * 1000, color="#FF000099", fill="True").add_to(M)

    # Build points from CSV if provided, else grid
    csv_path = config.get("csv_points")
    if csv_path and Path(csv_path).is_file():
        test_points = build_points_from_csv(csv_path)

        # set map center nicely
        if test_points:
            center = [
                sum(p[0] for p in test_points) / len(test_points),
                sum(p[1] for p in test_points) / len(test_points),
            ]
            M.location = center
    else:
        test_points = build_points_from_grid(center=center, radius_km=radius, resolution=resolution)

    print(f"Points to query: {len(test_points)}")
    print(f"Search radius (meters): {search_radius_m}")
    print(f"Concurrency: {concurrency}")

    # Run async worker pool
    unique_panoids = asyncio.run(run_requests(test_points, concurrency, search_radius_m, print_every))

    print(f"Unique panoids found: {len(unique_panoids)}")

    # Plot pano locations
    for pan in unique_panoids:
        try:
            folium.CircleMarker(
                [float(pan["lat"]), float(pan["lon"])],
                popup=str(pan.get("panoid", "")),
                radius=1,
                color="blue",
                fill=True,
            ).add_to(M)
        except Exception:
            continue

    # Save data
    out_json = f"panoids_{len(unique_panoids)}.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(unique_panoids, f, indent=2)

    # Save map and open it
    M.save(file)
    webbrowser.open(file)
    print(f"Wrote: {out_json}")
