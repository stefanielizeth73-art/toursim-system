import hashlib
import json
import os
from dataclasses import dataclass

from .filesystem import files_signature, read_json_file, write_json_atomic
from .geo import haversine_amap, polyline_distance
from .manual_collector import (
    collector_facility_id,
    collector_node_point,
    default_collector_meta,
    normalize_collector_edge,
    normalize_collector_link,
    normalize_collector_node,
    normalize_collector_point,
    normalize_tags,
)
from .route_algorithms import is_road_graph_node, nearest_graph_node_id


@dataclass
class CollectorRepositoryConfig:
    collector_dir: str
    nodes_file: str
    edges_file: str
    links_file: str
    facilities_file: str
    meta_file: str
    source_files: list
    manual_graph_file: str
    manual_place_id: str
    default_place_id: str
    road_snap_meters: float
    signature_cache: dict


@dataclass
class CollectorRepositoryServices:
    collector_source_summary: object
    invalidate_facilities_cache: object
    invalidate_route_graph_cache: object
    load_facilities: object


_config = None
_services = None

XMU_COLLECTOR_DIR = ""
XMU_COLLECTOR_NODES_FILE = ""
XMU_COLLECTOR_EDGES_FILE = ""
XMU_COLLECTOR_LINKS_FILE = ""
XMU_COLLECTOR_FACILITIES_FILE = ""
XMU_COLLECTOR_META_FILE = ""
XMU_COLLECTOR_SOURCE_FILES = []
XMU_MANUAL_GRAPH_FILE = ""
XMU_MANUAL_PLACE_ID = "xmu_manual"
DEFAULT_PLACE_ID = "xmu_manual"
XMU_ROAD_SNAP_METERS = 0
COLLECTOR_SIGNATURE_CACHE = {}


def configure_collector_repository(config, services):
    global _config, _services
    global XMU_COLLECTOR_DIR, XMU_COLLECTOR_NODES_FILE, XMU_COLLECTOR_EDGES_FILE
    global XMU_COLLECTOR_LINKS_FILE, XMU_COLLECTOR_FACILITIES_FILE, XMU_COLLECTOR_META_FILE
    global XMU_COLLECTOR_SOURCE_FILES, XMU_MANUAL_GRAPH_FILE, XMU_MANUAL_PLACE_ID
    global DEFAULT_PLACE_ID, XMU_ROAD_SNAP_METERS, COLLECTOR_SIGNATURE_CACHE
    _config = config
    _services = services
    XMU_COLLECTOR_DIR = config.collector_dir
    XMU_COLLECTOR_NODES_FILE = config.nodes_file
    XMU_COLLECTOR_EDGES_FILE = config.edges_file
    XMU_COLLECTOR_LINKS_FILE = config.links_file
    XMU_COLLECTOR_FACILITIES_FILE = config.facilities_file
    XMU_COLLECTOR_META_FILE = config.meta_file
    XMU_COLLECTOR_SOURCE_FILES = config.source_files
    XMU_MANUAL_GRAPH_FILE = config.manual_graph_file
    XMU_MANUAL_PLACE_ID = config.manual_place_id
    DEFAULT_PLACE_ID = config.default_place_id
    XMU_ROAD_SNAP_METERS = config.road_snap_meters
    COLLECTOR_SIGNATURE_CACHE = config.signature_cache


def _require_services():
    if _services is None:
        raise RuntimeError("collector repository services have not been configured")
    return _services


def collector_source_summary():
    return _require_services().collector_source_summary()


def invalidate_facilities_cache():
    return _require_services().invalidate_facilities_cache()


def invalidate_route_graph_cache(place_id=None):
    return _require_services().invalidate_route_graph_cache(place_id)


def load_facilities(parent_place=None):
    return _require_services().load_facilities(parent_place)


def ensure_collector_files():
    os.makedirs(XMU_COLLECTOR_DIR, exist_ok=True)
    read_json_file(XMU_COLLECTOR_NODES_FILE, {"nodes": []})
    read_json_file(XMU_COLLECTOR_EDGES_FILE, {"edges": []})
    read_json_file(XMU_COLLECTOR_LINKS_FILE, {"links": []})
    read_json_file(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": []})
    read_json_file(XMU_COLLECTOR_META_FILE, default_collector_meta())


def load_collector_nodes():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_NODES_FILE, {"nodes": []}).get("nodes", [])


def load_collector_edges():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_EDGES_FILE, {"edges": []}).get("edges", [])


def load_collector_links():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_LINKS_FILE, {"links": []}).get("links", [])


def load_collector_facilities():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": []}).get("facilities", [])


def load_collector_meta():
    ensure_collector_files()
    meta = default_collector_meta()
    meta.update(read_json_file(XMU_COLLECTOR_META_FILE, meta))
    return meta




























def nearest_collector_road_node_id(point):
    best = None
    for edge in load_collector_edges():
        edge_id = str(edge.get("id") or "")
        for index, road_point in enumerate(edge.get("amap_geometry") or []):
            if not road_point or len(road_point) < 2:
                continue
            distance = haversine_amap(point, [float(road_point[0]), float(road_point[1])])
            if best is None or distance < best[0]:
                best = (distance, edge_id, index)
    if not best:
        return ""
    return f"road_{best[1]}_{best[2]:03d}"


def empty_manual_graph(meta=None):
    meta = {**default_collector_meta(), **(meta or load_collector_meta())}
    graph = {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "source": "manual_collector",
        "default_start": "",
        "center": meta.get("center", [24.6095855, 118.3099666]),
        "amap_center": meta.get("amap_center", [118.3099666, 24.6095855]),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "facility_parent_place": meta.get("facility_parent_place", XMU_MANUAL_PLACE_ID),
        "image_overlay": None,
        "nodes": [],
        "edges": [],
    }
    graph["collector_source_signature"] = collector_source_signature()
    graph["collector_source_summary"] = collector_source_summary()
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    invalidate_route_graph_cache(XMU_MANUAL_PLACE_ID)
    return graph


def collector_source_signature():
    ensure_collector_files()
    source_files_signature = files_signature(XMU_COLLECTOR_SOURCE_FILES)
    if source_files_signature == COLLECTOR_SIGNATURE_CACHE.get("source_files_signature"):
        cached = COLLECTOR_SIGNATURE_CACHE.get("signature")
        if cached:
            return cached

    digest = hashlib.sha256()
    files = []
    for file_path in XMU_COLLECTOR_SOURCE_FILES:
        name = os.path.basename(file_path)
        digest.update(name.encode("utf-8"))
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError:
            content = b""
        digest.update(str(len(content)).encode("ascii"))
        digest.update(content)
        files.append({"name": name, "bytes": len(content)})
    signature = {
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "files": files,
    }
    COLLECTOR_SIGNATURE_CACHE["source_files_signature"] = source_files_signature
    COLLECTOR_SIGNATURE_CACHE["signature"] = signature
    return signature


def collector_sources_are_newer_than_graph():
    if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
        return True
    graph_mtime = os.path.getmtime(XMU_MANUAL_GRAPH_FILE)
    return any(os.path.exists(file_path) and os.path.getmtime(file_path) > graph_mtime for file_path in XMU_COLLECTOR_SOURCE_FILES)


def manual_graph_needs_rebuild():
    if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
        return True
    try:
        graph = read_json_file(XMU_MANUAL_GRAPH_FILE, {})
    except (OSError, json.JSONDecodeError):
        return True
    graph_signature = (graph.get("collector_source_signature") or {}).get("digest")
    current_signature = collector_source_signature().get("digest")
    if graph_signature:
        return graph_signature != current_signature
    return collector_sources_are_newer_than_graph()


def ensure_manual_graph_current():
    if manual_graph_needs_rebuild():
        return rebuild_manual_graph()
    return None


def ensure_route_graph_current(place_id):
    if (place_id or DEFAULT_PLACE_ID) == XMU_MANUAL_PLACE_ID:
        ensure_manual_graph_current()






def resolve_facility_nearest_node(facility, graph, road_only=True):
    node_map = graph.get("node_map", {})
    nearest_node = str((facility or {}).get("nearest_node") or "").strip()
    node = node_map.get(nearest_node)
    if node and (not road_only or is_road_graph_node(node)):
        return nearest_node

    try:
        point = [
            float((facility or {}).get("amap_lng", (facility or {}).get("lon"))),
            float((facility or {}).get("amap_lat", (facility or {}).get("lat"))),
        ]
    except (TypeError, ValueError):
        return nearest_node if node else ""

    if road_only:
        road_node = nearest_graph_node_id(point, graph, road_only=True)
        if road_node:
            return road_node
    return nearest_graph_node_id(point, graph)


def facilities_for_map(graph):
    parent_place = graph.get("facility_parent_place", graph.get("place_id"))
    node_map = graph.get("node_map", {})
    records = []
    for facility in load_facilities(parent_place):
        item = facility.copy()
        nearest_node = resolve_facility_nearest_node(item, graph, road_only=True)
        if nearest_node:
            item["nearest_node"] = nearest_node
            node = node_map.get(nearest_node)
            if node:
                item["nearest_lng"] = node.get("amap_lng", node.get("lon"))
                item["nearest_lat"] = node.get("amap_lat", node.get("lat"))
        records.append(item)
    return records


def normalize_collector_facility(payload, existing_count=0, graph=None):
    point = normalize_collector_point(payload)
    facility_type = str(payload.get("type") or payload.get("category") or "服务设施").strip()
    cuisine = str(payload.get("cuisine") or payload.get("food_category") or "").strip()
    facility_id = str(payload.get("id") or collector_facility_id(existing_count)).strip()
    nearest_node = str(payload.get("nearest_node") or "").strip()
    if graph:
        nearest_node = resolve_facility_nearest_node(
            {**payload, "nearest_node": nearest_node, "amap_lng": point[0], "amap_lat": point[1]},
            graph,
            road_only=True,
        )
    return {
        "id": facility_id,
        "name": str(payload.get("name") or f"场所{existing_count + 1}").strip(),
        "type": facility_type,
        "cuisine": cuisine,
        "tags": normalize_tags(payload.get("tags") or facility_type),
        "parent_place": XMU_MANUAL_PLACE_ID,
        "nearest_node": nearest_node,
        "amap_lng": point[0],
        "amap_lat": point[1],
        "description": str(payload.get("description") or "手动采集场所").strip(),
        "source": "manual_collector_facility",
    }








def rebuild_manual_graph():
    ensure_collector_files()
    meta = load_collector_meta()
    collector_nodes = load_collector_nodes()
    collector_edges = load_collector_edges()
    collector_links = load_collector_links()
    nodes = []
    node_map = {}
    edges = []
    edge_seen = set()
    road_node_ids = []
    point_node_lookup = {}

    for node in collector_nodes:
        normalized = normalize_collector_node(node, len(nodes))
        nodes.append(normalized)
        node_map[normalized["id"]] = normalized

    def nearest_road_node(point):
        if XMU_ROAD_SNAP_METERS <= 0:
            return ""
        best = None
        for node_id in road_node_ids:
            node = node_map.get(node_id)
            if not node:
                continue
            distance = haversine_amap(point, collector_node_point(node))
            if distance <= XMU_ROAD_SNAP_METERS and (not best or distance < best[1]):
                best = (node_id, distance)
        return best[0] if best else ""

    def add_road_node(point, edge_id, index):
        reused_id = nearest_road_node(point)
        if reused_id:
            return reused_id
        node_id = f"road_{edge_id}_{index:03d}"
        if node_id in node_map:
            return node_id
        node = {
            "id": node_id,
            "name": f"道路节点{edge_id}-{index}",
            "category": "道路折点",
            "kind": "road",
            "lat": round(float(point[1]), 7),
            "lon": round(float(point[0]), 7),
            "amap_lng": round(float(point[0]), 7),
            "amap_lat": round(float(point[1]), 7),
            "selectable": False,
            "source": "manual_collector_road_node",
        }
        nodes.append(node)
        node_map[node_id] = node
        road_node_ids.append(node_id)
        return node_id

    def add_graph_edge(from_id, to_id, segment, edge_payload):
        if not from_id or not to_id or from_id == to_id:
            return
        key = tuple(sorted((from_id, to_id)))
        if key in edge_seen:
            return
        edge_seen.add(key)
        distance = round(max(polyline_distance(segment), 1), 1)
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": distance,
            "congestion": edge_payload.get("congestion", 0.82),
            "road_type": edge_payload.get("road_type", "walkway"),
            "walk": edge_payload.get("walk", True),
            "bike": edge_payload.get("bike", True),
            "geometry": [[point[1], point[0]] for point in segment],
            "amap_geometry": segment,
            "source": edge_payload.get("source", "manual_collector_edge"),
        })

    for raw_edge in collector_edges:
        try:
            edge = normalize_collector_edge(raw_edge, collector_nodes, len(edges))
        except (TypeError, ValueError):
            continue
        points = edge["amap_geometry"]
        chain = []
        if edge["from"] in node_map:
            chain.append(edge["from"])
        for index, point in enumerate(points):
            chain.append(add_road_node(point, edge["id"], index))
        if edge["to"] in node_map:
            chain.append(edge["to"])
        compact_chain = []
        for node_id in chain:
            if node_id and (not compact_chain or compact_chain[-1] != node_id):
                compact_chain.append(node_id)
        chain = compact_chain
        all_points = [collector_node_point(node_map[node_id]) for node_id in chain]
        for index, (from_id, to_id) in enumerate(zip(chain, chain[1:])):
            add_graph_edge(from_id, to_id, [all_points[index], all_points[index + 1]], edge)
        point_node_ids = [add_road_node(point, edge["id"], index) for index, point in enumerate(points)]
        for index, node_id in enumerate(point_node_ids):
            point_node_lookup[(edge["id"], index)] = node_id
        for link in edge.get("poi_links", []):
            poi_id = link.get("poi")
            point_index = link.get("index")
            if poi_id not in node_map or not isinstance(point_index, int) or point_index >= len(point_node_ids):
                continue
            road_id = point_node_ids[point_index]
            add_graph_edge(poi_id, road_id, [collector_node_point(node_map[poi_id]), collector_node_point(node_map[road_id])], edge)
        for link in edge.get("road_links", []):
            point_index = link.get("index")
            target_edge_id = link.get("edge")
            target_index = link.get("target_index")
            if not isinstance(point_index, int) or point_index >= len(point_node_ids):
                continue
            target_raw = next((item for item in collector_edges if str(item.get("id") or "") == target_edge_id), None)
            if not target_raw:
                continue
            target_points = target_raw.get("amap_geometry") or []
            if not isinstance(target_index, int) or target_index < 0 or target_index >= len(target_points):
                continue
            from_id = point_node_ids[point_index]
            to_id = add_road_node(target_points[target_index], target_edge_id, target_index)
            add_graph_edge(from_id, to_id, [collector_node_point(node_map[from_id]), collector_node_point(node_map[to_id])], edge)

    normalized_edge_map = {}
    for raw_edge in collector_edges:
        try:
            edge = normalize_collector_edge(raw_edge, collector_nodes, len(edges))
        except (TypeError, ValueError):
            continue
        normalized_edge_map[edge["id"]] = edge

    def graph_node_for_ref(ref):
        if ref.get("type") == "poi":
            return ref.get("id") if ref.get("id") in node_map else ""
        if ref.get("type") == "road":
            edge_id = ref.get("edge")
            index = ref.get("point_index")
            node_id = point_node_lookup.get((edge_id, index))
            if node_id:
                return node_id
            edge = normalized_edge_map.get(edge_id)
            geometry = edge.get("amap_geometry") if edge else []
            if isinstance(index, int) and geometry and 0 <= index < len(geometry):
                node_id = add_road_node(geometry[index], edge_id, index)
                point_node_lookup[(edge_id, index)] = node_id
                return node_id
        return ""

    for raw_link in collector_links:
        try:
            link = normalize_collector_link(raw_link, collector_nodes, list(normalized_edge_map.values()), len(edges))
        except (TypeError, ValueError):
            continue
        from_id = graph_node_for_ref(link["a"])
        to_id = graph_node_for_ref(link["b"])
        add_graph_edge(from_id, to_id, link["amap_geometry"], link)

    selectable = [node for node in nodes if node.get("selectable")]
    meta["default_start"] = ""

    graph = {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "source": "manual_collector",
        "default_start": meta.get("default_start", ""),
        "center": meta.get("center", [24.6095855, 118.3099666]),
        "amap_center": meta.get("amap_center", [118.3099666, 24.6095855]),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "facility_parent_place": meta.get("facility_parent_place", XMU_MANUAL_PLACE_ID),
        "image_overlay": None,
        "nodes": nodes,
        "edges": edges,
    }
    write_json_atomic(XMU_COLLECTOR_META_FILE, meta)
    COLLECTOR_SIGNATURE_CACHE["source_files_signature"] = None
    graph["collector_source_signature"] = collector_source_signature()
    graph["collector_source_summary"] = collector_source_summary()
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    invalidate_route_graph_cache(XMU_MANUAL_PLACE_ID)
    invalidate_facilities_cache()
    return graph
