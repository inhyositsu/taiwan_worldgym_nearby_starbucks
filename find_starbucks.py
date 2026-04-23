#!/usr/bin/env python3
"""Step 2: for each World Gym branch, find Starbucks within 500m.

Inputs
------
- worldgym_branches.json (from scrape_worldgym.py)
- ~/.config/gmaps_api_key (your Google Maps API key)

Outputs
-------
- results.json : full detail per branch with matched Starbucks
- results.csv  : 分店 | 地址 | 最近星巴克 | 距離(m)

APIs used
---------
- Geocoding API          (fills in missing lat/lng)
- Places API (New) :searchNearby   (find Starbucks within 500m)
"""
from __future__ import annotations

import csv
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
KEY_FILE = Path.home() / ".config" / "gmaps_api_key"
BRANCH_FILE = HERE / "worldgym_branches.json"
OUT_JSON = HERE / "results.json"
OUT_CSV = HERE / "results.csv"

RADIUS_M = 500
STARBUCKS_NAMES = ("starbucks", "星巴克")

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"


def load_key() -> str:
    if not KEY_FILE.exists():
        sys.exit(f"API key not found at {KEY_FILE}")
    key = KEY_FILE.read_text().strip()
    if not key:
        sys.exit(f"API key file {KEY_FILE} is empty")
    return key


def http_get_json(url: str, params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{qs}", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post_json(url: str, body: dict, headers: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(query: str, key: str) -> tuple[float, float, str] | None:
    """Return (lat, lng, formatted_address) or None."""
    resp = http_get_json(
        GEOCODE_URL,
        {"address": query, "key": key, "region": "tw", "language": "zh-TW"},
    )
    if resp.get("status") != "OK" or not resp.get("results"):
        return None
    r0 = resp["results"][0]
    loc = r0["geometry"]["location"]
    return loc["lat"], loc["lng"], r0.get("formatted_address", "")


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def nearby_starbucks(lat: float, lng: float, key: str) -> list[dict]:
    body = {
        "includedTypes": ["cafe"],
        "maxResultCount": 20,
        "languageCode": "zh-TW",
        "regionCode": "tw",
        "locationRestriction": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": RADIUS_M}
        },
    }
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.id",
    }
    resp = http_post_json(NEARBY_URL, body, headers)
    results = []
    for p in resp.get("places", []):
        name = (p.get("displayName") or {}).get("text", "")
        if not any(k.lower() in name.lower() for k in STARBUCKS_NAMES):
            continue
        loc = p.get("location") or {}
        plat, plng = loc.get("latitude"), loc.get("longitude")
        if plat is None or plng is None:
            continue
        results.append(
            {
                "name": name,
                "address": p.get("formattedAddress", ""),
                "lat": plat,
                "lng": plng,
                "distance_m": round(haversine_m(lat, lng, plat, plng), 1),
                "place_id": p.get("id", ""),
            }
        )
    results.sort(key=lambda r: r["distance_m"])
    return results


def main() -> int:
    key = load_key()
    branches = json.loads(BRANCH_FILE.read_text(encoding="utf-8"))

    # Skip branches that were 404 on the source site
    branches = [b for b in branches if "error" not in b]

    # Step 2a: fill in missing lat/lng via geocoding
    to_geocode = [b for b in branches if b.get("lat") is None]
    print(f"[geocode] {len(to_geocode)} branches need geocoding", file=sys.stderr)
    for b in to_geocode:
        # Prefer address; fall back to name + "Taiwan"
        q = b.get("address") or f"{b.get('name','')} 台灣"
        try:
            hit = geocode(q, key)
        except Exception as e:
            print(f"[geocode:err] {b['slug']}: {e}", file=sys.stderr)
            hit = None
        if hit:
            b["lat"], b["lng"], geo_addr = hit
            if not b.get("address"):
                b["address"] = geo_addr
            b["geocoded"] = True
            print(f"[geocode:ok] {b['slug']} -> {b['lat']:.5f},{b['lng']:.5f}", file=sys.stderr)
        else:
            print(f"[geocode:miss] {b['slug']} / {b.get('name','')}", file=sys.stderr)
        time.sleep(0.1)

    # Step 2b: nearby Starbucks search
    rows: list[dict] = []
    for i, b in enumerate(branches, 1):
        if b.get("lat") is None:
            rows.append({**b, "starbucks": [], "nearest_starbucks": None, "nearest_distance_m": None})
            continue
        try:
            sbs = nearby_starbucks(b["lat"], b["lng"], key)
        except Exception as e:
            print(f"[nearby:err] {b['slug']}: {e}", file=sys.stderr)
            sbs = []
        nearest = sbs[0] if sbs else None
        rows.append({
            **b,
            "starbucks": sbs,
            "nearest_starbucks": nearest["name"] if nearest else None,
            "nearest_distance_m": nearest["distance_m"] if nearest else None,
        })
        if i % 20 == 0:
            print(f"[nearby] {i}/{len(branches)}", file=sys.stderr)
        time.sleep(0.05)

    # Save full
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # CSV: only branches with at least one Starbucks
    hits = [r for r in rows if r["starbucks"]]
    hits.sort(key=lambda r: r["nearest_distance_m"])
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["分店", "地址", "最近星巴克", "距離(m)", "星巴克地址", "WG經緯度", "星巴克經緯度"])
        for r in hits:
            sb = r["starbucks"][0]
            w.writerow([
                r["name"],
                r["address"],
                sb["name"],
                sb["distance_m"],
                sb["address"],
                f"{r['lat']},{r['lng']}",
                f"{sb['lat']},{sb['lng']}",
            ])

    print(f"[done] full results -> {OUT_JSON}", file=sys.stderr)
    print(f"[done] CSV (hits only) -> {OUT_CSV}", file=sys.stderr)
    print(f"[stat] total branches: {len(rows)}", file=sys.stderr)
    print(f"[stat] with Starbucks ≤{RADIUS_M}m: {len(hits)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
