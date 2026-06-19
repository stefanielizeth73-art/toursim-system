import heapq
import itertools

from .geo import haversine_amap


MAX_ROUTE_TARGETS = 8
SHORTEST_TREE_CACHE = {}


def is_road_graph_node(node):
    return str((node or {}).get("kind") or "").strip() == "road"

def nearest_graph_node_id(point, graph, selectable_only=False, road_only=False):
    best = None
    for node in graph.get("nodes", []):
        if selectable_only and not is_selectable_node(node):
            continue
        if road_only and not is_road_graph_node(node):
            continue
        if "amap_lng" not in node or "amap_lat" not in node:
            continue
        node_point = [float(node["amap_lng"]), float(node["amap_lat"])]
        distance = haversine_amap(point, node_point)
        if not best or distance < best[1]:
            best = (node["id"], distance)
    return best[0] if best else ""

def is_selectable_node(node):
    return node.get("selectable", node.get("kind") != "road")

def get_selectable_nodes(graph):
    return [node for node in graph.get("nodes", []) if is_selectable_node(node)]

def get_display_path_names(graph, path_ids):
    names = []
    for node_id in path_ids:
        node = graph["node_map"].get(node_id)
        if not node:
            continue
        if not is_selectable_node(node) and node_id not in (path_ids[0], path_ids[-1]):
            continue
        if not names or names[-1] != node["name"]:
            names.append(node["name"])
    return names

def flatten_edge_points(edges, field_name):
    points = []
    for edge in edges:
        edge_points = edge.get(field_name, [])
        if not edge_points:
            continue
        if points and edge_points and points[-1] == edge_points[0]:
            points.extend(edge_points[1:])
        else:
            points.extend(edge_points)
    return points

def serialize_route_result(result):
    if not result:
        return None
    return {
        "path_ids": result["path_ids"],
        "path_names": result["path_names"],
        "display_path_names": result.get("display_path_names", result["path_names"]),
        "edges": result["edges"],
        "total": round(result["total"], 1),
        "geometry": flatten_edge_points(result["edges"], "geometry"),
        "amap_geometry": flatten_edge_points(result["edges"], "amap_geometry"),
    }

def serialize_multi_route_result(multi_result):
    if not multi_result:
        return None
    return {
        "order": list(multi_result["order"]),
        "total": round(multi_result["total"], 1),
        "error": multi_result.get("error"),
        "returns_to_start": multi_result.get("returns_to_start", False),
        "segments": [serialize_route_result(segment) for segment in multi_result["segments"]],
        "geometry": flatten_edge_points(
            [edge for segment in multi_result["segments"] for edge in segment.get("edges", [])],
            "geometry"
        ),
        "amap_geometry": flatten_edge_points(
            [edge for segment in multi_result["segments"] for edge in segment.get("edges", [])],
            "amap_geometry"
        ),
    }

def calculate_edge_weight(edge, strategy="distance", transport="walk"):
    # 交通工具约束先过滤：非mixed模式下，不能通行该交通方式的边直接跳过。
    # 例如选择自行车时，只能走标记bike=True的道路。
    if transport != "mixed" and not edge.get(transport, False):
        return None

    distance = float(edge.get("distance", 0))
    if strategy == "distance":
        return distance

    # 时间最短策略把距离转换为时间权重：时间 = 距离 / (速度 * 拥挤度)。
    # congestion做下限保护，避免数据异常导致除零或权重过大。
    congestion = max(float(edge.get("congestion", 1)), 0.1)
    speeds = {"walk": 1.2, "bike": 4.0}

    if transport == "mixed":
        # mixed表示混合交通：同一条边如果步行/骑行都可用，就选择耗时更短的方式。
        candidates = []
        for mode, speed in speeds.items():
            if edge.get(mode, False):
                candidates.append(distance / (speed * congestion))
        return min(candidates) if candidates else None

    return distance / (speeds.get(transport, 1.2) * congestion)

def dijkstra_shortest_path(graph, start, end, strategy="distance", transport="walk"):
    if start not in graph["node_map"] or end not in graph["node_map"]:
        return None

    # distances保存从起点到各节点的当前最短估计；previous保存路径前驱，
    # 最后用于从终点反向回溯出完整路线。
    distances = {node_id: float("inf") for node_id in graph["node_map"]}
    previous = {}
    distances[start] = 0
    # heap是按当前距离排序的优先队列，每次弹出距离最小的待扩展节点。
    heap = [(0, start)]

    while heap:
        current_distance, current = heapq.heappop(heap)
        if current == end:
            break
        # 如果堆里弹出的旧距离已经不是最优值，说明它被后续松弛更新过，直接丢弃。
        if current_distance > distances[current]:
            continue

        for edge in graph["adjacency"].get(current, []):
            weight = calculate_edge_weight(edge, strategy=strategy, transport=transport)
            if weight is None:
                continue

            neighbor = edge["neighbor"]
            new_distance = current_distance + weight
            if new_distance < distances[neighbor]:
                # 松弛操作：发现更短路径就更新距离和前驱，并把新状态压入堆。
                distances[neighbor] = new_distance
                previous[neighbor] = (current, edge, weight)
                heapq.heappush(heap, (new_distance, neighbor))

    if distances[end] == float("inf"):
        return None

    path_ids = [end]
    edges = []
    cursor = end
    while cursor != start:
        # previous里记录的是“当前节点从哪个节点、沿哪条边过来”，因此可以反向还原路径。
        prev_node, edge, weight = previous[cursor]
        edges.append({**edge, "weight": weight})
        cursor = prev_node
        path_ids.append(cursor)

    path_ids.reverse()
    edges.reverse()

    return {
        "path_ids": path_ids,
        "path_names": [graph["node_map"][node_id]["name"] for node_id in path_ids],
        "display_path_names": get_display_path_names(graph, path_ids),
        "edges": edges,
        "total": distances[end],
    }

def dijkstra_shortest_tree(graph, start, strategy="distance", transport="walk"):
    if start not in graph.get("node_map", {}):
        return None

    # 最短路树用于“一个起点到多个候选点”的场景，例如附近设施/美食距离排序。
    # 同一个图、起点、策略、交通方式可以复用缓存，避免反复跑Dijkstra。
    graph_cache_key = graph.get("_cache_key")
    cache_key = (graph_cache_key, start, strategy, transport) if graph_cache_key else None
    if cache_key in SHORTEST_TREE_CACHE:
        return SHORTEST_TREE_CACHE[cache_key]

    distances = {node_id: float("inf") for node_id in graph["node_map"]}
    previous = {}
    distances[start] = 0
    heap = [(0, start)]

    while heap:
        current_distance, current = heapq.heappop(heap)
        if current_distance > distances[current]:
            continue

        for edge in graph["adjacency"].get(current, []):
            weight = calculate_edge_weight(edge, strategy=strategy, transport=transport)
            if weight is None:
                continue

            neighbor = edge["neighbor"]
            new_distance = current_distance + weight
            if new_distance < distances[neighbor]:
                distances[neighbor] = new_distance
                previous[neighbor] = (current, edge, weight)
                heapq.heappush(heap, (new_distance, neighbor))

    route_tree = {"start": start, "distances": distances, "previous": previous}
    if cache_key:
        SHORTEST_TREE_CACHE[cache_key] = route_tree
    return route_tree

def route_from_shortest_tree(graph, route_tree, end):
    if not route_tree or end not in graph.get("node_map", {}):
        return None

    start = route_tree["start"]
    distances = route_tree["distances"]
    previous = route_tree["previous"]
    if distances.get(end, float("inf")) == float("inf"):
        return None

    path_ids = [end]
    edges = []
    cursor = end
    while cursor != start:
        # 从已经计算好的最短路树中抽取到某个终点的路径，不需要重新搜索整张图。
        if cursor not in previous:
            return None
        prev_node, edge, weight = previous[cursor]
        edges.append({**edge, "weight": weight})
        cursor = prev_node
        path_ids.append(cursor)

    path_ids.reverse()
    edges.reverse()
    return {
        "path_ids": path_ids,
        "path_names": [graph["node_map"][node_id]["name"] for node_id in path_ids],
        "display_path_names": get_display_path_names(graph, path_ids),
        "edges": edges,
        "total": distances[end],
    }

def plan_multi_target_route(graph, start, targets, strategy="distance", transport="walk", return_to_start=False, final_target=None):
    # 多目标路线先去重并排除起点；final_target表示固定终点，
    # 其余targets作为可排列的途经点参与小规模TSP搜索。
    final_target = final_target if final_target and final_target != start and final_target in graph["node_map"] else None
    unique_targets = []
    for target in targets:
        if (
            target
            and target != start
            and target != final_target
            and target in graph["node_map"]
            and target not in unique_targets
        ):
            unique_targets.append(target)

    visit_count = len(unique_targets) + (1 if final_target else 0)
    if visit_count == 0:
        return None
    if visit_count > MAX_ROUTE_TARGETS:
        return {
            "order": tuple(),
            "segments": [],
            "total": 0,
            "returns_to_start": return_to_start,
            "error": f"途经点最多支持 {MAX_ROUTE_TARGETS} 个，请减少目标点后重试。",
        }

    # 先预计算“起点/途经点/终点”之间的两两最短路，后续排列时直接查表累加。
    pair_paths = {}
    candidate_targets = list(unique_targets)
    if final_target:
        candidate_targets.append(final_target)
    route_points = [start] + candidate_targets
    for from_node in route_points:
        outgoing_targets = list(candidate_targets)
        if return_to_start and from_node != start:
            outgoing_targets.append(start)
        for to_node in outgoing_targets:
            if from_node == to_node:
                continue
            path = dijkstra_shortest_path(graph, from_node, to_node, strategy=strategy, transport=transport)
            if path is not None:
                pair_paths[(from_node, to_node)] = path

    best_plan = None
    final_suffix = (final_target,) if final_target else tuple()
    for order in itertools.permutations(unique_targets):
        # 枚举途经点访问顺序。因为MAX_ROUTE_TARGETS限制为8，这里追求小规模绝对最优。
        ordered_targets = tuple(order) + final_suffix
        current = start
        segments = []
        total = 0
        feasible = True

        for target in ordered_targets:
            segment = pair_paths.get((current, target))
            if segment is None:
                feasible = False
                break
            segments.append(segment)
            total += segment["total"]
            current = target

        if feasible and return_to_start:
            # 往返路线需要在访问完所有目标后，再补一段回到起点的最短路。
            segment = pair_paths.get((current, start))
            if segment is None:
                feasible = False
            else:
                segments.append(segment)
                total += segment["total"]

        if feasible and (best_plan is None or total < best_plan["total"]):
            best_plan = {
                "order": ordered_targets,
                "segments": segments,
                "total": total,
                "returns_to_start": return_to_start,
            }

    return best_plan

def normalize_route_targets(start, end, targets, route_type):
    normalized = []
    for target in list(targets or []):
        if target and target != start and target not in normalized:
            normalized.append(target)
    if route_type in ("multi", "round_trip") and end and end != start and end not in normalized:
        normalized.append(end)
    return normalized

def route_targets_for_planning(targets, final_target=None):
    if not final_target:
        return list(targets or [])[:MAX_ROUTE_TARGETS]
    waypoints = [target for target in list(targets or []) if target != final_target]
    return waypoints[:max(0, MAX_ROUTE_TARGETS - 1)] + [final_target]
