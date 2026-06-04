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
    if transport != "mixed" and not edge.get(transport, False):
        return None

    distance = float(edge.get("distance", 0))
    if strategy == "distance":
        return distance

    congestion = max(float(edge.get("congestion", 1)), 0.1)
    speeds = {"walk": 1.2, "bike": 4.0}

    if transport == "mixed":
        candidates = []
        for mode, speed in speeds.items():
            if edge.get(mode, False):
                candidates.append(distance / (speed * congestion))
        return min(candidates) if candidates else None

    return distance / (speeds.get(transport, 1.2) * congestion)

def dijkstra_shortest_path(graph, start, end, strategy="distance", transport="walk"):
    if start not in graph["node_map"] or end not in graph["node_map"]:
        return None

    distances = {node_id: float("inf") for node_id in graph["node_map"]}
    previous = {}
    distances[start] = 0
    heap = [(0, start)]

    while heap:
        current_distance, current = heapq.heappop(heap)
        if current == end:
            break
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

    if distances[end] == float("inf"):
        return None

    path_ids = [end]
    edges = []
    cursor = end
    while cursor != start:
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
