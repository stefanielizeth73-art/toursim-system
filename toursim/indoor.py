import heapq
import json
import math
import re

from .search import normalize_search_text


INDOOR_BUILDING_TYPES = {"building", "teaching", "library", "dorm", "canteen"}
INDOOR_DEFAULT_START = "gate_1f"
INDOOR_DEFAULT_END = "room_402"
INDOOR_VERTICAL_MODES = {"auto", "elevator", "stairs"}
INDOOR_FLOOR_WIDTH = 1672
INDOOR_FLOOR_HEIGHT = 941
INDOOR_FLOOR_ASSETS = {
    1: "indoor_floors/floor_1f.png",
    2: "indoor_floors/floor_2f.png",
    3: "indoor_floors/floor_3f.png",
    4: "indoor_floors/floor_4f.png",
}
INDOOR_VERTICAL_CORES = {
    "west_elevator": {"type": "elevator", "label": "西电梯"},
    "east_elevator": {"type": "elevator", "label": "东电梯"},
    "northwest_stairs": {"type": "stairs", "label": "西北步梯"},
    "east_stairs": {"type": "stairs", "label": "东侧步梯"},
}


def indoor_edge_weight(edge, vertical_mode="auto"):
    # 室内导航把楼层内走廊、电梯、楼梯统一看成图的边。
    # vertical_mode用于过滤垂直交通方式：只坐电梯时不走楼梯，只走楼梯时不走电梯。
    mode = edge.get("mode", "walk")
    if vertical_mode == "elevator" and mode == "stairs":
        return None
    if vertical_mode == "stairs" and mode == "elevator":
        return None
    return float(edge.get("distance", 0))

def indoor_shortest_path(graph, start, end, vertical_mode="auto"):
    if start not in graph["node_map"] or end not in graph["node_map"]:
        return None

    # 与室外路线规划相同，这里复用堆优化Dijkstra：
    # distances记录起点到每个室内节点的最短距离，previous用于最终回溯路径。
    distances = {node_id: float("inf") for node_id in graph["node_map"]}
    previous = {}
    distances[start] = 0
    # heap按当前累计距离排序，每次优先扩展距离最短的节点。
    heap = [(0, start)]

    while heap:
        current_distance, current = heapq.heappop(heap)
        if current == end:
            break
        # 同一节点可能多次入堆；如果弹出的是旧距离，就跳过，保证松弛逻辑正确。
        if current_distance > distances[current]:
            continue
        for edge in graph["adjacency"].get(current, []):
            weight = indoor_edge_weight(edge, vertical_mode=vertical_mode)
            if weight is None:
                continue
            neighbor = edge["neighbor"]
            new_distance = current_distance + weight
            if new_distance < distances[neighbor]:
                # 松弛操作：找到更短的室内路径后，更新距离和前驱边。
                distances[neighbor] = new_distance
                previous[neighbor] = (current, edge, weight)
                heapq.heappush(heap, (new_distance, neighbor))

    if distances[end] == float("inf"):
        return None

    path_ids = [end]
    edges = []
    cursor = end
    while cursor != start:
        # 从终点沿previous反向回溯，得到经过的房间、走廊点、电梯/楼梯节点。
        previous_node, edge, weight = previous[cursor]
        edges.append({**edge, "weight": weight})
        cursor = previous_node
        path_ids.append(cursor)
    path_ids.reverse()
    edges.reverse()
    return {
        "path_ids": path_ids,
        "path_nodes": [graph["node_map"][node_id] for node_id in path_ids],
        "path_names": [graph["node_map"][node_id]["name"] for node_id in path_ids],
        "edges": edges,
        "total": distances[end],
    }

def indoor_route_steps(result, graph):
    if not result:
        return []
    key_types = {"gate", "room", "elevator", "stairs", "other"}

    def is_road_like(node):
        node_id = str(node.get("id") or "")
        node_name = str(node.get("name") or "")
        node_type = str(node.get("type") or "")
        return (
            node_type == "hall"
            or node_id.startswith("road_")
            or "_road_" in node_id
            or "\u9053\u8def" in node_name
            or "\u5ba4\u5185\u9053\u8def" in node_name
            or "road" in node_name.lower()
        )

    def is_key_node(node):
        # 生成文字步骤时只保留用户关心的关键点；
        # 纯走廊采样点用于算法寻路，但不直接展示给用户。
        node_type = str(node.get("type") or "")
        if node.get("selectable") is False:
            return False
        if is_road_like(node):
            return False
        return node_type in key_types

    def step_node_label(node, mode):
        name = str(node.get("name") or "").strip()
        if mode in {"elevator", "stairs"}:
            return f"{node.get('floor')}F {name}"
        return name

    def vertical_step_text(nodes):
        key_nodes = [node for node in nodes if is_key_node(node)]
        if not key_nodes:
            return ""
        first_name = str(key_nodes[0].get("name") or "").strip()
        floors = []
        for node in key_nodes:
            floor_label = f"{node.get('floor')}F"
            if floor_label not in floors:
                floors.append(floor_label)
        if len(floors) <= 1:
            return first_name
        return f"{first_name}：{' → '.join(floors)}"

    def compact_step_text(nodes, mode):
        if mode in {"elevator", "stairs"}:
            return vertical_step_text(nodes)
        key_nodes = []
        for node in (nodes[0], nodes[-1]) if nodes else ():
            if is_key_node(node) and all(existing["id"] != node["id"] for existing in key_nodes):
                key_nodes.append(node)

        labels = []
        for node in key_nodes:
            label = step_node_label(node, mode)
            if label and label not in labels:
                labels.append(label)
        return " → ".join(labels)

    steps = []
    current_nodes = []
    current_mode = "walk"
    for index, node_id in enumerate(result["path_ids"]):
        node = graph["node_map"][node_id]
        if index == 0:
            current_nodes = [node]
            continue
        edge = result["edges"][index - 1]
        edge_mode = edge.get("mode", "walk")
        if edge_mode != current_mode and current_nodes:
            # 按walk/elevator/stairs切分路线，把连续同类型边压缩成一步讲解。
            text = compact_step_text(current_nodes, current_mode)
            steps.append({
                "mode": current_mode,
                "floor": current_nodes[0]["floor"],
                "text": text,
            })
            current_nodes = [current_nodes[-1]]
        current_mode = edge_mode
        current_nodes.append(node)
    if current_nodes:
        text = compact_step_text(current_nodes, current_mode)
        steps.append({
            "mode": current_mode,
            "floor": current_nodes[0]["floor"],
            "text": text,
        })
    steps = [step for step in steps if step["text"]]
    for step in steps:
        if step["mode"] == "elevator":
            step["label"] = "乘坐电梯"
        elif step["mode"] == "stairs":
            step["label"] = "步梯换层"
        else:
            step["label"] = f"{step['floor']}F 步行"
    return steps

def prepare_indoor_floors(graph, result):
    path_ids = result["path_ids"] if result else []
    path_id_set = set(path_ids)
    start_id = path_ids[0] if path_ids else ""
    end_id = path_ids[-1] if path_ids else ""
    edge_pairs = set()
    if result:
        for edge in result.get("edges", []):
            edge_pairs.add(frozenset((edge["from"], edge["to"])))

    floors = []
    for floor in graph["floors"]:
        floor_nodes = [node for node in graph["nodes"] if node["floor"] == floor]
        floor_edges = []
        for edge in graph["edges"]:
            from_node = graph["node_map"][edge["from"]]
            to_node = graph["node_map"][edge["to"]]
            if from_node["floor"] != floor or to_node["floor"] != floor:
                continue
            floor_edges.append({
                **edge,
                "x1": from_node["x"],
                "y1": from_node["y"],
                "x2": to_node["x"],
                "y2": to_node["y"],
                "is_path": frozenset((edge["from"], edge["to"])) in edge_pairs,
            })
        display_nodes = []
        for node in floor_nodes:
            if node.get("selectable") is False:
                continue
            if node.get("type") not in {"gate", "room", "elevator", "stairs", "other"}:
                continue
            display_nodes.append({
                **node,
                "is_path": node["id"] in path_id_set,
                "is_start": node["id"] == start_id,
                "is_end": node["id"] == end_id,
            })
        floors.append({
            "number": floor,
            "image": graph.get("floor_assets", {}).get(floor, ""),
            "width": graph.get("floor_size", {}).get("width", INDOOR_FLOOR_WIDTH),
            "height": graph.get("floor_size", {}).get("height", INDOOR_FLOOR_HEIGHT),
            "nodes": floor_nodes,
            "display_nodes": display_nodes,
            "edges": floor_edges,
            "path_nodes": [graph["node_map"][node_id] for node_id in path_ids if graph["node_map"][node_id]["floor"] == floor],
            "active": any(node["floor"] == floor for node in (graph["node_map"][node_id] for node_id in path_ids)),
        })
    return floors

def indoor_node_options(graph):
    return [
        node for node in graph["nodes"]
        if node["type"] in {"gate", "room", "elevator", "stairs", "other"}
    ]

def indoor_default_endpoints(graph):
    options = indoor_node_options(graph)
    if not options:
        return INDOOR_DEFAULT_START, INDOOR_DEFAULT_END
    start = INDOOR_DEFAULT_START if INDOOR_DEFAULT_START in graph["node_map"] else options[0]["id"]
    end = INDOOR_DEFAULT_END if INDOOR_DEFAULT_END in graph["node_map"] else options[-1]["id"]
    if start == end and len(options) > 1:
        end = options[1]["id"]
    return start, end

def default_indoor_collector_payload():
    return {
        "meta": {
            "building_id": "demo_building",
            "building_name": "室内导航采集楼",
            "width": INDOOR_FLOOR_WIDTH,
            "height": INDOOR_FLOOR_HEIGHT,
            "floor_assets": INDOOR_FLOOR_ASSETS,
        },
        "floors": {
            str(floor): {
                "nodes": [],
                "edges": [],
                "links": [],
            }
            for floor in sorted(INDOOR_FLOOR_ASSETS)
        },
    }

def indoor_point_distance(point_a, point_b):
    return round(math.hypot(float(point_a[0]) - float(point_b[0]), float(point_a[1]) - float(point_b[1])) / 10, 1)

def indoor_polyline_distance(points):
    return round(sum(indoor_point_distance(start, end) for start, end in zip(points, points[1:])), 1)

def next_indoor_collector_id(prefix, floor, existing_items=None):
    existing_items = existing_items or []
    used_ids = {str(item.get("id")) for item in existing_items if isinstance(item, dict) and item.get("id")}
    id_prefix = f"{prefix}_{floor}f_"
    id_pattern = re.compile(rf"^{re.escape(id_prefix)}(\d+)$")
    max_index = 0
    for item_id in used_ids:
        match = id_pattern.match(item_id)
        if match:
            max_index = max(max_index, int(match.group(1)))

    next_index = max(max_index, len(used_ids)) + 1
    while True:
        candidate = f"{id_prefix}{next_index:03d}"
        if candidate not in used_ids:
            return candidate, next_index
        next_index += 1

def normalize_indoor_collector_node(payload, existing_items=None):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    x = min(max(float(payload.get("x", 0)), 0), INDOOR_FLOOR_WIDTH)
    y = min(max(float(payload.get("y", 0)), 0), INDOOR_FLOOR_HEIGHT)
    node_type = str(payload.get("type") or "hall").strip()
    if node_type in {"hall", "room", "gate"}:
        node_type = "other"
    if node_type not in {"other", "elevator", "stairs"}:
        node_type = "other"
    core_id = str(payload.get("core_id") or payload.get("core") or "").strip()
    core_meta = INDOOR_VERTICAL_CORES.get(core_id)
    if node_type in {"elevator", "stairs"}:
        if core_meta and core_meta.get("type") != node_type:
            raise ValueError("核心筒编号与关键点类型不匹配")
        if not core_meta:
            core_id = ""
    else:
        core_id = ""
    node_id, next_index = next_indoor_collector_id("indoor", floor, existing_items)
    name = str(payload.get("name") or f"{floor}F采集点{next_index}").strip()
    node_id = str(payload.get("id") or node_id).strip()
    node = {
        "id": node_id,
        "name": name,
        "floor": floor,
        "x": round(x, 1),
        "y": round(y, 1),
        "type": node_type,
    }
    if core_id:
        node["core_id"] = core_id
        node["core_name"] = INDOOR_VERTICAL_CORES[core_id]["label"]
    return node

def normalize_indoor_collector_edge(payload, nodes, existing_items=None):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    mode = str(payload.get("mode") or "walk").strip()
    if mode not in INDOOR_VERTICAL_MODES and mode != "walk":
        mode = "walk"
    geometry = payload.get("geometry") or payload.get("points") or []
    points = []
    for point in geometry:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        points.append([
            round(min(max(float(point[0]), 0), INDOOR_FLOOR_WIDTH), 1),
            round(min(max(float(point[1]), 0), INDOOR_FLOOR_HEIGHT), 1),
        ])
    node_map = {str(node.get("id")): node for node in nodes}
    from_id = str(payload.get("from") or "").strip()
    to_id = str(payload.get("to") or "").strip()
    if len(points) < 2 and from_id in node_map and to_id in node_map and from_id != to_id:
        points = [
            [round(float(node_map[from_id]["x"]), 1), round(float(node_map[from_id]["y"]), 1)],
            [round(float(node_map[to_id]["x"]), 1), round(float(node_map[to_id]["y"]), 1)],
        ]
    if len(points) < 2:
        raise ValueError("室内路径至少需要两个采样点")
    poi_links = []
    for link in payload.get("poi_links") or []:
        try:
            index = int(link.get("index", -1))
        except (TypeError, ValueError):
            continue
        poi_id = str(link.get("poi") or link.get("id") or "").strip()
        if poi_id in node_map and 0 <= index < len(points):
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
    edge_id, next_index = next_indoor_collector_id("indoor_edge", floor, existing_items)
    edge_id = str(payload.get("id") or edge_id).strip()
    return {
        "id": edge_id,
        "name": str(payload.get("name") or f"{floor}F室内路径{next_index}").strip(),
        "floor": floor,
        "from": from_id,
        "to": to_id,
        "geometry": points,
        "poi_links": poi_links,
        "road_links": road_links,
        "distance": indoor_polyline_distance(points),
        "mode": mode,
        "road_type": str(payload.get("road_type") or "corridor").strip(),
    }

def indoor_collector_ref_point(ref, nodes, edges):
    # 吸附关系既可以连接关键点，也可以连接道路采样点；
    # 这里把不同类型引用统一解析成坐标，后续才能计算连接边距离。
    ref_type = str((ref or {}).get("type") or "").strip()
    if ref_type in {"node", "poi"}:
        node_id = str((ref or {}).get("id") or (ref or {}).get("poi") or "").strip()
        node = next((item for item in nodes if str(item.get("id")) == node_id), None)
        if not node:
            return None
        return [float(node["x"]), float(node["y"])]
    if ref_type == "road":
        edge_id = str((ref or {}).get("edge") or "").strip()
        try:
            point_index = int((ref or {}).get("point_index", (ref or {}).get("target_index", -1)))
        except (TypeError, ValueError):
            return None
        edge = next((item for item in edges if str(item.get("id")) == edge_id), None)
        geometry = edge.get("geometry") if edge else []
        if not edge or point_index < 0 or point_index >= len(geometry):
            return None
        point = geometry[point_index]
        return [float(point[0]), float(point[1])]
    return None

def normalize_indoor_collector_ref(ref, nodes, edges):
    ref_type = str((ref or {}).get("type") or "").strip()
    if ref_type in {"node", "poi"}:
        node_id = str((ref or {}).get("id") or (ref or {}).get("poi") or "").strip()
        if not any(str(node.get("id")) == node_id for node in nodes):
            raise ValueError("关键点端点不存在")
        return {"type": "node", "id": node_id}
    if ref_type == "road":
        edge_id = str((ref or {}).get("edge") or "").strip()
        try:
            point_index = int((ref or {}).get("point_index", (ref or {}).get("target_index", -1)))
        except (TypeError, ValueError):
            raise ValueError("路径端点索引无效")
        edge = next((item for item in edges if str(item.get("id")) == edge_id), None)
        if not edge or point_index < 0 or point_index >= len(edge.get("geometry") or []):
            raise ValueError("路径端点不存在")
        return {"type": "road", "edge": edge_id, "point_index": point_index}
    raise ValueError("吸附端点类型无效")

def normalize_indoor_collector_link(payload, nodes, edges, existing_items=None):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    a_ref = normalize_indoor_collector_ref(payload.get("a") or payload.get("from") or {}, nodes, edges)
    b_ref = normalize_indoor_collector_ref(payload.get("b") or payload.get("to") or {}, nodes, edges)
    if json.dumps(a_ref, sort_keys=True) == json.dumps(b_ref, sort_keys=True):
        raise ValueError("不能吸附同一个端点")
    if sorted([a_ref["type"], b_ref["type"]]) == ["node", "node"]:
        raise ValueError("关键点不能直接吸附关键点，请连接到路径点")
    point_a = indoor_collector_ref_point(a_ref, nodes, edges)
    point_b = indoor_collector_ref_point(b_ref, nodes, edges)
    if not point_a or not point_b:
        raise ValueError("吸附端点坐标无效")
    link_id, _ = next_indoor_collector_id("indoor_link", floor, existing_items)
    link_id = str(payload.get("id") or link_id).strip()
    return {
        "id": link_id,
        "floor": floor,
        "kind": "node_road" if "node" in {a_ref["type"], b_ref["type"]} else "road_road",
        "a": a_ref,
        "b": b_ref,
        "geometry": [
            [round(point_a[0], 1), round(point_a[1], 1)],
            [round(point_b[0], 1), round(point_b[1], 1)],
        ],
        "distance": indoor_polyline_distance([point_a, point_b]),
        "mode": str(payload.get("mode") or "walk").strip() or "walk",
    }

def build_indoor_graph_from_collector(payload):
    # 将采集器保存的楼层JSON转换成算法可用的图：
    # nodes是图节点，edges是无向边，road_point_lookup把道路采样点映射为隐藏节点。
    nodes = []
    edges = []
    node_map = {}
    road_point_lookup = {}

    def add_node(node):
        if node["id"] in node_map:
            return node["id"]
        nodes.append(node)
        node_map[node["id"]] = node
        return node["id"]

    def add_edge(from_id, to_id, distance, mode="walk"):
        if not from_id or not to_id or from_id == to_id:
            return
        # 先按单向边保存，构建adjacency时再补反向边，因此最终图是无向可通行图。
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": max(float(distance or 0), 0.1),
            "mode": mode,
        })

    for floor_key, floor_payload in (payload.get("floors") or {}).items():
        try:
            floor = int(floor_key)
        except (TypeError, ValueError):
            continue
        for raw_node in floor_payload.get("nodes", []):
            try:
                normalized = normalize_indoor_collector_node(raw_node)
            except (TypeError, ValueError):
                continue
            add_node(normalized)
        for raw_edge in floor_payload.get("edges", []):
            try:
                edge = normalize_indoor_collector_edge(raw_edge, floor_payload.get("nodes", []), floor_payload.get("edges", []))
            except (TypeError, ValueError):
                continue
            # 每条室内道路折线会被拆成多个隐藏road节点，节点之间按折线长度连边。
            # 这样路线展示可以贴合真实走廊形状，而不是只在两个端点之间画直线。
            previous_node_id = ""
            for point_index, point in enumerate(edge.get("geometry") or []):
                road_node_id = f"road_{edge['id']}_{point_index:03d}"
                add_node({
                    "id": road_node_id,
                    "name": f"{edge.get('name', '室内路径')}#{point_index + 1}",
                    "floor": floor,
                    "x": point[0],
                    "y": point[1],
                    "type": "hall",
                    "selectable": False,
                })
                road_point_lookup[(edge["id"], point_index)] = road_node_id
                if previous_node_id:
                    previous = node_map[previous_node_id]
                    add_edge(previous_node_id, road_node_id, indoor_point_distance([previous["x"], previous["y"]], point), edge.get("mode", "walk"))
                previous_node_id = road_node_id
            for link in edge.get("poi_links", []):
                # poi_links把房间、电梯、楼梯等可选关键点连接到最近的道路采样点。
                road_node_id = road_point_lookup.get((edge["id"], link.get("index")))
                if road_node_id and link.get("poi") in node_map:
                    add_edge(link["poi"], road_node_id, indoor_point_distance(
                        [node_map[link["poi"]]["x"], node_map[link["poi"]]["y"]],
                        [node_map[road_node_id]["x"], node_map[road_node_id]["y"]],
                    ))
            for link in edge.get("road_links", []):
                # road_links连接不同道路折线的采样点，形成可转弯、可换走廊的连通图。
                from_id = road_point_lookup.get((edge["id"], link.get("index")))
                to_id = road_point_lookup.get((link.get("edge"), link.get("target_index")))
                if from_id and to_id:
                    add_edge(from_id, to_id, indoor_point_distance(
                        [node_map[from_id]["x"], node_map[from_id]["y"]],
                        [node_map[to_id]["x"], node_map[to_id]["y"]],
                    ))
        for raw_link in floor_payload.get("links", []):
            try:
                link = normalize_indoor_collector_link(
                    raw_link,
                    floor_payload.get("nodes", []),
                    floor_payload.get("edges", []),
                    floor_payload.get("links", []),
                )
            except (TypeError, ValueError):
                continue

            def graph_node_for_ref(ref):
                if ref.get("type") == "node":
                    return ref.get("id") if ref.get("id") in node_map else ""
                return road_point_lookup.get((ref.get("edge"), ref.get("point_index")), "")

            from_id = graph_node_for_ref(link.get("a") or {})
            to_id = graph_node_for_ref(link.get("b") or {})
            add_edge(from_id, to_id, link.get("distance", 0), link.get("mode", "walk"))

    def vertical_node_name_key(node):
        return normalize_search_text(str(node.get("name") or "").strip())

    for floor in sorted(INDOOR_FLOOR_ASSETS)[:-1]:
        # 垂直交通建模：把相邻楼层同名/同core的电梯或楼梯连成跨层边。
        # 这使得普通Dijkstra无需特殊跨层逻辑，也能完成1F到4F的路径规划。
        current = [node for node in nodes if node.get("floor") == floor and node.get("type") in {"elevator", "stairs"}]
        upper = [node for node in nodes if node.get("floor") == floor + 1 and node.get("type") in {"elevator", "stairs"}]
        for node in current:
            candidates = [item for item in upper if item.get("type") == node.get("type")]
            if not candidates:
                continue
            node_name_key = vertical_node_name_key(node)
            same_name = [
                item for item in candidates
                if node_name_key and vertical_node_name_key(item) == node_name_key
            ]
            if same_name:
                target = same_name[0]
                add_edge(node["id"], target["id"], 16 if node.get("type") == "elevator" else 24, node.get("type"))
                continue
            same_core = [
                item for item in candidates
                if node.get("core_id") and item.get("core_id") == node.get("core_id")
            ]
            if same_core:
                target = same_core[0]
                add_edge(node["id"], target["id"], 16 if node.get("type") == "elevator" else 24, node.get("type"))
                continue
            nearest = min(candidates, key=lambda item: math.hypot(float(item["x"]) - float(node["x"]), float(item["y"]) - float(node["y"])))
            if math.hypot(float(nearest["x"]) - float(node["x"]), float(nearest["y"]) - float(node["y"])) <= 120:
                add_edge(node["id"], nearest["id"], 16 if node.get("type") == "elevator" else 24, node.get("type"))

    adjacency = {node["id"]: [] for node in nodes}
    for edge in edges:
        if edge["from"] not in adjacency or edge["to"] not in adjacency:
            continue
        # adjacency是Dijkstra直接读取的邻接表；每条室内边补成双向边。
        adjacency[edge["from"]].append({**edge, "neighbor": edge["to"]})
        adjacency[edge["to"]].append({
            **edge,
            "from": edge["to"],
            "to": edge["from"],
            "neighbor": edge["from"],
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "node_map": node_map,
        "adjacency": adjacency,
        "floors": [1, 2, 3, 4],
        "floor_assets": INDOOR_FLOOR_ASSETS,
        "floor_size": {"width": INDOOR_FLOOR_WIDTH, "height": INDOOR_FLOOR_HEIGHT},
    }

def is_indoor_building_node(node):
    return str((node or {}).get("kind", "")).strip() in INDOOR_BUILDING_TYPES
