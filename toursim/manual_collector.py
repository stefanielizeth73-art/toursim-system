import re

from .geo import haversine_amap, polyline_distance


XMU_MANUAL_PLACE_ID = "xmu_manual"


def default_collector_meta():
    return {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": "厦门大学翔安校区（手动采集图）",
        "default_start": "",
        "center": [24.6095855, 118.3099666],
        "amap_center": [118.3099666, 24.6095855],
        "campus_bounds": [[24.6017940, 118.2991356], [24.6172287, 118.3199674]],
        "amap_bounds": [[118.2991356, 24.6017940], [118.3199674, 24.6172287]],
        "facility_parent_place": "xmu_manual",
        "source": "manual_collector",
    }

def normalize_collector_point(payload):
    lng = payload.get("amap_lng", payload.get("lng", payload.get("lon")))
    lat = payload.get("amap_lat", payload.get("lat"))
    if lng is None or lat is None:
        raise ValueError("缺少经纬度")
    return [round(float(lng), 7), round(float(lat), 7)]

def collector_node_point(node):
    return [float(node["amap_lng"]), float(node["amap_lat"])]

def nearest_collector_node(point, node_map):
    if not node_map:
        return None
    return min(node_map, key=lambda node_id: haversine_amap(point, collector_node_point(node_map[node_id])))

def valid_collector_node_id(node_id, node_map):
    node_id = str(node_id or "").strip()
    return node_id if node_id in node_map else ""

def collector_node_id(name, existing_count):
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in (name or "node")).strip("_")
    return f"route_point_{base or 'node'}_{existing_count + 1:03d}"

def normalize_tags(value):
    if isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = str(value or "").replace("，", ",").replace("、", ",").split(",")
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]

def normalize_collector_node(payload, existing_count=0):
    point = normalize_collector_point(payload)
    name = str(payload.get("name") or f"采集点{existing_count + 1}").strip()
    kind = str(payload.get("kind") or "building").strip()
    if kind not in ("gate", "building", "teaching", "library", "canteen", "dorm", "sports", "service", "facility", "landmark", "road"):
        kind = "building"
    node_id = str(payload.get("id") or collector_node_id(name, existing_count)).strip()
    return {
        "id": node_id,
        "name": name,
        "category": str(payload.get("category") or "手动采集点").strip(),
        "tags": normalize_tags(payload.get("tags")),
        "role": "road" if kind == "road" else "route_point",
        "kind": kind,
        "lat": point[1],
        "lon": point[0],
        "amap_lng": point[0],
        "amap_lat": point[1],
        "selectable": kind != "road",
        "source": "manual_collector_node",
    }

def normalize_collector_edge(payload, nodes, existing_count=0):
    geometry = payload.get("amap_geometry") or []
    if len(geometry) < 2:
        raise ValueError("道路至少需要两个采样点")
    points = [[round(float(point[0]), 7), round(float(point[1]), 7)] for point in geometry]
    node_map = {node["id"]: node for node in nodes}
    from_id = valid_collector_node_id(payload.get("from"), node_map)
    to_id = valid_collector_node_id(payload.get("to"), node_map)
    poi_links = []
    for link in payload.get("poi_links") or []:
        try:
            index = int(link.get("index", -1))
        except (TypeError, ValueError):
            continue
        poi_id = valid_collector_node_id(link.get("poi"), node_map)
        if poi_id and 0 <= index < len(points):
            poi_links.append({"index": index, "poi": poi_id})
    road_links = []
    for link in payload.get("road_links") or []:
        try:
            index = int(link.get("index", -1))
            target_index = int(link.get("target_index", -1))
        except (TypeError, ValueError):
            continue
        target_edge = str(link.get("edge") or "").strip()
        if target_edge and 0 <= index < len(points) and target_index >= 0:
            road_links.append({"index": index, "edge": target_edge, "target_index": target_index})
    edge_id = str(payload.get("id") or collector_edge_id(existing_count)).strip()
    try:
        congestion = float(payload.get("congestion", 0.82))
    except (TypeError, ValueError):
        congestion = 0.82
    congestion = min(max(congestion, 0.1), 1.0)
    return {
        "id": edge_id,
        "name": str(payload.get("name") or f"手动道路{existing_count + 1}").strip(),
        "road_type": str(payload.get("road_type") or "walkway").strip(),
        "from": from_id,
        "to": to_id,
        "poi_links": poi_links,
        "road_links": road_links,
        "amap_geometry": points,
        "distance": round(polyline_distance(points), 1),
        "walk": bool(payload.get("walk", True)),
        "bike": bool(payload.get("bike", True)),
        "congestion": congestion,
        "source": "manual_collector_edge",
    }

def collector_link_id(existing_count):
    return f"link_{existing_count + 1:04d}"

def collector_edge_id(existing_count):
    return f"edge_{existing_count + 1:04d}"

def collector_facility_id(existing_count):
    return f"facility_{existing_count + 1:04d}"

def next_prefixed_collector_id(items, prefix, width=4):
    existing_ids = {str(item.get("id") or "") for item in items}
    max_number = 0
    id_pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for item_id in existing_ids:
        match = id_pattern.match(item_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    next_number = max_number + 1
    while True:
        candidate = f"{prefix}_{next_number:0{width}d}"
        if candidate not in existing_ids:
            return candidate
        next_number += 1

def next_collector_node_id(name, nodes):
    existing_ids = {str(item.get("id") or "") for item in nodes}
    count = len(nodes)
    while True:
        candidate = collector_node_id(name, count)
        if candidate not in existing_ids:
            return candidate
        count += 1

def normalize_road_ref(payload, edge_map):
    edge_id = str((payload or {}).get("edge") or (payload or {}).get("edge_id") or "").strip()
    try:
        point_index = int((payload or {}).get("point_index", (payload or {}).get("target_index", -1)))
    except (TypeError, ValueError):
        raise ValueError("道路端点索引无效")
    edge = edge_map.get(edge_id)
    if not edge:
        raise ValueError("道路端点所属道路不存在")
    geometry = edge.get("amap_geometry") or []
    if point_index < 0 or point_index >= len(geometry):
        raise ValueError("道路端点索引超出范围")
    return {"edge": edge_id, "point_index": point_index}

def collector_ref_point(ref, node_map, edge_map):
    ref_type = ref.get("type")
    if ref_type == "poi":
        node = node_map.get(ref.get("id"))
        if not node:
            return None
        return collector_node_point(node)
    if ref_type == "road":
        edge = edge_map.get(ref.get("edge"))
        if not edge:
            return None
        index = ref.get("point_index")
        geometry = edge.get("amap_geometry") or []
        if not isinstance(index, int) or index < 0 or index >= len(geometry):
            return None
        point = geometry[index]
        return [float(point[0]), float(point[1])]
    return None

def normalize_collector_link(payload, nodes, edges, existing_count=0):
    node_map = {node["id"]: node for node in nodes}
    edge_map = {edge["id"]: edge for edge in edges}
    raw_a = payload.get("a") or payload.get("from") or {}
    raw_b = payload.get("b") or payload.get("to") or {}

    def normalize_ref(raw):
        ref_type = str(raw.get("type") or "").strip()
        if ref_type == "poi":
            poi_id = valid_collector_node_id(raw.get("id") or raw.get("poi"), node_map)
            if not poi_id:
                raise ValueError("POI 端点不存在")
            return {"type": "poi", "id": poi_id}
        if ref_type == "road":
            road_ref = normalize_road_ref(raw, edge_map)
            return {"type": "road", **road_ref}
        raise ValueError("吸附端点类型无效")

    a_ref = normalize_ref(raw_a)
    b_ref = normalize_ref(raw_b)
    ref_types = sorted([a_ref["type"], b_ref["type"]])
    if ref_types == ["poi", "poi"]:
        raise ValueError("POI 与 POI 不能直接吸附，请选择 POI 与道路节点")
    if ref_types == ["poi", "road"]:
        link_kind = "poi_road"
    elif ref_types == ["road", "road"]:
        link_kind = "road_road"
    else:
        raise ValueError("仅支持 POI-道路节点或道路节点-道路节点吸附")

    point_a = collector_ref_point(a_ref, node_map, edge_map)
    point_b = collector_ref_point(b_ref, node_map, edge_map)
    if not point_a or not point_b:
        raise ValueError("吸附端点坐标无效")
    if haversine_amap(point_a, point_b) < 0.2:
        raise ValueError("两个端点过近，无需新增吸附边")

    link_id = str(payload.get("id") or collector_link_id(existing_count)).strip()
    try:
        congestion = float(payload.get("congestion", 0.82))
    except (TypeError, ValueError):
        congestion = 0.82
    congestion = min(max(congestion, 0.1), 1.0)
    return {
        "id": link_id,
        "kind": link_kind,
        "a": a_ref,
        "b": b_ref,
        "amap_geometry": [[round(point_a[0], 7), round(point_a[1], 7)], [round(point_b[0], 7), round(point_b[1], 7)]],
        "distance": round(polyline_distance([point_a, point_b]), 1),
        # Snap links are stitching connectors, not real rideable roads.
        "walk": True,
        "bike": False,
        "congestion": congestion,
        "source": "manual_collector_link",
    }
