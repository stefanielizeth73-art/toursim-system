import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from werkzeug.utils import secure_filename

from .compression import compress_diary_text, parse_diary_package
from .diary_media import (
    diary_media_folder,
    diary_media_public_url,
    diary_media_thumbnail_public_url,
    probe_image_size,
)
from .diary_search import (
    filter_diaries_by_destination,
    search_diaries_by_keyword,
    search_diaries_by_title,
    sort_diaries,
)
from .search import normalize_search_text, split_search_terms


@dataclass
class DiaryRepositoryServices:
    get_db_connection: object
    ensure_diaries_table: object
    get_diary_index_cache: object
    invalidate_diary_index_cache: object
    sync_diary_index_view_count: object
    build_diary_comment_tree: object
    get_user_by_username: object
    ensure_user_avatar_asset: object


_services = None


def configure_diary_repository(services):
    global _services
    _services = services


def _require_services():
    if _services is None:
        raise RuntimeError("Diary repository services have not been configured")
    return _services


def get_db_connection():
    return _require_services().get_db_connection()


def ensure_diaries_table():
    return _require_services().ensure_diaries_table()


def get_diary_index_cache():
    return _require_services().get_diary_index_cache()


def invalidate_diary_index_cache():
    return _require_services().invalidate_diary_index_cache()


def sync_diary_index_view_count(*args, **kwargs):
    return _require_services().sync_diary_index_view_count(*args, **kwargs)


def build_diary_comment_tree(*args, **kwargs):
    return _require_services().build_diary_comment_tree(*args, **kwargs)


def get_user_by_username(*args, **kwargs):
    return _require_services().get_user_by_username(*args, **kwargs)


def ensure_user_avatar_asset(*args, **kwargs):
    return _require_services().ensure_user_avatar_asset(*args, **kwargs)

def diary_compression_summary(diary):
    package = parse_diary_package(diary.get("compressed_content"))
    if not package:
        return {
            "algorithm": diary.get("compression_algorithm", "plain"),
            "original_length": diary.get("compression_original_length", 0),
            "compressed_length": diary.get("compression_compressed_length", 0),
            "ratio": 0,
        }

    original_length = diary.get("compression_original_length", 0) or 0
    compressed_length = diary.get("compression_compressed_length", 0) or 0
    ratio = round(compressed_length / original_length, 3) if original_length else 0
    return {
        "algorithm": package.get("algorithm", diary.get("compression_algorithm", "plain")),
        "original_length": original_length,
        "compressed_length": compressed_length,
        "ratio": ratio,
        "package": package,
    }

def attach_diary_stats(row):
    diary = dict(row)
    if diary["rating_count"]:
        diary["avg_rating"] = round(diary["rating_total"] / diary["rating_count"], 1)
    else:
        diary["avg_rating"] = 0
    diary["content_preview"] = diary["content"][:70] + ("..." if len(diary["content"]) > 70 else "")
    diary["media_items"] = parse_diary_package(diary.get("media_json")) or []
    for item in diary["media_items"]:
        filename = item.get("filename")
        if filename:
            item["url"] = diary_media_public_url(diary["id"], filename)
            if item.get("kind") == "image":
                item["thumbnail_url"] = diary_media_thumbnail_public_url(diary["id"], filename)
            if item.get("kind") == "image" and (not item.get("width") or not item.get("height")):
                file_path = os.path.join(diary_media_folder(diary["id"]), filename)
                if os.path.exists(file_path):
                    width, height = probe_image_size(file_path)
                    if width and height:
                        item["width"], item["height"] = width, height
        if item.get("kind") == "image" and item.get("width") and item.get("height"):
            item["aspect_ratio"] = round(item["width"] / item["height"], 4) if item["height"] else 1
    diary["media_count"] = len(diary["media_items"])
    diary["image_count"] = sum(1 for item in diary["media_items"] if item.get("kind") == "image")
    diary["video_count"] = sum(1 for item in diary["media_items"] if item.get("kind") == "video")
    diary["has_media"] = diary["media_count"] > 0
    image_items = [item for item in diary["media_items"] if item.get("kind") == "image"]
    video_items = [item for item in diary["media_items"] if item.get("kind") == "video"]
    other_items = [item for item in diary["media_items"] if item.get("kind") not in {"image", "video"}]
    diary["cover_media"] = image_items[0] if image_items else (diary["media_items"][0] if diary["media_items"] else None)
    diary["gallery_items"] = (image_items + video_items + other_items)[:12]
    diary["cover_summary"] = diary["content_preview"]
    diary["compression"] = diary_compression_summary(diary)
    return diary

def load_diaries(title_query="", search_mode="exact", keyword="", destination="", sort_by="created_desc"):
    ensure_diaries_table()
    index_cache = get_diary_index_cache()
    diaries = [dict(row) for row in index_cache.get("display_records") or []]

    diaries = search_diaries_by_title(diaries, title_query, search_mode, index_cache=index_cache)
    diaries = search_diaries_by_keyword(diaries, keyword, index_cache=index_cache)
    diaries = filter_diaries_by_destination(diaries, destination)

    diaries = sort_diaries(diaries, sort_by)

    return diaries

def get_diary_search_results(query="", index_cache=None):
    diaries = load_diaries(sort_by="hot_rating_desc")
    normalized_query = normalize_search_text(query)
    if not normalized_query:
        return diaries

    index_cache = index_cache or get_diary_index_cache()
    query_terms = split_search_terms(query)
    ranked = []
    for diary in diaries:
        combined_text = " ".join([diary["title"], diary["destination"], diary["content"], diary["author"]])
        normalized_text = normalize_search_text(combined_text)
        score = 0
        if normalize_search_text(diary["title"]) == normalized_query:
            score += 160
        if normalized_query in normalize_search_text(diary["title"]):
            score += 120
        if normalized_query in normalized_text:
            score += 80
        if query_terms:
            term_hits = sum(1 for term in query_terms if term in normalized_text)
            score += term_hits * 22
        if diary.get("avg_rating", 0):
            score += diary["avg_rating"] * 8
        if diary.get("views", 0):
            score += min(diary["views"], 4000) / 80
        if diary.get("author", "") and normalized_query in normalize_search_text(diary["author"]):
            score += 25
        if diary.get("destination", "") and normalized_query in normalize_search_text(diary["destination"]):
            score += 35
        if score > 0:
            ranked.append((score, diary))

    ranked.sort(key=lambda item: (-item[0], -item[1].get("avg_rating", 0), -item[1].get("views", 0), item[1]["id"]))
    return [diary for _score, diary in ranked]

def create_diary(title, destination, content, author, compression_algorithm="huffman", media_items=None):
    ensure_diaries_table()
    compression_package, original_length, compressed_length = compress_diary_text(content, compression_algorithm)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO diaries
        (title, destination, content, author, views, rating_total, rating_count, created_at, media_json, compressed_content, compression_algorithm, compression_original_length, compression_compressed_length)
        VALUES (?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            destination,
            content,
            author,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            json.dumps(media_items or [], ensure_ascii=False),
            json.dumps(compression_package, ensure_ascii=False),
            compression_package["algorithm"],
            original_length,
            compressed_length,
        )
    )
    diary_id = cursor.lastrowid
    conn.commit()
    conn.close()
    invalidate_diary_index_cache()
    return diary_id

def update_diary_media(diary_id, media_items):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE diaries SET media_json = ? WHERE id = ?",
        (json.dumps(media_items or [], ensure_ascii=False), diary_id)
    )
    conn.commit()
    conn.close()
    invalidate_diary_index_cache()

def stored_diary_media_items(diary):
    return parse_diary_package(diary.get("media_json")) or []

def get_diary_by_id(diary_id, increase_views=False):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    if increase_views:
        cursor.execute("UPDATE diaries SET views = views + 1 WHERE id = ?", (diary_id,))
        conn.commit()
    cursor.execute("SELECT * FROM diaries WHERE id = ?", (diary_id,))
    row = cursor.fetchone()
    conn.close()
    if increase_views:
        sync_diary_index_view_count(diary_id)
    return attach_diary_stats(row) if row else None

def get_diary_compression_preview(diary_id, algorithm=None):
    diary = get_diary_by_id(diary_id, increase_views=False)
    if diary is None:
        return None
    selected_algorithm = algorithm or diary.get("compression", {}).get("algorithm", "huffman")
    package, original_length, compressed_length = compress_diary_text(diary["content"], selected_algorithm)
    return {
        "diary": diary,
        "package": package,
        "original_length": original_length,
        "compressed_length": compressed_length,
        "ratio": round(compressed_length / original_length, 3) if original_length else 0,
    }

def update_diary_compression_algorithm(diary_id, algorithm):
    diary = get_diary_by_id(diary_id, increase_views=False)
    if diary is None:
        return None
    compression_package, original_length, compressed_length = compress_diary_text(diary["content"], algorithm)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE diaries
        SET compressed_content = ?,
            compression_algorithm = ?,
            compression_original_length = ?,
            compression_compressed_length = ?
        WHERE id = ?
        """,
        (
            json.dumps(compression_package, ensure_ascii=False),
            compression_package["algorithm"],
            original_length,
            compressed_length,
            diary_id,
        ),
    )
    conn.commit()
    conn.close()
    invalidate_diary_index_cache()
    return get_diary_by_id(diary_id, increase_views=False)

def rate_diary(diary_id, rating):
    ensure_diaries_table()
    rating = max(1, min(5, int(rating)))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE diaries
        SET rating_total = rating_total + ?, rating_count = rating_count + 1
        WHERE id = ?
        """,
        (rating, diary_id)
    )
    conn.commit()
    conn.close()
    invalidate_diary_index_cache()

def get_diary_user_rating(diary_id, username):
    ensure_diaries_table()
    username = (username or "").strip()
    if not username:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT rating FROM diary_ratings WHERE diary_id = ? AND username = ?",
        (diary_id, username),
    )
    row = cursor.fetchone()
    conn.close()
    return int(row["rating"]) if row else None

def rate_diary_once(diary_id, username, rating):
    ensure_diaries_table()
    username = (username or "").strip()
    if not username:
        return False
    rating = max(1, min(5, int(rating)))
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO diary_ratings (diary_id, username, rating, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (diary_id, username, rating, datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        cursor.execute(
            """
            UPDATE diaries
            SET rating_total = rating_total + ?, rating_count = rating_count + 1
            WHERE id = ?
            """,
            (rating, diary_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return False
    conn.close()
    invalidate_diary_index_cache()
    return True

def create_diary_comment(diary_id, author, content, parent_id=None):
    ensure_diaries_table()
    content = (content or "").strip()
    if not content:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    parent_comment_id = None
    if parent_id:
        cursor.execute("SELECT id FROM diary_comments WHERE id = ? AND diary_id = ?", (parent_id, diary_id))
        parent_row = cursor.fetchone()
        if parent_row:
            parent_comment_id = int(parent_row["id"])
    user = get_user_by_username(author)
    avatar_path = ensure_user_avatar_asset(user["username"], user["id"], user["avatar_path"]) if user else ""
    cursor.execute(
        """
        INSERT INTO diary_comments (diary_id, parent_id, author, avatar_path, content, like_count, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """,
        (
            diary_id,
            parent_comment_id,
            author,
            avatar_path,
            content,
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
    )
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return comment_id

def load_diary_comments(diary_id, username=None):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    if username:
        cursor.execute(
            """
            SELECT
                diary_comments.*,
                users.id AS author_user_id,
                COALESCE(NULLIF(users.avatar_path, ''), diary_comments.avatar_path) AS resolved_avatar_path,
                EXISTS(
                    SELECT 1
                    FROM diary_comment_likes
                    WHERE diary_comment_likes.comment_id = diary_comments.id
                      AND diary_comment_likes.username = ?
                ) AS liked_by_current_user
            FROM diary_comments
            LEFT JOIN users ON users.username = diary_comments.author
            WHERE diary_id = ?
            ORDER BY like_count DESC, created_at ASC, id ASC
            """,
            (username, diary_id)
        )
    else:
        cursor.execute(
            """
            SELECT
                diary_comments.*,
                users.id AS author_user_id,
                COALESCE(NULLIF(users.avatar_path, ''), diary_comments.avatar_path) AS resolved_avatar_path,
                0 AS liked_by_current_user
            FROM diary_comments
            LEFT JOIN users ON users.username = diary_comments.author
            WHERE diary_id = ?
            ORDER BY like_count DESC, created_at ASC, id ASC
            """,
            (diary_id,)
        )
    rows = cursor.fetchall()
    conn.close()
    comment_threads, lookup = build_diary_comment_tree(rows)
    total_count = len(rows)
    return {
        "threads": comment_threads,
        "total_count": total_count,
        "lookup": lookup,
    }

def toggle_diary_comment_like(comment_id, username):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM diary_comment_likes WHERE comment_id = ? AND username = ?",
        (comment_id, username)
    )
    existing_like = cursor.fetchone()
    liked = False
    if existing_like:
        cursor.execute("DELETE FROM diary_comment_likes WHERE comment_id = ? AND username = ?", (comment_id, username))
        cursor.execute(
            """
            UPDATE diary_comments
            SET like_count = CASE WHEN like_count > 0 THEN like_count - 1 ELSE 0 END
            WHERE id = ?
            """,
            (comment_id,)
        )
    else:
        cursor.execute(
            "INSERT OR IGNORE INTO diary_comment_likes (comment_id, username, created_at) VALUES (?, ?, ?)",
            (comment_id, username, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        if cursor.rowcount:
            liked = True
            cursor.execute("UPDATE diary_comments SET like_count = like_count + 1 WHERE id = ?", (comment_id,))
    cursor.execute("SELECT like_count FROM diary_comments WHERE id = ?", (comment_id,))
    like_count = cursor.fetchone()
    conn.commit()
    conn.close()
    return liked, (like_count["like_count"] if like_count else 0)
