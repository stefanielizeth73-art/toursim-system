import heapq
import random
import re

from .search import normalize_search_text, split_search_terms


def parse_place_tag_query(tag_keyword):
    return [
        item.strip()
        for item in re.split(r"[;；,，\s]+", tag_keyword or "")
        if item.strip()
    ]

def place_matches_filters(place, keyword="", tag_keyword="", place_type="", city=""):
    # 查询阶段先做候选集过滤：关键词拆词后必须都命中景点信息块。
    # 这样后面的排序/Top-K只处理有效候选，避免把无关数据送入推荐堆。
    if keyword:
        keyword_terms = split_search_terms(keyword) or [normalize_search_text(keyword)]
        place_blob = place_search_blob(place)
        if not all(term in place_blob for term in keyword_terms if term):
            return False

    # 标签查询单独处理，支持用户按兴趣标签缩小候选范围。
    if tag_keyword:
        query_tags = [normalize_search_text(item) for item in parse_place_tag_query(tag_keyword)]
        place_tags = normalize_search_text(place.get("tags", ""))
        if not all(tag in place_tags for tag in query_tags if tag):
            return False

    if place_type and place.get("type") != place_type:
        return False

    if city and place.get("city") != city:
        return False

    return True

def filter_place_candidates(places, keyword="", tag_keyword="", place_type="", city=""):
    return [
        place for place in places
        if place_matches_filters(
            place,
            keyword=keyword,
            tag_keyword=tag_keyword,
            place_type=place_type,
            city=city,
        )
    ]

def filter_and_sort_places(places, keyword="", tag_keyword="", place_type="", city="", sort_by="default"):
    result = filter_place_candidates(
        places,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
    )

    if sort_by == "rating_desc":
        result = sorted(result, key=lambda x: x["rating"], reverse=True)
    elif sort_by == "rating_asc":
        result = sorted(result, key=lambda x: x["rating"])
    elif sort_by == "popularity_desc":
        result = sorted(result, key=lambda x: x["popularity"], reverse=True)
    elif sort_by == "popularity_asc":
        result = sorted(result, key=lambda x: x["popularity"])
    elif sort_by == "recommend_score_desc":
        result = sorted(result, key=lambda x: x.get("recommend_score_display", x.get("recommend_score", 0)), reverse=True)

    return result

def get_place_filter_options(places):
    return {
        "cities": sorted({place["city"] for place in places if place.get("city")}),
        "place_types": sorted({place["type"] for place in places if place.get("type")}),
        "tags": sorted({
            tag
            for place in places
            for tag in place.get("tags_list", [])
        }),
    }

def place_search_blob(place):
    return normalize_search_text(" ".join([
        place.get("name", ""),
        place.get("city", ""),
        place.get("type", ""),
        place.get("tags", ""),
        place.get("description", ""),
    ]))

def get_place_name_options(places):
    options = []
    seen = set()
    for place in places:
        name = str(place.get("name", "")).strip()
        if name and name not in seen:
            options.append(name)
            seen.add(name)
    return options

def find_place_match(destination, places):
    destination_key = normalize_search_text(destination)
    if not destination_key:
        return None

    exact_matches = [place for place in places if normalize_search_text(place.get("name", "")) == destination_key]
    if exact_matches:
        return exact_matches[0]

    contains_matches = [
        place for place in places
        if destination_key in normalize_search_text(place.get("name", ""))
        or normalize_search_text(place.get("name", "")) in destination_key
    ]
    if len(contains_matches) == 1:
        return contains_matches[0]
    if contains_matches and len(destination_key) >= 4:
        return max(contains_matches, key=lambda place: (place.get("rating", 0), place.get("popularity", 0)))

    return None

def get_related_places_for_diary(diary, places, limit=6):
    diary_text = normalize_search_text(" ".join([
        diary.get("title", ""),
        diary.get("destination", ""),
        diary.get("content", ""),
    ]))
    diary_terms = set(split_search_terms(diary_text))
    destination_key = normalize_search_text(diary.get("destination", ""))
    has_exact_destination = any(
        destination_key and destination_key == normalize_search_text(place.get("name", ""))
        for place in places
    )

    scored = []
    for place in places:
        name_key = normalize_search_text(place.get("name", ""))
        city_key = normalize_search_text(place.get("city", ""))
        tag_keys = [normalize_search_text(tag) for tag in place.get("tags_list", [])]
        compact_place_text = normalize_search_text(" ".join([
            place.get("name", ""),
            place.get("city", ""),
            place.get("type", ""),
            place.get("tags", ""),
        ]))

        relevance_score = 0
        strong_relation = 0

        if destination_key and destination_key == name_key:
            relevance_score += 1000
            strong_relation += 1000
        elif destination_key and (destination_key in name_key or name_key in destination_key):
            relevance_score += 700
            strong_relation += 700
        elif not has_exact_destination and destination_key and destination_key in city_key:
            relevance_score += 220
            strong_relation += 220
        elif name_key and name_key in diary_text:
            relevance_score += 500
            strong_relation += 500
        elif not has_exact_destination and city_key and city_key in diary_text:
            relevance_score += 120
            strong_relation += 120

        tag_hits = 0
        for tag_key in tag_keys:
            if tag_key and tag_key in diary_text:
                tag_hits += 1
        relevance_score += tag_hits * 45

        keyword_hits = sum(
            1 for term in diary_terms
            if len(term) >= 2 and term in compact_place_text
        )
        if keyword_hits:
            relevance_score += keyword_hits * 20

        if has_exact_destination and strong_relation == 0:
            continue

        if relevance_score > 0 and strong_relation > 0:
            popularity_score = place.get("rating", 0) * 20 + place.get("popularity", 0) * 0.18
            exact_bonus = 1 if destination_key and destination_key == name_key else 0
            scored.append((relevance_score, exact_bonus, popularity_score, place))

    return [
        place for _relevance, _exact_bonus, _popularity_score, place
        in heapq.nlargest(limit, scored, key=lambda item: (item[0], item[1], item[2]))
    ]

def get_related_diaries_for_place(place, diaries, limit=6):
    place_name_key = normalize_search_text(place.get("name", ""))
    city_key = normalize_search_text(place.get("city", ""))
    tag_keys = [normalize_search_text(tag) for tag in place.get("tags_list", [])]

    scored = []
    for diary in diaries:
        diary_text = normalize_search_text(" ".join([
            diary.get("title", ""),
            diary.get("destination", ""),
            diary.get("content", ""),
        ]))
        diary_destination_key = normalize_search_text(diary.get("destination", ""))
        relevance_score = 0
        strong_relation = 0

        if place_name_key and diary_destination_key == place_name_key:
            relevance_score += 1000
            strong_relation += 1000
        elif place_name_key and (place_name_key in diary_destination_key or diary_destination_key in place_name_key):
            relevance_score += 700
            strong_relation += 700
        elif place_name_key and place_name_key in diary_text:
            relevance_score += 500
            strong_relation += 500
        elif city_key and city_key == diary_destination_key:
            relevance_score += 220
            strong_relation += 220

        tag_hits = 0
        for tag_key in tag_keys:
            if tag_key and (tag_key in diary_text or tag_key in diary_destination_key):
                tag_hits += 1
        relevance_score += tag_hits * 45

        if relevance_score > 0 and strong_relation > 0:
            heat_score = diary.get("views", 0) * 0.8 + diary.get("avg_rating", 0) * 20 + diary.get("rating_count", 0) * 4
            exact_bonus = 1 if place_name_key and diary_destination_key == place_name_key else 0
            scored.append((relevance_score, exact_bonus, heat_score, diary))

    return [
        diary for _relevance, _exact_bonus, _heat_score, diary
        in heapq.nlargest(limit, scored, key=lambda item: (item[0], item[1], item[2]))
    ]

def calculate_base_score(place):
    """
    基础推荐分：
    评分占 60%
    热度占 40%
    热度做一个缩放，避免数值差太大
    """
    # 基础推荐分：rating * 60突出景点评价质量；
    # popularity * 0.4引入热度但做缩放，避免热度数值过大压制评分。
    return place["rating"] * 60 + place["popularity"] * 0.4

def calculate_personalized_score(place, preferred_tags):
    score = calculate_base_score(place)

    # 个性化部分使用兴趣标签命中数加分；标签越贴合用户偏好，排序越靠前。
    matched_tags = 0
    for tag in preferred_tags:
        if tag and tag in place["tags_list"]:
            matched_tags += 1

    # 每命中一个兴趣标签加15分，既能体现偏好，又不会完全覆盖评分和热度。
    score += matched_tags * 15
    return score

def normalize_preferred_place_tags(places, preferred_tags):
    available_tags = {
        tag
        for place in places
        for tag in place.get("tags_list", [])
    }
    normalized = []
    seen = set()
    for tag in preferred_tags or []:
        tag = str(tag).strip()
        if tag and tag in available_tags and tag not in seen:
            normalized.append(tag)
            seen.add(tag)
    return normalized

def place_matches_preferred_tags(place, preferred_tags):
    if not preferred_tags:
        return True
    return count_preferred_tag_matches(place, preferred_tags) > 0

def count_preferred_tag_matches(place, preferred_tags):
    place_tags = set(place.get("tags_list", []))
    return sum(1 for tag in preferred_tags if tag in place_tags)

def place_identity(place):
    return str(place.get("id") or place.get("name") or "")

def random_fill_places(places, selected_places, fill_count):
    if fill_count <= 0:
        return []

    selected_keys = {place_identity(place) for place in selected_places}
    fill_pool = [
        place for place in places
        if place_identity(place) and place_identity(place) not in selected_keys
    ]
    if not fill_pool:
        return []

    fillers = random.sample(fill_pool, min(fill_count, len(fill_pool)))
    result = []
    for place in fillers:
        place_copy = place.copy()
        place_copy["recommend_score"] = calculate_base_score(place_copy)
        place_copy["matched_preferred_tag_count"] = 0
        place_copy["matched_all_preferred_tags"] = False
        place_copy["is_random_fill"] = True
        result.append(place_copy)
    return result

def get_top_k_recommendations(places, preferred_tags=None, k=10, place_type="", city="", keyword="", tag_keyword=""):
    preferred_tags = normalize_preferred_place_tags(places, preferred_tags)

    # 小根堆只保存当前最优的K个景点。课程要求关注前10个结果，
    # 因此不必对全部候选完整排序，复杂度从O(N log N)降为O(N log K)。
    heap = []
    scanned_count = 0
    candidate_count = 0

    for index, place in enumerate(places):
        scanned_count += 1
        if not place_matches_filters(
            place,
            keyword=keyword,
            tag_keyword=tag_keyword,
            place_type=place_type,
            city=city,
        ):
            continue

        if not place_matches_preferred_tags(place, preferred_tags):
            continue

        candidate_count += 1
        place_copy = place.copy()
        matched_tag_count = count_preferred_tag_matches(place_copy, preferred_tags)
        place_copy["recommend_score"] = calculate_personalized_score(place_copy, preferred_tags)
        place_copy["matched_preferred_tag_count"] = matched_tag_count
        place_copy["matched_all_preferred_tags"] = bool(preferred_tags) and matched_tag_count == len(preferred_tags)

        ranking_key = (
            1 if place_copy["matched_all_preferred_tags"] else 0,
            matched_tag_count,
            place_copy["recommend_score"],
        )
        item = (ranking_key, -index, place_copy)
        if len(heap) < k:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            # 当前候选优于堆顶的“第K名”时才替换，堆内始终保持前K个高分景点。
            heapq.heapreplace(heap, item)

    # 最后只对K个入选结果做展示排序，不再对全部候选排序。
    # Only the k selected records are sorted for display.
    result = [item[2] for item in sorted(heap, key=lambda x: (x[0], x[1]), reverse=True)]
    random_fill_count = max(0, k - len(result))
    if random_fill_count:
        result.extend(random_fill_places(places, result, random_fill_count))
    stats = {
        "scanned_count": scanned_count,
        "candidate_count": candidate_count,
        "returned_count": len(result),
        "random_fill_count": random_fill_count,
        "preferred_tags": preferred_tags,
        "algorithm": "模糊查找 + 小根堆 Top-K",
    }
    return result, stats
