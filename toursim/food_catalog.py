import heapq
import re

from .route_algorithms import dijkstra_shortest_path, dijkstra_shortest_tree, route_from_shortest_tree
from .search import normalize_search_text, split_search_terms


FOOD_DEFAULT_PLACE_ID = "xmu_manual"
FOOD_CUISINE_OPTIONS = [
    "东北菜",
    "川菜",
    "湘菜",
    "火锅",
    "自助",
    "烧烤",
    "快餐",
    "奶茶",
    "咖啡",
    "小吃",
    "面食",
    "粉面",
    "粤菜",
    "西餐",
    "印度菜",
    "家常菜",
    "食堂",
    "超市便利",
    "饮品",
    "其他餐饮",
]


def normalize_tags(value):
    if isinstance(value, str):
        raw_tags = re.split(r"[、,，/;；\s]+", value)
    else:
        raw_tags = value or []
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]


def build_food_key(place_id, source_kind, raw_id):
    safe_place_id = re.sub(r"[^0-9A-Za-z_-]+", "_", str(place_id or "global")).strip("_") or "global"
    safe_source = re.sub(r"[^0-9A-Za-z_-]+", "_", str(source_kind or "item")).strip("_") or "item"
    safe_raw_id = re.sub(r"[^0-9A-Za-z_-]+", "_", str(raw_id or "item")).strip("_") or "item"
    return f"{safe_place_id}_{safe_source}_{safe_raw_id}"

def normalize_food_category(category, name="", description=""):
    category_text = normalize_search_text(category)
    name_text = normalize_search_text(name)
    description_text = normalize_search_text(description)
    combined = " ".join([category_text, name_text, description_text])

    for option in FOOD_CUISINE_OPTIONS:
        if normalize_search_text(option) in combined:
            return option
    if "齐齐哈尔" in name_text or "东北" in combined:
        return "东北菜"
    if "湘" in combined or "老湘村" in name_text:
        return "湘菜"
    if "川" in combined or "麻辣" in combined or "冒菜" in combined:
        return "川菜"
    if "火锅" in combined or "牛肉锅" in combined or "鸡煲" in combined:
        return "火锅"
    if "自助" in combined or "放题" in combined:
        return "自助"
    if "烧烤" in combined or "烤肉" in combined or "烤串" in combined:
        return "烧烤"
    if "印度" in combined or "india" in combined:
        return "印度菜"
    if "肠粉" in combined or "潮汕" in combined or "广式" in combined or "广东" in combined:
        return "粤菜"
    if "炸串" in combined or "小吃" in combined:
        return "小吃"
    if "自动售货机" in name_text or "售货机" in name_text:
        return "饮品"
    if "奶茶" in combined or "益禾堂" in name_text or "古茗" in name_text or "蜜雪" in name_text or "茶饮" in combined:
        return "奶茶"
    if "咖啡" in combined or "coffee" in name_text or "瑞幸" in name_text:
        return "咖啡"
    if "肯德基" in name_text or "kfc" in name_text or "快餐" in combined:
        return "快餐"
    if "面" in combined or "粉" in combined or "烙锅" in name_text:
        return "面食"
    if "超市" in combined or "便利" in combined or "商店" in combined:
        return "超市便利"
    if "食堂" in combined:
        return "食堂"
    if "饮" in combined:
        return "饮品"
    if "餐饮" in combined or "餐厅" in combined or "饭店" in combined:
        return "家常菜"
    return "其他餐饮"

def food_default_profile(category, name=""):
    category_text = normalize_search_text(category)
    name_text = normalize_search_text(name)

    profile = {
        "食堂": (4.4, 82, 18),
        "其他餐饮": (4.3, 76, 28),
        "家常菜": (4.2, 72, 26),
        "东北菜": (4.3, 74, 32),
        "川菜": (4.3, 76, 30),
        "湘菜": (4.3, 76, 30),
        "火锅": (4.4, 84, 52),
        "自助": (4.3, 80, 58),
        "烧烤": (4.2, 78, 42),
        "咖啡": (4.4, 78, 24),
        "超市便利": (4.0, 64, 15),
        "快餐": (4.2, 80, 22),
        "小吃": (4.1, 72, 14),
        "面食": (4.2, 68, 20),
        "粉面": (4.1, 68, 20),
        "粤菜": (4.2, 70, 28),
        "西餐": (4.1, 66, 36),
        "印度菜": (4.2, 68, 34),
        "奶茶": (4.1, 76, 14),
        "饮品": (4.0, 66, 16),
    }
    rating, popularity, avg_cost = profile.get(category, (4.2, 70, 22))

    if "肯德基" in name_text or "kfc" in name_text:
        rating += 0.1
        popularity += 8
        avg_cost += 6
    elif "瑞幸" in name_text or "蜜雪" in name_text or "coffee" in name_text:
        rating += 0.1
        popularity += 5
    elif "食堂" in category_text:
        popularity += 4
    elif "超市" in category_text:
        popularity += 2

    return round(min(rating, 5.0), 1), int(popularity), round(avg_cost, 1)

def food_media_lookup_keys(food):
    return [
        str(food.get("food_key") or "").strip(),
        str(food.get("id") or "").strip(),
        str(food.get("name") or "").strip(),
    ]

def visible_food_tags(tags, category=""):
    hidden = {
        "餐饮",
        "校园",
        "手动采集",
        "采集餐饮",
        "手动采集点",
        "模块三按道路图距离排序",
        "超市",
        "便利店",
        "超市便利",
    }
    normalized_category = str(category or "").strip()
    visible = []
    seen = set()
    for tag in normalize_tags(tags):
        cleaned = tag.strip(" ·，,。；;")
        if not cleaned or cleaned in hidden:
            continue
        if cleaned == normalized_category:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        visible.append(cleaned)
    return visible

def food_display_description(description, category="", source_kind=""):
    text = re.sub(r"\s+", " ", str(description or "").strip())
    generic_patterns = (
        "餐饮，手动采集，模块三按道路图距离排序。",
        "餐饮，手动采集，按道路图距离排序。",
        "餐饮 ·",
    )
    if not text or any(text.startswith(pattern) for pattern in generic_patterns):
        category_text = str(category or "美食").strip()
        if source_kind == "graph_node":
            return f"{category_text}窗口，来自路线图数据补位，已接入道路距离推荐。"
        return f"{category_text}店铺，已接入路线图距离排序。"
    return text.replace("模块三", "").replace("餐饮，", "").strip(" ，,")

def default_signature_dishes(category, avg_cost=22):
    dish_map = {
        "食堂": ["招牌套餐", "热卤饭", "鲜蔬小炒"],
        "快餐": ["脆皮汉堡", "香辣鸡块", "经典薯条"],
        "奶茶": ["招牌奶茶", "芝士果茶", "珍珠鲜奶"],
        "咖啡": ["拿铁咖啡", "冷萃咖啡", "可颂套餐"],
        "火锅": ["鲜切牛肉", "手打虾滑", "时蔬拼盘"],
        "烧烤": ["招牌烤串", "烤肉拼盘", "烤蔬菜"],
        "烤鱼": ["招牌烤鱼", "蒜香鱼片", "香辣配菜"],
        "粤菜": ["潮汕鸡煲", "石磨肠粉", "港式点心"],
        "湘菜": ["小炒黄牛肉", "剁椒鱼片", "农家小炒肉"],
        "川菜": ["香锅冒菜", "麻辣小碗", "口水鸡"],
        "东北菜": ["东北盒饭", "手工饺子", "锅包肉"],
        "印度菜": ["咖喱鸡饭", "香料烤饼", "黄油咖喱"],
        "自助": ["自助披萨", "烤肉拼盘", "甜品杯"],
        "西餐": ["意面套餐", "薄底披萨", "煎烤鸡排"],
        "面食": ["招牌汤面", "拌面小碗", "鲜香粉面"],
        "粉面": ["招牌粉面", "酸辣粉", "热汤米线"],
        "小吃": ["炸串拼盘", "特色小吃", "风味蘸料"],
        "超市便利": ["轻食饭团", "便当套餐", "冰饮零食"],
        "饮品": ["冰爽果饮", "气泡水", "鲜榨果汁"],
    }
    names = dish_map.get(category, ["招牌主食", "人气小吃", "清爽饮品"])
    base = max(8, int(float(avg_cost or 22) * 0.62))
    return [
        {"name": name, "price": f"￥{base + index * 4}", "image": ""}
        for index, name in enumerate(names[:3])
    ]

def default_food_recommendation_note():
    return "系统会综合口碑、人气、人均消费和路线可达性给出推荐；选择当前位置后，会优先参考道路距离。"

def public_food_recommendation_note(note):
    note = str(note or "").strip()
    if not note:
        return default_food_recommendation_note()
    internal_words = ("评分*18", "热度*0.35", "来源加分", "校园加分", "模糊查找与排序算法")
    if any(word in note for word in internal_words):
        return default_food_recommendation_note()
    return note

def coerce_food_number(value, fallback, number_type=float, min_value=None, max_value=None):
    try:
        result = number_type(value)
    except (TypeError, ValueError):
        return fallback
    if min_value is not None:
        result = max(min_value, result)
    if max_value is not None:
        result = min(max_value, result)
    return result

def optional_food_float(value, min_value=None, max_value=None):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        result = float(text)
    except (TypeError, ValueError):
        return None
    if min_value is not None:
        result = max(min_value, result)
    if max_value is not None:
        result = min(max_value, result)
    return result

def food_recommendation_breakdown(food, keyword_terms=None):
    keyword_terms = keyword_terms or []
    name_text = normalize_search_text(food.get("name", ""))
    blob = food_search_blob(food)
    matched_terms = [term for term in keyword_terms if term and term in blob]
    matched_count = len(matched_terms)
    keyword_bonus = matched_count * 12
    name_bonus = 8 if keyword_terms and name_text and any(term in name_text for term in keyword_terms) else 0
    rating_score = round(float(food.get("rating", 0)) * 18, 2)
    popularity_score = round(float(food.get("popularity", 0)) * 0.35, 2)
    cost_score = round(max(0, 34 - float(food.get("avg_cost", 0)) * 0.6), 2)
    distance = food.get("distance_m")
    distance_score = round(max(0, 40 - float(distance) / 30), 2) if distance is not None else 0.0
    source_bonus = 8.0
    campus_bonus = 10.0 if food.get("graph_place_id") in (FOOD_DEFAULT_PLACE_ID, "xmu_xiang_an") else 0.0
    total = round(
        rating_score
        + popularity_score
        + cost_score
        + distance_score
        + keyword_bonus
        + name_bonus
        + source_bonus
        + campus_bonus,
        2,
    )
    return {
        "total": total,
        "rating_score": rating_score,
        "popularity_score": popularity_score,
        "cost_score": cost_score,
        "distance_score": distance_score,
        "keyword_bonus": keyword_bonus,
        "name_bonus": name_bonus,
        "source_bonus": source_bonus,
        "campus_bonus": campus_bonus,
        "matched_terms": matched_terms,
        "formula": "评分*18 + 热度*0.35 + 人均惩罚 + 距离加分 + 关键词加分 + 名称加分 + 来源/校园加分",
    }

def food_search_blob(food):
    tags = food.get("tags_list", [])
    if isinstance(tags, str):
        tags = [tags]
    parts = [
        food.get("name", ""),
        food.get("category", ""),
        food.get("cuisine", ""),
        food.get("facility_type", ""),
        food.get("place_name", ""),
        food.get("description", ""),
        food.get("source_label", ""),
        " ".join(str(tag) for tag in tags if tag),
    ]
    return normalize_search_text(" ".join(str(part) for part in parts if part))

def food_dedupe_key(food):
    return "||".join([
        normalize_search_text(food.get("name", "")),
        normalize_search_text(food.get("place_name", "")),
    ])

def is_food_related_facility(name, facility_type="", description=""):
    name_text = normalize_search_text(name)
    type_text = normalize_search_text(facility_type)
    description_text = normalize_search_text(description)

    direct_type_hits = tuple(["食堂", "餐饮", "咖啡", "快餐", "小吃", "餐厅", *FOOD_CUISINE_OPTIONS])
    name_hits = ("餐厅", "食堂", "咖啡", "超市", "便利", "窗口", "小吃", "快餐", "面馆", "茶饮", "奶茶", "自动售货机", "售货机", "肯德基", "瑞幸", "蜜雪", "火锅", "烤肉", "炸串", "湘菜", "川菜", "自助", "肠粉", "鸡煲")

    if any(token in type_text for token in direct_type_hits):
        return True
    if any(token in name_text for token in name_hits):
        return True
    if "商店" in type_text and any(token in name_text for token in ("超市", "便利", "饮", "零食", "茶", "咖啡")):
        return True
    if any(token in description_text for token in ("餐饮", "咖啡", "食堂", "超市", "窗口", "小吃")):
        return True
    return False

def enrich_food_distance(food, graph, origin_node, route_tree=None):
    if not graph or not origin_node:
        food["distance_m"] = None
        food["distance_text"] = ""
        return food

    nearest_node = food.get("nearest_node") or food.get("graph_node_id")
    if nearest_node not in graph.get("node_map", {}):
        food["distance_m"] = None
        food["distance_text"] = ""
        return food

    if route_tree is None:
        path = dijkstra_shortest_path(graph, origin_node, nearest_node, strategy="distance", transport="walk")
    else:
        path = route_from_shortest_tree(graph, route_tree, nearest_node)
    if path is None:
        food["distance_m"] = None
        food["distance_text"] = "暂未连通"
        return food

    food["distance_m"] = round(path["total"], 1)
    food["distance_text"] = f"{food['distance_m']} 米"
    food["route_path_names"] = path.get("display_path_names", path.get("path_names", []))
    return food

def calculate_food_recommend_score(food, keyword_terms=None):
    return food_recommendation_breakdown(food, keyword_terms=keyword_terms)["total"]

def rank_food_candidates(foods, keyword="", category="", place_name="", sort_by="default", limit=None, graph=None, origin_node=""):
    keyword = keyword.strip()
    category = category.strip()
    place_name = place_name.strip()
    keyword_terms = split_search_terms(keyword) if keyword else []
    normalized_category = normalize_search_text(category)
    normalized_place_name = normalize_search_text(place_name)

    filtered = []
    scanned_count = 0
    candidate_count = 0
    route_tree = dijkstra_shortest_tree(graph, origin_node, strategy="distance", transport="walk") if graph and origin_node else None

    for food in foods:
        scanned_count += 1
        if category and normalize_search_text(food.get("category", "")) != normalized_category:
            continue
        if place_name and normalized_place_name not in food_search_blob(food):
            continue
        if keyword:
            blob = food_search_blob(food)
            if not any(term in blob for term in keyword_terms):
                continue

        candidate_count += 1
        food_copy = food.copy()
        if graph and origin_node:
            enrich_food_distance(food_copy, graph, origin_node, route_tree=route_tree)
        else:
            food_copy["distance_m"] = food_copy.get("distance_m")
        breakdown = food_recommendation_breakdown(food_copy, keyword_terms=keyword_terms)
        food_copy["recommend_score_detail"] = breakdown
        food_copy["recommend_score"] = breakdown["total"]
        food_copy["recommend_score_display"] = round(
            float(food_copy.get("recommend_score_override"))
            if food_copy.get("recommend_score_override") is not None
            else food_copy["recommend_score"],
            2,
        )
        filtered.append(food_copy)

    if sort_by == "distance_asc":
        key_fn = lambda item: item.get("distance_m") if item.get("distance_m") is not None else float("inf")
        ranked = heapq.nsmallest(limit, filtered, key=key_fn) if limit else sorted(filtered, key=key_fn)
    elif sort_by == "rating_asc":
        ranked = heapq.nsmallest(limit, filtered, key=lambda item: (item.get("rating", 0), item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("rating", 0), item.get("recommend_score", 0)))
    elif sort_by == "rating_desc":
        ranked = heapq.nlargest(limit, filtered, key=lambda item: (item.get("rating", 0), item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("rating", 0), item.get("recommend_score", 0)), reverse=True)
    elif sort_by == "popularity_asc":
        ranked = heapq.nsmallest(limit, filtered, key=lambda item: (item.get("popularity", 0), item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("popularity", 0), item.get("recommend_score", 0)))
    elif sort_by == "popularity_desc":
        ranked = heapq.nlargest(limit, filtered, key=lambda item: (item.get("popularity", 0), item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("popularity", 0), item.get("recommend_score", 0)), reverse=True)
    elif sort_by == "avg_cost_asc":
        ranked = heapq.nsmallest(limit, filtered, key=lambda item: (item.get("avg_cost", 0), -item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("avg_cost", 0), -item.get("recommend_score", 0)))
    elif sort_by == "avg_cost_desc":
        ranked = heapq.nlargest(limit, filtered, key=lambda item: (item.get("avg_cost", 0), item.get("recommend_score", 0))) if limit else sorted(filtered, key=lambda item: (item.get("avg_cost", 0), item.get("recommend_score", 0)), reverse=True)
    else:
        ranked = heapq.nlargest(limit, filtered, key=lambda item: (item.get("recommend_score", 0), item.get("rating", 0), item.get("popularity", 0))) if limit else sorted(filtered, key=lambda item: (item.get("recommend_score", 0), item.get("rating", 0), item.get("popularity", 0)), reverse=True)

    algorithm_parts = []
    if keyword_terms:
        algorithm_parts.append("模糊查找")
    if limit:
        algorithm_parts.append("Top-K 堆排序")
    else:
        algorithm_parts.append("完整排序")
    if graph and origin_node:
        algorithm_parts.append("Dijkstra 最短路树")

    stats = {
        "scanned_count": scanned_count,
        "candidate_count": candidate_count,
        "returned_count": len(ranked),
        "algorithm": " + ".join(algorithm_parts),
    }
    return ranked, stats
