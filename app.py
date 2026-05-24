from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from collections import defaultdict
import base64
import bisect
import copy
import hashlib
import heapq
import sqlite3
import csv
import itertools
import json
import math
import os
import re
import shutil
import time
from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode
from markupsafe import Markup, escape
try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def load_local_env():
    env_path = os.path.join(APP_DIR, ".env")
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8-sig") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@app.context_processor
def inject_asset_version():
    def asset_version(filename):
        file_path = os.path.join(APP_DIR, "static", filename)
        try:
            return str(int(os.path.getmtime(file_path) * 1000))
        except OSError:
            return str(int(time.time() * 1000))

    return {"asset_version": asset_version}


@app.after_request
def add_no_cache_headers(response):
    if request.endpoint == "static":
        response.headers["Cache-Control"] = "public, max-age=3600"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        return response
    if request.endpoint == "route_graph_data_api":
        response.headers["Cache-Control"] = "private, max-age=60"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        return response
    if os.getenv("FLASK_NO_CACHE", "1").lower() in ("1", "true", "yes", "on"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


load_local_env()

RUNTIME_DATA_DIR = os.getenv("DATA_DIR", APP_DIR)
DB_NAME = os.getenv("DB_NAME", "tourism.db")
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(RUNTIME_DATA_DIR, DB_NAME)
SEED_DB_PATH = os.path.join(APP_DIR, "tourism.db")

PLACES_FILE = os.path.join(APP_DIR, "data", "places.csv")
FACILITIES_FILE = os.path.join(APP_DIR, "data", "facilities.csv")
ROUTE_GRAPHS_DIR = os.path.join(APP_DIR, "data", "graphs")
PLACE_MEDIA_DIR = os.path.join(APP_DIR, "static", "place_media")
DEFAULT_PLACE_ID = "xmu_manual"
MAX_ROUTE_TARGETS = 8
AMAP_JS_KEY = os.getenv("AMAP_JS_KEY", "")
AMAP_SECURITY_JS_CODE = os.getenv("AMAP_SECURITY_JS_CODE", "")
AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY", "")
XMU_MANUAL_PLACE_ID = "xmu_manual"
XMU_MANUAL_GRAPH_FILE = os.path.join(ROUTE_GRAPHS_DIR, "xmu_manual.json")
XMU_COLLECTOR_DIR = os.path.join(APP_DIR, "data", "manual")
XMU_COLLECTOR_NODES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_nodes.json")
XMU_COLLECTOR_EDGES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_edges.json")
XMU_COLLECTOR_LINKS_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_links.json")
XMU_COLLECTOR_FACILITIES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_facilities.json")
XMU_COLLECTOR_META_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_meta.json")
XMU_FOOD_MEDIA_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_food_media.json")
XMU_FOOD_CUSTOM_MEDIA_DIR = os.path.join(APP_DIR, "static", "food_media", "custom")
INDOOR_DATA_DIR = os.path.join(APP_DIR, "data", "indoor")
INDOOR_COLLECTOR_FILE = os.path.join(INDOOR_DATA_DIR, "manual_collector.json")
XMU_ROAD_SNAP_METERS = 0
XMU_COLLECTOR_SOURCE_FILES = [
    XMU_COLLECTOR_NODES_FILE,
    XMU_COLLECTOR_EDGES_FILE,
    XMU_COLLECTOR_LINKS_FILE,
    XMU_COLLECTOR_FACILITIES_FILE,
    XMU_COLLECTOR_META_FILE,
]
PLACES_CACHE = {
    "signature": None,
    "records": [],
}
PLACE_IMAGE_CACHE = {
    "signature": None,
    "records": {},
}
COLLECTOR_SIGNATURE_CACHE = {
    "source_files_signature": None,
    "signature": None,
}
ROUTE_GRAPH_CACHE = {}
SHORTEST_TREE_CACHE = {}
FACILITIES_CACHE = {
    "signature": None,
    "records": [],
}
FOOD_CANDIDATES_CACHE = {}
FOOD_MEDIA_CACHE = {
    "signature": None,
    "records": {},
}
PLACES_PAGE_SIZE = 18
DIARIES_PAGE_SIZE = 12
XMU_XIANG_AN_GENERATED_FACILITIES_FILE = os.path.join(
    APP_DIR,
    "data",
    "generated",
    "facilities_厦门大学翔安校区_厦门_中国.csv",
)
FOOD_TOP_K = 10
FOOD_DEFAULT_PLACE_ID = XMU_MANUAL_PLACE_ID
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
FOOD_CAMPUS_CONTEXTS = {
    XMU_MANUAL_PLACE_ID: {
        "place_id": XMU_MANUAL_PLACE_ID,
        "graph_place_id": XMU_MANUAL_PLACE_ID,
        "place_name": "厦门大学翔安校区",
        "graph_place_name": "厦门大学翔安校区手动采集路线图",
        "top_k": FOOD_TOP_K,
        "default_sort": "recommend_score_desc",
    },
    "xmu_xiang_an": {
        "place_id": "xmu_xiang_an",
        "graph_place_id": "xmu_xiang_an",
        "place_name": "厦门大学翔安校区",
        "graph_place_name": "厦门大学翔安校区",
        "top_k": FOOD_TOP_K,
        "default_sort": "recommend_score_desc",
    }
}
DIARY_UPLOAD_DIR = os.path.join(APP_DIR, "data", "uploads", "diaries")
USER_AVATAR_DIR = os.path.join(APP_DIR, "static", "uploads", "avatars")
DIARY_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DIARY_ALLOWED_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
DIARY_ALLOWED_MEDIA_EXTS = DIARY_ALLOWED_IMAGE_EXTS | DIARY_ALLOWED_VIDEO_EXTS
DIARY_ALLOWED_AVATAR_EXTS = DIARY_ALLOWED_IMAGE_EXTS | {".svg"}
DIARY_VISIBLE_COMMENT_THREADS = 3
DIARY_VISIBLE_REPLIES = 3
INDOOR_BUILDING_TYPES = {"building", "teaching", "library", "dorm", "canteen"}
INDOOR_DEFAULT_START = "gate_1f"
INDOOR_DEFAULT_END = "room_402"
INDOOR_VERTICAL_MODES = {"auto", "elevator", "stairs"}
INDOOR_FLOOR_WIDTH = 1672
INDOOR_FLOOR_HEIGHT = 941
INDOOR_FLOOR_ASSETS = {
    1: "indoor_floors/floor_1f.png",
    2: "indoor_floors/floor_2f.png",
    3: "indoor_floors/floor_3f.png",
    4: "indoor_floors/floor_4f.png",
}
INDOOR_VERTICAL_CORES = {
    "west_elevator": {"type": "elevator", "label": "西电梯"},
    "east_elevator": {"type": "elevator", "label": "东电梯"},
    "northwest_stairs": {"type": "stairs", "label": "西北步梯"},
    "east_stairs": {"type": "stairs", "label": "东侧步梯"},
}


# =========================
# 数据库工具函数
# =========================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_parent_dir(file_path):
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def write_json_atomic(file_path, payload):
    ensure_parent_dir(file_path)
    temp_path = f"{file_path}.{os.getpid()}.{int(time.time() * 1000000)}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    last_error = None
    for attempt in range(8):
        try:
            os.replace(temp_path, file_path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    try:
        os.remove(temp_path)
    except OSError:
        pass
    raise last_error


def read_json_file(file_path, default):
    if not os.path.exists(file_path):
        write_json_atomic(file_path, default)
        return default
    with open(file_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def ensure_sqlite_column(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cursor.fetchall()}
    if column_name not in existing_columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def ensure_place_images_table(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS place_images (
        place_id INTEGER PRIMARY KEY,
        place_name TEXT NOT NULL,
        city TEXT NOT NULL DEFAULT '',
        place_type TEXT NOT NULL DEFAULT '',
        source_site TEXT NOT NULL DEFAULT 'wikimedia',
        source_page_title TEXT NOT NULL DEFAULT '',
        source_page_url TEXT NOT NULL DEFAULT '',
        source_image_title TEXT NOT NULL DEFAULT '',
        source_image_url TEXT NOT NULL DEFAULT '',
        local_path TEXT NOT NULL DEFAULT '',
        width INTEGER NOT NULL DEFAULT 0,
        height INTEGER NOT NULL DEFAULT 0,
        original_width INTEGER NOT NULL DEFAULT 0,
        original_height INTEGER NOT NULL DEFAULT 0,
        fetched_at TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ok',
        note TEXT NOT NULL DEFAULT ''
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_place_images_city_type ON place_images(city, place_type)")


def load_place_image_map():
    signature = file_signature(DB_PATH)
    cached = PLACE_IMAGE_CACHE.get("signature")
    if signature == cached:
        return PLACE_IMAGE_CACHE.get("records", {})

    image_map = {}
    if not os.path.exists(DB_PATH):
        PLACE_IMAGE_CACHE["signature"] = signature
        PLACE_IMAGE_CACHE["records"] = image_map
        return image_map

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT place_id, place_name, city, place_type, source_site, source_page_title,
                   source_page_url, source_image_title, source_image_url, local_path,
                   width, height, original_width, original_height, fetched_at, status, note
            FROM place_images
            WHERE status = 'ok' AND local_path <> ''
        """)
        for row in cursor.fetchall():
            image_map[int(row["place_id"])] = {
                "place_name": row["place_name"],
                "city": row["city"],
                "place_type": row["place_type"],
                "source_site": row["source_site"],
                "source_page_title": row["source_page_title"],
                "source_page_url": row["source_page_url"],
                "source_image_title": row["source_image_title"],
                "source_image_url": row["source_image_url"],
                "local_path": row["local_path"],
                "width": row["width"],
                "height": row["height"],
                "original_width": row["original_width"],
                "original_height": row["original_height"],
                "fetched_at": row["fetched_at"],
                "status": row["status"],
                "note": row["note"],
            }
    finally:
        conn.close()

    PLACE_IMAGE_CACHE["signature"] = signature
    PLACE_IMAGE_CACHE["records"] = image_map
    return image_map


def place_media_relative_path(place_id):
    return "/".join(["place_media", f"{int(place_id):03d}.jpg"])


def save_uploaded_place_cover(uploaded_file, place):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("请选择图片文件")
    if Image is None or ImageOps is None:
        raise ValueError("当前环境缺少 Pillow，无法处理图片")

    original_name = secure_filename(uploaded_file.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext and ext not in DIARY_ALLOWED_IMAGE_EXTS:
        raise ValueError("请上传图片格式文件")

    try:
        uploaded_file.stream.seek(0)
    except Exception:
        pass

    try:
        image = Image.open(uploaded_file.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("上传图片解析失败，请重新选择文件") from exc

    original_width, original_height = image.size
    cover = ImageOps.fit(
        image,
        (1920, 1080),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.42),
    )

    os.makedirs(PLACE_MEDIA_DIR, exist_ok=True)
    filename = f"{int(place['id']):03d}.jpg"
    file_path = os.path.join(PLACE_MEDIA_DIR, filename)
    cover.save(file_path, "JPEG", quality=88, optimize=True, progressive=True)
    return place_media_relative_path(place["id"]), original_width, original_height, original_name or "manual upload"


def save_place_image_record(place, local_path, original_width, original_height, source_image_title):
    conn = get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO place_images (
                place_id, place_name, city, place_type, source_site, source_page_title,
                source_page_url, source_image_title, source_image_url, local_path,
                width, height, original_width, original_height, fetched_at, status, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(place_id) DO UPDATE SET
                place_name=excluded.place_name,
                city=excluded.city,
                place_type=excluded.place_type,
                source_site=excluded.source_site,
                source_page_title=excluded.source_page_title,
                source_page_url=excluded.source_page_url,
                source_image_title=excluded.source_image_title,
                source_image_url=excluded.source_image_url,
                local_path=excluded.local_path,
                width=excluded.width,
                height=excluded.height,
                original_width=excluded.original_width,
                original_height=excluded.original_height,
                fetched_at=excluded.fetched_at,
                status=excluded.status,
                note=excluded.note
            """,
            (
                int(place["id"]),
                place["name"],
                place["city"],
                place["type"],
                "manual",
                place["name"],
                "",
                source_image_title or "manual upload",
                "",
                local_path,
                1920,
                1080,
                original_width,
                original_height,
                datetime.now().isoformat(timespec="seconds"),
                "ok",
                "manual upload",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def avatar_relative_path(filename):
    return os.path.relpath(os.path.join(USER_AVATAR_DIR, filename), os.path.join(APP_DIR, "static")).replace("\\", "/")


def avatar_url_from_path(avatar_path, username="", user_id=None):
    relative_path = avatar_path or ensure_user_avatar_asset(username, user_id)
    return url_for("static", filename=relative_path)


def avatar_initial(username):
    clean_name = re.sub(r"\s+", "", (username or "").strip())
    if not clean_name:
        return "U"
    first_char = clean_name[0]
    return first_char.upper() if first_char.isascii() else first_char


def avatar_palette(seed_text):
    digest = hashlib.sha1((seed_text or "avatar").encode("utf-8")).hexdigest()
    hues = [int(digest[index:index + 2], 16) for index in (0, 2, 4, 6, 8, 10)]
    start = f"rgb({72 + hues[0] % 110},{118 + hues[1] % 90},{168 + hues[2] % 60})"
    end = f"rgb({116 + hues[3] % 100},{160 + hues[4] % 70},{210 + hues[5] % 40})"
    accent = f"rgb({50 + hues[2] % 120},{90 + hues[3] % 110},{138 + hues[4] % 80})"
    return start, end, accent


def build_avatar_svg(username, user_id=None):
    start_color, end_color, accent_color = avatar_palette(f"{username}:{user_id or ''}")
    initial = escape(avatar_initial(username))
    label = escape((username or "User").strip()[:2] or "用户")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-label="{label} 的头像">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{start_color}"/>
      <stop offset="100%" stop-color="{end_color}"/>
    </linearGradient>
    <radialGradient id="glow" cx="32%" cy="24%" r="72%">
      <stop offset="0%" stop-color="rgba(255,255,255,0.52)"/>
      <stop offset="100%" stop-color="rgba(255,255,255,0)"/>
    </radialGradient>
  </defs>
  <rect width="256" height="256" rx="64" fill="url(#bg)"/>
  <circle cx="88" cy="74" r="60" fill="url(#glow)"/>
  <circle cx="170" cy="170" r="78" fill="rgba(255,255,255,0.09)"/>
  <path d="M46 176C72 156 98 148 128 148s56 8 82 28v38H46z" fill="rgba(255,255,255,0.20)"/>
  <circle cx="128" cy="112" r="54" fill="rgba(255,255,255,0.86)"/>
  <circle cx="128" cy="103" r="18" fill="{accent_color}"/>
  <path d="M87 184c8-27 31-42 41-42s33 15 41 42" fill="{accent_color}" opacity="0.88"/>
  <text x="128" y="156" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="56" font-weight="800" fill="#fff">{initial}</text>
</svg>"""


def ensure_user_avatar_asset(username, user_id=None, avatar_path=""):
    os.makedirs(USER_AVATAR_DIR, exist_ok=True)
    if avatar_path:
        candidate_path = os.path.join(APP_DIR, "static", avatar_path)
        if os.path.exists(candidate_path):
            return avatar_path

    safe_user = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "_", (username or "user").strip()) or "user"
    suffix = user_id if user_id is not None else hashlib.sha1((username or "user").encode("utf-8")).hexdigest()[:10]
    filename = f"{safe_user}_{suffix}.svg"
    file_path = os.path.join(USER_AVATAR_DIR, filename)
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(build_avatar_svg(username, user_id))
    return avatar_relative_path(filename)


def save_uploaded_user_avatar(uploaded_file, username, user_id):
    if not uploaded_file or not uploaded_file.filename:
        return ensure_user_avatar_asset(username, user_id)

    original_name = secure_filename(uploaded_file.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in DIARY_ALLOWED_AVATAR_EXTS:
        return ensure_user_avatar_asset(username, user_id)

    os.makedirs(USER_AVATAR_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"user_{user_id}_{timestamp}{ext or '.svg'}"
    file_path = os.path.join(USER_AVATAR_DIR, filename)
    uploaded_file.save(file_path)
    return avatar_relative_path(filename)


def initialize_database():
    ensure_parent_dir(DB_PATH)

    if (
        not os.path.exists(DB_PATH)
        and os.path.exists(SEED_DB_PATH)
        and os.path.abspath(DB_PATH) != os.path.abspath(SEED_DB_PATH)
    ):
        shutil.copy2(SEED_DB_PATH, DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL,
        avatar_path TEXT NOT NULL DEFAULT ''
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        destination TEXT NOT NULL,
        content TEXT NOT NULL,
        author TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0,
        rating_total REAL NOT NULL DEFAULT 0,
        rating_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        media_json TEXT NOT NULL DEFAULT '[]',
        compressed_content TEXT NOT NULL DEFAULT '',
        compression_algorithm TEXT NOT NULL DEFAULT 'plain',
        compression_original_length INTEGER NOT NULL DEFAULT 0,
        compression_compressed_length INTEGER NOT NULL DEFAULT 0
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diary_comments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diary_id INTEGER NOT NULL,
        parent_id INTEGER,
        author TEXT NOT NULL,
        avatar_path TEXT NOT NULL DEFAULT '',
        content TEXT NOT NULL,
        like_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(diary_id) REFERENCES diaries(id) ON DELETE CASCADE,
        FOREIGN KEY(parent_id) REFERENCES diary_comments(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diary_comment_likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        comment_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(comment_id, username),
        FOREIGN KEY(comment_id) REFERENCES diary_comments(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_type TEXT NOT NULL,
        item_key TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        subtitle TEXT NOT NULL DEFAULT '',
        meta_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        UNIQUE(user_id, item_type, item_key),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    ensure_place_images_table(cursor)
    ensure_sqlite_column(cursor, "users", "avatar_path", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column(cursor, "diaries", "media_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_sqlite_column(cursor, "diaries", "compressed_content", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column(cursor, "diaries", "compression_algorithm", "TEXT NOT NULL DEFAULT 'plain'")
    ensure_sqlite_column(cursor, "diaries", "compression_original_length", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column(cursor, "diaries", "compression_compressed_length", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column(cursor, "diary_comments", "avatar_path", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column(cursor, "diary_comments", "like_count", "INTEGER NOT NULL DEFAULT 0")

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diary_comments_diary_created ON diary_comments(diary_id, like_count DESC, created_at ASC, id ASC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diary_comment_likes_comment_username ON diary_comment_likes(comment_id, username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_user_type_created ON user_favorites(user_id, item_type, created_at DESC)")

    cursor.execute("SELECT id, username, avatar_path FROM users ORDER BY id ASC")
    existing_users = cursor.fetchall()
    for user in existing_users:
        resolved_avatar = ensure_user_avatar_asset(user["username"], user["id"], user["avatar_path"])
        if resolved_avatar != user["avatar_path"]:
            cursor.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (resolved_avatar, user["id"]))

    cursor.execute("SELECT COUNT(*) FROM diaries")
    if cursor.fetchone()[0] == 0:
        samples = [
            ("沙河校区半日游", "北京邮电大学沙河校区", "从南门进入，先到中心广场，再经过图书馆和观景湖，最后在第一食堂休息。路线短，适合首次参观校园。", "system"),
            ("故宫历史路线记录", "故宫", "适合喜欢历史文化的同学，建议提前规划路线并避开高峰时段，重点关注建筑轴线和展馆介绍。", "system"),
            ("西湖休闲游记", "西湖", "西湖适合按照湖边景点分段游览，下午可以结合美食推荐安排休息点。", "system"),
        ]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cursor.executemany(
            """
            INSERT INTO diaries
            (title, destination, content, author, views, rating_total, rating_count, created_at, media_json, compressed_content, compression_algorithm, compression_original_length, compression_compressed_length)
            VALUES (?, ?, ?, ?, 0, 0, 0, ?, '[]', '', 'plain', 0, 0)
            """,
            [(title, destination, content, author, now) for title, destination, content, author in samples]
        )

    conn.commit()
    conn.close()


initialize_database()


def update_user_avatar_path(user_id, avatar_path):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (avatar_path, user_id))
    cursor.execute(
        """
        UPDATE diary_comments
        SET avatar_path = ?
        WHERE author = (SELECT username FROM users WHERE id = ?)
        """,
        (avatar_path, user_id)
    )
    conn.commit()
    conn.close()


def create_user(username, password, avatar_path=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_password = generate_password_hash(password)

    try:
        cursor.execute(
            "INSERT INTO users (username, password, avatar_path) VALUES (?, ?, ?)",
            (username, hashed_password, avatar_path or "")
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = cursor.fetchone()
    conn.close()
    return user


def get_user_by_id(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user


def update_user_account(user_id, new_username="", current_password="", new_password=""):
    user = get_user_by_id(user_id)
    if user is None:
        return False, "用户不存在"

    new_username = (new_username or "").strip()
    current_password = (current_password or "").strip()
    new_password = (new_password or "").strip()
    if not new_username:
        return False, "用户名不能为空"
    if new_username != user["username"] or new_password:
        if not current_password or not check_password_hash(user["password"], current_password):
            return False, "请先输入正确的当前密码"

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        old_username = user["username"]
        password_hash = generate_password_hash(new_password) if new_password else user["password"]
        cursor.execute(
            "UPDATE users SET username = ?, password = ? WHERE id = ?",
            (new_username, password_hash, user_id)
        )
        if new_username != old_username:
            cursor.execute("UPDATE diaries SET author = ? WHERE author = ?", (new_username, old_username))
            cursor.execute("UPDATE diary_comments SET author = ? WHERE author = ?", (new_username, old_username))
            cursor.execute("UPDATE diary_comment_likes SET username = ? WHERE username = ?", (new_username, old_username))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        return False, "用户名已存在，请更换用户名"
    finally:
        conn.close()

    if new_username != user["username"]:
        invalidate_diary_index_cache()
    return True, "账号信息已更新"


def get_user_avatar_url(user_or_username):
    if not user_or_username:
        return ""
    if isinstance(user_or_username, sqlite3.Row):
        username = user_or_username["username"]
        user_id = user_or_username["id"]
        avatar_path = user_or_username["avatar_path"] if "avatar_path" in user_or_username.keys() else ""
        return avatar_url_from_path(avatar_path, username, user_id)
    if isinstance(user_or_username, dict):
        username = user_or_username.get("username", "")
        user_id = user_or_username.get("id")
        avatar_path = user_or_username.get("avatar_path", "")
        return avatar_url_from_path(avatar_path, username, user_id)
    user = get_user_by_username(str(user_or_username))
    if user is None:
        return avatar_url_from_path("", str(user_or_username))
    return get_user_avatar_url(user)


def get_logged_in_user():
    username = session.get("username")
    if not username:
        return None
    user = get_user_by_username(username)
    if user and (not user["avatar_path"] or not os.path.exists(os.path.join(APP_DIR, "static", user["avatar_path"]))):
        resolved_avatar = ensure_user_avatar_asset(user["username"], user["id"], user["avatar_path"])
        if resolved_avatar != user["avatar_path"]:
            update_user_avatar_path(user["id"], resolved_avatar)
            user = get_user_by_username(username)
    return user


def diary_comment_avatar_url(comment):
    avatar_path = ""
    if isinstance(comment, dict):
        avatar_path = comment.get("resolved_avatar_path") or comment.get("avatar_path", "")
    author = comment.get("author", "") if isinstance(comment, dict) else ""
    return avatar_url_from_path(avatar_path, author, comment.get("author_user_id") if isinstance(comment, dict) else None)


def build_diary_comment_tree(comment_rows):
    comments = []
    lookup = {}
    for row in comment_rows:
        comment = dict(row)
        comment["avatar_url"] = diary_comment_avatar_url(comment)
        comment["liked_by_current_user"] = bool(comment.get("liked_by_current_user", 0))
        comment["reply_count"] = 0
        comment["replies"] = []
        comment["depth"] = 1
        comment["parent_author"] = ""
        lookup[comment["id"]] = comment
        comments.append(comment)

    roots = []
    for comment in comments:
        parent_id = comment.get("parent_id")
        if parent_id and parent_id in lookup:
            parent_comment = lookup[parent_id]
            comment["depth"] = int(parent_comment.get("depth", 1)) + 1
            comment["parent_author"] = parent_comment.get("author", "")
            parent_comment["replies"].append(comment)
        else:
            roots.append(comment)

    def comment_sort_key(item):
        created_at = item.get("created_at", "")
        return (-int(item.get("like_count", 0) or 0), created_at, item.get("id", 0))

    def sort_comment_branch(items):
        items.sort(key=comment_sort_key)
        for item in items:
            sort_comment_branch(item["replies"])
            item["reply_count"] = len(item["replies"])
        return items

    return sort_comment_branch(roots), lookup


def flatten_diary_comment_replies(replies):
    flattened = []
    for reply in replies:
        display_reply = dict(reply)
        depth = int(display_reply.get("depth", 2) or 2)
        display_reply["display_depth"] = 2 if depth <= 2 else 3
        display_reply["reply_to_author"] = display_reply.get("parent_author", "") if depth >= 3 else ""
        flattened.append(display_reply)
        flattened.extend(flatten_diary_comment_replies(reply.get("replies", [])))
    return flattened


def ensure_diaries_table():
    initialize_database()


DIARY_INDEX_CACHE = {
    "fingerprint": None,
    "source_signature": None,
    "records": [],
    "display_records": [],
    "record_map": {},
    "exact_title_index": defaultdict(list),
    "prefix_title_index": [],
    "inverted_index": defaultdict(set),
}


def normalize_search_text(text):
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def split_search_terms(text):
    normalized = normalize_search_text(text)
    if not normalized:
        return []

    terms = []
    for chunk in re.findall(r"[0-9a-zA-Z]+|[\u4e00-\u9fff]+", normalized):
        if re.fullmatch(r"[0-9a-zA-Z]+", chunk):
            terms.append(chunk)
            continue
        if len(chunk) <= 2:
            terms.append(chunk)
            continue
        terms.append(chunk)
        terms.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return list(dict.fromkeys(terms))


def file_signature(path):
    try:
        stat = os.stat(path)
    except OSError:
        return None
    return (int(stat.st_mtime_ns), int(stat.st_size))


def files_signature(paths):
    return tuple((path, file_signature(path)) for path in paths)


def invalidate_route_graph_cache(place_id=None):
    SHORTEST_TREE_CACHE.clear()
    if place_id is None:
        ROUTE_GRAPH_CACHE.clear()
        FOOD_CANDIDATES_CACHE.clear()
        return
    ROUTE_GRAPH_CACHE.pop(place_id or DEFAULT_PLACE_ID, None)
    FOOD_CANDIDATES_CACHE.pop(place_id or DEFAULT_PLACE_ID, None)


def invalidate_facilities_cache():
    FACILITIES_CACHE["signature"] = None
    FACILITIES_CACHE["records"] = []
    FOOD_CANDIDATES_CACHE.clear()


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


def build_pagination(endpoint, page, total_pages, base_params, radius=2):
    window = build_page_window(page, total_pages, radius=radius)

    def page_url(target_page):
        params = []
        for key, value in dict(base_params).items():
            if isinstance(value, (list, tuple)):
                params.extend((key, item) for item in value if item not in ("", None))
            elif value not in ("", None):
                params.append((key, value))
        params.append(("page", target_page))
        return url_for(endpoint) + "?" + urlencode(params)

    return {
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": page_url(page - 1) if page > 1 else None,
        "next_url": page_url(page + 1) if page < total_pages else None,
        "pages": [
            {
                "page": target_page,
                "url": page_url(target_page),
                "is_current": target_page == page,
            }
            for target_page in window
        ],
    }


def build_url_with_query(endpoint, params, anchor=None):
    query_items = []
    for key, value in dict(params or {}).items():
        if isinstance(value, (list, tuple)):
            query_items.extend((key, item) for item in value if item not in ("", None))
        elif value not in ("", None, []):
            query_items.append((key, value))

    url = url_for(endpoint)
    if query_items:
        url += "?" + urlencode(query_items, doseq=True)
    if anchor:
        url += f"#{anchor}"
    return url


def diary_media_folder(diary_id):
    return os.path.join(DIARY_UPLOAD_DIR, str(diary_id))


def diary_media_public_url(diary_id, filename):
    return url_for("diary_media_file", diary_id=diary_id, filename=filename)


def diary_media_kind(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in DIARY_ALLOWED_IMAGE_EXTS:
        return "image"
    if ext in DIARY_ALLOWED_VIDEO_EXTS:
        return "video"
    return "file"


def is_allowed_diary_media(filename):
    ext = os.path.splitext(filename)[1].lower()
    return ext in DIARY_ALLOWED_MEDIA_EXTS


def probe_image_size(file_path):
    if Image is None:
        return None, None
    try:
        with Image.open(file_path) as img:
            return img.size
    except Exception:
        return None, None


def diary_index_fingerprint(rows):
    if not rows:
        return (0, 0, "")
    tail = rows[-1]
    return (len(rows), int(tail["id"]), str(tail["created_at"]))


def rebuild_diary_indexes(rows):
    exact_title_index = defaultdict(list)
    prefix_title_index = []
    inverted_index = defaultdict(set)
    record_map = {}
    display_records = []

    for row in rows:
        diary = dict(row)
        diary_id = diary["id"]
        record_map[diary_id] = diary
        display_record = attach_diary_stats(dict(diary))
        display_records.append(display_record)

        title_key = normalize_search_text(diary["title"])
        exact_title_index[title_key].append(diary_id)
        prefix_title_index.append((title_key, diary_id))

        combined_text = " ".join([diary["title"], diary["destination"], diary["content"], diary["author"]])
        for term in split_search_terms(combined_text):
            inverted_index[term].add(diary_id)

    prefix_title_index.sort(key=lambda item: (item[0], item[1]))
    DIARY_INDEX_CACHE.update({
        "fingerprint": diary_index_fingerprint(rows),
        "records": rows,
        "display_records": display_records,
        "record_map": record_map,
        "exact_title_index": exact_title_index,
        "prefix_title_index": prefix_title_index,
        "inverted_index": inverted_index,
    })
    return DIARY_INDEX_CACHE


def get_diary_index_cache():
    ensure_diaries_table()
    source_signature = file_signature(DB_PATH)
    if source_signature == DIARY_INDEX_CACHE.get("source_signature") and DIARY_INDEX_CACHE.get("fingerprint") is not None:
        return DIARY_INDEX_CACHE
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diaries ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    rebuild_diary_indexes(rows)
    DIARY_INDEX_CACHE["source_signature"] = source_signature
    return DIARY_INDEX_CACHE


def invalidate_diary_index_cache():
    DIARY_INDEX_CACHE["fingerprint"] = None
    DIARY_INDEX_CACHE["source_signature"] = None


def save_diary_media_files(diary_id, uploaded_files):
    saved_items = []
    media_folder = diary_media_folder(diary_id)
    os.makedirs(media_folder, exist_ok=True)

    for file_storage in uploaded_files:
        if not file_storage or not file_storage.filename:
            continue

        original_name = file_storage.filename
        if not is_allowed_diary_media(original_name):
            continue

        safe_name = secure_filename(original_name)
        if not safe_name:
            continue

        timestamp_prefix = datetime.now().strftime("%Y%m%d%H%M%S%f")
        final_name = f"{timestamp_prefix}_{safe_name}"
        file_path = os.path.join(media_folder, final_name)
        file_storage.save(file_path)
        media_kind = diary_media_kind(final_name)
        media_item = {
            "filename": final_name,
            "original_name": original_name,
            "kind": media_kind,
            "size": os.path.getsize(file_path),
        }
        if media_kind == "image":
            media_item["width"], media_item["height"] = probe_image_size(file_path)
        saved_items.append({**media_item})

    return saved_items


def pack_varints(values):
    output = bytearray()
    for value in values:
        value = int(value)
        while True:
            to_write = value & 0x7F
            value >>= 7
            if value:
                output.append(to_write | 0x80)
            else:
                output.append(to_write)
                break
    return bytes(output)


def unpack_varints(payload):
    values = []
    current = 0
    shift = 0
    for byte in payload:
        current |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        values.append(current)
        current = 0
        shift = 0
    return values


def build_huffman_codes(byte_payload):
    if not byte_payload:
        return {0: "0"}

    frequencies = defaultdict(int)
    for byte in byte_payload:
        frequencies[byte] += 1

    heap = []
    counter = itertools.count()
    for byte_value, frequency in frequencies.items():
        heapq.heappush(heap, (frequency, next(counter), byte_value))

    if len(heap) == 1:
        return {heap[0][2]: "0"}

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)
        heapq.heappush(heap, (left[0] + right[0], next(counter), (left[2], right[2])))

    root = heap[0][2]
    codes = {}

    def walk(node, prefix):
        if isinstance(node, int):
            codes[node] = prefix or "0"
            return
        left, right = node
        walk(left, prefix + "0")
        walk(right, prefix + "1")

    walk(root, "")
    return codes


def huffman_compress_text(text):
    raw_bytes = text.encode("utf-8")
    if not raw_bytes:
        package = {
            "algorithm": "huffman",
            "bit_length": 0,
            "payload_b64": "",
            "codes": {},
        }
        return package, 0, 0

    codes = build_huffman_codes(raw_bytes)
    bit_stream = "".join(codes[byte] for byte in raw_bytes)
    padded_bits = bit_stream + ("0" * ((8 - len(bit_stream) % 8) % 8))
    compressed_bytes = bytes(int(padded_bits[i:i + 8], 2) for i in range(0, len(padded_bits), 8)) if padded_bits else b""
    reverse_codes = {code: byte_value for byte_value, code in codes.items()}

    decoded_bits = "".join(f"{byte:08b}" for byte in compressed_bytes)[:len(bit_stream)]
    restored = bytearray()
    buffer = ""
    for bit in decoded_bits:
        buffer += bit
        if buffer in reverse_codes:
            restored.append(reverse_codes[buffer])
            buffer = ""

    if restored.decode("utf-8") != text:
        raise ValueError("Huffman 压缩校验失败")

    package = {
        "algorithm": "huffman",
        "bit_length": len(bit_stream),
        "payload_b64": base64.b64encode(compressed_bytes).decode("ascii"),
        "codes": {str(byte_value): code for byte_value, code in codes.items()},
    }
    return package, len(raw_bytes), len(compressed_bytes)


def huffman_decompress_text(package):
    payload = base64.b64decode(package.get("payload_b64", "") or "")
    bit_length = int(package.get("bit_length", 0) or 0)
    codes = {code: int(byte_value) for byte_value, code in package.get("codes", {}).items()}
    if not payload or bit_length == 0:
        return ""

    bit_stream = "".join(f"{byte:08b}" for byte in payload)[:bit_length]
    restored = bytearray()
    buffer = ""
    for bit in bit_stream:
        buffer += bit
        if buffer in codes:
            restored.append(codes[buffer])
            buffer = ""
    return restored.decode("utf-8")


def lzw_compress_text(text):
    raw_bytes = text.encode("utf-8")
    if not raw_bytes:
        package = {
            "algorithm": "dictionary",
            "payload_b64": "",
            "code_count": 0,
        }
        return package, 0, 0

    dictionary = {bytes([byte_value]): byte_value for byte_value in range(256)}
    next_code = 256
    current = b""
    codes = []
    for byte in raw_bytes:
        candidate = current + bytes([byte])
        if candidate in dictionary:
            current = candidate
            continue
        if current:
            codes.append(dictionary[current])
        dictionary[candidate] = next_code
        next_code += 1
        current = bytes([byte])
    if current:
        codes.append(dictionary[current])

    packed = pack_varints(codes)
    restored = lzw_decompress_text({
        "payload_b64": base64.b64encode(packed).decode("ascii"),
    })
    if restored != text:
        raise ValueError("字典压缩校验失败")

    package = {
        "algorithm": "dictionary",
        "payload_b64": base64.b64encode(packed).decode("ascii"),
        "code_count": len(codes),
    }
    return package, len(raw_bytes), len(packed)


def lzw_decompress_text(package):
    payload = base64.b64decode(package.get("payload_b64", "") or "")
    if not payload:
        return ""

    codes = unpack_varints(payload)
    dictionary = {code: bytes([code]) for code in range(256)}
    next_code = 256
    decoded = bytearray()

    first_code = codes[0]
    if first_code not in dictionary:
        raise ValueError("字典压缩数据损坏")
    current_entry = dictionary[first_code]
    decoded.extend(current_entry)

    for code in codes[1:]:
        if code in dictionary:
            entry = dictionary[code]
        elif code == next_code:
            entry = current_entry + current_entry[:1]
        else:
            raise ValueError("字典压缩数据损坏")

        decoded.extend(entry)
        dictionary[next_code] = current_entry + entry[:1]
        next_code += 1
        current_entry = entry

    return decoded.decode("utf-8")


def compress_diary_text(text, algorithm):
    algorithm = (algorithm or "huffman").lower()
    if algorithm == "dictionary":
        package, original_length, compressed_length = lzw_compress_text(text)
    else:
        package, original_length, compressed_length = huffman_compress_text(text)
        algorithm = "huffman"

    package["algorithm"] = algorithm
    return package, original_length, compressed_length


def parse_diary_package(raw_value):
    if not raw_value:
        return None
    try:
        return json.loads(raw_value)
    except (TypeError, json.JSONDecodeError):
        return None


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


def refresh_diary_storage():
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diaries")
    rows = cursor.fetchall()

    for row in rows:
        diary_id = row["id"]
        current_media = parse_diary_package(row["media_json"]) or []
        package = parse_diary_package(row["compressed_content"])
        if not package or row["compression_algorithm"] not in {"huffman", "dictionary"}:
            package, original_length, compressed_length = compress_diary_text(row["content"], "huffman")
            cursor.execute(
                """
                UPDATE diaries
                SET compressed_content = ?, compression_algorithm = ?, compression_original_length = ?, compression_compressed_length = ?
                WHERE id = ?
                """,
                (json.dumps(package, ensure_ascii=False), "huffman", original_length, compressed_length, diary_id)
            )
        if current_media is None:
            cursor.execute(
                "UPDATE diaries SET media_json = '[]' WHERE id = ?",
                (diary_id,)
            )

    conn.commit()
    conn.close()
    invalidate_diary_index_cache()


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


refresh_diary_storage()


def haversine_amap(point_a, point_b):
    lat1, lon1 = float(point_a[1]), float(point_a[0])
    lat2, lon2 = float(point_b[1]), float(point_b[0])
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def polyline_distance(points):
    return sum(haversine_amap(start, end) for start, end in zip(points, points[1:]))


def default_collector_meta():
    return {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": "厦门大学翔安校区（手动采集图）",
        "default_start": "",
        "center": [24.6095855, 118.3099666],
        "amap_center": [118.3099666, 24.6095855],
        "campus_bounds": [[24.6017940, 118.2991356], [24.6172287, 118.3199674]],
        "amap_bounds": [[118.2991356, 24.6017940], [118.3199674, 24.6172287]],
        "facility_parent_place": "xmu_manual",
        "source": "manual_collector",
    }


def ensure_collector_files():
    os.makedirs(XMU_COLLECTOR_DIR, exist_ok=True)
    read_json_file(XMU_COLLECTOR_NODES_FILE, {"nodes": []})
    read_json_file(XMU_COLLECTOR_EDGES_FILE, {"edges": []})
    read_json_file(XMU_COLLECTOR_LINKS_FILE, {"links": []})
    read_json_file(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": []})
    read_json_file(XMU_COLLECTOR_META_FILE, default_collector_meta())


def load_collector_nodes():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_NODES_FILE, {"nodes": []}).get("nodes", [])


def load_collector_edges():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_EDGES_FILE, {"edges": []}).get("edges", [])


def load_collector_links():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_LINKS_FILE, {"links": []}).get("links", [])


def load_collector_facilities():
    ensure_collector_files()
    return read_json_file(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": []}).get("facilities", [])


def load_collector_meta():
    ensure_collector_files()
    meta = default_collector_meta()
    meta.update(read_json_file(XMU_COLLECTOR_META_FILE, meta))
    return meta


def normalize_collector_point(payload):
    lng = payload.get("amap_lng", payload.get("lng", payload.get("lon")))
    lat = payload.get("amap_lat", payload.get("lat"))
    if lng is None or lat is None:
        raise ValueError("缺少经纬度")
    return [round(float(lng), 7), round(float(lat), 7)]


def collector_node_point(node):
    return [float(node["amap_lng"]), float(node["amap_lat"])]


def nearest_collector_node(point, node_map):
    if not node_map:
        return None
    return min(node_map, key=lambda node_id: haversine_amap(point, collector_node_point(node_map[node_id])))


def valid_collector_node_id(node_id, node_map):
    node_id = str(node_id or "").strip()
    return node_id if node_id in node_map else ""


def collector_node_id(name, existing_count):
    base = "".join(ch.lower() if ch.isalnum() else "_" for ch in (name or "node")).strip("_")
    return f"route_point_{base or 'node'}_{existing_count + 1:03d}"


def normalize_tags(value):
    if isinstance(value, list):
        raw_tags = value
    else:
        raw_tags = str(value or "").replace("，", ",").replace("、", ",").split(",")
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]


def normalize_collector_node(payload, existing_count=0):
    point = normalize_collector_point(payload)
    name = str(payload.get("name") or f"采集点{existing_count + 1}").strip()
    kind = str(payload.get("kind") or "building").strip()
    if kind not in ("gate", "building", "teaching", "library", "canteen", "dorm", "sports", "service", "facility", "landmark", "road"):
        kind = "building"
    node_id = str(payload.get("id") or collector_node_id(name, existing_count)).strip()
    return {
        "id": node_id,
        "name": name,
        "category": str(payload.get("category") or "手动采集点").strip(),
        "tags": normalize_tags(payload.get("tags")),
        "role": "road" if kind == "road" else "route_point",
        "kind": kind,
        "lat": point[1],
        "lon": point[0],
        "amap_lng": point[0],
        "amap_lat": point[1],
        "selectable": kind != "road",
        "source": "manual_collector_node",
    }


def normalize_collector_edge(payload, nodes, existing_count=0):
    geometry = payload.get("amap_geometry") or []
    if len(geometry) < 2:
        raise ValueError("道路至少需要两个采样点")
    points = [[round(float(point[0]), 7), round(float(point[1]), 7)] for point in geometry]
    node_map = {node["id"]: node for node in nodes}
    from_id = valid_collector_node_id(payload.get("from"), node_map)
    to_id = valid_collector_node_id(payload.get("to"), node_map)
    poi_links = []
    for link in payload.get("poi_links") or []:
        try:
            index = int(link.get("index", -1))
        except (TypeError, ValueError):
            continue
        poi_id = valid_collector_node_id(link.get("poi"), node_map)
        if poi_id and 0 <= index < len(points):
            poi_links.append({"index": index, "poi": poi_id})
    road_links = []
    for link in payload.get("road_links") or []:
        try:
            index = int(link.get("index", -1))
            target_index = int(link.get("target_index", -1))
        except (TypeError, ValueError):
            continue
        target_edge = str(link.get("edge") or "").strip()
        if target_edge and 0 <= index < len(points) and target_index >= 0:
            road_links.append({"index": index, "edge": target_edge, "target_index": target_index})
    edge_id = str(payload.get("id") or collector_edge_id(existing_count)).strip()
    try:
        congestion = float(payload.get("congestion", 0.82))
    except (TypeError, ValueError):
        congestion = 0.82
    congestion = min(max(congestion, 0.1), 1.0)
    return {
        "id": edge_id,
        "name": str(payload.get("name") or f"手动道路{existing_count + 1}").strip(),
        "road_type": str(payload.get("road_type") or "walkway").strip(),
        "from": from_id,
        "to": to_id,
        "poi_links": poi_links,
        "road_links": road_links,
        "amap_geometry": points,
        "distance": round(polyline_distance(points), 1),
        "walk": bool(payload.get("walk", True)),
        "bike": bool(payload.get("bike", True)),
        "congestion": congestion,
        "source": "manual_collector_edge",
    }


def collector_link_id(existing_count):
    return f"link_{existing_count + 1:04d}"


def collector_edge_id(existing_count):
    return f"edge_{existing_count + 1:04d}"


def collector_facility_id(existing_count):
    return f"facility_{existing_count + 1:04d}"


def next_prefixed_collector_id(items, prefix, width=4):
    existing_ids = {str(item.get("id") or "") for item in items}
    max_number = 0
    id_pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    for item_id in existing_ids:
        match = id_pattern.match(item_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    next_number = max_number + 1
    while True:
        candidate = f"{prefix}_{next_number:0{width}d}"
        if candidate not in existing_ids:
            return candidate
        next_number += 1


def next_collector_node_id(name, nodes):
    existing_ids = {str(item.get("id") or "") for item in nodes}
    count = len(nodes)
    while True:
        candidate = collector_node_id(name, count)
        if candidate not in existing_ids:
            return candidate
        count += 1


def nearest_collector_road_node_id(point):
    best = None
    for edge in load_collector_edges():
        edge_id = str(edge.get("id") or "")
        for index, road_point in enumerate(edge.get("amap_geometry") or []):
            if not road_point or len(road_point) < 2:
                continue
            distance = haversine_amap(point, [float(road_point[0]), float(road_point[1])])
            if best is None or distance < best[0]:
                best = (distance, edge_id, index)
    if not best:
        return ""
    return f"road_{best[1]}_{best[2]:03d}"


def empty_manual_graph(meta=None):
    meta = {**default_collector_meta(), **(meta or load_collector_meta())}
    graph = {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "source": "manual_collector",
        "default_start": "",
        "center": meta.get("center", [24.6095855, 118.3099666]),
        "amap_center": meta.get("amap_center", [118.3099666, 24.6095855]),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "facility_parent_place": meta.get("facility_parent_place", XMU_MANUAL_PLACE_ID),
        "image_overlay": None,
        "nodes": [],
        "edges": [],
    }
    graph["collector_source_signature"] = collector_source_signature()
    graph["collector_source_summary"] = collector_source_summary()
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    invalidate_route_graph_cache(XMU_MANUAL_PLACE_ID)
    return graph


def collector_source_signature():
    ensure_collector_files()
    source_files_signature = files_signature(XMU_COLLECTOR_SOURCE_FILES)
    if source_files_signature == COLLECTOR_SIGNATURE_CACHE.get("source_files_signature"):
        cached = COLLECTOR_SIGNATURE_CACHE.get("signature")
        if cached:
            return cached

    digest = hashlib.sha256()
    files = []
    for file_path in XMU_COLLECTOR_SOURCE_FILES:
        name = os.path.basename(file_path)
        digest.update(name.encode("utf-8"))
        try:
            with open(file_path, "rb") as f:
                content = f.read()
        except OSError:
            content = b""
        digest.update(str(len(content)).encode("ascii"))
        digest.update(content)
        files.append({"name": name, "bytes": len(content)})
    signature = {
        "algorithm": "sha256",
        "digest": digest.hexdigest(),
        "files": files,
    }
    COLLECTOR_SIGNATURE_CACHE["source_files_signature"] = source_files_signature
    COLLECTOR_SIGNATURE_CACHE["signature"] = signature
    return signature


def collector_sources_are_newer_than_graph():
    if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
        return True
    graph_mtime = os.path.getmtime(XMU_MANUAL_GRAPH_FILE)
    return any(os.path.exists(file_path) and os.path.getmtime(file_path) > graph_mtime for file_path in XMU_COLLECTOR_SOURCE_FILES)


def manual_graph_needs_rebuild():
    if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
        return True
    try:
        graph = read_json_file(XMU_MANUAL_GRAPH_FILE, {})
    except (OSError, json.JSONDecodeError):
        return True
    graph_signature = (graph.get("collector_source_signature") or {}).get("digest")
    current_signature = collector_source_signature().get("digest")
    if graph_signature:
        return graph_signature != current_signature
    return collector_sources_are_newer_than_graph()


def ensure_manual_graph_current():
    if manual_graph_needs_rebuild():
        return rebuild_manual_graph()
    return None


def ensure_route_graph_current(place_id):
    if (place_id or DEFAULT_PLACE_ID) == XMU_MANUAL_PLACE_ID:
        ensure_manual_graph_current()


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


def resolve_facility_nearest_node(facility, graph, road_only=True):
    node_map = graph.get("node_map", {})
    nearest_node = str((facility or {}).get("nearest_node") or "").strip()
    node = node_map.get(nearest_node)
    if node and (not road_only or is_road_graph_node(node)):
        return nearest_node

    try:
        point = [
            float((facility or {}).get("amap_lng", (facility or {}).get("lon"))),
            float((facility or {}).get("amap_lat", (facility or {}).get("lat"))),
        ]
    except (TypeError, ValueError):
        return nearest_node if node else ""

    if road_only:
        road_node = nearest_graph_node_id(point, graph, road_only=True)
        if road_node:
            return road_node
    return nearest_graph_node_id(point, graph)


def facilities_for_map(graph):
    parent_place = graph.get("facility_parent_place", graph.get("place_id"))
    node_map = graph.get("node_map", {})
    records = []
    for facility in load_facilities(parent_place):
        item = facility.copy()
        nearest_node = resolve_facility_nearest_node(item, graph, road_only=True)
        if nearest_node:
            item["nearest_node"] = nearest_node
            node = node_map.get(nearest_node)
            if node:
                item["nearest_lng"] = node.get("amap_lng", node.get("lon"))
                item["nearest_lat"] = node.get("amap_lat", node.get("lat"))
        records.append(item)
    return records


def normalize_collector_facility(payload, existing_count=0, graph=None):
    point = normalize_collector_point(payload)
    facility_type = str(payload.get("type") or payload.get("category") or "服务设施").strip()
    cuisine = str(payload.get("cuisine") or payload.get("food_category") or "").strip()
    facility_id = str(payload.get("id") or collector_facility_id(existing_count)).strip()
    nearest_node = str(payload.get("nearest_node") or "").strip()
    if graph:
        nearest_node = resolve_facility_nearest_node(
            {**payload, "nearest_node": nearest_node, "amap_lng": point[0], "amap_lat": point[1]},
            graph,
            road_only=True,
        )
    return {
        "id": facility_id,
        "name": str(payload.get("name") or f"场所{existing_count + 1}").strip(),
        "type": facility_type,
        "cuisine": cuisine,
        "tags": normalize_tags(payload.get("tags") or facility_type),
        "parent_place": XMU_MANUAL_PLACE_ID,
        "nearest_node": nearest_node,
        "amap_lng": point[0],
        "amap_lat": point[1],
        "description": str(payload.get("description") or "手动采集场所").strip(),
        "source": "manual_collector_facility",
    }


def normalize_road_ref(payload, edge_map):
    edge_id = str((payload or {}).get("edge") or (payload or {}).get("edge_id") or "").strip()
    try:
        point_index = int((payload or {}).get("point_index", (payload or {}).get("target_index", -1)))
    except (TypeError, ValueError):
        raise ValueError("道路端点索引无效")
    edge = edge_map.get(edge_id)
    if not edge:
        raise ValueError("道路端点所属道路不存在")
    geometry = edge.get("amap_geometry") or []
    if point_index < 0 or point_index >= len(geometry):
        raise ValueError("道路端点索引超出范围")
    return {"edge": edge_id, "point_index": point_index}


def collector_ref_point(ref, node_map, edge_map):
    ref_type = ref.get("type")
    if ref_type == "poi":
        node = node_map.get(ref.get("id"))
        if not node:
            return None
        return collector_node_point(node)
    if ref_type == "road":
        edge = edge_map.get(ref.get("edge"))
        if not edge:
            return None
        index = ref.get("point_index")
        geometry = edge.get("amap_geometry") or []
        if not isinstance(index, int) or index < 0 or index >= len(geometry):
            return None
        point = geometry[index]
        return [float(point[0]), float(point[1])]
    return None


def normalize_collector_link(payload, nodes, edges, existing_count=0):
    node_map = {node["id"]: node for node in nodes}
    edge_map = {edge["id"]: edge for edge in edges}
    raw_a = payload.get("a") or payload.get("from") or {}
    raw_b = payload.get("b") or payload.get("to") or {}

    def normalize_ref(raw):
        ref_type = str(raw.get("type") or "").strip()
        if ref_type == "poi":
            poi_id = valid_collector_node_id(raw.get("id") or raw.get("poi"), node_map)
            if not poi_id:
                raise ValueError("POI 端点不存在")
            return {"type": "poi", "id": poi_id}
        if ref_type == "road":
            road_ref = normalize_road_ref(raw, edge_map)
            return {"type": "road", **road_ref}
        raise ValueError("吸附端点类型无效")

    a_ref = normalize_ref(raw_a)
    b_ref = normalize_ref(raw_b)
    ref_types = sorted([a_ref["type"], b_ref["type"]])
    if ref_types == ["poi", "poi"]:
        raise ValueError("POI 与 POI 不能直接吸附，请选择 POI 与道路节点")
    if ref_types == ["poi", "road"]:
        link_kind = "poi_road"
    elif ref_types == ["road", "road"]:
        link_kind = "road_road"
    else:
        raise ValueError("仅支持 POI-道路节点或道路节点-道路节点吸附")

    point_a = collector_ref_point(a_ref, node_map, edge_map)
    point_b = collector_ref_point(b_ref, node_map, edge_map)
    if not point_a or not point_b:
        raise ValueError("吸附端点坐标无效")
    if haversine_amap(point_a, point_b) < 0.2:
        raise ValueError("两个端点过近，无需新增吸附边")

    link_id = str(payload.get("id") or collector_link_id(existing_count)).strip()
    try:
        congestion = float(payload.get("congestion", 0.82))
    except (TypeError, ValueError):
        congestion = 0.82
    congestion = min(max(congestion, 0.1), 1.0)
    return {
        "id": link_id,
        "kind": link_kind,
        "a": a_ref,
        "b": b_ref,
        "amap_geometry": [[round(point_a[0], 7), round(point_a[1], 7)], [round(point_b[0], 7), round(point_b[1], 7)]],
        "distance": round(polyline_distance([point_a, point_b]), 1),
        "walk": bool(payload.get("walk", True)),
        "bike": bool(payload.get("bike", True)),
        "congestion": congestion,
        "source": "manual_collector_link",
    }


def rebuild_manual_graph():
    ensure_collector_files()
    meta = load_collector_meta()
    collector_nodes = load_collector_nodes()
    collector_edges = load_collector_edges()
    collector_links = load_collector_links()
    nodes = []
    node_map = {}
    edges = []
    edge_seen = set()
    road_node_ids = []
    point_node_lookup = {}

    for node in collector_nodes:
        normalized = normalize_collector_node(node, len(nodes))
        nodes.append(normalized)
        node_map[normalized["id"]] = normalized

    def nearest_road_node(point):
        if XMU_ROAD_SNAP_METERS <= 0:
            return ""
        best = None
        for node_id in road_node_ids:
            node = node_map.get(node_id)
            if not node:
                continue
            distance = haversine_amap(point, collector_node_point(node))
            if distance <= XMU_ROAD_SNAP_METERS and (not best or distance < best[1]):
                best = (node_id, distance)
        return best[0] if best else ""

    def add_road_node(point, edge_id, index):
        reused_id = nearest_road_node(point)
        if reused_id:
            return reused_id
        node_id = f"road_{edge_id}_{index:03d}"
        if node_id in node_map:
            return node_id
        node = {
            "id": node_id,
            "name": f"道路节点{edge_id}-{index}",
            "category": "道路折点",
            "kind": "road",
            "lat": round(float(point[1]), 7),
            "lon": round(float(point[0]), 7),
            "amap_lng": round(float(point[0]), 7),
            "amap_lat": round(float(point[1]), 7),
            "selectable": False,
            "source": "manual_collector_road_node",
        }
        nodes.append(node)
        node_map[node_id] = node
        road_node_ids.append(node_id)
        return node_id

    def add_graph_edge(from_id, to_id, segment, edge_payload):
        if not from_id or not to_id or from_id == to_id:
            return
        key = tuple(sorted((from_id, to_id)))
        if key in edge_seen:
            return
        edge_seen.add(key)
        distance = round(max(polyline_distance(segment), 1), 1)
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": distance,
            "congestion": edge_payload.get("congestion", 0.82),
            "road_type": edge_payload.get("road_type", "walkway"),
            "walk": edge_payload.get("walk", True),
            "bike": edge_payload.get("bike", True),
            "geometry": [[point[1], point[0]] for point in segment],
            "amap_geometry": segment,
            "source": edge_payload.get("source", "manual_collector_edge"),
        })

    for raw_edge in collector_edges:
        try:
            edge = normalize_collector_edge(raw_edge, collector_nodes, len(edges))
        except (TypeError, ValueError):
            continue
        points = edge["amap_geometry"]
        chain = []
        if edge["from"] in node_map:
            chain.append(edge["from"])
        for index, point in enumerate(points):
            chain.append(add_road_node(point, edge["id"], index))
        if edge["to"] in node_map:
            chain.append(edge["to"])
        compact_chain = []
        for node_id in chain:
            if node_id and (not compact_chain or compact_chain[-1] != node_id):
                compact_chain.append(node_id)
        chain = compact_chain
        all_points = [collector_node_point(node_map[node_id]) for node_id in chain]
        for index, (from_id, to_id) in enumerate(zip(chain, chain[1:])):
            add_graph_edge(from_id, to_id, [all_points[index], all_points[index + 1]], edge)
        point_node_ids = [add_road_node(point, edge["id"], index) for index, point in enumerate(points)]
        for index, node_id in enumerate(point_node_ids):
            point_node_lookup[(edge["id"], index)] = node_id
        for link in edge.get("poi_links", []):
            poi_id = link.get("poi")
            point_index = link.get("index")
            if poi_id not in node_map or not isinstance(point_index, int) or point_index >= len(point_node_ids):
                continue
            road_id = point_node_ids[point_index]
            add_graph_edge(poi_id, road_id, [collector_node_point(node_map[poi_id]), collector_node_point(node_map[road_id])], edge)
        for link in edge.get("road_links", []):
            point_index = link.get("index")
            target_edge_id = link.get("edge")
            target_index = link.get("target_index")
            if not isinstance(point_index, int) or point_index >= len(point_node_ids):
                continue
            target_raw = next((item for item in collector_edges if str(item.get("id") or "") == target_edge_id), None)
            if not target_raw:
                continue
            target_points = target_raw.get("amap_geometry") or []
            if not isinstance(target_index, int) or target_index < 0 or target_index >= len(target_points):
                continue
            from_id = point_node_ids[point_index]
            to_id = add_road_node(target_points[target_index], target_edge_id, target_index)
            add_graph_edge(from_id, to_id, [collector_node_point(node_map[from_id]), collector_node_point(node_map[to_id])], edge)

    normalized_edge_map = {}
    for raw_edge in collector_edges:
        try:
            edge = normalize_collector_edge(raw_edge, collector_nodes, len(edges))
        except (TypeError, ValueError):
            continue
        normalized_edge_map[edge["id"]] = edge

    def graph_node_for_ref(ref):
        if ref.get("type") == "poi":
            return ref.get("id") if ref.get("id") in node_map else ""
        if ref.get("type") == "road":
            edge_id = ref.get("edge")
            index = ref.get("point_index")
            node_id = point_node_lookup.get((edge_id, index))
            if node_id:
                return node_id
            edge = normalized_edge_map.get(edge_id)
            geometry = edge.get("amap_geometry") if edge else []
            if isinstance(index, int) and geometry and 0 <= index < len(geometry):
                node_id = add_road_node(geometry[index], edge_id, index)
                point_node_lookup[(edge_id, index)] = node_id
                return node_id
        return ""

    for raw_link in collector_links:
        try:
            link = normalize_collector_link(raw_link, collector_nodes, list(normalized_edge_map.values()), len(edges))
        except (TypeError, ValueError):
            continue
        from_id = graph_node_for_ref(link["a"])
        to_id = graph_node_for_ref(link["b"])
        add_graph_edge(from_id, to_id, link["amap_geometry"], link)

    selectable = [node for node in nodes if node.get("selectable")]
    meta["default_start"] = ""

    graph = {
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "source": "manual_collector",
        "default_start": meta.get("default_start", ""),
        "center": meta.get("center", [24.6095855, 118.3099666]),
        "amap_center": meta.get("amap_center", [118.3099666, 24.6095855]),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "facility_parent_place": meta.get("facility_parent_place", XMU_MANUAL_PLACE_ID),
        "image_overlay": None,
        "nodes": nodes,
        "edges": edges,
    }
    write_json_atomic(XMU_COLLECTOR_META_FILE, meta)
    COLLECTOR_SIGNATURE_CACHE["source_files_signature"] = None
    graph["collector_source_signature"] = collector_source_signature()
    graph["collector_source_summary"] = collector_source_summary()
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    invalidate_route_graph_cache(XMU_MANUAL_PLACE_ID)
    invalidate_facilities_cache()
    return graph


ensure_collector_files()
if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
    rebuild_manual_graph()


# =========================
# 登录状态工具函数
# =========================
def is_logged_in():
    return "username" in session


# =========================
# 景点数据读取函数
# =========================
def load_places():
    signature = file_signature(PLACES_FILE)
    if signature == PLACES_CACHE.get("signature"):
        return PLACES_CACHE["records"]

    places = []
    if not os.path.exists(PLACES_FILE):
        PLACES_CACHE["signature"] = signature
        PLACES_CACHE["records"] = places
        return places

    with open(PLACES_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = {
                (key.strip() if isinstance(key, str) else key):
                (value.strip() if isinstance(value, str) else value)
                for key, value in row.items()
            }

            try:
                row["id"] = int(row["id"])
            except (ValueError, KeyError):
                row["id"] = 0

            try:
                row["rating"] = float(row["rating"])
            except (ValueError, KeyError):
                row["rating"] = 0.0

            try:
                row["popularity"] = int(row["popularity"])
            except (ValueError, KeyError):
                row["popularity"] = 0

            row["tags_list"] = [tag.strip() for tag in row.get("tags", "").split(";") if tag.strip()]
            places.append(row)

    image_map = load_place_image_map()
    for row in places:
        image_info = image_map.get(row["id"])
        if image_info:
            row["cover_image"] = image_info.get("local_path", "")
            row["cover_image_source"] = image_info.get("source_page_url", "")
            row["cover_image_title"] = image_info.get("source_page_title", "")
            row["cover_image_source_url"] = image_info.get("source_image_url", "")
            row["cover_image_width"] = image_info.get("original_width") or image_info.get("width") or 0
            row["cover_image_height"] = image_info.get("original_height") or image_info.get("height") or 0
        else:
            row["cover_image"] = ""
            row["cover_image_source"] = ""
            row["cover_image_title"] = ""
            row["cover_image_source_url"] = ""
            row["cover_image_width"] = 0
            row["cover_image_height"] = 0

    PLACES_CACHE["signature"] = signature
    PLACES_CACHE["records"] = places
    return places


def get_place_by_id(place_id):
    places = load_places()
    for place in places:
        if place["id"] == place_id:
            return place
    return None

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


def apply_food_media(food):
    media_records = load_food_media_records()
    media = None
    for key in food_media_lookup_keys(food):
        if key and key in media_records:
            media = media_records[key]
            break

    food["visible_tags"] = visible_food_tags(food.get("tags_list", []), food.get("category", ""))
    if media:
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
    return food


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


# =========================
# 图结构、设施与路线算法
# =========================
def get_route_graph_path(place_id=None):
    if place_id:
        safe_place_id = "".join(ch for ch in place_id if ch.isalnum() or ch in ("_", "-"))
        graph_path = os.path.join(ROUTE_GRAPHS_DIR, f"{safe_place_id}.json")
        if os.path.exists(graph_path):
            return graph_path
    return XMU_MANUAL_GRAPH_FILE


def get_route_graph_version(place_id=None):
    signature = file_signature(get_route_graph_path(place_id or DEFAULT_PLACE_ID))
    if not signature:
        return "missing"
    return f"{signature[0]}-{signature[1]}"


def load_route_graph(place_id=None):
    effective_place_id = place_id or DEFAULT_PLACE_ID
    graph_path = get_route_graph_path(effective_place_id)
    graph_signature = file_signature(graph_path)
    cached = ROUTE_GRAPH_CACHE.get(effective_place_id)
    if effective_place_id == XMU_MANUAL_PLACE_ID:
        current_source_digest = collector_source_signature().get("digest")
        if (
            cached
            and cached.get("path") == graph_path
            and cached.get("signature") == graph_signature
            and cached.get("source_digest") == current_source_digest
        ):
            return cached["graph"]
        ensure_manual_graph_current()
        graph_signature = file_signature(graph_path)
        cached = ROUTE_GRAPH_CACHE.get(effective_place_id)
    elif cached and cached.get("path") == graph_path and cached.get("signature") == graph_signature:
        return cached["graph"]

    if not os.path.exists(graph_path):
        return {"default_start": "", "nodes": [], "edges": [], "node_map": {}, "adjacency": {}}

    with open(graph_path, "r", encoding="utf-8-sig") as f:
        graph = json.load(f)

    graph.setdefault("place_id", effective_place_id)
    graph.setdefault("place_name", "当前路线图")
    graph.setdefault("bounds", [])
    graph.setdefault("campus_bounds", graph.get("bounds", []))
    graph.setdefault("center", [])
    graph.setdefault("amap_center", [])
    graph.setdefault("amap_bounds", [])
    graph.setdefault("facility_parent_place", graph.get("place_id", effective_place_id))
    graph.setdefault("image_overlay", None)
    if effective_place_id == XMU_MANUAL_PLACE_ID:
        graph["default_start"] = ""

    node_map = {node["id"]: node for node in graph.get("nodes", [])}
    adjacency = {node_id: [] for node_id in node_map}

    for edge in graph.get("edges", []):
        start = edge["from"]
        end = edge["to"]
        if start not in adjacency or end not in adjacency:
            continue
        if not edge.get("geometry"):
            edge["geometry"] = [
                [node_map[start].get("lat"), node_map[start].get("lon")],
                [node_map[end].get("lat"), node_map[end].get("lon")],
            ]
        if not edge.get("amap_geometry"):
            edge["amap_geometry"] = [
                [node_map[start].get("amap_lng", node_map[start].get("lon")), node_map[start].get("amap_lat", node_map[start].get("lat"))],
                [node_map[end].get("amap_lng", node_map[end].get("lon")), node_map[end].get("amap_lat", node_map[end].get("lat"))],
            ]
        adjacency[start].append({**edge, "neighbor": end})
        adjacency[end].append({
            **edge,
            "from": end,
            "to": start,
            "geometry": list(reversed(edge["geometry"])),
            "amap_geometry": list(reversed(edge.get("amap_geometry", []))),
            "neighbor": start
        })

    graph["node_map"] = node_map
    graph["adjacency"] = adjacency
    graph["_cache_key"] = (graph_path, graph_signature)
    ROUTE_GRAPH_CACHE[effective_place_id] = {
        "path": graph_path,
        "signature": graph_signature,
        "source_digest": (graph.get("collector_source_signature") or {}).get("digest"),
        "graph": graph,
    }
    return graph


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


def road_display_edges_for_map(graph):
    if graph.get("place_id") != XMU_MANUAL_PLACE_ID:
        return []
    display_edges = []
    for edge in load_collector_edges():
        geometry = edge.get("amap_geometry") or []
        if len(geometry) < 2:
            continue
        display_edges.append({
            "id": edge.get("id", ""),
            "name": edge.get("name", ""),
            "road_type": edge.get("road_type", ""),
            "walk": edge.get("walk", True),
            "bike": edge.get("bike", True),
            "amap_geometry": geometry,
        })
    return display_edges


def serialize_graph_for_map(graph, include_road_nodes=True, compact_edges=False):
    nodes = graph.get("nodes", []) if include_road_nodes else get_selectable_nodes(graph)
    edges = graph.get("edges", [])
    if compact_edges:
        compacted_edges = []
        for edge in edges:
            compact_edge = {
                "from": edge.get("from", ""),
                "to": edge.get("to", ""),
                "distance": edge.get("distance", 0),
                "amap_geometry": edge.get("amap_geometry", []),
            }
            if not compact_edge["amap_geometry"]:
                compact_edge["geometry"] = edge.get("geometry", [])
            compacted_edges.append(compact_edge)
        edges = compacted_edges
    return {
        "place_id": graph.get("place_id", DEFAULT_PLACE_ID),
        "place_name": graph.get("place_name", "当前路线图"),
        "default_start": graph.get("default_start", ""),
        "center": graph.get("center", []),
        "amap_center": graph.get("amap_center", []),
        "bounds": graph.get("bounds", []),
        "campus_bounds": graph.get("campus_bounds", graph.get("bounds", [])),
        "amap_bounds": graph.get("amap_bounds", []),
        "image_overlay": graph.get("image_overlay"),
        "nodes": nodes,
        "edges": edges,
        "road_display_edges": road_display_edges_for_map(graph),
        "selectable_nodes": get_selectable_nodes(graph),
    }


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


def build_indoor_graph(building_id="demo_building"):
    collector_payload = load_indoor_collector_payload()
    collector_summary_data = indoor_collector_summary(collector_payload)
    if collector_summary_data.get("manual_nodes", 0) or collector_summary_data.get("manual_edges", 0):
        return build_indoor_graph_from_collector(collector_payload)

    floors_list = (1, 2, 3, 4)
    floors_display = [1, 2, 3, 4]
    nodes = []
    edges = []

    def add_node(node_id, name, floor, x, y, node_type, **extra):
        nodes.append({
            "id": node_id,
            "name": name,
            "floor": floor,
            "x": x,
            "y": y,
            "type": node_type,
            **extra,
        })

    def add_edge(from_id, to_id, distance=None, mode="walk"):
        if distance is None:
            from_node = next(node for node in nodes if node["id"] == from_id)
            to_node = next(node for node in nodes if node["id"] == to_id)
            distance = round(math.hypot(from_node["x"] - to_node["x"], from_node["y"] - to_node["y"]) / 10, 1)
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": distance,
            "mode": mode,
        })

    corridor_points = [
        ("gate_lobby", "入口大厅", 158, 792),
        ("south_w", "南走廊西段", 450, 790),
        ("south_c", "南走廊中段", 720, 790),
        ("south_e", "南走廊东段", 1010, 790),
        ("south_east", "东南连接廊", 1265, 790),
        ("east_core", "东侧电梯厅", 1508, 690),
        ("east_mid", "东走廊中段", 1508, 520),
        ("east_n", "东走廊北段", 1508, 340),
        ("ne", "东北转角", 1420, 250),
        ("north_e", "北走廊东段", 1170, 250),
        ("north_c", "北走廊中段", 880, 250),
        ("north_w", "北走廊西段", 575, 250),
        ("nw", "西北转角", 255, 250),
        ("west_n", "西走廊北段", 165, 350),
        ("west_s", "西走廊南段", 145, 620),
    ]
    corridor_ring = [key for key, _name, _x, _y in corridor_points]
    inner_corridor = [
        ("mid_w", "中庭西廊", 430, 470),
        ("mid_c", "中庭中廊", 735, 470),
        ("mid_e", "中庭东廊", 1040, 470),
        ("east_branch", "东侧支廊", 1330, 470),
    ]
    room_layout = [
        (1, "北侧教室A", 325, 170, "north_w"),
        (2, "北侧教室B", 520, 170, "north_w"),
        (3, "北侧教室C", 720, 170, "north_c"),
        (4, "北侧教室D", 945, 170, "north_c"),
        (5, "北侧教室E", 1160, 170, "north_e"),
        (6, "东侧综合教室", 1425, 170, "ne"),
        (7, "西侧研讨室", 330, 335, "mid_w"),
        (8, "中区实验室A", 560, 335, "mid_w"),
        (9, "中区实验室B", 790, 335, "mid_c"),
        (10, "中区实验室C", 1000, 335, "mid_e"),
        (11, "东区实验室", 1200, 335, "mid_e"),
        (12, "东侧讨论室", 1355, 420, "east_branch"),
        (13, "南侧教室A", 350, 680, "south_w"),
        (14, "南侧教室B", 570, 720, "south_w"),
        (15, "南侧教室C", 800, 720, "south_c"),
        (16, "南侧教室D", 1020, 720, "south_e"),
        (17, "南侧教室E", 1220, 720, "south_e"),
        (18, "东南功能室", 1540, 660, "east_core"),
    ]

    for floor in floors_list:
        suffix = f"{floor}f"
        for key, name, x, y in corridor_points:
            add_node(f"hall_{key}_{suffix}", f"{floor}层{name}", floor, x, y, "hall")
        for key, name, x, y in inner_corridor:
            add_node(f"hall_{key}_{suffix}", f"{floor}层{name}", floor, x, y, "hall")

        add_node(f"elevator_a_{suffix}", f"{floor}层西电梯", floor, 270, 785, "elevator")
        add_node(f"elevator_b_{suffix}", f"{floor}层东电梯", floor, 1540, 685, "elevator")
        add_node(f"stairs_a_{suffix}", f"{floor}层西北步梯", floor, 205, 235, "stairs")
        add_node(f"stairs_b_{suffix}", f"{floor}层东侧步梯", floor, 1540, 350, "stairs")
        if floor == 1:
            add_node("gate_1f", "一层主入口", floor, 92, 790, "gate")
            add_edge("gate_1f", "hall_gate_lobby_1f")

        for room_index, room_name, x, y, anchor_key in room_layout:
            room_number = floor * 100 + room_index
            add_node(
                f"room_{room_number}",
                f"{room_number} {room_name}",
                floor,
                x,
                y,
                "room",
                door_anchor=f"hall_{anchor_key}_{suffix}",
            )

        corridor = [f"hall_{key}_{suffix}" for key in corridor_ring]
        for left, right in zip(corridor, corridor[1:]):
            add_edge(left, right)
        add_edge(corridor[-1], corridor[0])

        add_edge(f"hall_mid_w_{suffix}", f"hall_mid_c_{suffix}")
        add_edge(f"hall_mid_c_{suffix}", f"hall_mid_e_{suffix}")
        add_edge(f"hall_mid_e_{suffix}", f"hall_east_branch_{suffix}")
        add_edge(f"hall_mid_w_{suffix}", f"hall_west_s_{suffix}")
        add_edge(f"hall_mid_c_{suffix}", f"hall_north_c_{suffix}")
        add_edge(f"hall_mid_c_{suffix}", f"hall_south_c_{suffix}")
        add_edge(f"hall_mid_e_{suffix}", f"hall_north_e_{suffix}")
        add_edge(f"hall_mid_e_{suffix}", f"hall_south_e_{suffix}")
        add_edge(f"hall_east_branch_{suffix}", f"hall_east_mid_{suffix}")

        add_edge(f"elevator_a_{suffix}", f"hall_gate_lobby_{suffix}")
        add_edge(f"elevator_b_{suffix}", f"hall_east_core_{suffix}")
        add_edge(f"stairs_a_{suffix}", f"hall_nw_{suffix}")
        add_edge(f"stairs_b_{suffix}", f"hall_east_n_{suffix}")

        for room_index, _room_name, _x, _y, anchor_key in room_layout:
            add_edge(f"room_{floor * 100 + room_index}", f"hall_{anchor_key}_{suffix}")

    for floor in floors_list[:-1]:
        next_floor = floor + 1
        add_edge(f"elevator_a_{floor}f", f"elevator_a_{next_floor}f", 16, "elevator")
        add_edge(f"elevator_b_{floor}f", f"elevator_b_{next_floor}f", 16, "elevator")
        add_edge(f"stairs_a_{floor}f", f"stairs_a_{next_floor}f", 24, "stairs")
        add_edge(f"stairs_b_{floor}f", f"stairs_b_{next_floor}f", 24, "stairs")

    node_map = {node["id"]: node for node in nodes}
    adjacency = {node["id"]: [] for node in nodes}
    for edge in edges:
        if edge["from"] not in adjacency or edge["to"] not in adjacency:
            continue
        adjacency[edge["from"]].append({**edge, "neighbor": edge["to"]})
        adjacency[edge["to"]].append({
            **edge,
            "from": edge["to"],
            "to": edge["from"],
            "neighbor": edge["from"],
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "node_map": node_map,
        "adjacency": adjacency,
        "floors": floors_display,
        "floor_assets": INDOOR_FLOOR_ASSETS,
        "floor_size": {"width": INDOOR_FLOOR_WIDTH, "height": INDOOR_FLOOR_HEIGHT},
    }


def indoor_edge_weight(edge, vertical_mode="auto"):
    mode = edge.get("mode", "walk")
    if vertical_mode == "elevator" and mode == "stairs":
        return None
    if vertical_mode == "stairs" and mode == "elevator":
        return None
    return float(edge.get("distance", 0))


def indoor_shortest_path(graph, start, end, vertical_mode="auto"):
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
            weight = indoor_edge_weight(edge, vertical_mode=vertical_mode)
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
        previous_node, edge, weight = previous[cursor]
        edges.append({**edge, "weight": weight})
        cursor = previous_node
        path_ids.append(cursor)
    path_ids.reverse()
    edges.reverse()
    return {
        "path_ids": path_ids,
        "path_nodes": [graph["node_map"][node_id] for node_id in path_ids],
        "path_names": [graph["node_map"][node_id]["name"] for node_id in path_ids],
        "edges": edges,
        "total": distances[end],
    }


def indoor_route_steps(result, graph):
    if not result:
        return []
    steps = []
    current_nodes = []
    current_mode = "walk"
    for index, node_id in enumerate(result["path_ids"]):
        node = graph["node_map"][node_id]
        if index == 0:
            current_nodes = [node]
            continue
        edge = result["edges"][index - 1]
        edge_mode = edge.get("mode", "walk")
        if edge_mode != current_mode and current_nodes:
            steps.append({
                "mode": current_mode,
                "floor": current_nodes[0]["floor"],
                "text": " → ".join(item["name"] for item in current_nodes),
            })
            current_nodes = [current_nodes[-1]]
        current_mode = edge_mode
        current_nodes.append(node)
    if current_nodes:
        steps.append({
            "mode": current_mode,
            "floor": current_nodes[0]["floor"],
            "text": " → ".join(item["name"] for item in current_nodes),
        })
    for step in steps:
        if step["mode"] == "elevator":
            step["label"] = "乘坐电梯"
        elif step["mode"] == "stairs":
            step["label"] = "步梯换层"
        else:
            step["label"] = f"{step['floor']}层步行"
    return steps


def prepare_indoor_floors(graph, result):
    path_ids = result["path_ids"] if result else []
    path_id_set = set(path_ids)
    edge_pairs = set()
    if result:
        for edge in result.get("edges", []):
            edge_pairs.add(frozenset((edge["from"], edge["to"])))

    floors = []
    for floor in graph["floors"]:
        floor_nodes = [node for node in graph["nodes"] if node["floor"] == floor]
        floor_edges = []
        for edge in graph["edges"]:
            from_node = graph["node_map"][edge["from"]]
            to_node = graph["node_map"][edge["to"]]
            if from_node["floor"] != floor or to_node["floor"] != floor:
                continue
            floor_edges.append({
                **edge,
                "x1": from_node["x"],
                "y1": from_node["y"],
                "x2": to_node["x"],
                "y2": to_node["y"],
                "is_path": frozenset((edge["from"], edge["to"])) in edge_pairs,
            })
        floors.append({
            "number": floor,
            "image": graph.get("floor_assets", {}).get(floor, ""),
            "width": graph.get("floor_size", {}).get("width", INDOOR_FLOOR_WIDTH),
            "height": graph.get("floor_size", {}).get("height", INDOOR_FLOOR_HEIGHT),
            "nodes": floor_nodes,
            "edges": floor_edges,
            "path_nodes": [graph["node_map"][node_id] for node_id in path_ids if graph["node_map"][node_id]["floor"] == floor],
            "active": any(node["floor"] == floor for node in (graph["node_map"][node_id] for node_id in path_ids)),
        })
    return floors


def indoor_node_options(graph):
    return [
        node for node in graph["nodes"]
        if node["type"] in {"gate", "room", "elevator", "stairs"}
    ]


def default_indoor_collector_payload():
    return {
        "meta": {
            "building_id": "demo_building",
            "building_name": "室内导航采集楼",
            "width": INDOOR_FLOOR_WIDTH,
            "height": INDOOR_FLOOR_HEIGHT,
            "floor_assets": INDOOR_FLOOR_ASSETS,
        },
        "floors": {
            str(floor): {
                "nodes": [],
                "edges": [],
                "links": [],
            }
            for floor in sorted(INDOOR_FLOOR_ASSETS)
        },
    }


def load_indoor_collector_payload():
    payload = read_json_file(INDOOR_COLLECTOR_FILE, default_indoor_collector_payload())
    default_payload = default_indoor_collector_payload()
    payload.setdefault("meta", default_payload["meta"])
    payload.setdefault("floors", default_payload["floors"])
    for floor in sorted(INDOOR_FLOOR_ASSETS):
        floor_key = str(floor)
        payload["floors"].setdefault(floor_key, {"nodes": [], "edges": [], "links": []})
        payload["floors"][floor_key].setdefault("nodes", [])
        payload["floors"][floor_key].setdefault("edges", [])
        payload["floors"][floor_key].setdefault("links", [])
    return payload


def save_indoor_collector_payload(payload):
    write_json_atomic(INDOOR_COLLECTOR_FILE, payload)
    return payload


def indoor_point_distance(point_a, point_b):
    return round(math.hypot(float(point_a[0]) - float(point_b[0]), float(point_a[1]) - float(point_b[1])) / 10, 1)


def indoor_polyline_distance(points):
    return round(sum(indoor_point_distance(start, end) for start, end in zip(points, points[1:])), 1)


def indoor_collector_summary(payload=None):
    payload = payload or load_indoor_collector_payload()
    nodes = 0
    edges = 0
    links = 0
    road_points = 0
    for floor_payload in payload.get("floors", {}).values():
        nodes += len(floor_payload.get("nodes", []))
        edges += len(floor_payload.get("edges", []))
        links += len(floor_payload.get("links", []))
        road_points += sum(len(edge.get("geometry") or []) for edge in floor_payload.get("edges", []))
    return {
        "floors": len(payload.get("floors", {})),
        "nodes": nodes + road_points,
        "edges": edges + links,
        "manual_nodes": nodes,
        "manual_edges": edges,
        "links": links,
        "road_points": road_points,
    }


def normalize_indoor_collector_node(payload, existing_count=0):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    x = min(max(float(payload.get("x", 0)), 0), INDOOR_FLOOR_WIDTH)
    y = min(max(float(payload.get("y", 0)), 0), INDOOR_FLOOR_HEIGHT)
    node_type = str(payload.get("type") or "hall").strip()
    if node_type not in {"hall", "room", "gate", "elevator", "stairs"}:
        node_type = "hall"
    core_id = str(payload.get("core_id") or payload.get("core") or "").strip()
    core_meta = INDOOR_VERTICAL_CORES.get(core_id)
    if node_type in {"elevator", "stairs"}:
        if core_meta and core_meta.get("type") != node_type:
            raise ValueError("核心筒编号与关键点类型不匹配")
        if not core_meta:
            core_id = ""
    else:
        core_id = ""
    name = str(payload.get("name") or f"{floor}F采集点{existing_count + 1}").strip()
    node_id = str(payload.get("id") or f"indoor_{floor}f_{existing_count + 1:03d}").strip()
    node = {
        "id": node_id,
        "name": name,
        "floor": floor,
        "x": round(x, 1),
        "y": round(y, 1),
        "type": node_type,
    }
    if core_id:
        node["core_id"] = core_id
        node["core_name"] = INDOOR_VERTICAL_CORES[core_id]["label"]
    return node


def normalize_indoor_collector_edge(payload, nodes, existing_count=0):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    mode = str(payload.get("mode") or "walk").strip()
    if mode not in INDOOR_VERTICAL_MODES and mode != "walk":
        mode = "walk"
    geometry = payload.get("geometry") or payload.get("points") or []
    points = []
    for point in geometry:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        points.append([
            round(min(max(float(point[0]), 0), INDOOR_FLOOR_WIDTH), 1),
            round(min(max(float(point[1]), 0), INDOOR_FLOOR_HEIGHT), 1),
        ])
    node_map = {str(node.get("id")): node for node in nodes}
    from_id = str(payload.get("from") or "").strip()
    to_id = str(payload.get("to") or "").strip()
    if len(points) < 2 and from_id in node_map and to_id in node_map and from_id != to_id:
        points = [
            [round(float(node_map[from_id]["x"]), 1), round(float(node_map[from_id]["y"]), 1)],
            [round(float(node_map[to_id]["x"]), 1), round(float(node_map[to_id]["y"]), 1)],
        ]
    if len(points) < 2:
        raise ValueError("室内路径至少需要两个采样点")
    poi_links = []
    for link in payload.get("poi_links") or []:
        try:
            index = int(link.get("index", -1))
        except (TypeError, ValueError):
            continue
        poi_id = str(link.get("poi") or link.get("id") or "").strip()
        if poi_id in node_map and 0 <= index < len(points):
            poi_links.append({"index": index, "poi": poi_id})
    road_links = []
    for link in payload.get("road_links") or []:
        try:
            index = int(link.get("index", -1))
            target_index = int(link.get("target_index", -1))
        except (TypeError, ValueError):
            continue
        target_edge = str(link.get("edge") or "").strip()
        if target_edge and 0 <= index < len(points) and target_index >= 0:
            road_links.append({"index": index, "edge": target_edge, "target_index": target_index})
    edge_id = str(payload.get("id") or f"indoor_edge_{floor}f_{existing_count + 1:03d}").strip()
    return {
        "id": edge_id,
        "name": str(payload.get("name") or f"{floor}F室内路径{existing_count + 1}").strip(),
        "floor": floor,
        "from": from_id,
        "to": to_id,
        "geometry": points,
        "poi_links": poi_links,
        "road_links": road_links,
        "distance": indoor_polyline_distance(points),
        "mode": mode,
        "road_type": str(payload.get("road_type") or "corridor").strip(),
    }


def indoor_collector_ref_point(ref, nodes, edges):
    ref_type = str((ref or {}).get("type") or "").strip()
    if ref_type in {"node", "poi"}:
        node_id = str((ref or {}).get("id") or (ref or {}).get("poi") or "").strip()
        node = next((item for item in nodes if str(item.get("id")) == node_id), None)
        if not node:
            return None
        return [float(node["x"]), float(node["y"])]
    if ref_type == "road":
        edge_id = str((ref or {}).get("edge") or "").strip()
        try:
            point_index = int((ref or {}).get("point_index", (ref or {}).get("target_index", -1)))
        except (TypeError, ValueError):
            return None
        edge = next((item for item in edges if str(item.get("id")) == edge_id), None)
        geometry = edge.get("geometry") if edge else []
        if not edge or point_index < 0 or point_index >= len(geometry):
            return None
        point = geometry[point_index]
        return [float(point[0]), float(point[1])]
    return None


def normalize_indoor_collector_ref(ref, nodes, edges):
    ref_type = str((ref or {}).get("type") or "").strip()
    if ref_type in {"node", "poi"}:
        node_id = str((ref or {}).get("id") or (ref or {}).get("poi") or "").strip()
        if not any(str(node.get("id")) == node_id for node in nodes):
            raise ValueError("关键点端点不存在")
        return {"type": "node", "id": node_id}
    if ref_type == "road":
        edge_id = str((ref or {}).get("edge") or "").strip()
        try:
            point_index = int((ref or {}).get("point_index", (ref or {}).get("target_index", -1)))
        except (TypeError, ValueError):
            raise ValueError("路径端点索引无效")
        edge = next((item for item in edges if str(item.get("id")) == edge_id), None)
        if not edge or point_index < 0 or point_index >= len(edge.get("geometry") or []):
            raise ValueError("路径端点不存在")
        return {"type": "road", "edge": edge_id, "point_index": point_index}
    raise ValueError("吸附端点类型无效")


def normalize_indoor_collector_link(payload, nodes, edges, existing_count=0):
    floor = int(payload.get("floor", 1))
    if floor not in INDOOR_FLOOR_ASSETS:
        raise ValueError("楼层无效")
    a_ref = normalize_indoor_collector_ref(payload.get("a") or payload.get("from") or {}, nodes, edges)
    b_ref = normalize_indoor_collector_ref(payload.get("b") or payload.get("to") or {}, nodes, edges)
    if json.dumps(a_ref, sort_keys=True) == json.dumps(b_ref, sort_keys=True):
        raise ValueError("不能吸附同一个端点")
    if sorted([a_ref["type"], b_ref["type"]]) == ["node", "node"]:
        raise ValueError("关键点不能直接吸附关键点，请连接到路径点")
    point_a = indoor_collector_ref_point(a_ref, nodes, edges)
    point_b = indoor_collector_ref_point(b_ref, nodes, edges)
    if not point_a or not point_b:
        raise ValueError("吸附端点坐标无效")
    link_id = str(payload.get("id") or f"indoor_link_{floor}f_{existing_count + 1:03d}").strip()
    return {
        "id": link_id,
        "floor": floor,
        "kind": "node_road" if "node" in {a_ref["type"], b_ref["type"]} else "road_road",
        "a": a_ref,
        "b": b_ref,
        "geometry": [
            [round(point_a[0], 1), round(point_a[1], 1)],
            [round(point_b[0], 1), round(point_b[1], 1)],
        ],
        "distance": indoor_polyline_distance([point_a, point_b]),
        "mode": str(payload.get("mode") or "walk").strip() or "walk",
    }


def build_indoor_graph_from_collector(payload):
    nodes = []
    edges = []
    node_map = {}
    road_point_lookup = {}

    def add_node(node):
        if node["id"] in node_map:
            return node["id"]
        nodes.append(node)
        node_map[node["id"]] = node
        return node["id"]

    def add_edge(from_id, to_id, distance, mode="walk"):
        if not from_id or not to_id or from_id == to_id:
            return
        edges.append({
            "from": from_id,
            "to": to_id,
            "distance": max(float(distance or 0), 0.1),
            "mode": mode,
        })

    for floor_key, floor_payload in (payload.get("floors") or {}).items():
        try:
            floor = int(floor_key)
        except (TypeError, ValueError):
            continue
        for raw_node in floor_payload.get("nodes", []):
            try:
                normalized = normalize_indoor_collector_node(raw_node)
            except (TypeError, ValueError):
                continue
            add_node(normalized)
        for edge_index, raw_edge in enumerate(floor_payload.get("edges", [])):
            try:
                edge = normalize_indoor_collector_edge(raw_edge, floor_payload.get("nodes", []), edge_index)
            except (TypeError, ValueError):
                continue
            previous_node_id = ""
            for point_index, point in enumerate(edge.get("geometry") or []):
                road_node_id = f"road_{edge['id']}_{point_index:03d}"
                add_node({
                    "id": road_node_id,
                    "name": f"{edge.get('name', '室内路径')}#{point_index + 1}",
                    "floor": floor,
                    "x": point[0],
                    "y": point[1],
                    "type": "hall",
                    "selectable": False,
                })
                road_point_lookup[(edge["id"], point_index)] = road_node_id
                if previous_node_id:
                    previous = node_map[previous_node_id]
                    add_edge(previous_node_id, road_node_id, indoor_point_distance([previous["x"], previous["y"]], point), edge.get("mode", "walk"))
                previous_node_id = road_node_id
            for link in edge.get("poi_links", []):
                road_node_id = road_point_lookup.get((edge["id"], link.get("index")))
                if road_node_id and link.get("poi") in node_map:
                    add_edge(link["poi"], road_node_id, indoor_point_distance(
                        [node_map[link["poi"]]["x"], node_map[link["poi"]]["y"]],
                        [node_map[road_node_id]["x"], node_map[road_node_id]["y"]],
                    ))
            for link in edge.get("road_links", []):
                from_id = road_point_lookup.get((edge["id"], link.get("index")))
                to_id = road_point_lookup.get((link.get("edge"), link.get("target_index")))
                if from_id and to_id:
                    add_edge(from_id, to_id, indoor_point_distance(
                        [node_map[from_id]["x"], node_map[from_id]["y"]],
                        [node_map[to_id]["x"], node_map[to_id]["y"]],
                    ))
        for link_index, raw_link in enumerate(floor_payload.get("links", [])):
            try:
                link = normalize_indoor_collector_link(
                    raw_link,
                    floor_payload.get("nodes", []),
                    floor_payload.get("edges", []),
                    link_index,
                )
            except (TypeError, ValueError):
                continue

            def graph_node_for_ref(ref):
                if ref.get("type") == "node":
                    return ref.get("id") if ref.get("id") in node_map else ""
                return road_point_lookup.get((ref.get("edge"), ref.get("point_index")), "")

            from_id = graph_node_for_ref(link.get("a") or {})
            to_id = graph_node_for_ref(link.get("b") or {})
            add_edge(from_id, to_id, link.get("distance", 0), link.get("mode", "walk"))

    for floor in sorted(INDOOR_FLOOR_ASSETS)[:-1]:
        current = [node for node in nodes if node.get("floor") == floor and node.get("type") in {"elevator", "stairs"}]
        upper = [node for node in nodes if node.get("floor") == floor + 1 and node.get("type") in {"elevator", "stairs"}]
        for node in current:
            candidates = [item for item in upper if item.get("type") == node.get("type")]
            if not candidates:
                continue
            same_core = [
                item for item in candidates
                if node.get("core_id") and item.get("core_id") == node.get("core_id")
            ]
            if same_core:
                target = same_core[0]
                add_edge(node["id"], target["id"], 16 if node.get("type") == "elevator" else 24, node.get("type"))
                continue
            nearest = min(candidates, key=lambda item: math.hypot(float(item["x"]) - float(node["x"]), float(item["y"]) - float(node["y"])))
            if math.hypot(float(nearest["x"]) - float(node["x"]), float(nearest["y"]) - float(node["y"])) <= 120:
                add_edge(node["id"], nearest["id"], 16 if node.get("type") == "elevator" else 24, node.get("type"))

    adjacency = {node["id"]: [] for node in nodes}
    for edge in edges:
        if edge["from"] not in adjacency or edge["to"] not in adjacency:
            continue
        adjacency[edge["from"]].append({**edge, "neighbor": edge["to"]})
        adjacency[edge["to"]].append({
            **edge,
            "from": edge["to"],
            "to": edge["from"],
            "neighbor": edge["from"],
        })
    return {
        "nodes": nodes,
        "edges": edges,
        "node_map": node_map,
        "adjacency": adjacency,
        "floors": [1, 2, 3, 4],
        "floor_assets": INDOOR_FLOOR_ASSETS,
        "floor_size": {"width": INDOOR_FLOOR_WIDTH, "height": INDOOR_FLOOR_HEIGHT},
    }


def is_indoor_building_node(node):
    return str((node or {}).get("kind", "")).strip() in INDOOR_BUILDING_TYPES


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


def load_facilities(parent_place=None):
    signature = files_signature([FACILITIES_FILE, XMU_COLLECTOR_FACILITIES_FILE])
    if signature == FACILITIES_CACHE.get("signature"):
        records = FACILITIES_CACHE.get("records", [])
        if parent_place:
            return [facility for facility in records if facility.get("parent_place") == parent_place]
        return list(records)

    facilities = []
    if not os.path.exists(FACILITIES_FILE):
        csv_facilities = []
    else:
        csv_facilities = []
        with open(FACILITIES_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if parent_place and row.get("parent_place") != parent_place:
                    continue
                try:
                    row["id"] = int(row["id"])
                except (ValueError, KeyError):
                    row["id"] = 0
                row.setdefault("tags", "")
                csv_facilities.append(row)
    facilities.extend(csv_facilities)

    for item in load_collector_facilities():
        facility = normalize_collector_facility(item, len(facilities))
        facility["tags_text"] = " ".join(facility.get("tags", []))
        facilities.append(facility)

    FACILITIES_CACHE["signature"] = signature
    FACILITIES_CACHE["records"] = facilities
    if parent_place:
        return [facility for facility in facilities if facility.get("parent_place") == parent_place]
    return facilities


def find_nearby_facilities(graph, start_node, facility_type="", keyword="", max_distance=None):
    result = []
    keyword_lower = keyword.lower()
    if not start_node or start_node not in graph.get("node_map", {}):
        return result
    route_tree = dijkstra_shortest_tree(graph, start_node, strategy="distance", transport="walk")
    if route_tree is None:
        return result

    for facility in load_facilities(graph.get("facility_parent_place", graph.get("place_id"))):
        tags = facility.get("tags", [])
        if isinstance(tags, str):
            tags_text = tags
        else:
            tags_text = " ".join(tags)
        searchable = " ".join([
            str(facility.get("name", "")),
            str(facility.get("type", "")),
            str(facility.get("description", "")),
            tags_text,
        ]).lower()

        if facility_type and facility_type not in [facility.get("type"), *normalize_tags(tags)]:
            continue
        if keyword and keyword_lower not in searchable:
            continue

        nearest_node = resolve_facility_nearest_node(facility, graph, road_only=True)
        path = route_from_shortest_tree(graph, route_tree, nearest_node)
        if path is None:
            continue

        item = facility.copy()
        item["distance"] = round(path["total"], 1)
        if max_distance is not None and item["distance"] > max_distance:
            continue
        item["path_names"] = " -> ".join(path.get("display_path_names", path["path_names"]))
        item["walk_minutes"] = round(item["distance"] / 1.2 / 60, 1)
        result.append(item)

    return sorted(result, key=lambda item: item["distance"])


def parse_place_tag_query(tag_keyword):
    return [
        item.strip()
        for item in re.split(r"[;；,，\s]+", tag_keyword or "")
        if item.strip()
    ]


def place_matches_filters(place, keyword="", tag_keyword="", place_type="", city=""):
    if keyword:
        keyword_terms = split_search_terms(keyword) or [normalize_search_text(keyword)]
        place_blob = place_search_blob(place)
        if not all(term in place_blob for term in keyword_terms if term):
            return False

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


# =========================
# 推荐算法函数
# =========================
def calculate_base_score(place):
    """
    基础推荐分：
    评分占 60%
    热度占 40%
    热度做一个缩放，避免数值差太大
    """
    return place["rating"] * 60 + place["popularity"] * 0.4


def calculate_personalized_score(place, preferred_tags):
    score = calculate_base_score(place)

    matched_tags = 0
    for tag in preferred_tags:
        if tag and tag in place["tags_list"]:
            matched_tags += 1

    # 每匹配一个兴趣标签，加 15 分
    score += matched_tags * 15
    return score


def get_top_k_recommendations(places, preferred_tags=None, k=10, place_type="", city="", keyword="", tag_keyword=""):
    if preferred_tags is None:
        preferred_tags = []

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

        candidate_count += 1
        place_copy = place.copy()
        place_copy["recommend_score"] = calculate_personalized_score(place_copy, preferred_tags)

        item = (place_copy["recommend_score"], index, place_copy)
        if len(heap) < k:
            heapq.heappush(heap, item)
        elif item[0] > heap[0][0]:
            heapq.heapreplace(heap, item)

    # Only the k selected records are sorted for display.
    result = [item[2] for item in sorted(heap, key=lambda x: x[0], reverse=True)]
    stats = {
        "scanned_count": scanned_count,
        "candidate_count": candidate_count,
        "returned_count": len(result),
        "algorithm": "模糊查找 + 小根堆 Top-K",
    }
    return result, stats


# =========================
# 旅游日记管理函数
# =========================
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
        invalidate_diary_index_cache()
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


# =========================
# 路由
# =========================
@app.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("home"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        avatar_file = request.files.get("avatar")

        if not username or not password or not confirm_password:
            flash("用户名和密码不能为空")
            return render_template("register.html")

        if password != confirm_password:
            flash("两次输入的密码不一致")
            return render_template("register.html")

        user_id = create_user(username, password)
        if not user_id:
            flash("用户名已存在，请更换用户名")
            return render_template("register.html")

        avatar_path = save_uploaded_user_avatar(avatar_file, username, user_id)
        update_user_avatar_path(user_id, avatar_path)

        flash("注册成功，请登录")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("用户名和密码不能为空")
            return render_template("login.html")

        user = get_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            session["username"] = user["username"]
            session["avatar_path"] = user["avatar_path"] if "avatar_path" in user.keys() else ""
            return redirect(url_for("home"))
        else:
            flash("用户名或密码错误")
            return render_template("login.html")

    return render_template("login.html")


@app.route("/home")
def home():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    current_user = get_logged_in_user()
    return render_template(
        "home.html",
        username=session["username"],
        current_user=current_user,
        current_user_avatar_url=get_user_avatar_url(current_user) if current_user else "",
    )


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("你已退出登录")
    return redirect(url_for("login"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    current_user = get_logged_in_user()
    if current_user is None:
        flash("账号不存在，请重新登录")
        session.pop("username", None)
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action", "account").strip().lower()
        if action == "avatar":
            avatar_file = request.files.get("avatar")
            if not avatar_file or not avatar_file.filename:
                flash("请选择头像文件")
            else:
                avatar_path = save_uploaded_user_avatar(avatar_file, current_user["username"], current_user["id"])
                update_user_avatar_path(current_user["id"], avatar_path)
                session["avatar_path"] = avatar_path
                flash("头像已更新")
            return redirect(url_for("profile"))

        new_username = request.form.get("username", "").strip()
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        if new_password and new_password != confirm_password:
            flash("两次输入的新密码不一致")
            return redirect(url_for("profile"))
        ok, message = update_user_account(
            current_user["id"],
            new_username=new_username,
            current_password=current_password,
            new_password=new_password,
        )
        flash(message)
        if ok:
            session["username"] = new_username
        return redirect(url_for("profile"))

    current_user = get_logged_in_user()
    stats = get_user_activity_stats(current_user)
    my_diaries = load_user_diaries(current_user["username"], limit=6)
    favorite_diaries = load_favorite_diaries(current_user["id"], limit=6)
    favorite_foods = load_favorite_foods(current_user["id"], limit=6)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT diary_comments.*, diaries.title AS diary_title
        FROM diary_comments
        LEFT JOIN diaries ON diaries.id = diary_comments.diary_id
        WHERE diary_comments.author = ?
        ORDER BY diary_comments.created_at DESC, diary_comments.id DESC
        LIMIT 5
        """,
        (current_user["username"],)
    )
    recent_comments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template(
        "profile.html",
        username=current_user["username"],
        current_user=current_user,
        current_user_avatar_url=get_user_avatar_url(current_user),
        stats=stats,
        my_diaries=my_diaries,
        favorite_diaries=favorite_diaries,
        favorite_foods=favorite_foods,
        recent_comments=recent_comments,
    )


@app.route("/user/<int:user_id>")
def user_profile(user_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    profile_user = get_user_by_id(user_id)
    if profile_user is None:
        flash("未找到该用户")
        return redirect(url_for("diaries"))

    current_user = get_logged_in_user()
    user_diaries = load_user_diaries(profile_user["username"], limit=12)
    stats = get_user_activity_stats(profile_user)
    return render_template(
        "user_profile.html",
        username=session["username"],
        current_user=current_user,
        profile_user=profile_user,
        profile_avatar_url=get_user_avatar_url(profile_user),
        stats=stats,
        user_diaries=user_diaries,
        is_self=current_user and current_user["id"] == profile_user["id"],
    )


@app.route("/indoor")
def indoor():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    building_id = request.args.get("building_id", "demo_building").strip() or "demo_building"
    building_name = request.args.get("building_name", "").strip()

    if not building_name:
        graph_node = next((node for node in load_route_graph(DEFAULT_PLACE_ID).get("nodes", []) if str(node.get("id")) == building_id), None)
        building_name = graph_node.get("name") if graph_node else "通用教学楼"

    graph = build_indoor_graph(building_id)

    default_start = INDOOR_DEFAULT_START
    default_end = INDOOR_DEFAULT_END

    start = request.args.get("start", default_start).strip() or default_start
    end = request.args.get("end", default_end).strip() or default_end
    vertical_mode = request.args.get("vertical_mode", "auto").strip().lower()

    if start not in graph["node_map"]:
        start = default_start
    if end not in graph["node_map"]:
        end = default_end
    if vertical_mode not in INDOOR_VERTICAL_MODES:
        vertical_mode = "auto"

    route_result = indoor_shortest_path(graph, start, end, vertical_mode=vertical_mode)
    return render_template(
        "indoor.html",
        username=session["username"],
        building_id=building_id,
        building_name=building_name,
        start=start,
        end=end,
        vertical_mode=vertical_mode,
        node_options=indoor_node_options(graph),
        floors=prepare_indoor_floors(graph, route_result),
        route_result=route_result,
        route_steps=indoor_route_steps(route_result, graph),
        vertical_modes=[
            {"value": "auto", "label": "自动选择"},
            {"value": "elevator", "label": "优先电梯"},
            {"value": "stairs", "label": "只走步梯"},
        ],
    )


@app.route("/indoor/collector")
def indoor_collector():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    payload = load_indoor_collector_payload()
    return render_template(
        "indoor_collector.html",
        username=session["username"],
        payload=payload,
        summary=indoor_collector_summary(payload),
    )


@app.route("/api/indoor/collector")
def indoor_collector_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = load_indoor_collector_payload()
    return jsonify({
        **payload,
        "summary": indoor_collector_summary(payload),
    })


@app.route("/api/indoor/collector/node", methods=["POST"])
def indoor_collector_node_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = load_indoor_collector_payload()
        source = request.get_json(force=True) or {}
        floor_key = str(int(source.get("floor", 1)))
        floor_payload = payload["floors"].setdefault(floor_key, {"nodes": [], "edges": [], "links": []})
        node = normalize_indoor_collector_node(source, len(floor_payload.get("nodes", [])))
        floor_payload["nodes"] = [item for item in floor_payload.get("nodes", []) if item.get("id") != node["id"]]
        floor_payload["nodes"].append(node)
        save_indoor_collector_payload(payload)
        return jsonify({"ok": True, "node": node, "summary": indoor_collector_summary(payload)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/indoor/collector/edge", methods=["POST"])
def indoor_collector_edge_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = load_indoor_collector_payload()
        source = request.get_json(force=True) or {}
        floor_key = str(int(source.get("floor", 1)))
        floor_payload = payload["floors"].setdefault(floor_key, {"nodes": [], "edges": [], "links": []})
        edge = normalize_indoor_collector_edge(
            source,
            floor_payload.get("nodes", []),
            len(floor_payload.get("edges", [])),
        )
        floor_payload["edges"] = [item for item in floor_payload.get("edges", []) if item.get("id") != edge["id"]]
        floor_payload["edges"].append(edge)
        save_indoor_collector_payload(payload)
        return jsonify({"ok": True, "edge": edge, "summary": indoor_collector_summary(payload)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/indoor/collector/link", methods=["POST"])
def indoor_collector_link_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = load_indoor_collector_payload()
        source = request.get_json(force=True) or {}
        floor_key = str(int(source.get("floor", 1)))
        floor_payload = payload["floors"].setdefault(floor_key, {"nodes": [], "edges": [], "links": []})
        link = normalize_indoor_collector_link(
            source,
            floor_payload.get("nodes", []),
            floor_payload.get("edges", []),
            len(floor_payload.get("links", [])),
        )

        def ref_key(ref):
            if ref.get("type") == "node":
                return f"node:{ref.get('id')}"
            return f"road:{ref.get('edge')}:{ref.get('point_index')}"

        new_pair = sorted([ref_key(link["a"]), ref_key(link["b"])])
        for existing in floor_payload.get("links", []):
            existing_pair = sorted([
                ref_key((existing or {}).get("a") or {}),
                ref_key((existing or {}).get("b") or {}),
            ])
            if existing_pair == new_pair:
                return jsonify({"error": "该吸附关系已存在"}), 400
        floor_payload.setdefault("links", []).append(link)
        save_indoor_collector_payload(payload)
        return jsonify({"ok": True, "link": link, "summary": indoor_collector_summary(payload)})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/indoor/collector/restore", methods=["POST"])
def indoor_collector_restore_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    source = request.get_json(force=True) or {}
    if not isinstance(source.get("floors"), dict):
        return jsonify({"error": "采集快照格式无效"}), 400
    payload = default_indoor_collector_payload()
    payload["meta"].update(source.get("meta") if isinstance(source.get("meta"), dict) else {})
    for floor in sorted(INDOOR_FLOOR_ASSETS):
        floor_key = str(floor)
        floor_source = source["floors"].get(floor_key, {})
        payload["floors"][floor_key] = {
            "nodes": floor_source.get("nodes", []) if isinstance(floor_source.get("nodes", []), list) else [],
            "edges": floor_source.get("edges", []) if isinstance(floor_source.get("edges", []), list) else [],
            "links": floor_source.get("links", []) if isinstance(floor_source.get("links", []), list) else [],
        }
    save_indoor_collector_payload(payload)
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


@app.route("/api/indoor/collector/node/<node_id>", methods=["DELETE"])
def indoor_collector_node_delete_api(node_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = load_indoor_collector_payload()
    removed = False
    for floor_payload in payload.get("floors", {}).values():
        before = len(floor_payload.get("nodes", []))
        floor_payload["nodes"] = [
            node for node in floor_payload.get("nodes", [])
            if str(node.get("id")) != str(node_id)
        ]
        removed = removed or len(floor_payload["nodes"]) != before
        floor_payload["links"] = [
            link for link in floor_payload.get("links", [])
            if str(((link.get("a") or {}).get("id"))) != str(node_id)
            and str(((link.get("b") or {}).get("id"))) != str(node_id)
        ]
        for edge in floor_payload.get("edges", []):
            edge["poi_links"] = [
                link for link in edge.get("poi_links", [])
                if str(link.get("poi")) != str(node_id)
            ]
    if not removed:
        return jsonify({"error": "节点不存在"}), 404
    save_indoor_collector_payload(payload)
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


@app.route("/api/indoor/collector/edge/<edge_id>", methods=["DELETE"])
def indoor_collector_edge_delete_api(edge_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = load_indoor_collector_payload()
    removed = False
    for floor_payload in payload.get("floors", {}).values():
        before = len(floor_payload.get("edges", []))
        floor_payload["edges"] = [
            edge for edge in floor_payload.get("edges", [])
            if str(edge.get("id")) != str(edge_id)
        ]
        removed = removed or len(floor_payload["edges"]) != before
        floor_payload["links"] = [
            link for link in floor_payload.get("links", [])
            if str(((link.get("a") or {}).get("edge"))) != str(edge_id)
            and str(((link.get("b") or {}).get("edge"))) != str(edge_id)
        ]
        for edge in floor_payload.get("edges", []):
            edge["road_links"] = [
                link for link in edge.get("road_links", [])
                if str(link.get("edge")) != str(edge_id)
            ]
    if not removed:
        return jsonify({"error": "路径不存在"}), 404
    save_indoor_collector_payload(payload)
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


@app.route("/api/indoor/collector/edge/<edge_id>/point/<int:point_index>", methods=["DELETE"])
def indoor_collector_edge_point_delete_api(edge_id, point_index):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = load_indoor_collector_payload()
    found = False
    for floor_payload in payload.get("floors", {}).values():
        for edge in floor_payload.get("edges", []):
            if str(edge.get("id")) != str(edge_id):
                continue
            geometry = edge.get("geometry") or []
            if point_index < 0 or point_index >= len(geometry):
                return jsonify({"error": "路径点不存在"}), 404
            if len(geometry) <= 2:
                return jsonify({"error": "路径至少保留两个点"}), 400
            found = True
            edge["geometry"] = geometry[:point_index] + geometry[point_index + 1:]
            edge["distance"] = indoor_polyline_distance(edge["geometry"])
            adjusted_poi_links = []
            for link in edge.get("poi_links", []):
                index = int(link.get("index", -1))
                if index == point_index:
                    continue
                adjusted_poi_links.append({**link, "index": index - 1 if index > point_index else index})
            edge["poi_links"] = adjusted_poi_links

            adjusted_road_links = []
            for link in edge.get("road_links", []):
                index = int(link.get("index", -1))
                if index == point_index:
                    continue
                adjusted_road_links.append({**link, "index": index - 1 if index > point_index else index})
            edge["road_links"] = adjusted_road_links

            adjusted_links = []
            for link in floor_payload.get("links", []):
                next_link = copy.deepcopy(link)
                should_keep = True
                for key in ("a", "b"):
                    ref = next_link.get(key) or {}
                    if ref.get("type") != "road" or str(ref.get("edge")) != str(edge_id):
                        continue
                    ref_index = int(ref.get("point_index", -1))
                    if ref_index == point_index:
                        should_keep = False
                        break
                    if ref_index > point_index:
                        ref["point_index"] = ref_index - 1
                        point = edge["geometry"][ref["point_index"]]
                        geometry_index = 0 if key == "a" else 1
                        if len(next_link.get("geometry", [])) > geometry_index:
                            next_link["geometry"][geometry_index] = [point[0], point[1]]
                if should_keep:
                    adjusted_links.append(next_link)
            floor_payload["links"] = adjusted_links
            break
    if not found:
        return jsonify({"error": "路径不存在"}), 404
    save_indoor_collector_payload(payload)
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


@app.route("/api/indoor/collector/link/<link_id>", methods=["DELETE"])
def indoor_collector_link_delete_api(link_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = load_indoor_collector_payload()
    removed = False
    for floor_payload in payload.get("floors", {}).values():
        before = len(floor_payload.get("links", []))
        floor_payload["links"] = [
            link for link in floor_payload.get("links", [])
            if str(link.get("id")) != str(link_id)
        ]
        removed = removed or len(floor_payload["links"]) != before
    if not removed:
        return jsonify({"error": "吸附关系不存在"}), 404
    save_indoor_collector_payload(payload)
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


@app.route("/api/indoor/collector/clear", methods=["POST"])
def indoor_collector_clear_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = save_indoor_collector_payload(default_indoor_collector_payload())
    return jsonify({"ok": True, "summary": indoor_collector_summary(payload)})


# =========================
# places ??????????
# =========================
@app.route("/places")
def places():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    keyword = request.args.get("keyword", "").strip()
    tag_keyword = request.args.get("tag_keyword", "").strip()
    place_type = request.args.get("type", "").strip()
    city = request.args.get("city", "").strip()
    sort_by = request.args.get("sort_by", "default").strip()
    selected_tags = request.args.getlist("preferred_tags")
    try:
        k = int(request.args.get("k", "10"))
    except ValueError:
        k = 10
    k = max(1, min(k, 20))

    all_places = load_places()
    filtered_places = filter_and_sort_places(
        all_places,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
        sort_by=sort_by
    )
    filter_options = get_place_filter_options(all_places)
    recommended_places, recommendation_stats = get_top_k_recommendations(
        all_places,
        preferred_tags=selected_tags,
        k=k,
        place_type=place_type,
        city=city,
        keyword=keyword,
        tag_keyword=tag_keyword,
    )
    page = parse_positive_int(request.args.get("page", 1))
    visible_places, pagination_state = paginate_items(filtered_places, page, PLACES_PAGE_SIZE)
    pagination = build_pagination(
        "places",
        pagination_state["page"],
        pagination_state["total_pages"],
        {
            "keyword": keyword,
            "tag_keyword": tag_keyword,
            "type": place_type,
            "city": city,
            "sort_by": sort_by,
            "preferred_tags": selected_tags,
            "k": k,
        },
    )

    return render_template(
        "places.html",
        username=session["username"],
        places=visible_places,
        recommended_places=recommended_places,
        recommendation_stats=recommendation_stats,
        total_places=len(all_places),
        filtered_places_total=len(filtered_places),
        pagination=pagination,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
        sort_by=sort_by,
        selected_tags=selected_tags,
        all_available_tags=filter_options["tags"],
        k=k,
        cities=filter_options["cities"],
        place_types=filter_options["place_types"],
    )


# =========================
# places ??????
# =========================
@app.route("/place/<int:place_id>")
def place_detail(place_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place = get_place_by_id(place_id)
    if place is None:
        flash("未找到该景点或学校")
        return redirect(url_for("places"))

    related_diaries = get_related_diaries_for_place(place, load_diaries(sort_by="hot_rating_desc"), limit=6)

    return render_template(
        "place_detail.html",
        username=session["username"],
        place=place,
        related_diaries=related_diaries
    )


@app.route("/place/<int:place_id>/image/upload", methods=["POST"])
def upload_place_image(place_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place = get_place_by_id(place_id)
    if place is None:
        flash("未找到该景点或学校")
        return redirect(url_for("places"))

    try:
        local_path, original_width, original_height, original_name = save_uploaded_place_cover(
            request.files.get("image_file"),
            place,
        )
        save_place_image_record(place, local_path, original_width, original_height, original_name)
        flash("封面图片已更新")
    except ValueError as exc:
        flash(str(exc))

    return redirect(url_for("place_detail", place_id=place_id))


# =========================
# places ?????????
# =========================
@app.route("/places/recommend", methods=["GET", "POST"])
def recommend_places():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    params = []
    source = request.values if request.method == "POST" else request.args
    for key in source.keys():
        values = source.getlist(key)
        params.extend((key, value) for value in values if value not in ("", None))
    return redirect(url_for("places") + ("?" + urlencode(params, doseq=True) if params else ""))


# =========================
# route ?????????
# =========================
@app.route("/route")
def route():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    collect_mode = request.args.get("collect", "").strip() in ("1", "true", "yes", "on")
    food_pick_mode = request.args.get("food_pick", "").strip() in ("1", "true", "yes", "on")
    return_to = request.args.get("return_to", "").strip()
    return_food_key = request.args.get("return_food_key", "").strip()
    return_place_id = request.args.get("return_place_id", place_id).strip() or place_id
    edit_roads = request.args.get("edit_roads", "").strip() in ("1", "true", "yes", "on")

    graph = load_route_graph(place_id)
    start = request.args.get("start", "").strip()
    end = request.args.get("end", "").strip()
    strategy = request.args.get("strategy", "distance").strip()
    transport = request.args.get("transport", "walk").strip()
    targets = request.args.getlist("targets")
    route_type = request.args.get("route_type", "single").strip()
    effective_targets = normalize_route_targets(start, end, targets, route_type)

    result = None
    multi_result = None
    if route_type in ("multi", "round_trip") and start and effective_targets:
        final_target = end if route_type == "multi" else None
        multi_result = plan_multi_target_route(
            graph,
            start,
            route_targets_for_planning(effective_targets, final_target),
            strategy=strategy,
            transport=transport,
            return_to_start=route_type == "round_trip",
            final_target=final_target,
        )
    elif start and end:
        result = dijkstra_shortest_path(
            graph,
            start,
            end,
            strategy=strategy,
            transport=transport,
        )

    keyword = request.args.get("keyword", "").strip()
    tag_keyword = request.args.get("tag_keyword", "").strip()
    place_type = request.args.get("type", "").strip()
    city = request.args.get("city", "").strip()
    sort_by = request.args.get("sort_by", "default").strip()
    selected_tags = request.args.getlist("preferred_tags")
    try:
        k = int(request.args.get("k", "10"))
    except ValueError:
        k = 10
    k = max(1, min(k, 20))
    page = parse_positive_int(request.args.get("page", 1))

    all_places = load_places()
    filtered_places = filter_and_sort_places(
        all_places,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
        sort_by=sort_by,
    )
    place_filter_options = get_place_filter_options(all_places)
    recommended_places, recommendation_stats = get_top_k_recommendations(
        all_places,
        preferred_tags=selected_tags,
        k=k,
        place_type=place_type,
        city=city,
        keyword=keyword,
        tag_keyword=tag_keyword,
    )
    visible_places, pagination_state = paginate_items(filtered_places, page, PLACES_PAGE_SIZE)

    facility_start_node = request.args.get("facility_start_node", "").strip() or start
    facility_type = request.args.get("facility_type", "").strip()
    facility_keyword = request.args.get("facility_keyword", "").strip()
    max_distance_raw = request.args.get("max_distance", "").strip()
    try:
        max_distance = float(max_distance_raw) if max_distance_raw else None
    except ValueError:
        max_distance = None

    all_facilities = load_facilities(graph.get("place_id"))
    facility_types = sorted({facility["type"] for facility in all_facilities if facility.get("type")})
    facilities_result = find_nearby_facilities(
        graph,
        facility_start_node,
        facility_type=facility_type,
        keyword=facility_keyword,
        max_distance=max_distance,
    )

    base_query_params = {
        "place_id": place_id,
        "start": start,
        "end": end,
        "targets": effective_targets,
        "strategy": strategy,
        "transport": transport,
        "route_type": route_type,
        "collect": "1" if collect_mode else None,
        "food_pick": "1" if food_pick_mode else None,
        "edit_roads": "1" if edit_roads else None,
        "keyword": keyword,
        "tag_keyword": tag_keyword,
        "type": place_type,
        "city": city,
        "sort_by": sort_by,
        "preferred_tags": selected_tags,
        "k": k,
        "facility_start_node": facility_start_node,
        "facility_type": facility_type,
        "facility_keyword": facility_keyword,
        "max_distance": max_distance_raw,
    }
    place_pagination = build_pagination(
        "route",
        pagination_state["page"],
        pagination_state["total_pages"],
        base_query_params,
    )

    route_state_params = {
        **base_query_params,
        "page": page,
    }
    for facility in facilities_result:
        nearest_node = str(facility.get("nearest_node", "")).strip()
        if not nearest_node:
            continue
        facility["set_start_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "start": nearest_node,
                "facility_start_node": nearest_node,
            },
            anchor="routeSummary",
        )
        facility["set_end_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "end": nearest_node,
                "facility_start_node": nearest_node,
            },
            anchor="routeSummary",
        )
        facility["focus_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "facility_start_node": nearest_node,
            },
            anchor="facilityResults",
        )

    route_foods, route_food_stats = get_route_linked_foods(place_id, graph, start, limit=5)
    route_graph_args = {
        "place_id": place_id,
        "v": get_route_graph_version(place_id),
    }
    if collect_mode or edit_roads:
        route_graph_args["full"] = "1"

    return render_template(
        "route.html",
        username=session["username"],
        place_id=place_id,
        graph_stats={
            "nodes_count": len(graph.get("nodes", [])),
            "edges_count": len(graph.get("edges", [])),
            "selectable_count": len(get_selectable_nodes(graph)),
        },
        route_graph_url=url_for("route_graph_data_api", **route_graph_args),
        nodes=get_selectable_nodes(graph),
        start=start,
        end=end,
        targets=effective_targets,
        strategy=strategy,
        transport=transport,
        route_type=route_type,
        result=result,
        multi_result=multi_result,
        map_result=serialize_route_result(result),
        map_multi_result=serialize_multi_route_result(multi_result),
        amap_js_key=AMAP_JS_KEY,
        amap_security_js_code=AMAP_SECURITY_JS_CODE,
        route_edit_roads=edit_roads,
        route_collect_mode=collect_mode,
        route_food_pick_mode=food_pick_mode,
        route_return_to=return_to,
        route_return_food_key=return_food_key,
        route_return_place_id=return_place_id,
        route_foods=route_foods,
        route_food_stats=route_food_stats,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
        sort_by=sort_by,
        selected_tags=selected_tags,
        k=k,
        page=page,
        places=visible_places,
        recommended_places=recommended_places,
        recommendation_stats=recommendation_stats,
        total_places=len(all_places),
        filtered_places_total=len(filtered_places),
        place_pagination=place_pagination,
        all_available_tags=place_filter_options["tags"],
        cities=place_filter_options["cities"],
        place_types=place_filter_options["place_types"],
        facility_start_node=facility_start_node,
        facility_type=facility_type,
        facility_keyword=facility_keyword,
        max_distance=max_distance_raw,
        facility_types=facility_types,
        facilities=facilities_result,
        facility_total=len(facilities_result),
        facility_source_total=len(all_facilities),
        place_form_state={
            "keyword": keyword,
            "tag_keyword": tag_keyword,
            "type": place_type,
            "city": city,
            "sort_by": sort_by,
            "k": k,
            "page": page,
            "preferred_tags": selected_tags,
            "place_id": place_id,
            "start": start,
            "end": end,
            "targets": effective_targets,
            "strategy": strategy,
            "transport": transport,
            "route_type": route_type,
            "collect": "1" if collect_mode else "",
            "food_pick": "1" if food_pick_mode else "",
            "edit_roads": "1" if edit_roads else "",
            "facility_start_node": facility_start_node,
            "facility_type": facility_type,
            "facility_keyword": facility_keyword,
            "max_distance": max_distance_raw,
        },
        route_form_state={
            "place_id": place_id,
            "start": start,
            "end": end,
            "targets": effective_targets,
            "strategy": strategy,
            "transport": transport,
            "route_type": route_type,
            "collect": "1" if collect_mode else "",
            "food_pick": "1" if food_pick_mode else "",
            "return_to": return_to,
            "return_food_key": return_food_key,
            "return_place_id": return_place_id,
            "edit_roads": "1" if edit_roads else "",
            "keyword": keyword,
            "tag_keyword": tag_keyword,
            "type": place_type,
            "city": city,
            "sort_by": sort_by,
            "k": k,
            "page": page,
            "preferred_tags": selected_tags,
            "facility_start_node": facility_start_node,
            "facility_type": facility_type,
            "facility_keyword": facility_keyword,
            "max_distance": max_distance_raw,
        },
        facility_form_state={
            "place_id": place_id,
            "facility_start_node": facility_start_node,
            "facility_type": facility_type,
            "facility_keyword": facility_keyword,
            "max_distance": max_distance_raw,
            "keyword": keyword,
            "tag_keyword": tag_keyword,
            "type": place_type,
            "city": city,
            "sort_by": sort_by,
            "k": k,
            "page": page,
            "preferred_tags": selected_tags,
            "start": start,
            "end": end,
            "targets": effective_targets,
            "strategy": strategy,
            "transport": transport,
            "route_type": route_type,
            "collect": "1" if collect_mode else "",
            "food_pick": "1" if food_pick_mode else "",
            "return_to": return_to,
            "return_food_key": return_food_key,
            "return_place_id": return_place_id,
            "edit_roads": "1" if edit_roads else "",
        },
        route_food_pick_url=build_url_with_query(
            "route",
            {
                "place_id": place_id,
                "start": start,
                "food_pick": "1",
                "return_to": return_to,
                "return_food_key": return_food_key,
                "return_place_id": return_place_id,
                "strategy": strategy,
                "transport": transport,
                "route_type": route_type,
                "collect": "1" if collect_mode else "",
                "edit_roads": "1" if edit_roads else "",
                "keyword": keyword,
                "tag_keyword": tag_keyword,
                "type": place_type,
                "city": city,
                "sort_by": sort_by,
                "k": k,
                "page": page,
                "preferred_tags": selected_tags,
                "facility_start_node": facility_start_node,
                "facility_type": facility_type,
                "facility_keyword": facility_keyword,
                "max_distance": max_distance_raw,
            },
        ),
    )


@app.route("/facilities")
def facilities():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    params = []
    facility_start_node = request.args.get("start_node", "").strip()
    if facility_start_node:
        params.append(("facility_start_node", facility_start_node))
    facility_type = request.args.get("type", "").strip()
    if facility_type:
        params.append(("facility_type", facility_type))
    facility_keyword = request.args.get("keyword", "").strip()
    if facility_keyword:
        params.append(("facility_keyword", facility_keyword))
    max_distance = request.args.get("max_distance", "").strip()
    if max_distance:
        params.append(("max_distance", max_distance))
    for key in ("place_id", "start", "end", "strategy", "transport", "route_type", "collect", "food_pick", "edit_roads"):
        values = request.args.getlist(key)
        if values:
            params.extend((key, value) for value in values if value not in ("", None))
    for tag in request.args.getlist("preferred_tags"):
        if tag:
            params.append(("preferred_tags", tag))
    return redirect(url_for("route") + ("?" + urlencode(params, doseq=True) if params else ""))


@app.route("/collector")
def collector():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", XMU_MANUAL_PLACE_ID).strip() or XMU_MANUAL_PLACE_ID
    meta = load_collector_meta()
    graph = {
        "place_id": place_id,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "default_start": meta.get("default_start", ""),
        "center": meta.get("center", []),
        "amap_center": meta.get("amap_center", []),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "image_overlay": None,
        "nodes": [],
        "edges": [],
    }
    return render_template(
        "route_collector.html",
        username=session["username"],
        place_id=place_id,
        graph=graph,
        summary=collector_source_summary(),
        amap_js_key=AMAP_JS_KEY,
        amap_security_js_code=AMAP_SECURITY_JS_CODE,
    )


@app.route("/api/route")
def route_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401

    place_id = request.args.get("place_id", DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    graph = load_route_graph(place_id)
    start = request.args.get("start", graph.get("default_start", "")).strip()
    end = request.args.get("end", "").strip()
    strategy = request.args.get("strategy", "distance").strip()
    transport = request.args.get("transport", "walk").strip()
    targets = request.args.getlist("targets")
    route_type = request.args.get("route_type", "single").strip()
    effective_targets = normalize_route_targets(start, end, targets, route_type)

    result = None
    multi_result = None
    if route_type in ("multi", "round_trip") and start and effective_targets:
        final_target = end if route_type == "multi" else None
        multi_result = plan_multi_target_route(
            graph,
            start,
            route_targets_for_planning(effective_targets, final_target),
            strategy=strategy,
            transport=transport,
            return_to_start=route_type == "round_trip",
            final_target=final_target
        )
    elif start and end:
        result = dijkstra_shortest_path(
            graph,
            start,
            end,
            strategy=strategy,
            transport=transport
        )

    return jsonify({
        "graph": serialize_graph_for_map(graph),
        "route_type": route_type,
        "strategy": strategy,
        "transport": transport,
        "start": start,
        "end": end,
        "targets": effective_targets,
        "result": serialize_route_result(result),
        "multi_result": serialize_multi_route_result(multi_result),
    })


@app.route("/api/route/graph-data")
def route_graph_data_api():
    if not is_logged_in():
        return jsonify({"error": "璇峰厛鐧诲綍"}), 401

    place_id = request.args.get("place_id", DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    full_graph = request.args.get("full", "").strip() in ("1", "true", "yes", "on")
    graph = load_route_graph(place_id)
    return jsonify({
        "graph": serialize_graph_for_map(graph, include_road_nodes=full_graph, compact_edges=not full_graph),
        "facilities": facilities_for_map(graph),
    })


def collector_summary(graph):
    selectable = [node for node in graph.get("nodes", []) if is_selectable_node(node)]
    return {
        "nodes": len(graph.get("nodes", [])),
        "edges": len(graph.get("edges", [])),
        "selectable_nodes": len(selectable),
        "facilities": len(load_collector_facilities()),
        "place_id": graph.get("place_id", XMU_MANUAL_PLACE_ID),
    }


def collector_source_summary():
    nodes = load_collector_nodes()
    edges = load_collector_edges()
    links = load_collector_links()
    facilities = load_collector_facilities()
    road_points = sum(len(edge.get("amap_geometry") or []) for edge in edges)
    road_segments = sum(max(0, len(edge.get("amap_geometry") or []) - 1) for edge in edges)
    return {
        "nodes": len(nodes) + road_points,
        "edges": road_segments + len(links),
        "selectable_nodes": len(nodes),
        "manual_nodes": len(nodes),
        "manual_edges": len(edges),
        "road_points": road_points,
        "links": len(links),
        "facilities": len(facilities),
        "place_id": XMU_MANUAL_PLACE_ID,
    }


def collector_meta_graph():
    meta = load_collector_meta()
    return serialize_graph_for_map({
        "place_id": XMU_MANUAL_PLACE_ID,
        "place_name": meta.get("place_name", "厦门大学翔安校区（手动采集图）"),
        "default_start": meta.get("default_start", ""),
        "center": meta.get("center", []),
        "amap_center": meta.get("amap_center", []),
        "bounds": meta.get("campus_bounds", []),
        "campus_bounds": meta.get("campus_bounds", []),
        "amap_bounds": meta.get("amap_bounds", []),
        "image_overlay": None,
        "nodes": [],
        "edges": [],
    })


def collector_payload(include_graph=False):
    graph_payload = serialize_graph_for_map(load_route_graph(XMU_MANUAL_PLACE_ID)) if include_graph else collector_meta_graph()
    return {
        "nodes": load_collector_nodes(),
        "edges": load_collector_edges(),
        "links": load_collector_links(),
        "facilities": load_collector_facilities(),
        "meta": load_collector_meta(),
        "graph": graph_payload,
        "summary": collector_source_summary(),
    }


@app.route("/api/collector/graph")
def collector_graph_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    return jsonify(collector_payload())


@app.route("/api/collector/node", methods=["POST"])
def collector_node_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = request.get_json(force=True) or {}
        nodes = load_collector_nodes()
        if not str(payload.get("id") or "").strip():
            payload = {**payload, "id": next_collector_node_id(payload.get("name") or "node", nodes)}
        node = normalize_collector_node(payload, len(nodes))
        nodes = [item for item in nodes if item.get("id") != node["id"]]
        nodes.append(node)
        write_json_atomic(XMU_COLLECTOR_NODES_FILE, {"nodes": nodes})
        return jsonify({"ok": True, "node": node, "summary": collector_source_summary()})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/collector/facility", methods=["POST"])
def collector_facility_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = request.get_json(force=True) or {}
        facilities = load_collector_facilities()
        if not str(payload.get("id") or "").strip():
            payload = {**payload, "id": next_prefixed_collector_id(facilities, "facility")}
        if not str(payload.get("nearest_node") or "").strip():
            point = normalize_collector_point(payload)
            payload = {**payload, "nearest_node": nearest_collector_road_node_id(point)}
        facility = normalize_collector_facility(payload, len(facilities))
        facilities = [item for item in facilities if item.get("id") != facility["id"]]
        facilities.append(facility)
        write_json_atomic(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": facilities})
        return jsonify({"ok": True, "facility": facility, "summary": collector_source_summary()})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/collector/edge", methods=["POST"])
def collector_edge_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = request.get_json(force=True) or {}
        nodes = load_collector_nodes()
        edges = load_collector_edges()
        if not str(payload.get("id") or "").strip():
            payload = {**payload, "id": next_prefixed_collector_id(edges, "edge")}
        edge = normalize_collector_edge(payload, nodes, len(edges))
        edges = [item for item in edges if item.get("id") != edge["id"]]
        edges.append(edge)
        write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": edges})
        return jsonify({"ok": True, "edge": edge, "summary": collector_source_summary()})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/collector/link", methods=["POST"])
def collector_link_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    try:
        payload = request.get_json(force=True) or {}
        nodes = load_collector_nodes()
        edges = load_collector_edges()
        links = load_collector_links()
        if not str(payload.get("id") or "").strip():
            payload = {**payload, "id": next_prefixed_collector_id(links, "link")}
        link = normalize_collector_link(payload, nodes, edges, len(links))
        duplicate_key = json.dumps({"kind": link["kind"], "a": link["a"], "b": link["b"]}, sort_keys=True)
        reverse_key = json.dumps({"kind": link["kind"], "a": link["b"], "b": link["a"]}, sort_keys=True)
        kept_links = []
        for item in links:
            item_key = json.dumps({"kind": item.get("kind"), "a": item.get("a"), "b": item.get("b")}, sort_keys=True)
            if item_key in (duplicate_key, reverse_key):
                continue
            kept_links.append(item)
        kept_links.append(link)
        write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": kept_links})
        return jsonify({"ok": True, "link": link, "summary": collector_source_summary()})
    except (TypeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/api/collector/node/<node_id>", methods=["DELETE"])
def collector_delete_node_api(node_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    nodes = [node for node in load_collector_nodes() if node.get("id") != node_id]
    edges = [
        edge for edge in load_collector_edges()
        if edge.get("from") != node_id and edge.get("to") != node_id
    ]
    links = [
        link for link in load_collector_links()
        if not (
            (link.get("a") or {}).get("type") == "poi" and (link.get("a") or {}).get("id") == node_id
            or (link.get("b") or {}).get("type") == "poi" and (link.get("b") or {}).get("id") == node_id
        )
    ]
    write_json_atomic(XMU_COLLECTOR_NODES_FILE, {"nodes": nodes})
    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": edges})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    return jsonify({"ok": True, "summary": collector_source_summary()})


@app.route("/api/collector/facility/<facility_id>", methods=["DELETE"])
def collector_delete_facility_api(facility_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    facilities = [facility for facility in load_collector_facilities() if facility.get("id") != facility_id]
    write_json_atomic(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": facilities})
    return jsonify({"ok": True, "summary": collector_source_summary()})


@app.route("/api/collector/edge/<edge_id>", methods=["DELETE"])
def collector_delete_edge_api(edge_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    edges = [edge for edge in load_collector_edges() if edge.get("id") != edge_id]
    links = [
        link for link in load_collector_links()
        if not (
            (link.get("a") or {}).get("type") == "road" and (link.get("a") or {}).get("edge") == edge_id
            or (link.get("b") or {}).get("type") == "road" and (link.get("b") or {}).get("edge") == edge_id
        )
    ]
    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": edges})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    return jsonify({"ok": True, "summary": collector_source_summary()})


@app.route("/api/collector/edge/<edge_id>/point/<int:point_index>", methods=["DELETE"])
def collector_delete_edge_point_api(edge_id, point_index):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    edges = load_collector_edges()
    target = next((edge for edge in edges if edge.get("id") == edge_id), None)
    if not target:
        return jsonify({"error": "道路不存在"}), 404
    geometry = target.get("amap_geometry") or []
    if point_index < 0 or point_index >= len(geometry):
        return jsonify({"error": "道路节点索引无效"}), 400

    existing_ids = {edge.get("id") for edge in edges}
    next_count = len(edges)

    def next_edge_id():
        nonlocal next_count
        while True:
            next_count += 1
            candidate = collector_edge_id(next_count - 1)
            if candidate not in existing_ids:
                existing_ids.add(candidate)
                return candidate

    left_points = geometry[:point_index]
    right_points = geometry[point_index + 1:]
    replacement_specs = []
    if len(left_points) >= 2:
        replacement_specs.append((target.get("id"), left_points, 0))
    if len(right_points) >= 2:
        replacement_id = target.get("id") if not replacement_specs else next_edge_id()
        replacement_specs.append((replacement_id, right_points, point_index + 1))

    replacements = []
    for replacement_id, points, original_start in replacement_specs:
        new_edge = {**target}
        new_edge["id"] = replacement_id
        suffix = "" if replacement_id == target.get("id") else "-拆分"
        new_edge["name"] = f"{target.get('name', '手动道路')}{suffix}"
        new_edge["amap_geometry"] = points
        new_edge["distance"] = round(polyline_distance(points), 1)
        new_edge["poi_links"] = []
        new_edge["road_links"] = []
        new_edge["_original_start"] = original_start
        replacements.append(new_edge)

    def remap_road_ref(ref):
        if (ref or {}).get("type") != "road" or ref.get("edge") != edge_id:
            return ref
        old_index = ref.get("point_index")
        if not isinstance(old_index, int) or old_index == point_index:
            return None
        for replacement in replacements:
            start = replacement["_original_start"]
            end = start + len(replacement["amap_geometry"])
            if start <= old_index < end:
                return {**ref, "edge": replacement["id"], "point_index": old_index - start}
        return None

    links = []
    for link in load_collector_links():
        a_ref = remap_road_ref(link.get("a"))
        b_ref = remap_road_ref(link.get("b"))
        if not a_ref or not b_ref:
            continue
        links.append({**link, "a": a_ref, "b": b_ref})

    for replacement in replacements:
        replacement.pop("_original_start", None)

    new_edges = []
    for edge in edges:
        if edge.get("id") == edge_id:
            new_edges.extend(replacements)
        else:
            new_edges.append(edge)

    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": new_edges})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    result = collector_payload()
    result.update({"ok": True, "summary": collector_source_summary()})
    return jsonify(result)


@app.route("/api/collector/link/<link_id>", methods=["DELETE"])
def collector_delete_link_api(link_id):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    links = [link for link in load_collector_links() if link.get("id") != link_id]
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    return jsonify({"ok": True, "summary": collector_source_summary()})


@app.route("/api/collector/batch-delete", methods=["POST"])
def collector_batch_delete_api():
    if not is_logged_in():
        return jsonify({"error": "Please login first"}), 401
    payload = request.get_json(force=True) or {}
    node_ids = {str(item) for item in payload.get("node_ids", []) if str(item).strip()}
    facility_ids = {str(item) for item in payload.get("facility_ids", []) if str(item).strip()}
    road_delete_map = {}
    for ref in payload.get("road_points", []):
        edge_id = str((ref or {}).get("edge") or "").strip()
        try:
            point_index = int((ref or {}).get("point_index", (ref or {}).get("target_index", -1)))
        except (TypeError, ValueError):
            continue
        if edge_id and point_index >= 0:
            road_delete_map.setdefault(edge_id, set()).add(point_index)

    if not node_ids and not facility_ids and not road_delete_map:
        return jsonify({"error": "No selected collector items"}), 400

    nodes = [node for node in load_collector_nodes() if str(node.get("id")) not in node_ids]
    facilities = [
        facility for facility in load_collector_facilities()
        if str(facility.get("id")) not in facility_ids
    ]
    original_edges = load_collector_edges()
    existing_ids = {str(edge.get("id")) for edge in original_edges}
    next_count = len(existing_ids)

    def next_edge_id():
        nonlocal next_count
        while True:
            next_count += 1
            candidate = collector_edge_id(next_count - 1)
            if candidate not in existing_ids:
                existing_ids.add(candidate)
                return candidate

    edge_index_map = {}
    new_edges = []
    removed_road_points = 0

    for edge in original_edges:
        edge_id = str(edge.get("id") or "")
        points = edge.get("amap_geometry") or []
        delete_indices = {
            index for index in road_delete_map.get(edge_id, set())
            if 0 <= index < len(points)
        }
        if not delete_indices:
            new_edges.append(edge)
            for index in range(len(points)):
                edge_index_map[(edge_id, index)] = {"edge": edge_id, "point_index": index}
            continue

        removed_road_points += len(delete_indices)
        runs = []
        run = []
        for index, point in enumerate(points):
            if index in delete_indices:
                if len(run) >= 2:
                    runs.append(run)
                run = []
                continue
            run.append((index, point))
        if len(run) >= 2:
            runs.append(run)

        for run_index, run_items in enumerate(runs):
            replacement_id = edge_id if run_index == 0 else next_edge_id()
            replacement_points = [item[1] for item in run_items]
            old_to_new = {old_index: new_index for new_index, (old_index, _point) in enumerate(run_items)}
            for old_index, new_index in old_to_new.items():
                edge_index_map[(edge_id, old_index)] = {
                    "edge": replacement_id,
                    "point_index": new_index,
                }

            replacement = {**edge}
            replacement["id"] = replacement_id
            replacement["amap_geometry"] = replacement_points
            replacement["distance"] = round(polyline_distance(replacement_points), 1)
            replacement["from"] = "" if replacement.get("from") in node_ids else replacement.get("from", "")
            replacement["to"] = "" if replacement.get("to") in node_ids else replacement.get("to", "")
            replacement["poi_links"] = [
                {"index": old_to_new[link.get("index")], "poi": link.get("poi")}
                for link in edge.get("poi_links", [])
                if link.get("poi") not in node_ids and link.get("index") in old_to_new
            ]
            replacement["road_links"] = [
                {
                    "index": old_to_new[link.get("index")],
                    "edge": link.get("edge"),
                    "target_index": link.get("target_index"),
                }
                for link in edge.get("road_links", [])
                if link.get("index") in old_to_new
            ]
            if run_index > 0:
                replacement["name"] = f"{edge.get('name', 'manual road')}-{run_index + 1}"
            new_edges.append(replacement)

    def remap_link_ref(ref):
        ref = ref or {}
        ref_type = ref.get("type")
        if ref_type == "poi":
            return None if str(ref.get("id")) in node_ids else ref
        if ref_type == "facility":
            return None if str(ref.get("id")) in facility_ids else ref
        if ref_type == "road":
            try:
                point_index = int(ref.get("point_index", -1))
            except (TypeError, ValueError):
                return None
            mapped = edge_index_map.get((str(ref.get("edge") or ""), point_index))
            return {**ref, **mapped} if mapped else None
        return ref

    links = []
    for link in load_collector_links():
        a_ref = remap_link_ref(link.get("a"))
        b_ref = remap_link_ref(link.get("b"))
        if not a_ref or not b_ref:
            continue
        links.append({**link, "a": a_ref, "b": b_ref})

    write_json_atomic(XMU_COLLECTOR_NODES_FILE, {"nodes": nodes})
    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": new_edges})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    write_json_atomic(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": facilities})
    result = collector_payload()
    result.update({
        "ok": True,
        "deleted": {
            "nodes": len(node_ids),
            "facilities": len(facility_ids),
            "road_points": removed_road_points,
        },
        "summary": collector_source_summary(),
    })
    return jsonify(result)


@app.route("/api/collector/rebuild", methods=["POST"])
def collector_rebuild_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    graph = rebuild_manual_graph()
    return jsonify({"ok": True, "summary": collector_summary(graph), "graph": serialize_graph_for_map(load_route_graph(XMU_MANUAL_PLACE_ID))})


@app.route("/api/collector/restore", methods=["POST"])
def collector_restore_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    payload = request.get_json(force=True) or {}
    nodes = payload.get("nodes", [])
    edges = payload.get("edges", [])
    links = payload.get("links", [])
    facilities = payload.get("facilities", [])
    meta = payload.get("meta")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(links, list) or not isinstance(facilities, list):
        return jsonify({"error": "采集快照格式无效"}), 400
    write_json_atomic(XMU_COLLECTOR_NODES_FILE, {"nodes": nodes})
    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": edges})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": links})
    write_json_atomic(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": facilities})
    if isinstance(meta, dict):
        current_meta = load_collector_meta()
        current_meta.update(meta)
        write_json_atomic(XMU_COLLECTOR_META_FILE, current_meta)
    return jsonify({"ok": True, "summary": collector_source_summary(), "graph": collector_meta_graph()})


@app.route("/api/collector/clear", methods=["POST"])
def collector_clear_api():
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401
    write_json_atomic(XMU_COLLECTOR_NODES_FILE, {"nodes": []})
    write_json_atomic(XMU_COLLECTOR_EDGES_FILE, {"edges": []})
    write_json_atomic(XMU_COLLECTOR_LINKS_FILE, {"links": []})
    write_json_atomic(XMU_COLLECTOR_FACILITIES_FILE, {"facilities": []})
    graph = empty_manual_graph()
    return jsonify({"ok": True, "summary": collector_summary(graph), "graph": serialize_graph_for_map(graph)})


@app.route("/diaries", methods=["GET", "POST"])
def diaries():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    all_places = load_places()
    place_name_options = get_place_name_options(all_places)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        destination = request.form.get("destination", "").strip()
        content = request.form.get("content", "").strip()
        compression_algorithm = request.form.get("compression_algorithm", "huffman").strip().lower()
        uploaded_files = request.files.getlist("attachments")
        if not title or not destination or not content:
            flash("标题、目的地和正文不能为空")
        else:
            diary_id = create_diary(
                title,
                destination,
                content,
                session["username"],
                compression_algorithm=compression_algorithm
            )
            media_items = save_diary_media_files(diary_id, uploaded_files)
            if media_items:
                update_diary_media(diary_id, media_items)
            flash("日记发布成功")
            return redirect(url_for("diaries"))

    diaries_list = load_diaries(sort_by="hot_rating_desc")
    current_user = get_logged_in_user()
    return render_template(
        "diaries.html",
        username=session["username"],
        current_user=current_user,
        current_user_avatar_url=get_user_avatar_url(current_user) if current_user else "",
        diaries=diaries_list,
        diaries_total=len(diaries_list),
        place_name_options=place_name_options,
        publish_default_destination="",
    )


@app.route("/diaries/search")
def diary_search():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    query = request.args.get("q", "").strip()
    all_places = load_places()
    place_name_options = get_place_name_options(all_places)
    if query:
        diaries_list = get_diary_search_results(query)
    else:
        diaries_list = load_diaries(sort_by="hot_rating_desc")[:16]
    current_user = get_logged_in_user()
    return render_template(
        "diary_search.html",
        username=session["username"],
        current_user=current_user,
        current_user_avatar_url=get_user_avatar_url(current_user) if current_user else "",
        diaries=diaries_list,
        query=query,
        recommendations=load_diaries(sort_by="hot_rating_desc")[:12],
        place_name_options=place_name_options,
    )


@app.route("/diary/<int:diary_id>", methods=["GET", "POST"])
def diary_detail(diary_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    if request.method == "POST":
        action = request.form.get("action", "rating").strip().lower()
        if action == "comment":
            content = request.form.get("content", "").strip()
            parent_id = parse_positive_int(request.form.get("parent_id", 0))
            if not content:
                flash("评论内容不能为空")
                return redirect(url_for("diary_detail", diary_id=diary_id))
            comment_id = create_diary_comment(diary_id, session["username"], content, parent_id=parent_id)
            flash("评论已发布")
            if comment_id:
                return redirect(url_for("diary_detail", diary_id=diary_id, comment_posted=1, _anchor=f"comment-{comment_id}"))
            return redirect(url_for("diary_detail", diary_id=diary_id))

        rating = request.form.get("rating", "5")
        rate_diary(diary_id, rating)
        flash("评分成功")
        return redirect(url_for("diary_detail", diary_id=diary_id))

    increase_views = request.method == "GET" and request.args.get("count_view", "1") != "0"
    diary = get_diary_by_id(diary_id, increase_views=increase_views)
    if diary is None:
        flash("未找到该旅游日记")
        return redirect(url_for("diaries"))

    all_places = load_places()
    matched_place = find_place_match(diary.get("destination", ""), all_places)
    related_places = get_related_places_for_diary(diary, all_places, limit=4)
    if matched_place:
        related_places = [place for place in related_places if place["id"] != matched_place["id"]]

    compression_algorithm = request.args.get(
        "compress_algorithm",
        diary.get("compression", {}).get("algorithm", "huffman")
    ).strip().lower()
    compression_preview = get_diary_compression_preview(diary_id, compression_algorithm)
    current_user = get_logged_in_user()
    diary_author = get_user_by_username(diary.get("author", ""))
    comment_payload = load_diary_comments(diary_id, current_user["username"] if current_user else None)
    visible_threads = comment_payload["threads"][:DIARY_VISIBLE_COMMENT_THREADS]
    hidden_threads = comment_payload["threads"][DIARY_VISIBLE_COMMENT_THREADS:]
    for comment_group in (visible_threads, hidden_threads):
        for thread in comment_group:
            thread["flat_replies"] = flatten_diary_comment_replies(thread.get("replies", []))

    return render_template(
        "diary_detail.html",
        username=session["username"],
        current_user=current_user,
        current_user_avatar_url=get_user_avatar_url(current_user) if current_user else "",
        diary=diary,
        diary_author=diary_author,
        diary_author_avatar_url=get_user_avatar_url(diary.get("author", "")),
        diary_favorited=is_item_favorited(current_user["id"], "diary", diary_id) if current_user else False,
        place_name_options=get_place_name_options(all_places),
        matched_place=matched_place,
        related_places=related_places,
        compression_preview=compression_preview,
        compression_algorithm=compression_algorithm,
        comments=visible_threads,
        hidden_comments=hidden_threads,
        comment_total=comment_payload["total_count"],
        visible_comment_threads=DIARY_VISIBLE_COMMENT_THREADS,
        visible_comment_replies=DIARY_VISIBLE_REPLIES,
        comment_posted=request.args.get("comment_posted", "").strip() == "1",
    )


@app.route("/diary/<int:diary_id>/favorite", methods=["POST"])
def diary_favorite(diary_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    current_user = get_logged_in_user()
    diary = get_diary_by_id(diary_id, increase_views=False)
    if current_user is None or diary is None:
        flash("未找到该旅游日记")
        return redirect(url_for("diaries"))
    favorited = toggle_user_favorite(
        current_user["id"],
        "diary",
        diary_id,
        title=diary["title"],
        subtitle=f"{diary['destination']} · {diary['author']}",
        meta={"destination": diary["destination"], "author": diary["author"]},
    )
    flash("已收藏这篇日记" if favorited else "已取消收藏")
    return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0))


@app.route("/diary/<int:diary_id>/comments/<int:comment_id>/like", methods=["POST"])
def diary_comment_like(diary_id, comment_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM diary_comments WHERE id = ? AND diary_id = ?", (comment_id, diary_id))
    comment = cursor.fetchone()
    conn.close()
    if comment is None:
        flash("评论不存在")
        return redirect(url_for("diary_detail", diary_id=diary_id))
    toggle_diary_comment_like(comment_id, session["username"])
    return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0, _anchor=f"comment-{comment_id}"))


@app.route("/diary-media/<int:diary_id>/<path:filename>")
def diary_media_file(diary_id, filename):
    media_folder = diary_media_folder(diary_id)
    file_path = os.path.join(media_folder, filename)
    if not os.path.exists(file_path):
        abort(404)
    return send_from_directory(media_folder, filename)


@app.route("/foods")
def foods():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = FOOD_DEFAULT_PLACE_ID
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()
    place_name = ""
    sort_by = request.args.get("sort_by", "default").strip()
    requested_origin_node = request.args.get("origin_node", "").strip()

    food_context = FOOD_CAMPUS_CONTEXTS[place_id]
    campus_foods = build_food_candidates_for_place(place_id)
    graph = load_route_graph(food_context.get("graph_place_id", place_id))
    origin_node = requested_origin_node if requested_origin_node in graph.get("node_map", {}) else ""
    if not sort_by or sort_by == "default":
        sort_by = food_context.get("default_sort", "recommend_score_desc")
    if not origin_node and sort_by == "distance_asc":
        sort_by = "recommend_score_desc"
    filtered_foods, food_stats = rank_food_candidates(
        campus_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by,
        limit=None,
        graph=graph,
        origin_node=origin_node,
    )
    food_page = parse_positive_int(request.args.get("page", 1))
    paged_foods, page_info = paginate_items(filtered_foods, page=food_page, per_page=FOOD_TOP_K)
    food_pagination = build_pagination(
        "foods",
        page_info["page"],
        page_info["total_pages"],
        {
            "place_id": place_id,
            "keyword": keyword,
            "category": category,
            "sort_by": sort_by,
            "origin_node": origin_node,
        },
    )
    food_pagination["per_page"] = FOOD_TOP_K
    food_pagination["total"] = len(filtered_foods)
    food_stats = dict(food_stats or {})
    food_stats["returned_count"] = len(paged_foods)
    food_stats["filtered_count"] = len(filtered_foods)
    food_stats["page"] = page_info["page"]
    food_stats["page_size"] = FOOD_TOP_K
    present_categories = {food["category"] for food in campus_foods if food.get("category")}
    categories = [option for option in FOOD_CUISINE_OPTIONS if option in present_categories]
    categories.extend(sorted(present_categories - set(categories)))

    return render_template(
        "foods.html",
        username=session["username"],
        foods=paged_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by,
        categories=categories,
        place_id=place_id,
        origin_node=origin_node,
        food_pagination=food_pagination,
        food_context={
            **food_context,
            "top_k": FOOD_TOP_K,
            "show_all": False,
            "origin_node": origin_node,
            "origin_node_name": graph.get("node_map", {}).get(origin_node, {}).get("name", ""),
        },
        food_stats=food_stats,
        food_mode="campus",
    )


@app.route("/food/<food_key>")
def food_detail(food_key):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = FOOD_DEFAULT_PLACE_ID
    requested_origin_node = request.args.get("origin_node", "").strip()
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()
    sort_by = request.args.get("sort_by", "").strip()
    page = parse_positive_int(request.args.get("page", 1))
    food_context = FOOD_CAMPUS_CONTEXTS[place_id]
    graph = load_route_graph(food_context.get("graph_place_id", place_id))
    origin_node = requested_origin_node if requested_origin_node in graph.get("node_map", {}) else ""
    food = get_food_by_key(food_key, place_id=place_id, origin_node=origin_node)
    if food is None:
        flash("未找到该美食信息")
        return redirect(url_for("foods", place_id=place_id) if place_id else url_for("foods"))
    current_user = get_logged_in_user()

    return render_template(
        "food_detail.html",
        username=session["username"],
        current_user=current_user,
        food=food,
        food_favorited=is_item_favorited(current_user["id"], "food", food_key) if current_user else False,
        place_id=place_id,
        origin_node=origin_node,
        keyword=keyword,
        category=category,
        sort_by=sort_by,
        page=page,
        return_to="food_detail",
        return_food_key=food_key,
        return_place_id=place_id,
        route_food_pick_url=build_url_with_query(
            "route",
            {
                "place_id": place_id,
                "food_pick": "1",
                "return_to": "food_detail",
                "return_food_key": food_key,
                "return_place_id": place_id,
            },
        ),
        food_context={
            **food_context,
            "origin_node": origin_node,
            "origin_node_name": graph.get("node_map", {}).get(origin_node, {}).get("name", ""),
        },
    )


@app.route("/food/<food_key>/favorite", methods=["POST"])
def food_favorite(food_key):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    current_user = get_logged_in_user()
    place_id = request.form.get("place_id", request.args.get("place_id", FOOD_DEFAULT_PLACE_ID)).strip() or FOOD_DEFAULT_PLACE_ID
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = FOOD_DEFAULT_PLACE_ID
    origin_node = request.form.get("origin_node", request.args.get("origin_node", "")).strip()
    keyword = request.form.get("keyword", request.args.get("keyword", "")).strip()
    category = request.form.get("category", request.args.get("category", "")).strip()
    sort_by = request.form.get("sort_by", request.args.get("sort_by", "")).strip()
    page = parse_positive_int(request.form.get("page", request.args.get("page", 1)))
    food = get_food_by_key(food_key, place_id=place_id, origin_node=origin_node)
    if current_user is None or food is None:
        flash("未找到该美食信息")
        return redirect(url_for("foods", place_id=place_id))
    favorited = toggle_user_favorite(
        current_user["id"],
        "food",
        food_key,
        title=food["name"],
        subtitle=f"{food.get('cuisine') or food.get('category', '')} · 评分 {food.get('rating', 0)}",
        meta={
            "place_id": place_id,
            "origin_node": origin_node,
            "keyword": keyword,
            "category": category,
            "sort_by": sort_by,
            "page": page,
            "cuisine": food.get("cuisine") or food.get("category", ""),
            "rating": food.get("rating", 0),
            "avg_cost": food.get("avg_cost", 0),
            "cover_image": food.get("cover_image", ""),
        },
    )
    flash("已收藏这家美食" if favorited else "已取消收藏")
    return redirect(url_for(
        "food_detail",
        food_key=food_key,
        place_id=place_id,
        origin_node=origin_node,
        keyword=keyword,
        category=category,
        sort_by=sort_by,
        page=page,
    ))


def save_food_data_url(data_url, food_key, image_kind, index=None):
    if not data_url:
        return ""
    if Image is None:
        raise ValueError("当前环境缺少 Pillow，无法处理图片")
    data_url = str(data_url)
    if "," in data_url:
        header, encoded = data_url.split(",", 1)
        if "image/" not in header:
            raise ValueError("请粘贴图片格式的数据")
    else:
        encoded = data_url
    try:
        raw = base64.b64decode(encoded, validate=True)
        image = Image.open(BytesIO(raw)).convert("RGB")
    except Exception as exc:
        raise ValueError("图片解析失败，请重新粘贴图片") from exc
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(food_key or "food")).strip("._") or "food"
    kind = str(image_kind or "").strip().lower()
    if kind == "cover":
        suffix = "cover"
    elif kind == "detail":
        suffix = "detail"
    else:
        suffix = f"dish-{int(index or 0) + 1}"
    filename = f"{safe_key}-{suffix}.jpg"
    os.makedirs(XMU_FOOD_CUSTOM_MEDIA_DIR, exist_ok=True)
    abs_path = os.path.join(XMU_FOOD_CUSTOM_MEDIA_DIR, filename)
    image.save(abs_path, "JPEG", quality=88, optimize=True, progressive=True)
    return "/".join(["food_media", "custom", filename])


def save_food_uploaded_file(upload, food_key, image_kind, index=None):
    if not upload:
        return ""
    if Image is None:
        raise ValueError("当前环境缺少 Pillow，无法处理图片")
    filename = str(getattr(upload, "filename", "") or "").strip()
    try:
        upload.stream.seek(0)
    except Exception:
        pass
    try:
        image = Image.open(upload.stream).convert("RGB")
    except Exception as exc:
        raise ValueError("上传图片解析失败，请重新选择文件") from exc
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(food_key or "food")).strip("._") or "food"
    kind = str(image_kind or "").strip().lower()
    if kind == "cover":
        suffix = "cover"
    elif kind == "detail":
        suffix = "detail"
    else:
        suffix = f"dish-{int(index or 0) + 1}"
    filename = f"{safe_key}-{suffix}.jpg"
    os.makedirs(XMU_FOOD_CUSTOM_MEDIA_DIR, exist_ok=True)
    abs_path = os.path.join(XMU_FOOD_CUSTOM_MEDIA_DIR, filename)
    image.save(abs_path, "JPEG", quality=88, optimize=True, progressive=True)
    return "/".join(["food_media", "custom", filename])


def normalize_food_media_record(food, existing_record=None):
    existing_record = existing_record if isinstance(existing_record, dict) else {}
    dishes = []
    source_dishes = existing_record.get("signature_dishes") if isinstance(existing_record.get("signature_dishes"), list) else []
    food_dishes = food.get("signature_dishes") or []
    for index in range(3):
        source = source_dishes[index] if index < len(source_dishes) and isinstance(source_dishes[index], dict) else {}
        fallback = food_dishes[index] if index < len(food_dishes) and isinstance(food_dishes[index], dict) else {}
        dishes.append({
            "name": str(source.get("name") or fallback.get("name") or "").strip(),
            "price": str(source.get("price") or fallback.get("price") or "").strip(),
            "image": str(source.get("image") or fallback.get("image") or "food_media/dishes/food-dish-placeholder.jpg").strip(),
        })
    return {
        "name": str(existing_record.get("name") or food.get("name") or "").strip(),
        "cuisine": str(existing_record.get("cuisine") or food.get("cuisine") or food.get("category") or "").strip(),
        "cover_image": str(existing_record.get("cover_image") or food.get("cover_image") or "food_media/shops/food-cover-placeholder.jpg").strip(),
        "detail_image": str(
            existing_record.get("detail_image")
            or food.get("detail_image")
            or existing_record.get("cover_image")
            or food.get("cover_image")
            or "food_media/shops/food-cover-placeholder.jpg"
        ).strip(),
        "recommend_score_override": existing_record.get("recommend_score_override"),
        "rating": food.get("rating"),
        "popularity": food.get("popularity"),
        "avg_cost": food.get("avg_cost"),
        "display_description": str(existing_record.get("display_description") or food.get("display_description") or "").strip(),
        "recommendation_note": str(existing_record.get("recommendation_note") or food.get("recommendation_note") or default_food_recommendation_note()).strip(),
        "signature_dishes": dishes,
    }


@app.route("/api/food-media/<food_key>/update", methods=["POST"])
def update_food_media(food_key):
    if not is_logged_in():
        return jsonify({"error": "请先登录"}), 401

    if request.is_json:
        payload = request.get_json(force=True, silent=True) or {}
        files = {}
    else:
        payload = request.form.to_dict(flat=True)
        files = request.files
    place_id = str(payload.get("place_id") or FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = FOOD_DEFAULT_PLACE_ID
    food = get_food_by_key(food_key, place_id=place_id)
    if food is None:
        return jsonify({"error": "未找到该美食"}), 404

    media_payload = load_food_media_payload()
    records = media_payload.setdefault("foods", {})
    record = normalize_food_media_record(food, records.get(food_key, {}))

    try:
        cover_file = files.get("cover_file")
        if cover_file and getattr(cover_file, "filename", ""):
            record["cover_image"] = save_food_uploaded_file(cover_file, food_key, "cover")
        elif payload.get("cover_image"):
            record["cover_image"] = save_food_data_url(payload.get("cover_image"), food_key, "cover")

        detail_file = files.get("detail_file")
        if detail_file and getattr(detail_file, "filename", ""):
            record["detail_image"] = save_food_uploaded_file(detail_file, food_key, "detail")
        elif payload.get("detail_image"):
            record["detail_image"] = save_food_data_url(payload.get("detail_image"), food_key, "detail")

        if "rating" in payload:
            record["rating"] = round(coerce_food_number(payload.get("rating"), food.get("rating", 4.0), float, 0, 5), 1)
        if "popularity" in payload:
            record["popularity"] = int(coerce_food_number(payload.get("popularity"), food.get("popularity", 60), int, 0, 9999))
        if "avg_cost" in payload:
            record["avg_cost"] = round(coerce_food_number(payload.get("avg_cost"), food.get("avg_cost", 22), float, 0, 9999), 1)
        if "display_description" in payload:
            record["display_description"] = str(payload.get("display_description") or "").strip()
        if "recommendation_note" in payload:
            record["recommendation_note"] = str(payload.get("recommendation_note") or "").strip() or default_food_recommendation_note()
        if "recommend_score_override" in payload:
            record["recommend_score_override"] = optional_food_float(payload.get("recommend_score_override"))

        incoming_dishes = payload.get("dishes")
        if isinstance(incoming_dishes, str):
            try:
                incoming_dishes = json.loads(incoming_dishes)
            except json.JSONDecodeError:
                incoming_dishes = []
        if not isinstance(incoming_dishes, list):
            incoming_dishes = []
        if not incoming_dishes:
            for index in range(3):
                name_key = f"dish_name_{index}"
                price_key = f"dish_price_{index}"
                if name_key in payload or price_key in payload:
                    incoming_dishes.append({
                        "name": payload.get(name_key, ""),
                        "price": payload.get(price_key, ""),
                    })
        if isinstance(incoming_dishes, list):
            for index, dish_payload in enumerate(incoming_dishes[:3]):
                if not isinstance(dish_payload, dict):
                    continue
                dish = record["signature_dishes"][index]
                if "name" in dish_payload:
                    dish["name"] = str(dish_payload.get("name") or "").strip()
                if "price" in dish_payload:
                    dish["price"] = str(dish_payload.get("price") or "").strip()
                if dish_payload.get("image"):
                    dish["image"] = save_food_data_url(dish_payload.get("image"), food_key, "dish", index=index)

        dish_index = payload.get("dish_index")
        dish_file = files.get("dish_file")
        if dish_index is not None and dish_file and getattr(dish_file, "filename", ""):
            index = int(dish_index)
            if index < 0 or index > 2:
                raise ValueError("招牌菜序号不合法")
            record["signature_dishes"][index]["image"] = save_food_uploaded_file(dish_file, food_key, "dish", index=index)
        elif dish_index is not None and payload.get("dish_image"):
            index = int(dish_index)
            if index < 0 or index > 2:
                raise ValueError("招牌菜序号不合法")
            record["signature_dishes"][index]["image"] = save_food_data_url(payload.get("dish_image"), food_key, "dish", index=index)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    records[food_key] = record
    media_payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_food_media_payload(media_payload)
    return jsonify({"ok": True, "food_key": food_key, "record": record})


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug, use_reloader=debug)

