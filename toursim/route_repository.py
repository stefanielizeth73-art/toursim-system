import json
import os
from dataclasses import dataclass

from .filesystem import file_signature
from .route_algorithms import get_selectable_nodes


@dataclass
class RouteRepositoryConfig:
    route_graphs_dir: str
    manual_graph_file: str
    default_place_id: str = "xmu_manual"
    manual_place_id: str = "xmu_manual"
    route_graph_cache: dict = None


@dataclass
class RouteRepositoryServices:
    collector_source_signature: object
    ensure_manual_graph_current: object
    load_collector_edges: object
    load_collector_links: object


_config = RouteRepositoryConfig("", "", route_graph_cache={})
_services = None


def configure_route_repository(config, services):
    global _config, _services, ROUTE_GRAPHS_DIR, XMU_MANUAL_GRAPH_FILE, DEFAULT_PLACE_ID, XMU_MANUAL_PLACE_ID, ROUTE_GRAPH_CACHE
    _config = config
    _services = services
    ROUTE_GRAPHS_DIR = config.route_graphs_dir
    XMU_MANUAL_GRAPH_FILE = config.manual_graph_file
    DEFAULT_PLACE_ID = config.default_place_id
    XMU_MANUAL_PLACE_ID = config.manual_place_id
    ROUTE_GRAPH_CACHE = config.route_graph_cache if config.route_graph_cache is not None else {}


def _require_services():
    if _services is None:
        raise RuntimeError("Route repository services have not been configured")
    return _services


def collector_source_signature(*args, **kwargs):
    return _require_services().collector_source_signature(*args, **kwargs)


def ensure_manual_graph_current(*args, **kwargs):
    return _require_services().ensure_manual_graph_current(*args, **kwargs)


def load_collector_edges(*args, **kwargs):
    return _require_services().load_collector_edges(*args, **kwargs)


def load_collector_links(*args, **kwargs):
    return _require_services().load_collector_links(*args, **kwargs)


ROUTE_GRAPHS_DIR = _config.route_graphs_dir
XMU_MANUAL_GRAPH_FILE = _config.manual_graph_file
DEFAULT_PLACE_ID = _config.default_place_id
XMU_MANUAL_PLACE_ID = _config.manual_place_id
ROUTE_GRAPH_CACHE = _config.route_graph_cache

def get_route_graph_path(place_id=None):
    if place_id:
        safe_place_id = "".join(ch for ch in place_id if ch.isalnum() or ch in ("_", "-"))
        graph_path = os.path.join(ROUTE_GRAPHS_DIR, f"{safe_place_id}.json")
        if os.path.exists(graph_path):
            return graph_path
    return XMU_MANUAL_GRAPH_FILE

def get_route_graph_version(place_id=None):
    signature = file_signature(get_route_graph_path(place_id or DEFAULT_PLACE_ID))
    if not signature:
        return "missing"
    return f"{signature[0]}-{signature[1]}"

def enforce_walk_only_snap_link(edge):
    if (edge or {}).get("source") == "manual_collector_link":
        edge["walk"] = True
        edge["bike"] = False
    return edge

def load_route_graph(place_id=None):
    effective_place_id = place_id or DEFAULT_PLACE_ID
    graph_path = get_route_graph_path(effective_place_id)
    graph_signature = file_signature(graph_path)
    cached = ROUTE_GRAPH_CACHE.get(effective_place_id)
    if effective_place_id == XMU_MANUAL_PLACE_ID:
        current_source_digest = collector_source_signature().get("digest")
        if (
            cached
            and cached.get("path") == graph_path
            and cached.get("signature") == graph_signature
            and cached.get("source_digest") == current_source_digest
        ):
            return cached["graph"]
        ensure_manual_graph_current()
        graph_signature = file_signature(graph_path)
        cached = ROUTE_GRAPH_CACHE.get(effective_place_id)
    elif cached and cached.get("path") == graph_path and cached.get("signature") == graph_signature:
        return cached["graph"]

    if not os.path.exists(graph_path):
        return {"default_start": "", "nodes": [], "edges": [], "node_map": {}, "adjacency": {}}

    with open(graph_path, "r", encoding="utf-8-sig") as f:
        graph = json.load(f)

    graph.setdefault("place_id", effective_place_id)
    graph.setdefault("place_name", "当前路线图")
    graph.setdefault("bounds", [])
    graph.setdefault("campus_bounds", graph.get("bounds", []))
    graph.setdefault("center", [])
    graph.setdefault("amap_center", [])
    graph.setdefault("amap_bounds", [])
    graph.setdefault("facility_parent_place", graph.get("place_id", effective_place_id))
    graph.setdefault("image_overlay", None)
    if effective_place_id == XMU_MANUAL_PLACE_ID:
        graph["default_start"] = ""

    node_map = {node["id"]: node for node in graph.get("nodes", [])}
    adjacency = {node_id: [] for node_id in node_map}

    for edge in graph.get("edges", []):
        if effective_place_id == XMU_MANUAL_PLACE_ID:
            enforce_walk_only_snap_link(edge)
        start = edge["from"]
        end = edge["to"]
        if start not in adjacency or end not in adjacency:
            continue
        if not edge.get("geometry"):
            edge["geometry"] = [
                [node_map[start].get("lat"), node_map[start].get("lon")],
                [node_map[end].get("lat"), node_map[end].get("lon")],
            ]
        if not edge.get("amap_geometry"):
            edge["amap_geometry"] = [
                [node_map[start].get("amap_lng", node_map[start].get("lon")), node_map[start].get("amap_lat", node_map[start].get("lat"))],
                [node_map[end].get("amap_lng", node_map[end].get("lon")), node_map[end].get("amap_lat", node_map[end].get("lat"))],
            ]
        adjacency[start].append({**edge, "neighbor": end})
        adjacency[end].append({
            **edge,
            "from": end,
            "to": start,
            "geometry": list(reversed(edge["geometry"])),
            "amap_geometry": list(reversed(edge.get("amap_geometry", []))),
            "neighbor": start
        })

    graph["node_map"] = node_map
    graph["adjacency"] = adjacency
    graph["_cache_key"] = (graph_path, graph_signature)
    ROUTE_GRAPH_CACHE[effective_place_id] = {
        "path": graph_path,
        "signature": graph_signature,
        "source_digest": (graph.get("collector_source_signature") or {}).get("digest"),
        "graph": graph,
    }
    return graph

def road_display_edges_for_map(graph):
    if graph.get("place_id") != XMU_MANUAL_PLACE_ID:
        return []
    display_edges = []
    for edge in load_collector_edges():
        geometry = edge.get("amap_geometry") or []
        if len(geometry) < 2:
            continue
        display_edges.append({
            "id": edge.get("id", ""),
            "name": edge.get("name", ""),
            "road_type": edge.get("road_type", ""),
            "walk": edge.get("walk", True),
            "bike": edge.get("bike", True),
            "amap_geometry": geometry,
        })
    for link in load_collector_links():
        if link.get("kind") != "road_road":
            continue
        geometry = link.get("amap_geometry") or []
        if len(geometry) < 2:
            continue
        display_edges.append({
            "id": link.get("id", ""),
            "name": link.get("name", ""),
            "kind": link.get("kind", ""),
            "road_type": "snap_link",
            "walk": True,
            "bike": False,
            "amap_geometry": geometry,
            "source": link.get("source", "manual_collector_link"),
        })
    return display_edges

def serialize_graph_for_map(graph, include_road_nodes=True, compact_edges=False):
    nodes = graph.get("nodes", []) if include_road_nodes else get_selectable_nodes(graph)
    edges = graph.get("edges", [])
    if compact_edges:
        compacted_edges = []
        for edge in edges:
            compact_edge = {
                "from": edge.get("from", ""),
                "to": edge.get("to", ""),
                "distance": edge.get("distance", 0),
                "amap_geometry": edge.get("amap_geometry", []),
            }
            if not compact_edge["amap_geometry"]:
                compact_edge["geometry"] = edge.get("geometry", [])
            compacted_edges.append(compact_edge)
        edges = compacted_edges
    return {
        "place_id": graph.get("place_id", DEFAULT_PLACE_ID),
        "place_name": graph.get("place_name", "当前路线图"),
        "default_start": graph.get("default_start", ""),
        "center": graph.get("center", []),
        "amap_center": graph.get("amap_center", []),
        "bounds": graph.get("bounds", []),
        "campus_bounds": graph.get("campus_bounds", graph.get("bounds", [])),
        "amap_bounds": graph.get("amap_bounds", []),
        "image_overlay": graph.get("image_overlay"),
        "nodes": nodes,
        "edges": edges,
        "road_display_edges": road_display_edges_for_map(graph),
        "selectable_nodes": get_selectable_nodes(graph),
    }
