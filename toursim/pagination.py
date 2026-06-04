import math


def parse_positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)


def paginate_items(items, page=1, per_page=20):
    total = len(items)
    per_page = max(1, int(per_page))
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    current_page = max(1, min(parse_positive_int(page), total_pages))
    start = (current_page - 1) * per_page
    end = start + per_page
    return items[start:end], {
        "page": current_page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_page": current_page - 1 if current_page > 1 else 1,
        "next_page": current_page + 1 if current_page < total_pages else total_pages,
    }


def build_page_window(current_page, total_pages, radius=2):
    if total_pages <= 1:
        return [1]
    start = max(1, current_page - radius)
    end = min(total_pages, current_page + radius)
    return list(range(start, end + 1))
