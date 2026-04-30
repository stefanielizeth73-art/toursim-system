"""
Build an internal route graph and facility CSV from OpenStreetMap data.

Inputs:
  python scripts/data/build_osm_graph.py --place "北京邮电大学沙河校区, 北京, 中国"

Outputs:
  data/generated/route_graph_<slug>.json
  data/generated/facilities_<slug>.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parents[2]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "toursim-system-course-design/1.0 (student project)"


def request_json(url: str, params: dict[str, str] | None = None, data: str | None = None) -> dict | list:
    if params:
        url = f"{url}?{urlencode(params)}"
    body = data.encode("utf-8") if data is not None else None
    request = Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def slugify(text: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", text).strip("_")
    return slug[:40] or "place"


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_bbox(place: str) -> tuple[float, float, float, float]:
    params = {
        "q": place,
        "format": "jsonv2",
        "limit": "1",
        "accept-language": "zh-CN",
    }
    results = request_json(NOMINATIM_URL, params=params)
    if not results:
        raise RuntimeError(f"Nominatim did not find: {place}")

    south, north, west, east = [float(value) for value in results[0]["boundingbox"]]
    time.sleep(1.1)
    return south, west, north, east


def build_overpass_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    bbox_text = f"{south},{west},{north},{east}"
    return f"""
[out:json][timeout:60];
(
  way["highway"~"^(footway|path|pedestrian|service|residential|living_street|steps|cycleway|unclassified|tertiary)$"]({bbox_text});
  node["amenity"]({bbox_text});
  node["shop"]({bbox_text});
  node["tourism"]({bbox_text});
  node["leisure"]({bbox_text});
  way["amenity"]({bbox_text});
  way["shop"]({bbox_text});
  way["tourism"]({bbox_text});
  way["leisure"]({bbox_text});
  way["building"]({bbox_text});
);
out body center;
>;
out skel qt;
"""


def classify_facility(tags: dict[str, str]) -> str:
    amenity = tags.get("amenity", "")
    shop = tags.get("shop", "")
    tourism = tags.get("tourism", "")
    leisure = tags.get("leisure", "")
    building = tags.get("building", "")

    mapping = {
        "toilets": "卫生间",
        "restaurant": "餐饮",
        "cafe": "咖啡",
        "fast_food": "餐饮",
        "library": "图书馆",
        "hospital": "医疗点",
        "clinic": "医疗点",
        "parking": "交通设施",
        "bicycle_parking": "交通设施",
        "information": "服务站",
    }
    if amenity in mapping:
        return mapping[amenity]
    if shop:
        return "商店"
    if tourism:
        return "景点"
    if leisure:
        return "休闲设施"
    if building:
        return "建筑物"
    return "服务设施"


def nearest_node_id(lat: float, lon: float, road_nodes: dict[int, dict]) -> str:
    best_osm_id = min(
        road_nodes,
        key=lambda node_id: haversine(lat, lon, road_nodes[node_id]["lat"], road_nodes[node_id]["lon"]),
    )
    return f"osm_{best_osm_id}"


def scale_xy(nodes: list[dict]) -> None:
    if not nodes:
        return
    min_lat = min(node["lat"] for node in nodes)
    max_lat = max(node["lat"] for node in nodes)
    min_lon = min(node["lon"] for node in nodes)
    max_lon = max(node["lon"] for node in nodes)
    lat_span = max(max_lat - min_lat, 0.000001)
    lon_span = max(max_lon - min_lon, 0.000001)
    for node in nodes:
        node["x"] = round((node["lon"] - min_lon) / lon_span * 760 + 20, 1)
        node["y"] = round((max_lat - node["lat"]) / lat_span * 460 + 20, 1)


def build_graph(payload: dict, place_name: str, max_edges: int) -> tuple[dict, list[dict]]:
    elements = payload.get("elements", [])
    osm_nodes = {
        element["id"]: element
        for element in elements
        if element.get("type") == "node" and "lat" in element and "lon" in element
    }
    highway_ways = [
        element for element in elements
        if element.get("type") == "way" and "highway" in element.get("tags", {}) and element.get("nodes")
    ]

    used_node_ids: set[int] = set()
    edges = []
    edge_seen = set()
    for way in highway_ways:
        way_nodes = way["nodes"]
        tags = way.get("tags", {})
        for start, end in zip(way_nodes, way_nodes[1:]):
            if start not in osm_nodes or end not in osm_nodes:
                continue
            key = tuple(sorted((start, end)))
            if key in edge_seen:
                continue
            start_node = osm_nodes[start]
            end_node = osm_nodes[end]
            distance = haversine(start_node["lat"], start_node["lon"], end_node["lat"], end_node["lon"])
            edges.append({
                "from": f"osm_{start}",
                "to": f"osm_{end}",
                "distance": round(distance, 1),
                "congestion": 0.85,
                "walk": True,
                "bike": tags.get("bicycle") != "no" and tags.get("highway") != "steps",
                "source": "openstreetmap",
            })
            edge_seen.add(key)
            used_node_ids.update((start, end))
            if max_edges and len(edges) >= max_edges:
                break
        if max_edges and len(edges) >= max_edges:
            break

    road_nodes = {
        node_id: osm_nodes[node_id]
        for node_id in used_node_ids
        if node_id in osm_nodes
    }
    nodes = [
        {
            "id": f"osm_{node_id}",
            "name": f"道路节点{node_id}",
            "category": "路口",
            "kind": "intersection",
            "lat": node["lat"],
            "lon": node["lon"],
        }
        for node_id, node in road_nodes.items()
    ]
    scale_xy(nodes)

    facilities = []
    facility_id = 1
    for element in elements:
        tags = element.get("tags", {})
        if not any(key in tags for key in ("amenity", "shop", "tourism", "leisure", "building")):
            continue

        lat = element.get("lat") or element.get("center", {}).get("lat")
        lon = element.get("lon") or element.get("center", {}).get("lon")
        if lat is None or lon is None or not road_nodes:
            continue

        name = tags.get("name") or tags.get("name:zh") or f"{classify_facility(tags)}{facility_id}"
        facilities.append({
            "id": facility_id,
            "name": name,
            "type": classify_facility(tags),
            "parent_place": place_name,
            "nearest_node": nearest_node_id(float(lat), float(lon), road_nodes),
            "description": tags.get("description", f"来自 OpenStreetMap 的 {name} 数据。"),
        })
        facility_id += 1

    graph = {
        "place_name": place_name,
        "default_start": nodes[0]["id"] if nodes else "",
        "nodes": nodes,
        "edges": edges,
        "source": "openstreetmap_overpass",
    }
    return graph, facilities


def main() -> None:
    parser = argparse.ArgumentParser(description="Build TourSim graph data from OpenStreetMap.")
    parser.add_argument("--place", required=True, help="Place name accepted by Nominatim.")
    parser.add_argument("--graph-output", type=Path)
    parser.add_argument("--facilities-output", type=Path)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--max-edges", type=int, default=300)
    args = parser.parse_args()

    slug = slugify(args.place)
    graph_output = args.graph_output or ROOT_DIR / "data" / "generated" / f"route_graph_{slug}.json"
    facilities_output = args.facilities_output or ROOT_DIR / "data" / "generated" / f"facilities_{slug}.csv"
    raw_output = args.raw_output or ROOT_DIR / "data" / "raw" / "overpass" / f"{slug}.json"

    bbox = geocode_bbox(args.place)
    query = build_overpass_query(bbox)
    payload = request_json(OVERPASS_URL, data=urlencode({"data": query}))
    raw_output.parent.mkdir(parents=True, exist_ok=True)
    raw_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    graph, facilities = build_graph(payload, args.place, max_edges=args.max_edges)
    graph_output.parent.mkdir(parents=True, exist_ok=True)
    graph_output.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")

    facilities_output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["id", "name", "type", "parent_place", "nearest_node", "description"]
    with facilities_output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(facilities)

    print(f"graph nodes: {len(graph['nodes'])}, edges: {len(graph['edges'])}")
    print(f"facilities: {len(facilities)}")
    print(f"graph written: {graph_output}")
    print(f"facilities written: {facilities_output}")


if __name__ == "__main__":
    main()
