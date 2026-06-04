import csv
import json
import os
from dataclasses import dataclass

from .filesystem import ensure_parent_dir, file_signature, files_signature
from .food_catalog import (
    coerce_food_number,
    default_food_recommendation_note,
    default_signature_dishes,
    enrich_food_distance,
    food_default_profile,
    food_dedupe_key,
    food_display_description,
    food_media_lookup_keys,
    food_recommendation_breakdown,
    is_food_related_facility,
    normalize_food_category,
    normalize_tags,
    optional_food_float,
    public_food_recommendation_note,
    rank_food_candidates,
    visible_food_tags,
    build_food_key,
)


@dataclass
class FoodRepositoryConfig:
    facilities_file: str
    collector_facilities_file: str
    food_media_file: str
    generated_facilities_file: str
    food_default_place_id: str
    food_campus_contexts: dict
    food_candidates_cache: dict
    food_media_cache: dict


@dataclass
class FoodRepositoryServices:
    get_route_graph_path: object
    load_route_graph: object
    load_facilities: object
    resolve_facility_nearest_node: object


_config = None
_services = None


def configure_food_repository(config, services):
    global _config, _services
    global FACILITIES_FILE, XMU_COLLECTOR_FACILITIES_FILE, XMU_FOOD_MEDIA_FILE, XMU_XIANG_AN_GENERATED_FACILITIES_FILE
    global FOOD_DEFAULT_PLACE_ID, FOOD_CAMPUS_CONTEXTS, FOOD_CANDIDATES_CACHE, FOOD_MEDIA_CACHE
    _config = config
    _services = services
    FACILITIES_FILE = config.facilities_file
    XMU_COLLECTOR_FACILITIES_FILE = config.collector_facilities_file
    XMU_FOOD_MEDIA_FILE = config.food_media_file
    XMU_XIANG_AN_GENERATED_FACILITIES_FILE = config.generated_facilities_file
    FOOD_DEFAULT_PLACE_ID = config.food_default_place_id
    FOOD_CAMPUS_CONTEXTS = config.food_campus_contexts
    FOOD_CANDIDATES_CACHE = config.food_candidates_cache
    FOOD_MEDIA_CACHE = config.food_media_cache


def _require_services():
    if _services is None:
        raise RuntimeError("Food repository services have not been configured")
    return _services


def get_route_graph_path(*args, **kwargs):
    return _require_services().get_route_graph_path(*args, **kwargs)


def load_route_graph(*args, **kwargs):
    return _require_services().load_route_graph(*args, **kwargs)


def load_facilities(*args, **kwargs):
    return _require_services().load_facilities(*args, **kwargs)


def resolve_facility_nearest_node(*args, **kwargs):
    return _require_services().resolve_facility_nearest_node(*args, **kwargs)


FACILITIES_FILE = ""
XMU_COLLECTOR_FACILITIES_FILE = ""
XMU_FOOD_MEDIA_FILE = ""
XMU_XIANG_AN_GENERATED_FACILITIES_FILE = ""
FOOD_DEFAULT_PLACE_ID = "xmu_manual"
FOOD_CAMPUS_CONTEXTS = {}
FOOD_CANDIDATES_CACHE = {}
FOOD_MEDIA_CACHE = {"signature": None, "records": {}}

def get_food_by_key(food_key, place_id="", origin_node=""):
    food_key = str(food_key or "").strip()
    if not food_key:
        return None

    if place_id in FOOD_CAMPUS_CONTEXTS:
        graph_place_id = FOOD_CAMPUS_CONTEXTS[place_id].get("graph_place_id", place_id)
        graph = load_route_graph(graph_place_id)
        effective_origin_node = origin_node if origin_node in graph.get("node_map", {}) else get_food_origin_node(place_id)
        for food in build_food_candidates_for_place(place_id):
            if food.get("food_key") == food_key:
                enrich_food_distance(food, graph, effective_origin_node)
                breakdown = food_recommendation_breakdown(food)
                food["recommend_score_detail"] = breakdown
                food["recommend_score"] = breakdown["total"]
                food["recommend_score_display"] = round(
                    float(food.get("recommend_score_override"))
                    if food.get("recommend_score_override") is not None
                    else food["recommend_score"],
                    2,
                )
                return food
    return None

def load_csv_rows(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def load_food_media_payload():
    if not os.path.exists(XMU_FOOD_MEDIA_FILE):
        return {
            "description": "厦门大学翔安校区美食系统本地媒体清单。",
            "source_policy": "Local static paths only.",
            "foods": {},
        }
    try:
        with open(XMU_FOOD_MEDIA_FILE, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    foods_payload = payload.get("foods")
    if not isinstance(foods_payload, dict):
        payload["foods"] = {}
    payload.setdefault("description", "厦门大学翔安校区美食系统本地媒体清单。")
    payload.setdefault("source_policy", "Local static paths only.")
    return payload

def save_food_media_payload(payload):
    ensure_parent_dir(XMU_FOOD_MEDIA_FILE)
    with open(XMU_FOOD_MEDIA_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    FOOD_MEDIA_CACHE.update({"signature": None, "records": {}})
    FOOD_CANDIDATES_CACHE.clear()

def load_food_media_records():
    signature = file_signature(XMU_FOOD_MEDIA_FILE)
    if FOOD_MEDIA_CACHE.get("signature") == signature:
        return FOOD_MEDIA_CACHE.get("records", {})

    records = {}
    if signature:
        payload = load_food_media_payload()

        raw_items = payload.get("foods", payload) if isinstance(payload, dict) else payload
        if isinstance(raw_items, dict):
            iterable = raw_items.items()
        elif isinstance(raw_items, list):
            iterable = ((item.get("food_key") or item.get("key"), item) for item in raw_items if isinstance(item, dict))
        else:
            iterable = []

        for key, item in iterable:
            if not isinstance(item, dict):
                continue
            normalized_key = str(key or item.get("food_key") or "").strip()
            if not normalized_key:
                continue
            dishes = []
            for dish in item.get("signature_dishes", [])[:3]:
                if not isinstance(dish, dict):
                    continue
                dish_name = str(dish.get("name") or "").strip()
                image = str(dish.get("image") or "").strip()
                if not dish_name or not image:
                    continue
                dishes.append({
                    "name": dish_name,
                    "price": str(dish.get("price") or "").strip(),
                    "image": image,
                })
            records[normalized_key] = {
                "name": str(item.get("name") or "").strip(),
                "cuisine": str(item.get("cuisine") or "").strip(),
                "cover_image": str(item.get("cover_image") or "").strip(),
                "detail_image": str(item.get("detail_image") or "").strip(),
                "signature_dishes": dishes,
                "recommend_score_override": item.get("recommend_score_override"),
                "rating": item.get("rating"),
                "popularity": item.get("popularity"),
                "avg_cost": item.get("avg_cost"),
                "display_description": str(item.get("display_description") or "").strip(),
                "recommendation_note": str(item.get("recommendation_note") or "").strip(),
            }

    FOOD_MEDIA_CACHE.update({"signature": signature, "records": records})
    return records

def apply_food_media(food):
    media_records = load_food_media_records()
    media = None
    for key in food_media_lookup_keys(food):
        if key and key in media_records:
            media = media_records[key]
            break

    if media:
        cuisine_override = str(media.get("cuisine") or "").strip()
        if cuisine_override and cuisine_override != "其他餐饮":
            previous_category = str(food.get("category") or "").strip()
            food["category"] = cuisine_override
            food["cuisine"] = cuisine_override
            food["has_explicit_cuisine"] = True
            tags_list = []
            for tag in normalize_tags(food.get("tags_list") or food.get("tags")):
                if tag and tag != previous_category and tag not in tags_list:
                    tags_list.append(tag)
            if cuisine_override not in tags_list:
                tags_list.append(cuisine_override)
            food["tags_list"] = tags_list
            food["tags"] = ";".join(tags_list)
        food["recommend_score_override"] = optional_food_float(media.get("recommend_score_override"))
        food["rating"] = round(coerce_food_number(media.get("rating"), food.get("rating", 4.0), float, 0, 5), 1)
        food["popularity"] = int(coerce_food_number(media.get("popularity"), food.get("popularity", 60), int, 0, 9999))
        food["avg_cost"] = round(coerce_food_number(media.get("avg_cost"), food.get("avg_cost", 22), float, 0, 9999), 1)
        if media.get("display_description"):
            food["display_description"] = media["display_description"]
        food["recommendation_note"] = public_food_recommendation_note(media.get("recommendation_note"))
        food["cover_image"] = media.get("cover_image") or "food_media/shops/food-cover-placeholder.jpg"
        food["detail_image"] = media.get("detail_image") or food["cover_image"]
        dishes = [dish.copy() for dish in media.get("signature_dishes", []) if dish.get("image")]
    else:
        food["recommend_score_override"] = None
        food["recommendation_note"] = default_food_recommendation_note()
        food["cover_image"] = "food_media/shops/food-cover-placeholder.jpg"
        food["detail_image"] = food["cover_image"]
        dishes = []

    if len(dishes) < 3:
        fallback_dishes = default_signature_dishes(food.get("category", ""), food.get("avg_cost", 22))
        for index in range(len(dishes), 3):
            dish = fallback_dishes[index]
            dish["image"] = "food_media/dishes/food-dish-placeholder.jpg"
            dishes.append(dish)
    food["signature_dishes"] = dishes[:3]
    food["visible_tags"] = visible_food_tags(food.get("tags_list", []), food.get("category", ""))
    return food

def make_food_candidate(raw_item, place_id, place_name, source_kind, graph=None):
    if not raw_item:
        return None

    candidate_name = str(raw_item.get("name") or "").strip()
    if not candidate_name:
        return None

    description = str(raw_item.get("description") or "").strip()
    explicit_cuisine = str(raw_item.get("cuisine") or raw_item.get("food_category") or "").strip()
    has_explicit_cuisine = bool(explicit_cuisine and explicit_cuisine != "其他餐饮")
    if explicit_cuisine and explicit_cuisine != "其他餐饮":
        category = explicit_cuisine
    else:
        category = normalize_food_category(raw_item.get("category") or raw_item.get("type"), candidate_name, description)
    rating, popularity, avg_cost = food_default_profile(category, candidate_name)
    tags_list = normalize_tags(raw_item.get("tags") or [place_name, category, "校园"])
    nearest_node = str(raw_item.get("nearest_node") or raw_item.get("anchor_node") or "").strip()
    if source_kind in ("collector_facility", "facility_csv", "generated_facility"):
        resolved_node = resolve_facility_nearest_node(raw_item, graph, road_only=True)
        if resolved_node:
            nearest_node = resolved_node
    graph_node_id = str(raw_item.get("id") or "").strip()
    source_labels = {
        "graph_node": "路线图节点",
        "collector_facility": "采集餐饮设施",
        "facility_csv": "设施表补位",
        "generated_facility": "候选补位",
    }
    source_label = source_labels.get(source_kind, "采集补位")

    raw_tags = raw_item.get("tags")
    if isinstance(raw_tags, list):
        tags_text = ";".join(str(tag).strip() for tag in raw_tags if str(tag).strip())
    elif isinstance(raw_tags, str):
        tags_text = raw_tags.strip()
    else:
        tags_text = ";".join(tags_list)

    candidate = {
        "food_key": build_food_key(place_id, source_kind, raw_item.get("id") or raw_item.get("nearest_node") or candidate_name),
        "id": raw_item.get("id"),
        "name": candidate_name,
        "place_name": place_name,
        "category": category,
        "cuisine": category,
        "has_explicit_cuisine": has_explicit_cuisine,
        "facility_type": raw_item.get("type") or raw_item.get("kind") or "",
        "rating": round(float(rating), 1),
        "popularity": int(popularity),
        "avg_cost": round(float(avg_cost), 1),
        "tags": tags_text if tags_text else ";".join(tags_list),
        "tags_list": tags_list,
        "description": str(raw_item.get("description") or raw_item.get("note") or "").strip(),
        "source_kind": source_kind,
        "source_label": source_label,
        "graph_place_id": place_id,
        "graph_place_name": place_name,
        "graph_node_id": graph_node_id,
        "nearest_node": nearest_node,
        "distance_m": None,
        "distance_text": "",
        "recommend_score": 0.0,
    }

    candidate["description"] = candidate["description"] or "来自翔安校区图数据补位。"
    candidate["display_description"] = food_display_description(candidate["description"], category, source_kind)
    apply_food_media(candidate)
    return candidate

def build_food_candidates_for_place(place_id):
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        return []

    context = FOOD_CAMPUS_CONTEXTS[place_id]
    graph_place_id = context.get("graph_place_id", place_id)
    graph = load_route_graph(graph_place_id)
    source_signature = (
        file_signature(get_route_graph_path(graph_place_id)),
        files_signature([FACILITIES_FILE, XMU_COLLECTOR_FACILITIES_FILE, XMU_XIANG_AN_GENERATED_FACILITIES_FILE, XMU_FOOD_MEDIA_FILE]),
    )
    cached = FOOD_CANDIDATES_CACHE.get(place_id)
    if cached and cached.get("signature") == source_signature:
        return [item.copy() for item in cached.get("records", [])]

    place_name = context["place_name"]
    candidate_map = {}

    def maybe_store(candidate, priority):
        if not candidate:
            return
        key = food_dedupe_key(candidate)
        existing = candidate_map.get(key)
        if existing is None:
            candidate["source_priority"] = priority
            candidate_map[key] = candidate
            return
        existing_priority = existing.get("source_priority", -1)
        if priority > existing_priority:
            candidate["source_priority"] = priority
            candidate_map[key] = candidate
            return
        if priority == existing_priority and candidate.get("has_explicit_cuisine") and not existing.get("has_explicit_cuisine"):
            candidate["source_priority"] = priority
            candidate_map[key] = candidate
            return
        if existing_priority == priority and not existing.get("description") and candidate.get("description"):
            candidate["source_priority"] = priority
            candidate_map[key] = candidate

    for node in graph.get("nodes", []):
        if node.get("kind") == "road":
            continue
        node_type = node.get("type") or node.get("category") or node.get("kind", "")
        description = " ".join(str(part) for part in [
            node.get("description", ""),
            node.get("source", ""),
            node.get("kind", ""),
        ] if part)
        if not is_food_related_facility(node.get("name", ""), node_type, description):
            continue
        candidate = make_food_candidate(node, place_id, place_name, "graph_node", graph)
        if candidate:
            if not candidate.get("nearest_node"):
                candidate["nearest_node"] = node.get("id", "")
            maybe_store(candidate, 4)

    facility_parent_place = graph.get("facility_parent_place", graph.get("place_id", graph_place_id))
    for facility in load_facilities(facility_parent_place):
        if not is_food_related_facility(facility.get("name", ""), facility.get("type", ""), facility.get("description", "")):
            continue
        source_kind = "collector_facility" if str(facility.get("id", "")).startswith("facility_") else "facility_csv"
        candidate = make_food_candidate(facility, place_id, place_name, source_kind, graph)
        if candidate:
            if not candidate.get("nearest_node") and facility.get("nearest_node"):
                candidate["nearest_node"] = str(facility.get("nearest_node")).strip()
            maybe_store(candidate, 5 if source_kind == "collector_facility" else 3)

    if place_id == "xmu_xiang_an":
        for row in load_csv_rows(XMU_XIANG_AN_GENERATED_FACILITIES_FILE):
            if not is_food_related_facility(row.get("name", ""), row.get("type", ""), row.get("description", "")):
                continue
            candidate = make_food_candidate(row, place_id, place_name, "generated_facility", graph)
            if candidate:
                maybe_store(candidate, 1)

    candidates = list(candidate_map.values())
    FOOD_CANDIDATES_CACHE[place_id] = {
        "signature": source_signature,
        "records": [item.copy() for item in candidates],
    }
    return candidates

def get_food_origin_node(place_id):
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        return ""
    graph_place_id = FOOD_CAMPUS_CONTEXTS[place_id].get("graph_place_id", place_id)
    graph = load_route_graph(graph_place_id)
    start = graph.get("default_start", "")
    if start in graph.get("node_map", {}):
        return start
    return ""

def get_route_linked_foods(place_id, graph, start_node, limit=5):
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        return [], None

    origin_node = start_node if start_node in graph.get("node_map", {}) else get_food_origin_node(place_id)
    foods = build_food_candidates_for_place(place_id)
    return rank_food_candidates(
        foods,
        sort_by="distance_asc" if origin_node else "recommend_score_desc",
        limit=limit,
        graph=graph,
        origin_node=origin_node,
    )
