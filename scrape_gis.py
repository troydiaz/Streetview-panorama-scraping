"""
scrape_gis.py

Scrapes GovernmentJobs "newprint" pages for Kaua'i job IDs and flags postings
that match official GIS Analyst class titles / variants.

Example:
  python scrape_gis.py --start 3503376 --end 3502376 --out kauai_gis_hits.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import requests


# --- Keyword set derived from Kaua'i class spec titles (plus common variants) ---
# Titles:
#  - GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST I..V :contentReference[oaicite:6]{index=6} :contentReference[oaicite:7]{index=7} :contentReference[oaicite:8]{index=8} :contentReference[oaicite:9]{index=9} :contentReference[oaicite:10]{index=10}
#  - SENIOR GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST :contentReference[oaicite:11]{index=11}
KEY_TERMS: List[str] = [
    # Official long-form titles:
    "GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST I",
    "GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST II",
    "GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST III",
    "GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST IV",
    "GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST V",
    "SENIOR GEOGRAPHIC INFORMATION SYSTEMS (GIS) ANALYST",

    # Common short-form variants (often appears in postings / headers):
    "GIS ANALYST I",
    "GIS ANALYST II",
    "GIS ANALYST III",
    "GIS ANALYST IV",
    "GIS ANALYST V",
    "SENIOR GIS ANALYST",

    # Extra variants that sometimes appear without parentheses:
    "GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST I",
    "GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST II",
    "GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST III",
    "GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST IV",
    "GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST V",
    "SENIOR GEOGRAPHIC INFORMATION SYSTEMS GIS ANALYST",

    # Sometimes the posting uses "Geographic Information Systems Analyst" (no "(GIS)")
    "GEOGRAPHIC INFORMATION SYSTEMS ANALYST I",
    "GEOGRAPHIC INFORMATION SYSTEMS ANALYST II",
    "GEOGRAPHIC INFORMATION SYSTEMS ANALYST III",
    "GEOGRAPHIC INFORMATION SYSTEMS ANALYST IV",
    "GEOGRAPHIC INFORMATION SYSTEMS ANALYST V",
    "SENIOR GEOGRAPHIC INFORMATION SYSTEMS ANALYST",
]


@dataclass
class Hit:
    job_id: int
    url: str
    status_code: int
    title_guess: str
    matched_terms: str  # pipe-separated


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def extract_title(html: str) -> str:
    """
    Best-effort title extraction from the print page.
    This is intentionally resilient (GovernmentJobs markup can vary).
    """
    # Try <title> first
    m = re.search(r"<title>\s*(.*?)\s*</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        t = normalize_space(re.sub(r"<.*?>", "", m.group(1)))
        if t:
            return t

    # Fallback: try a top-level heading (h1/h2)
    m = re.search(r"<h1[^>]*>\s*(.*?)\s*</h1>", html, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        m = re.search(r"<h2[^>]*>\s*(.*?)\s*</h2>", html, flags=re.IGNORECASE | re.DOTALL)
    if m:
        t = normalize_space(re.sub(r"<.*?>", "", m.group(1)))
        if t:
            return t

    return ""


def find_matches(text: str, terms: List[str]) -> List[str]:
    upper_text = text.upper()
    hits = []
    for term in terms:
        if term.upper() in upper_text:
            hits.append(term)
    return hits


def fetch(session: requests.Session, url: str, timeout: float) -> Tuple[int, str]:
    r = session.get(url, timeout=timeout)
    return r.status_code, r.text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True, help="Start job ID (inclusive)")
    ap.add_argument("--end", type=int, required=True, help="End job ID (inclusive)")
    ap.add_argument("--out", type=str, default="kauai_gis_hits.csv", help="Output CSV path")
    ap.add_argument("--sleep", type=float, default=0.4, help="Delay between requests (seconds)")
    ap.add_argument("--timeout", type=float, default=20.0, help="Request timeout (seconds)")
    ap.add_argument("--base", type=str, default="https://www.governmentjobs.com/careers/kauai/jobs/newprint",
                    help="Base URL for newprint pages")
    args = ap.parse_args()

    start_id = min(args.start, args.end)
    end_id = max(args.start, args.end)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; KauaiGISScraper/1.0; +https://www.governmentjobs.com/)",
        "Accept-Language": "en-US,en;q=0.9",
    })

    hits: List[Hit] = []

    step = 1 if args.start <= args.end else -1
    for job_id in range(args.start, args.end + step, step):
        url = f"{args.base}/{job_id}"

        try:
            status, html = fetch(session, url, timeout=args.timeout)
        except requests.RequestException as e:
            # Record failures (optional) or just skip
            print(f"[{job_id}] ERROR: {e}")
            time.sleep(args.sleep)
            continue

        # If page doesn't exist, GovernmentJobs often returns 404 (or a generic page)
        if status != 200 or not html:
            print(f"[{job_id}] status={status} (skip)")
            time.sleep(args.sleep)
            continue

        # Search full HTML text for keywords (case-insensitive)
        matches = find_matches(html, KEY_TERMS)
        if matches:
            title_guess = extract_title(html)
            hit = Hit(
                job_id=job_id,
                url=url,
                status_code=status,
                title_guess=title_guess,
                matched_terms="|".join(matches),
            )
            hits.append(hit)
            print(f"[{job_id}] HIT: {title_guess or '(no title found)'}  -> {hit.matched_terms}")
        else:
            print(f"[{job_id}] no match")

        time.sleep(args.sleep)

    # Write results
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["job_id", "url", "status_code", "title_guess", "matched_terms"])
        for h in hits:
            w.writerow([h.job_id, h.url, h.status_code, h.title_guess, h.matched_terms])

    print(f"\nDone. Matches: {len(hits)}")
    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
