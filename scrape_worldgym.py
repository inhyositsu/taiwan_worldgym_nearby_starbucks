#!/usr/bin/env python3
"""Scrape all World Gym Taiwan branches: slug, name, address.

Source: https://www.worldgymtaiwan.com/sitemap.xml
Output: worldgym_branches.json (list of {slug, name, address, url})
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SITEMAP_URL = "https://www.worldgymtaiwan.com/sitemap.xml"
BRANCH_URL_RE = re.compile(r"https://www\.worldgymtaiwan\.com/find-a-club/([a-z0-9-]+)(?=[<\s/])")
TITLE_RE = re.compile(r"<title>([^<]+)</title>")
ADDRESS_RE = re.compile(
    r"([一-鿿]{1,4}[縣市][一-鿿]{1,6}[區鄉鎮市][^\"<>,{}]{3,80}?號(?:[^\"<>,{}]{0,20}?樓)?)"
)
LATLNG_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
EXCLUDE_SLUGS = {
    "employee-welfare-committee",  # not a real club
}
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}


def fetch(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def list_branch_slugs() -> list[str]:
    xml = fetch(SITEMAP_URL)
    slugs: set[str] = set()
    for m in BRANCH_URL_RE.finditer(xml):
        slugs.add(m.group(1))
    # exclude sub-pages that leaked through (none expected, but safe)
    return sorted(s for s in slugs if s not in EXCLUDE_SLUGS)


def parse_branch(slug: str) -> dict:
    url = f"https://www.worldgymtaiwan.com/find-a-club/{slug}"
    html = fetch(url)
    title_m = TITLE_RE.search(html)
    title = title_m.group(1).strip() if title_m else ""
    # Canonical name like "World Gym彰化和平店" appears at tail of title
    name_m = re.search(r"World Gym[一-鿿\w]+店", title)
    name = name_m.group(0) if name_m else title.split("｜")[0]
    addr_m = ADDRESS_RE.search(html)
    address = addr_m.group(1) if addr_m else ""
    ll_m = LATLNG_RE.search(html)
    lat = float(ll_m.group(1)) if ll_m else None
    lng = float(ll_m.group(2)) if ll_m else None
    return {"slug": slug, "name": name, "address": address, "lat": lat, "lng": lng, "url": url}


def main() -> int:
    slugs = list_branch_slugs()
    print(f"[info] {len(slugs)} branch slugs from sitemap", file=sys.stderr)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(parse_branch, s): s for s in slugs}
        for i, f in enumerate(as_completed(futures), 1):
            slug = futures[f]
            try:
                results.append(f.result())
            except Exception as e:
                print(f"[warn] {slug}: {e}", file=sys.stderr)
                results.append({"slug": slug, "name": "", "address": "", "lat": None, "lng": None, "url": f"https://www.worldgymtaiwan.com/find-a-club/{slug}", "error": str(e)})
            if i % 20 == 0:
                print(f"[info] {i}/{len(slugs)} done", file=sys.stderr)

    results.sort(key=lambda r: r["slug"])
    out = Path(__file__).parent / "worldgym_branches.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_addr = [r for r in results if not r["address"]]
    missing_ll = [r for r in results if r["lat"] is None]
    print(f"[done] {len(results)} branches → {out}", file=sys.stderr)
    print(f"[stat] missing address: {len(missing_addr)}", file=sys.stderr)
    print(f"[stat] missing lat/lng: {len(missing_ll)}", file=sys.stderr)
    if missing_ll:
        for r in missing_ll:
            print(f"  - {r['slug']} / {r['name']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
