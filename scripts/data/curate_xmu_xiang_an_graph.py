"""
Curate the XMU Xiang'an campus graph from the generated OSM candidate graph.

The generated OSM file keeps hundreds of raw road points. This script turns it
into the official course-demo graph:
- road nodes remain in the graph for Dijkstra, but are hidden from selectors;
- POI nodes are hand-named and selectable;
- road chains are simplified while preserving full geometry on each edge.
"""

from __future__ import annotations

import collections
import json
import math
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
GENERATED_DIR = ROOT_DIR / "data" / "generated"
OUTPUT_FILE = ROOT_DIR / "data" / "graphs" / "xmu_xiang_an.json"
TURN_KEEP_THRESHOLD = 50

PLACE_ID = "xmu_xiang_an"
PLACE_NAME = "厦门大学翔安校区"
BOUNDS = [[24.6044231, 118.2941235], [24.6202117, 118.3154670]]
CAMPUS_BOUNDS = [[24.6046, 118.2944], [24.6200, 118.3152]]
CENTER = [24.6123744, 118.3052155]

POIS = [
    {"id": "south_gate", "name": "南门", "category": "出入口", "kind": "gate", "lat": 24.6051, "lon": 118.3052, "x": 495, "y": 690},
    {"id": "bus_stop_south", "name": "南门公交站", "category": "交通设施", "kind": "facility", "lat": 24.6049, "lon": 118.3041, "x": 450, "y": 700},
    {"id": "cycle_parking", "name": "共享单车停放点", "category": "交通设施", "kind": "facility", "lat": 24.6053, "lon": 118.3058, "x": 530, "y": 685},
    {"id": "service_center", "name": "校区服务中心", "category": "服务站", "kind": "facility", "lat": 24.6058, "lon": 118.3049, "x": 485, "y": 650},
    {"id": "admin_square", "name": "主入口广场", "category": "景观", "kind": "landmark", "lat": 24.6070, "lon": 118.3047, "x": 480, "y": 600},
    {"id": "college_south", "name": "南部学院楼群", "category": "教学楼", "kind": "building", "lat": 24.6068, "lon": 118.3024, "x": 360, "y": 610},
    {"id": "medical_center", "name": "校区医务室", "category": "医疗点", "kind": "facility", "lat": 24.6066, "lon": 118.2980, "x": 170, "y": 620},
    {"id": "central_lake_south", "name": "中央湖区南岸", "category": "景观", "kind": "landmark", "lat": 24.6092, "lon": 118.3058, "x": 520, "y": 485},
    {"id": "canteen_furong", "name": "芙蓉餐厅", "category": "食堂", "kind": "facility", "lat": 24.6084, "lon": 118.3017, "x": 335, "y": 520},
    {"id": "teaching_west", "name": "西部教学楼群", "category": "教学楼", "kind": "building", "lat": 24.6097, "lon": 118.2996, "x": 250, "y": 460},
    {"id": "supermarket", "name": "校园超市", "category": "超市", "kind": "facility", "lat": 24.6099, "lon": 118.3020, "x": 340, "y": 455},
    {"id": "stadium_west", "name": "西区运动场", "category": "场馆", "kind": "landmark", "lat": 24.6094, "lon": 118.2967, "x": 120, "y": 480},
    {"id": "dorm_west", "name": "西部宿舍区", "category": "宿舍", "kind": "building", "lat": 24.6119, "lon": 118.2975, "x": 155, "y": 355},
    {"id": "west_gate", "name": "西门", "category": "出入口", "kind": "gate", "lat": 24.6104, "lon": 118.2948, "x": 30, "y": 450},
    {"id": "library_dewang", "name": "德旺图书馆", "category": "图书馆", "kind": "building", "lat": 24.6120, "lon": 118.3060, "x": 525, "y": 365},
    {"id": "gym_center", "name": "综合体育馆", "category": "场馆", "kind": "facility", "lat": 24.6128, "lon": 118.3067, "x": 560, "y": 330},
    {"id": "central_lake_north", "name": "中央湖区北岸", "category": "景观", "kind": "landmark", "lat": 24.6142, "lon": 118.3062, "x": 540, "y": 250},
    {"id": "central_lake_east", "name": "中央湖区东岸", "category": "景观", "kind": "landmark", "lat": 24.6117, "lon": 118.3096, "x": 690, "y": 365},
    {"id": "teaching_east", "name": "东部教学楼群", "category": "教学楼", "kind": "building", "lat": 24.6115, "lon": 118.3114, "x": 775, "y": 360},
    {"id": "dorm_east", "name": "东部宿舍区", "category": "宿舍", "kind": "building", "lat": 24.6133, "lon": 118.3125, "x": 825, "y": 275},
    {"id": "stadium_east", "name": "东区运动场", "category": "场馆", "kind": "landmark", "lat": 24.6097, "lon": 118.3139, "x": 890, "y": 460},
    {"id": "east_gate", "name": "东门", "category": "出入口", "kind": "gate", "lat": 24.6115, "lon": 118.3150, "x": 890, "y": 350},
    {"id": "college_east", "name": "东南学院楼群", "category": "教学楼", "kind": "building", "lat": 24.6076, "lon": 118.3123, "x": 825, "y": 585},
    {"id": "science_platform", "name": "科研平台楼群", "category": "科研平台", "kind": "building", "lat": 24.6160, "lon": 118.3078, "x": 615, "y": 160},
    {"id": "north_lake", "name": "北部生态湖", "category": "景观", "kind": "landmark", "lat": 24.6173, "lon": 118.3064, "x": 550, "y": 125},
    {"id": "north_gate", "name": "北门", "category": "出入口", "kind": "gate", "lat": 24.6190, "lon": 118.3057, "x": 500, "y": 70},
]


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def generated_graph_path() -> Path:
    candidates = sorted(GENERATED_DIR.glob("route_graph_*.json"), key=lambda p: p.stat().st_size, reverse=True)
    for candidate in candidates:
        data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        if data.get("place_id") == PLACE_ID:
            return candidate
    raise FileNotFoundError("No generated XMU Xiang'an graph found under data/generated.")


def edge_geometry(edge: dict, start_id: str, end_id: str, nodes: dict[str, dict]) -> list[list[float]]:
    geometry = edge.get("geometry") or [
        [nodes[start_id]["lat"], nodes[start_id]["lon"]],
        [nodes[end_id]["lat"], nodes[end_id]["lon"]],
    ]
    if edge.get("from") == start_id:
        return geometry
    return list(reversed(geometry))


def turn_angle(node_id: str, neighbors: list[tuple[str, dict]], nodes: dict[str, dict]) -> float:
    if len(neighbors) != 2:
        return 180
    current = nodes[node_id]
    bearings = []
    for neighbor_id, _edge in neighbors:
        neighbor = nodes[neighbor_id]
        bearings.append(math.atan2(neighbor["lat"] - current["lat"], neighbor["lon"] - current["lon"]))
    angle = abs((bearings[0] - bearings[1] + math.pi) % (2 * math.pi) - math.pi)
    return abs(180 - math.degrees(angle))


def nearest_node_id(lat: float, lon: float, road_nodes: dict[str, dict]) -> str:
    return min(
        road_nodes,
        key=lambda node_id: haversine(lat, lon, road_nodes[node_id]["lat"], road_nodes[node_id]["lon"])
    )


def collect_chain(
    selected: set[str],
    start_id: str,
    next_id: str,
    first_edge: dict,
    adjacency: dict[str, list[tuple[str, dict]]],
    nodes: dict[str, dict],
) -> tuple[str, float, list[list[float]], bool]:
    previous = start_id
    current = next_id
    distance = float(first_edge.get("distance", 0))
    geometry = edge_geometry(first_edge, start_id, next_id, nodes)
    seen = {start_id}

    while current not in selected:
        if current in seen or len(adjacency[current]) != 2:
            return current, distance, geometry, False
        seen.add(current)
        choices = [(node_id, edge) for node_id, edge in adjacency[current] if node_id != previous]
        if not choices:
            return current, distance, geometry, False
        following, edge = choices[0]
        segment = edge_geometry(edge, current, following, nodes)
        geometry.extend(segment[1:])
        distance += float(edge.get("distance", 0))
        previous, current = current, following

    return current, distance, geometry, True


def build_curated_graph() -> dict:
    source = json.loads(generated_graph_path().read_text(encoding="utf-8-sig"))
    source_nodes = {node["id"]: node for node in source["nodes"]}
    adjacency: dict[str, list[tuple[str, dict]]] = collections.defaultdict(list)
    for edge in source["edges"]:
        if edge["from"] in source_nodes and edge["to"] in source_nodes:
            adjacency[edge["from"]].append((edge["to"], edge))
            adjacency[edge["to"]].append((edge["from"], edge))

    selected = {
        node_id
        for node_id, neighbors in adjacency.items()
        if len(neighbors) != 2 or turn_angle(node_id, neighbors, source_nodes) >= TURN_KEEP_THRESHOLD
    }

    anchor_ids = {
        nearest_node_id(poi["lat"], poi["lon"], source_nodes)
        for poi in POIS
    }
    selected.update(anchor_ids)

    curated_nodes = []
    for node_id in sorted(selected):
        node = source_nodes[node_id].copy()
        node["name"] = f"道路节点{node_id.replace('osm_', '')}"
        node["category"] = "道路"
        node["kind"] = "road"
        node["selectable"] = False
        curated_nodes.append(node)

    curated_edges = []
    edge_seen = set()
    for start_id in sorted(selected):
        for next_id, edge in adjacency[start_id]:
            end_id, distance, geometry, ok = collect_chain(selected, start_id, next_id, edge, adjacency, source_nodes)
            if not ok or end_id not in selected or start_id == end_id:
                continue
            key = tuple(sorted((start_id, end_id)))
            if key in edge_seen:
                continue
            edge_seen.add(key)
            curated_edges.append({
                "from": start_id,
                "to": end_id,
                "distance": round(distance, 1),
                "congestion": 0.85,
                "walk": True,
                "bike": bool(edge.get("bike", True)),
                "geometry": [[round(point[0], 7), round(point[1], 7)] for point in geometry],
                "source": "openstreetmap_simplified",
            })

    road_node_map = {node["id"]: node for node in curated_nodes}
    for poi in POIS:
        anchor_id = nearest_node_id(poi["lat"], poi["lon"], road_node_map)
        anchor = road_node_map[anchor_id]
        distance = haversine(poi["lat"], poi["lon"], anchor["lat"], anchor["lon"])
        poi_node = {**poi, "selectable": True, "anchor_node": anchor_id}
        curated_nodes.append(poi_node)
        curated_edges.append({
            "from": poi["id"],
            "to": anchor_id,
            "distance": round(max(distance, 10), 1),
            "congestion": 0.92,
            "walk": True,
            "bike": poi["kind"] not in ("landmark",),
            "geometry": [[round(poi["lat"], 7), round(poi["lon"], 7)], [round(anchor["lat"], 7), round(anchor["lon"], 7)]],
            "source": "manual_poi_connector",
        })

    connect_components(curated_nodes, curated_edges)

    return {
        "place_id": PLACE_ID,
        "place_name": PLACE_NAME,
        "source": "osm_simplified_with_manual_poi",
        "default_start": "south_gate",
        "center": CENTER,
        "bounds": BOUNDS,
        "campus_bounds": CAMPUS_BOUNDS,
        "image_overlay": {
            "url": "/static/xmu_xiang_an_plan.jpg",
            "bounds": BOUNDS,
            "opacity": 0.42,
            "attribution": "厦门大学翔安校区总平面图",
        },
        "nodes": curated_nodes,
        "edges": curated_edges,
    }


def validate(graph: dict) -> dict:
    nodes = {node["id"]: node for node in graph["nodes"]}
    adjacency = {node_id: set() for node_id in nodes}
    bad_edges = []
    for edge in graph["edges"]:
        if edge["from"] not in nodes or edge["to"] not in nodes:
            bad_edges.append(edge)
            continue
        if edge.get("distance", 0) <= 0 or len(edge.get("geometry", [])) < 2:
            bad_edges.append(edge)
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])

    seen = set()
    components = []
    for node_id in nodes:
        if node_id in seen:
            continue
        stack = [node_id]
        seen.add(node_id)
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)

    selectable = [node for node in graph["nodes"] if node.get("selectable", node.get("kind") != "road")]
    return {
        "nodes": len(graph["nodes"]),
        "road_nodes": sum(1 for node in graph["nodes"] if node.get("kind") == "road"),
        "selectable_nodes": len(selectable),
        "edges": len(graph["edges"]),
        "components": sorted([len(component) for component in components], reverse=True),
        "bad_edges": len(bad_edges),
        "unreachable_poi": [
            node["id"]
            for node in selectable
            if not adjacency.get(node["id"])
        ],
    }


def connect_components(nodes: list[dict], edges: list[dict]) -> None:
    node_map = {node["id"]: node for node in nodes}
    adjacency = {node_id: set() for node_id in node_map}
    for edge in edges:
        adjacency[edge["from"]].add(edge["to"])
        adjacency[edge["to"]].add(edge["from"])

    def components() -> list[list[str]]:
        seen = set()
        result = []
        for node_id in node_map:
            if node_id in seen:
                continue
            stack = [node_id]
            seen.add(node_id)
            component = []
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in adjacency[current]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            result.append(component)
        return sorted(result, key=len, reverse=True)

    comps = components()
    if not comps:
        return

    main = set(comps[0])
    for comp in comps[1:]:
        best = None
        for from_id in comp:
            from_node = node_map[from_id]
            for to_id in main:
                to_node = node_map[to_id]
                distance = haversine(from_node["lat"], from_node["lon"], to_node["lat"], to_node["lon"])
                if best is None or distance < best[0]:
                    best = (distance, from_id, to_id)
        if best is None:
            continue
        distance, from_id, to_id = best
        from_node = node_map[from_id]
        to_node = node_map[to_id]
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": round(distance, 1),
            "congestion": 0.78,
            "walk": True,
            "bike": True,
            "geometry": [
                [round(from_node["lat"], 7), round(from_node["lon"], 7)],
                [round(to_node["lat"], 7), round(to_node["lon"], 7)],
            ],
            "source": "manual_component_connector",
        })
        adjacency[from_id].add(to_id)
        adjacency[to_id].add(from_id)
        main.update(comp)


def main() -> None:
    graph = build_curated_graph()
    stats = validate(graph)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"written: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
