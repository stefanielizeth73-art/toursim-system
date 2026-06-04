import bisect
from collections import defaultdict

from .search import normalize_search_text, split_search_terms


def build_diary_search_index(diaries):
    exact_title_index = defaultdict(list)
    prefix_index = []
    term_index = defaultdict(set)
    normalized_cache = {}

    for diary in diaries:
        diary_id = diary["id"]
        title_key = normalize_search_text(diary["title"])
        destination_key = normalize_search_text(diary["destination"])
        content_key = normalize_search_text(diary["content"])
        combined_text = " ".join([diary["title"], diary["destination"], diary["content"], diary["author"]])

        exact_title_index[title_key].append(diary)
        prefix_index.append((title_key, diary_id, diary))
        normalized_cache[diary_id] = {
            "title": title_key,
            "destination": destination_key,
            "content": content_key,
            "combined": normalize_search_text(combined_text),
        }

        for term in split_search_terms(combined_text):
            term_index[term].add(diary_id)

    prefix_index.sort(key=lambda item: (item[0], item[1]))
    return exact_title_index, prefix_index, term_index, normalized_cache

def search_diaries_by_title(diaries, title_query, search_mode, index_cache=None):
    if not title_query:
        return diaries

    normalized_query = normalize_search_text(title_query)
    index_cache = index_cache or get_diary_index_cache()

    if search_mode == "prefix":
        titles = [item[0] for item in index_cache["prefix_title_index"]]
        left = bisect.bisect_left(titles, normalized_query)
        right = bisect.bisect_left(titles, normalized_query + chr(0x10FFFF))
        matched_ids = [
            index_cache["prefix_title_index"][index][1]
            for index in range(left, right)
            if titles[index].startswith(normalized_query)
        ]
        return [diary for diary in diaries if diary["id"] in set(matched_ids)]

    if search_mode == "contains":
        return [diary for diary in diaries if normalized_query in normalize_search_text(diary["title"])]

    matched_ids = set(index_cache["exact_title_index"].get(normalized_query, []))
    return [diary for diary in diaries if diary["id"] in matched_ids]

def search_diaries_by_keyword(diaries, keyword, index_cache=None):
    if not keyword:
        return diaries

    index_cache = index_cache or get_diary_index_cache()
    normalized_query = normalize_search_text(keyword)
    query_terms = split_search_terms(keyword)

    scores = defaultdict(int)
    if query_terms:
        for term in query_terms:
            for diary_id in index_cache["inverted_index"].get(term, set()):
                scores[diary_id] += 1

    if not scores:
        for diary in diaries:
            combined_text = " ".join([diary["title"], diary["destination"], diary["content"], diary["author"]])
            if normalized_query in normalize_search_text(combined_text):
                scores[diary["id"]] = 1

    ranked_ids = [item[0] for item in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]
    diary_lookup = {diary["id"]: diary for diary in diaries}
    return [diary_lookup[diary_id] for diary_id in ranked_ids if diary_id in diary_lookup]

def filter_diaries_by_destination(diaries, destination):
    if not destination:
        return diaries
    destination_key = normalize_search_text(destination)
    return [diary for diary in diaries if destination_key in normalize_search_text(diary["destination"])]

def sort_diaries(diaries, sort_by):
    if sort_by == "views_desc":
        return sorted(diaries, key=lambda diary: (diary["views"], diary["avg_rating"], diary["created_at"]), reverse=True)
    if sort_by == "rating_desc":
        return sorted(diaries, key=lambda diary: (diary["avg_rating"], diary["views"], diary["created_at"]), reverse=True)
    if sort_by == "hot_rating_desc":
        return sorted(diaries, key=lambda diary: (diary["views"], diary["avg_rating"], diary["rating_count"], diary["created_at"]), reverse=True)
    if sort_by == "title_asc":
        return sorted(diaries, key=lambda diary: normalize_search_text(diary["title"]))
    return sorted(diaries, key=lambda diary: diary["created_at"], reverse=True)
