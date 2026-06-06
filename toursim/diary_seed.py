import json
import os


DIARY_COLUMNS = (
    "id",
    "title",
    "destination",
    "content",
    "author",
    "views",
    "rating_total",
    "rating_count",
    "created_at",
    "media_json",
    "compressed_content",
    "compression_algorithm",
    "compression_original_length",
    "compression_compressed_length",
)

DIARY_COMMENT_COLUMNS = (
    "id",
    "diary_id",
    "parent_id",
    "author",
    "avatar_path",
    "content",
    "like_count",
    "created_at",
)

DIARY_RATING_COLUMNS = (
    "id",
    "diary_id",
    "username",
    "rating",
    "created_at",
)


def load_seed_payload(seed_path):
    if not seed_path or not os.path.exists(seed_path):
        return {}
    with open(seed_path, "r", encoding="utf-8") as file:
        return json.load(file)


def upsert_rows(cursor, table_name, columns, rows):
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(columns))
    column_list = ", ".join(columns)
    update_columns = [column for column in columns if column != "id"]
    update_clause = ", ".join([f"{column} = excluded.{column}" for column in update_columns])
    sql = f"""
        INSERT INTO {table_name} ({column_list})
        VALUES ({placeholders})
        ON CONFLICT(id) DO UPDATE SET {update_clause}
    """
    values = [tuple(row.get(column) for column in columns) for row in rows]
    cursor.executemany(sql, values)


def seed_demo_diaries(cursor, seed_path):
    payload = load_seed_payload(seed_path)
    seed_diaries = payload.get("diaries") or []
    if not seed_diaries:
        return 0

    cursor.execute("SELECT COUNT(*) FROM diaries")
    current_count = int(cursor.fetchone()[0])
    if current_count >= len(seed_diaries):
        return 0

    upsert_rows(cursor, "diaries", DIARY_COLUMNS, seed_diaries)
    upsert_rows(cursor, "diary_comments", DIARY_COMMENT_COLUMNS, payload.get("diary_comments") or [])
    upsert_rows(cursor, "diary_ratings", DIARY_RATING_COLUMNS, payload.get("diary_ratings") or [])
    return len(seed_diaries)
