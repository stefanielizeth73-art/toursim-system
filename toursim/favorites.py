import json
from dataclasses import dataclass
from datetime import datetime

from .compression import parse_diary_package
from .food_catalog import FOOD_DEFAULT_PLACE_ID


@dataclass
class FavoriteServices:
    get_db_connection: object
    get_diary_by_id: object
    get_food_by_key: object
    load_diaries: object


_services = None


def configure_favorites(services):
    global _services
    _services = services


def _require_services():
    if _services is None:
        raise RuntimeError("Favorite services have not been configured")
    return _services


def get_db_connection():
    return _require_services().get_db_connection()


def get_diary_by_id(*args, **kwargs):
    return _require_services().get_diary_by_id(*args, **kwargs)


def get_food_by_key(*args, **kwargs):
    return _require_services().get_food_by_key(*args, **kwargs)


def load_diaries(*args, **kwargs):
    return _require_services().load_diaries(*args, **kwargs)

def favorite_key(value):
    return str(value or "").strip()

def is_item_favorited(user_id, item_type, item_key):
    if not user_id:
        return False
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM user_favorites WHERE user_id = ? AND item_type = ? AND item_key = ?",
        (user_id, item_type, favorite_key(item_key))
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def toggle_user_favorite(user_id, item_type, item_key, title="", subtitle="", meta=None):
    item_key = favorite_key(item_key)
    meta = meta if isinstance(meta, dict) else {}
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM user_favorites WHERE user_id = ? AND item_type = ? AND item_key = ?",
        (user_id, item_type, item_key)
    )
    existing = cursor.fetchone()
    favorited = False
    if existing:
        cursor.execute("DELETE FROM user_favorites WHERE id = ?", (existing["id"],))
    else:
        cursor.execute(
            """
            INSERT INTO user_favorites (user_id, item_type, item_key, title, subtitle, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                item_type,
                item_key,
                title or "",
                subtitle or "",
                json.dumps(meta, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        favorited = True
    conn.commit()
    conn.close()
    return favorited

def load_user_favorites(user_id, item_type="", limit=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    params = [user_id]
    where = "WHERE user_id = ?"
    if item_type:
        where += " AND item_type = ?"
        params.append(item_type)
    sql = f"SELECT * FROM user_favorites {where} ORDER BY created_at DESC, id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    cursor.execute(sql, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    for row in rows:
        row["meta"] = parse_diary_package(row.get("meta_json")) or {}
    return rows

def load_favorite_diaries(user_id, limit=None):
    favorites = load_user_favorites(user_id, "diary", limit=limit)
    diaries = []
    for favorite in favorites:
        try:
            diary_id = int(favorite["item_key"])
        except (TypeError, ValueError):
            continue
        diary = get_diary_by_id(diary_id, increase_views=False)
        if diary:
            diary["favorite_created_at"] = favorite["created_at"]
            diaries.append(diary)
    return diaries

def load_favorite_foods(user_id, limit=None):
    favorites = load_user_favorites(user_id, "food", limit=limit)
    foods = []
    for favorite in favorites:
        meta = favorite.get("meta", {})
        place_id = meta.get("place_id") or FOOD_DEFAULT_PLACE_ID
        origin_node = meta.get("origin_node") or ""
        food = get_food_by_key(favorite["item_key"], place_id=place_id, origin_node=origin_node)
        if food is None:
            food = {
                "food_key": favorite["item_key"],
                "name": favorite.get("title") or "已收藏美食",
                "display_description": favorite.get("subtitle") or "该美食数据暂未加载",
                "cuisine": meta.get("cuisine", ""),
                "rating": meta.get("rating", 0),
                "avg_cost": meta.get("avg_cost", 0),
                "cover_image": meta.get("cover_image") or "food_media/shops/food-cover-placeholder.jpg",
                "missing": True,
            }
        food["favorite_created_at"] = favorite["created_at"]
        food["favorite_place_id"] = place_id
        food["favorite_origin_node"] = origin_node
        foods.append(food)
    return foods

def load_user_diaries(username, limit=None):
    user_diaries = [diary for diary in load_diaries(sort_by="created_desc") if diary.get("author") == username]
    return user_diaries[:limit] if limit else user_diaries

def get_user_activity_stats(user):
    username = user["username"]
    own_diaries = load_user_diaries(username)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM diary_comments WHERE author = ?", (username,))
    comment_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ?", (user["id"],))
    favorite_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ? AND item_type = 'diary'", (user["id"],))
    favorite_diary_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_favorites WHERE user_id = ? AND item_type = 'food'", (user["id"],))
    favorite_food_count = cursor.fetchone()[0]
    conn.close()
    total_views = sum(int(diary.get("views", 0)) for diary in own_diaries)
    rated_diaries = [diary for diary in own_diaries if diary.get("avg_rating", 0)]
    avg_rating = round(sum(diary["avg_rating"] for diary in rated_diaries) / len(rated_diaries), 1) if rated_diaries else 0
    return {
        "diary_count": len(own_diaries),
        "comment_count": comment_count,
        "favorite_count": favorite_count,
        "favorite_diary_count": favorite_diary_count,
        "favorite_food_count": favorite_food_count,
        "total_views": total_views,
        "avg_rating": avg_rating,
    }
