"""
Fetch macro-level place data for the recommendation module.

The script uses the public OpenStreetMap Nominatim search API for small,
polite geocoding jobs. It writes a CSV compatible with the current Flask app.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SEEDS = ROOT_DIR / "scripts" / "data" / "place_seeds.csv"
DEFAULT_OUTPUT = ROOT_DIR / "data" / "generated" / "places_crawled.csv"
DEFAULT_RAW_DIR = ROOT_DIR / "data" / "raw" / "nominatim"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "toursim-system-course-design/1.0 (student project)"


def request_json(url: str, params: dict[str, str]) -> list[dict]:
    query_url = f"{url}?{urlencode(params)}"
    request = Request(query_url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_score(value: float, low: float, high: float, target_low: float, target_high: float) -> float:
    if high <= low:
        return target_low
    ratio = (value - low) / (high - low)
    return target_low + ratio * (target_high - target_low)


def build_place_row(index: int, seed: dict[str, str], result: dict | None) -> dict[str, str]:
    name = seed["name"].strip()
    place_type = seed.get("type", "").strip() or "景区"
    city = seed.get("city", "").strip()
    tags = seed.get("tags", "").strip()

    if result:
        importance = float(result.get("importance") or 0.5)
        rating = round(normalize_score(importance, 0.2, 0.9, 4.2, 4.9), 1)
        popularity = int(round(normalize_score(importance, 0.2, 0.9, 78, 100)))
        lat = result.get("lat", "")
        lon = result.get("lon", "")
        osm_type = result.get("osm_type", "")
        osm_id = result.get("osm_id", "")
        description = result.get("display_name", name)
    else:
        rating = 4.5
        popularity = 80
        lat = lon = osm_type = osm_id = ""
        description = f"{name}，待补充公开地图数据。"

    return {
        "id": str(index),
        "name": name,
        "type": place_type,
        "city": city,
        "rating": str(rating),
        "popularity": str(popularity),
        "tags": tags,
        "description": description,
        "lat": str(lat),
        "lon": str(lon),
        "osm_type": str(osm_type),
        "osm_id": str(osm_id),
    }


def fetch_place(seed: dict[str, str], raw_dir: Path, delay: float) -> dict | None:
    name = seed["name"].strip()
    city = seed.get("city", "").strip()
    query = f"{name}, {city}, 中国" if city else f"{name}, 中国"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{name}.json"

    if raw_file.exists():
        return json.loads(raw_file.read_text(encoding="utf-8"))[0]

    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": "1",
        "accept-language": "zh-CN",
    }
    try:
        payload = request_json(NOMINATIM_URL, params)
    except (HTTPError, URLError, TimeoutError) as exc:
        print(f"[WARN] {name}: {exc}")
        return None

    raw_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    time.sleep(delay)
    return payload[0] if payload else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch places for TourSim recommendation data.")
    parser.add_argument("--seeds", type=Path, default=DEFAULT_SEEDS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--limit", type=int, default=0, help="0 means all seed rows.")
    parser.add_argument("--delay", type=float, default=1.1, help="Nominatim policy-friendly delay.")
    args = parser.parse_args()

    seeds = list(csv.DictReader(args.seeds.open("r", encoding="utf-8-sig")))
    if args.limit > 0:
        seeds = seeds[: args.limit]

    rows = []
    for index, seed in enumerate(seeds, start=1):
        result = fetch_place(seed, args.raw_dir, args.delay)
        rows.append(build_place_row(index, seed, result))
        print(f"[OK] {seed['name']}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "name", "type", "city", "rating", "popularity", "tags", "description", "lat", "lon", "osm_type", "osm_id"]
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"written: {args.output}")


if __name__ == "__main__":
    main()
