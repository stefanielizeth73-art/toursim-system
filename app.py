from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, has_request_context
from werkzeug.utils import secure_filename
from collections import defaultdict
import base64
import io
import copy
import sqlite3
import csv
import json
import math
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlencode, quote
from markupsafe import Markup
from toursim import avatars as avatar_helpers
from toursim.ai_assistant import (
    AIAssistantServices,
    ai_action,
    ai_assistant_config,
    ai_build_model_prompt,
    ai_build_url,
    ai_context_memory_bundle,
    ai_deepseek_answer,
    ai_detect_system_module,
    ai_env_flag,
    ai_executable_route_answer,
    ai_fallback_route_decision,
    ai_find_route_node_mentions,
    ai_food_card,
    ai_food_intent_from_text,
    ai_generic_local_answer,
    ai_human_food_summary,
    ai_is_context_followup,
    ai_json_from_text,
    ai_last_action_command,
    ai_last_system_modules,
    ai_latest_conversation_id,
    ai_llm_chat_text,
    ai_local_assistant_payload,
    ai_model_route_decision,
    ai_normalize_limit,
    ai_openai_answer,
    ai_parse_budget,
    ai_place_card,
    ai_provider_answer,
    ai_recent_chat_messages,
    ai_recent_history_text,
    ai_resolve_node_id,
    ai_route_arguments_from_history,
    ai_route_arguments_from_text,
    ai_route_card,
    ai_route_node_name_from_id,
    ai_run_rag_tools,
    ai_safe_text,
    ai_store_chat_message,
    ai_tool_plan_indoor,
    ai_tool_plan_route,
    ai_tool_recommend_foods,
    ai_tool_recommend_places,
    ai_tool_search_diaries,
    ai_url_for,
    configure_ai_assistant,
)
from toursim.compression import (
    build_huffman_codes,
    compress_diary_text,
    huffman_compress_text,
    huffman_decompress_text,
    lzw_compress_text,
    lzw_decompress_text,
    pack_varints,
    parse_diary_package,
    unpack_varints,
)
from toursim.filesystem import (
    ensure_parent_dir,
    file_signature,
    files_signature,
    read_json_file,
    write_json_atomic,
)
from toursim.favorites import (
    FavoriteServices,
    configure_favorites,
    favorite_key,
    get_user_activity_stats,
    is_item_favorited,
    load_favorite_diaries,
    load_favorite_foods,
    load_favorite_places,
    load_user_diaries,
    load_user_favorites,
    toggle_user_favorite,
)
from toursim.user_accounts import (
    UserAccountServices,
    configure_user_accounts,
    create_user,
    diary_comment_avatar_url,
    get_user_avatar_url,
    get_user_by_id,
    get_user_by_username,
    update_user_account,
    update_user_avatar_path,
)
from toursim.diary_search import (
    build_diary_search_index,
    filter_diaries_by_destination,
    search_diaries_by_keyword,
    search_diaries_by_title,
    sort_diaries,
)
from toursim.diary_media import (
    DiaryMediaConfig,
    DiaryMediaServices,
    configure_diary_media,
    diary_generated_video_folder,
    diary_generated_video_public_url,
    diary_media_folder,
    diary_media_kind,
    diary_media_public_url,
    diary_media_thumbnail_folder,
    diary_media_thumbnail_public_url,
    diary_thumbnail_filename,
    ensure_diary_image_thumbnail,
    generate_image_blur_base64,
    is_allowed_diary_media,
    prewarm_all_diary_thumbnails,
    probe_image_size,
    resolve_diary_generated_video_path,
    resolve_diary_media_path,
)
from toursim.diary_video import (
    DiaryVideoConfig,
    DiaryVideoServices,
    build_bailian_video_payload,
    build_diary_video_prompt,
    configure_diary_video,
    dashscope_base_url,
    dashscope_json_request,
    diary_image_data_url,
    download_diary_generated_video,
    get_dashscope_api_key,
    normalize_diary_video_duration,
    normalize_diary_video_resolution,
    normalize_diary_video_status,
    poll_bailian_video_task,
    select_diary_video_image,
    serialize_diary_video_task,
    submit_bailian_image_to_video_task,
)
from toursim.diary_repository import (
    DiaryRepositoryServices,
    attach_diary_stats,
    configure_diary_repository,
    create_diary,
    create_diary_comment,
    diary_compression_summary,
    get_diary_by_id,
    get_diary_compression_preview,
    get_diary_search_results,
    get_diary_user_rating,
    load_diaries,
    load_diary_comments,
    rate_diary,
    rate_diary_once,
    stored_diary_media_items,
    toggle_diary_comment_like,
    update_diary_compression_algorithm,
    update_diary_media,
)
from toursim.geo import haversine_amap, polyline_distance
from toursim.food_repository import (
    FoodRepositoryConfig,
    FoodRepositoryServices,
    apply_food_media,
    build_food_candidates_for_place,
    configure_food_repository,
    get_food_by_key,
    get_food_origin_node,
    get_route_linked_foods,
    load_csv_rows,
    load_food_media_payload,
    load_food_media_records,
    make_food_candidate,
    save_food_media_payload,
)
from toursim.route_repository import (
    RouteRepositoryConfig,
    RouteRepositoryServices,
    configure_route_repository,
    enforce_walk_only_snap_link,
    get_route_graph_path,
    get_route_graph_version,
    load_route_graph,
    road_display_edges_for_map,
    serialize_graph_for_map,
)
from toursim.food_catalog import (
    FOOD_CUISINE_OPTIONS,
    build_food_key,
    calculate_food_recommend_score,
    coerce_food_number,
    default_food_recommendation_note,
    default_signature_dishes,
    enrich_food_distance,
    food_default_profile,
    food_dedupe_key,
    food_display_description,
    food_media_lookup_keys,
    food_recommendation_breakdown,
    food_search_blob,
    is_food_related_facility,
    normalize_food_category,
    optional_food_float,
    public_food_recommendation_note,
    rank_food_candidates,
    visible_food_tags,
)
from toursim.indoor import (
    INDOOR_BUILDING_TYPES,
    INDOOR_DEFAULT_END,
    INDOOR_DEFAULT_START,
    INDOOR_FLOOR_ASSETS,
    INDOOR_FLOOR_HEIGHT,
    INDOOR_FLOOR_WIDTH,
    INDOOR_VERTICAL_CORES,
    INDOOR_VERTICAL_MODES,
    build_indoor_graph_from_collector,
    default_indoor_collector_payload,
    indoor_collector_ref_point,
    indoor_default_endpoints,
    indoor_edge_weight,
    indoor_node_options,
    indoor_point_distance,
    indoor_polyline_distance,
    indoor_route_steps,
    indoor_shortest_path,
    is_indoor_building_node,
    next_indoor_collector_id,
    normalize_indoor_collector_edge,
    normalize_indoor_collector_link,
    normalize_indoor_collector_node,
    normalize_indoor_collector_ref,
    prepare_indoor_floors,
)
from toursim.places import (
    calculate_base_score,
    calculate_personalized_score,
    filter_and_sort_places,
    filter_place_candidates,
    find_place_match,
    get_place_filter_options,
    get_place_name_options,
    get_related_diaries_for_place,
    get_related_places_for_diary,
    get_top_k_recommendations,
    parse_place_tag_query,
    place_matches_filters,
    place_search_blob,
)
from toursim.place_repository import (
    PlaceRepositoryConfig,
    PlaceRepositoryServices,
    configure_place_repository,
    get_place_by_id,
    load_place_image_map,
    load_places,
    place_media_relative_path,
    save_place_image_record,
    save_uploaded_place_cover,
)
from toursim.route_algorithms import (
    MAX_ROUTE_TARGETS,
    SHORTEST_TREE_CACHE,
    calculate_edge_weight,
    dijkstra_shortest_path,
    dijkstra_shortest_tree,
    flatten_edge_points,
    get_display_path_names,
    get_selectable_nodes,
    is_road_graph_node,
    is_selectable_node,
    nearest_graph_node_id,
    normalize_route_targets,
    plan_multi_target_route,
    route_from_shortest_tree,
    route_targets_for_planning,
    serialize_multi_route_result,
    serialize_route_result,
)
from toursim.search import normalize_search_text, split_search_terms
from toursim.manual_collector import (
    collector_edge_id,
    collector_facility_id,
    collector_link_id,
    collector_node_id,
    collector_node_point,
    collector_ref_point,
    default_collector_meta,
    nearest_collector_node,
    next_collector_node_id,
    next_prefixed_collector_id,
    normalize_collector_edge,
    normalize_collector_link,
    normalize_collector_node,
    normalize_collector_point,
    normalize_road_ref,
    normalize_tags,
    valid_collector_node_id,
)
from toursim.collector_repository import (
    CollectorRepositoryConfig,
    CollectorRepositoryServices,
    collector_source_signature,
    collector_sources_are_newer_than_graph,
    configure_collector_repository,
    empty_manual_graph,
    ensure_collector_files,
    ensure_manual_graph_current,
    ensure_route_graph_current,
    facilities_for_map,
    load_collector_edges,
    load_collector_facilities,
    load_collector_links,
    load_collector_meta,
    load_collector_nodes,
    manual_graph_needs_rebuild,
    nearest_collector_road_node_id,
    normalize_collector_facility,
    rebuild_manual_graph,
    resolve_facility_nearest_node,
)
from toursim.pagination import build_page_window, paginate_items, parse_positive_int
from toursim.routes.auth import AuthRouteServices, create_auth_blueprint
from toursim.routes.assistant import AssistantRouteServices, create_assistant_blueprint
from toursim.routes.diary_media import DiaryMediaRouteServices, create_diary_media_blueprint
from toursim.routes.diaries import DiariesRouteServices, create_diaries_blueprint
from toursim.routes.facilities import FacilitiesRouteServices, create_facilities_blueprint
from toursim.routes.foods import FoodsRouteServices, create_foods_blueprint
from toursim.routes.places import PlacesRouteServices, create_places_blueprint
try:
    from PIL import Image
except ImportError:
    Image = None

import mimetypes
mimetypes.add_type('video/mp4', '.mp4')
mimetypes.add_type('video/webm', '.webm')

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

    return {
        "asset_version": asset_version,
        "preset_avatar_options": get_preset_avatar_options,
    }


@app.after_request
def add_no_cache_headers(response):
    if request.endpoint == "static":
        response.headers["Cache-Control"] = "public, max-age=3600"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
        return response
    if request.endpoint in {
        "diary_media_file",
        "diary_media_thumbnail_file",
        "diary_generated_video_file",
        "diary_media_routes.diary_media_file",
        "diary_media_routes.diary_media_thumbnail_file",
        "diary_media_routes.diary_generated_video_file",
    }:
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
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
AMAP_JS_KEY = os.getenv("AMAP_JS_KEY", "")
AMAP_SECURITY_JS_CODE = os.getenv("AMAP_SECURITY_JS_CODE", "")
AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-v4-pro")
AI_REASONING_MODEL = os.getenv("AI_REASONING_MODEL", AI_MODEL)
AI_ASSISTANT_ENABLED = os.getenv("AI_ASSISTANT_ENABLED", "1")
AI_CHAT_HISTORY_LIMIT = 12
DEEPSEEK_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
XMU_MANUAL_PLACE_ID = "xmu_manual"
XMU_MANUAL_GRAPH_FILE = os.path.join(ROUTE_GRAPHS_DIR, "xmu_manual.json")
XMU_COLLECTOR_DIR = os.path.join(APP_DIR, "data", "manual")
XMU_COLLECTOR_NODES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_nodes.json")
XMU_COLLECTOR_EDGES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_edges.json")
XMU_COLLECTOR_LINKS_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_links.json")
XMU_COLLECTOR_FACILITIES_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_facilities.json")
XMU_COLLECTOR_META_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_collector_meta.json")
XMU_FOOD_MEDIA_FILE = os.path.join(XMU_COLLECTOR_DIR, "xmu_food_media.json")
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
DIARY_GENERATED_VIDEO_DIR = os.path.join(APP_DIR, "data", "uploads", "diary-generated-videos")
DIARY_THUMBNAIL_DIRNAME = "_thumbs_v3"
DIARY_THUMBNAIL_VERSION = "3"
DIARY_THUMBNAIL_MAX_SIZE = (960, 1200)
DIARY_THUMBNAIL_JPEG_QUALITY = 88
DIARY_VIDEO_MODEL = os.getenv("DASHSCOPE_VIDEO_MODEL", "wan2.7-i2v-2026-04-25")
DIARY_VIDEO_DEFAULT_DURATION = int(os.getenv("DIARY_VIDEO_DEFAULT_DURATION", "5") or 5)
DIARY_VIDEO_DEFAULT_RESOLUTION = os.getenv("DIARY_VIDEO_DEFAULT_RESOLUTION", "720P")
USER_AVATAR_DIR = os.path.join(APP_DIR, "static", "uploads", "avatars")
DIARY_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DIARY_ALLOWED_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
DIARY_ALLOWED_MEDIA_EXTS = DIARY_ALLOWED_IMAGE_EXTS | DIARY_ALLOWED_VIDEO_EXTS
DIARY_ALLOWED_AVATAR_EXTS = DIARY_ALLOWED_IMAGE_EXTS | {".svg"}
DIARY_VISIBLE_COMMENT_THREADS = 3
DIARY_VISIBLE_REPLIES = 3


# =========================
# 数据库工具函数
# =========================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def ensure_diary_video_tasks_table(cursor):
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS diary_video_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diary_id INTEGER NOT NULL,
        task_id TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'PENDING',
        prompt TEXT NOT NULL DEFAULT '',
        image_filename TEXT NOT NULL DEFAULT '',
        result_url TEXT NOT NULL DEFAULT '',
        local_video_filename TEXT NOT NULL DEFAULT '',
        error_message TEXT NOT NULL DEFAULT '',
        request_payload_json TEXT NOT NULL DEFAULT '{}',
        response_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(diary_id) REFERENCES diaries(id) ON DELETE CASCADE
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diary_video_tasks_diary_created ON diary_video_tasks(diary_id, created_at DESC, id DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diary_video_tasks_task_id ON diary_video_tasks(task_id)")


def avatar_relative_path(filename):
    return avatar_helpers.avatar_relative_path(filename, APP_DIR, USER_AVATAR_DIR)


def get_preset_avatar_options():
    return avatar_helpers.get_preset_avatar_options()


def is_preset_avatar_path(avatar_path):
    return avatar_helpers.is_preset_avatar_path(avatar_path)


def default_preset_avatar_path(username="", user_id=None):
    return avatar_helpers.default_preset_avatar_path(username, user_id)


def is_legacy_generated_avatar_path(avatar_path):
    return avatar_helpers.is_legacy_generated_avatar_path(avatar_path)


def select_preset_avatar_path(selected_avatar_path, username="", user_id=None):
    return avatar_helpers.select_preset_avatar_path(selected_avatar_path, username, user_id)


def avatar_url_from_path(avatar_path, username="", user_id=None):
    relative_path = avatar_path or ensure_user_avatar_asset(username, user_id)
    return url_for("static", filename=relative_path)


def avatar_initial(username):
    return avatar_helpers.avatar_initial(username)


def avatar_palette(seed_text):
    return avatar_helpers.avatar_palette(seed_text)


def build_avatar_svg(username, user_id=None):
    return avatar_helpers.build_avatar_svg(username, user_id)


def ensure_user_avatar_asset(username, user_id=None, avatar_path=""):
    return avatar_helpers.ensure_user_avatar_asset(username, user_id, avatar_path, APP_DIR)


def save_uploaded_user_avatar(uploaded_file, username, user_id):
    return avatar_helpers.save_uploaded_user_avatar(
        uploaded_file,
        username,
        user_id,
        APP_DIR,
        USER_AVATAR_DIR,
        DIARY_ALLOWED_AVATAR_EXTS,
    )


def save_user_avatar_choice(uploaded_file, selected_avatar_path, username, user_id):
    if uploaded_file and uploaded_file.filename:
        return save_uploaded_user_avatar(uploaded_file, username, user_id)
    return select_preset_avatar_path(selected_avatar_path, username, user_id)


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
    CREATE TABLE IF NOT EXISTS diary_ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        diary_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        rating INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(diary_id, username),
        FOREIGN KEY(diary_id) REFERENCES diaries(id) ON DELETE CASCADE
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_user_profiles (
        user_id INTEGER PRIMARY KEY,
        travel_style TEXT NOT NULL DEFAULT '',
        budget_level TEXT NOT NULL DEFAULT '',
        food_preferences_json TEXT NOT NULL DEFAULT '{}',
        mobility_preferences_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        conversation_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_calls_json TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    )
    """)

    ensure_place_images_table(cursor)
    ensure_diary_video_tasks_table(cursor)
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
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_diary_ratings_diary_username ON diary_ratings(diary_id, username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_favorites_user_type_created ON user_favorites(user_id, item_type, created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_chat_messages_user_conversation_created ON ai_chat_messages(user_id, conversation_id, created_at DESC, id DESC)")

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


def create_diary_video_task(diary_id, task_id, prompt, image_filename, request_payload, raw_response, status="PENDING"):
    ensure_diaries_table()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    cursor = conn.cursor()
    ensure_diary_video_tasks_table(cursor)
    cursor.execute(
        """
        INSERT INTO diary_video_tasks
        (diary_id, task_id, status, prompt, image_filename, request_payload_json, response_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            diary_id,
            task_id,
            normalize_diary_video_status(status),
            prompt or "",
            image_filename or "",
            json.dumps(request_payload or {}, ensure_ascii=False),
            json.dumps(raw_response or {}, ensure_ascii=False),
            now,
            now,
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    cursor.execute("SELECT * FROM diary_video_tasks WHERE id = ?", (row_id,))
    row = cursor.fetchone()
    conn.close()
    return serialize_diary_video_task(row)


def get_diary_video_task(task_id, diary_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    ensure_diary_video_tasks_table(cursor)
    if diary_id is None:
        cursor.execute("SELECT * FROM diary_video_tasks WHERE id = ?", (task_id,))
    else:
        cursor.execute("SELECT * FROM diary_video_tasks WHERE id = ? AND diary_id = ?", (task_id, diary_id))
    row = cursor.fetchone()
    conn.close()
    return serialize_diary_video_task(row)


def get_latest_diary_video_task(diary_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    ensure_diary_video_tasks_table(cursor)
    cursor.execute(
        "SELECT * FROM diary_video_tasks WHERE diary_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (diary_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return serialize_diary_video_task(row)


def update_diary_video_task(task_db_id, **fields):
    allowed_fields = {
        "status",
        "result_url",
        "local_video_filename",
        "error_message",
        "response_json",
    }
    updates = []
    values = []
    for key, value in fields.items():
        if key not in allowed_fields:
            continue
        updates.append(f"{key} = ?")
        if key == "response_json":
            values.append(json.dumps(value or {}, ensure_ascii=False))
        elif key == "status":
            values.append(normalize_diary_video_status(value))
        else:
            values.append(value or "")
    updates.append("updated_at = ?")
    values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    values.append(task_db_id)

    conn = get_db_connection()
    cursor = conn.cursor()
    ensure_diary_video_tasks_table(cursor)
    cursor.execute(f"UPDATE diary_video_tasks SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    cursor.execute("SELECT * FROM diary_video_tasks WHERE id = ?", (task_db_id,))
    row = cursor.fetchone()
    conn.close()
    return serialize_diary_video_task(row)


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


def sync_diary_index_view_count(diary_id):
    if DIARY_INDEX_CACHE.get("fingerprint") is None:
        return
    for record in DIARY_INDEX_CACHE.get("display_records") or []:
        if record.get("id") == diary_id:
            record["views"] = int(record.get("views", 0) or 0) + 1
            break
    record_map = DIARY_INDEX_CACHE.get("record_map") or {}
    if diary_id in record_map:
        record_map[diary_id]["views"] = int(record_map[diary_id].get("views", 0) or 0) + 1
    DIARY_INDEX_CACHE["source_signature"] = file_signature(DB_PATH)


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
            # 优化：在此处立刻同步生成缩略图，避免用户首次进入时因实时切图而卡顿
            ensure_diary_image_thumbnail(diary_id, final_name)
            # 优化第二阶段：同步写入极微 Base64 到数据库字典中，用于 0ms 秒开占位
            media_item["blur_base64"] = generate_image_blur_base64(diary_id, final_name)
        saved_items.append({**media_item})

    return saved_items


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


refresh_diary_storage()


# =========================
# 登录状态工具函数
# =========================
def is_logged_in():
    return "username" in session


# =========================
# 景点数据读取函数
# =========================
def build_indoor_graph(building_id="demo_building"):
    collector_payload = load_indoor_collector_payload()
    if os.path.exists(INDOOR_COLLECTOR_FILE):
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
        item["nearest_node"] = nearest_node
        nearest = graph.get("node_map", {}).get(nearest_node)
        if nearest:
            item["nearest_lng"] = nearest.get("amap_lng", nearest.get("lon"))
            item["nearest_lat"] = nearest.get("amap_lat", nearest.get("lat"))
        item["distance"] = round(path["total"], 1)
        if max_distance is not None and item["distance"] > max_distance:
            continue
        item["path_names"] = " -> ".join(path.get("display_path_names", path["path_names"]))
        item["walk_minutes"] = round(item["distance"] / 1.2 / 60, 1)
        result.append(item)

    return sorted(result, key=lambda item: item["distance"])


def _route_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def facility_map_payload(facility, graph, id_prefix="facility"):
    facility_id = str((facility or {}).get("id") or "").strip()
    name = str((facility or {}).get("name") or (facility or {}).get("category") or (facility or {}).get("type") or "场所").strip()
    facility_type = str((facility or {}).get("type") or (facility or {}).get("category") or "场所").strip()
    nearest_node = str((facility or {}).get("nearest_node") or "").strip()
    node = graph.get("node_map", {}).get(nearest_node) if nearest_node else None

    lng = _route_float((facility or {}).get("amap_lng", (facility or {}).get("lon")))
    lat = _route_float((facility or {}).get("amap_lat", (facility or {}).get("lat")))
    if (lng is None or lat is None) and node:
        lng = _route_float(node.get("amap_lng", node.get("lon")))
        lat = _route_float(node.get("amap_lat", node.get("lat")))
    if lng is None or lat is None:
        return None

    payload = {
        "id": f"{id_prefix}:{facility_id}" if facility_id and ":" not in facility_id else (facility_id or f"{id_prefix}:{name}"),
        "source_id": facility_id,
        "name": name,
        "type": facility_type,
        "category": facility_type,
        "nearest_node": nearest_node,
        "amap_lng": lng,
        "amap_lat": lat,
        "lon": lng,
        "lat": lat,
        "distance": (facility or {}).get("distance"),
        "walk_minutes": (facility or {}).get("walk_minutes"),
        "path_names": (facility or {}).get("path_names", ""),
    }
    if node:
        payload["nearest_lng"] = node.get("amap_lng", node.get("lon"))
        payload["nearest_lat"] = node.get("amap_lat", node.get("lat"))
    return payload


def food_facility_start_payload(food_key, place_id, graph, origin_node=""):
    pinned = pinned_food_facility_for_route(food_key, place_id, graph, origin_node=origin_node)
    if not pinned:
        return None
    return {
        **pinned,
        "id": f"food:{pinned.get('food_key') or food_key}",
        "source_id": pinned.get("food_key") or food_key,
        "type": pinned.get("type") or "美食",
        "category": pinned.get("category") or "美食",
    }


def build_facility_start_options(graph, facilities, place_id):
    options = []
    for node in get_selectable_nodes(graph):
        options.append({
            "value": str(node.get("id", "")),
            "name": str(node.get("name", "")),
            "type": str(node.get("category") or node.get("kind") or "路线点"),
            "source": "node",
        })
    for facility in facilities:
        facility_id = str(facility.get("id") or "").strip()
        marker = facility_map_payload(facility, graph, id_prefix="facility")
        if not facility_id or not marker:
            continue
        options.append({
            "value": f"facility:{facility_id}",
            "name": marker["name"],
            "type": marker["type"],
            "source": "facility",
        })
    for food in build_food_candidates_for_place(place_id):
        food_key = str(food.get("food_key") or "").strip()
        nearest_node = str(food.get("nearest_node") or "").strip()
        if not food_key or not nearest_node or nearest_node not in graph.get("node_map", {}):
            continue
        options.append({
            "value": f"food:{food_key}",
            "name": str(food.get("name") or "餐馆"),
            "type": str(food.get("cuisine") or food.get("category") or "美食"),
            "source": "food",
        })
    return options


def resolve_facility_query_start(raw_value, place_id, graph, facilities, explicit_food_key=""):
    raw_value = str(raw_value or "").strip()
    explicit_food_key = str(explicit_food_key or "").strip()

    if explicit_food_key:
        marker = food_facility_start_payload(explicit_food_key, place_id, graph)
        if marker and marker.get("nearest_node") in graph.get("node_map", {}):
            return {
                "value": f"food:{marker.get('source_id')}",
                "node_id": marker["nearest_node"],
                "label": marker["name"],
                "kind": "food",
                "marker": marker,
            }

    if raw_value.startswith("food:"):
        food_key = raw_value.split(":", 1)[1]
        marker = food_facility_start_payload(food_key, place_id, graph)
        if marker and marker.get("nearest_node") in graph.get("node_map", {}):
            return {
                "value": raw_value,
                "node_id": marker["nearest_node"],
                "label": marker["name"],
                "kind": "food",
                "marker": marker,
            }

    if raw_value.startswith("facility:"):
        facility_id = raw_value.split(":", 1)[1]
        for facility in facilities:
            if str(facility.get("id") or "").strip() != facility_id:
                continue
            nearest_node = resolve_facility_nearest_node(facility, graph, road_only=True)
            marker = facility_map_payload({**facility, "nearest_node": nearest_node}, graph, id_prefix="facility")
            if nearest_node in graph.get("node_map", {}) and marker:
                return {
                    "value": raw_value,
                    "node_id": nearest_node,
                    "label": marker["name"],
                    "kind": "facility",
                    "marker": marker,
                }
            break

    if raw_value in graph.get("node_map", {}):
        node = graph["node_map"][raw_value]
        return {
            "value": raw_value,
            "node_id": raw_value,
            "label": node.get("name") or raw_value,
            "kind": "node",
            "marker": None,
        }

    return {
        "value": "",
        "node_id": "",
        "label": "",
        "kind": "",
        "marker": None,
    }


def pinned_food_facility_for_route(food_key, place_id, graph, origin_node=""):
    food_key = str(food_key or "").strip()
    if not food_key:
        return None

    food = get_food_by_key(food_key, place_id=place_id, origin_node=origin_node)
    if not food:
        return None

    nearest_node = str(food.get("nearest_node") or food.get("graph_node_id") or "").strip()
    node = graph.get("node_map", {}).get(nearest_node) if nearest_node else None

    lng = food.get("amap_lng", food.get("lon"))
    lat = food.get("amap_lat", food.get("lat"))
    try:
        lng = float(lng)
        lat = float(lat)
    except (TypeError, ValueError):
        lng = None
        lat = None

    if (lng is None or lat is None) and node:
        try:
            lng = float(node.get("amap_lng", node.get("lon")))
            lat = float(node.get("amap_lat", node.get("lat")))
        except (TypeError, ValueError):
            lng = None
            lat = None

    if lng is None or lat is None:
        return None

    pinned = {
        "id": food.get("food_key") or food_key,
        "food_key": food.get("food_key") or food_key,
        "name": food.get("name") or "终点",
        "type": food.get("cuisine") or food.get("category") or "美食终点",
        "category": food.get("category") or food.get("cuisine") or "美食终点",
        "nearest_node": nearest_node,
        "amap_lng": lng,
        "amap_lat": lat,
        "lon": lng,
        "lat": lat,
    }

    if node:
        pinned["nearest_lng"] = node.get("amap_lng", node.get("lon"))
        pinned["nearest_lat"] = node.get("amap_lat", node.get("lat"))

    return pinned


# =========================
# 推荐算法函数
# =========================


# =========================
# 旅游日记管理函数
# =========================


# =========================
# 路由
# =========================
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

    default_start, default_end = indoor_default_endpoints(graph)
    clear_selection = request.args.get("clear", "").strip() == "1"
    has_start_arg = "start" in request.args
    has_end_arg = "end" in request.args
    has_endpoint_args = has_start_arg or has_end_arg

    if clear_selection:
        start = ""
        end = ""
    elif has_endpoint_args:
        start = request.args.get("start", "").strip()
        end = request.args.get("end", "").strip()
    else:
        start = request.args.get("start", default_start).strip() or default_start
        end = request.args.get("end", default_end).strip() or default_end
    vertical_mode = request.args.get("vertical_mode", "auto").strip().lower()

    if start and start not in graph["node_map"]:
        start = default_start if not has_endpoint_args else ""
    if end and end not in graph["node_map"]:
        end = default_end if not has_endpoint_args else ""
    if vertical_mode not in INDOOR_VERTICAL_MODES:
        vertical_mode = "auto"

    pick_mode = request.args.get("pick_mode", "").strip().lower()
    if pick_mode not in {"start", "end"}:
        pick_mode = "end" if start and not end else "start"

    def indoor_selection_url(**overrides):
        params = {
            "building_id": building_id,
            "building_name": building_name,
            "vertical_mode": vertical_mode,
        }
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        params.update(overrides)
        params = {key: value for key, value in params.items() if value not in ("", None)}
        query = urlencode(params)
        return url_for("indoor") + (f"?{query}" if query else "")

    route_result = indoor_shortest_path(graph, start, end, vertical_mode=vertical_mode) if start and end else None
    node_options = indoor_node_options(graph)
    floors = prepare_indoor_floors(graph, route_result)
    for floor in floors:
        for node in floor.get("display_nodes", []):
            next_start = start
            next_end = end
            if pick_mode == "end":
                next_end = node["id"]
            else:
                next_start = node["id"]
            node["pick_target"] = pick_mode
            node["pick_url"] = indoor_selection_url(
                start=next_start,
                end=next_end,
                pick_mode="start" if next_start and next_end else ("start" if pick_mode == "end" else "end"),
            )
            node["pick_label"] = f"设为{'终点' if pick_mode == 'end' else '起点'}：{node.get('name', node['id'])}"

    return render_template(
        "indoor.html",
        username=session["username"],
        building_id=building_id,
        building_name=building_name,
        clear_selection=clear_selection,
        pick_mode=pick_mode,
        pick_start_url=indoor_selection_url(pick_mode="start"),
        pick_end_url=indoor_selection_url(pick_mode="end"),
        start=start,
        end=end,
        start_node=graph["node_map"].get(start),
        end_node=graph["node_map"].get(end),
        vertical_mode=vertical_mode,
        node_options=node_options,
        floors=floors,
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
        node = normalize_indoor_collector_node(source, floor_payload.get("nodes", []))
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
            floor_payload.get("edges", []),
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
            floor_payload.get("links", []),
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
# places list and recommendation overview
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

    requested_facility_start = request.args.get("facility_start_node", "").strip()
    requested_facility_start_food = request.args.get("facility_start_food", "").strip()
    facility_query_requested = request.args.get("facility_query", "").strip() == "1"
    facility_type = request.args.get("facility_type", "").strip()
    facility_keyword = request.args.get("facility_keyword", "").strip()
    max_distance_raw = request.args.get("max_distance", "").strip()
    try:
        max_distance = float(max_distance_raw) if max_distance_raw else None
    except ValueError:
        max_distance = None

    all_facilities = load_facilities(graph.get("place_id"))
    facility_start_context = resolve_facility_query_start(
        requested_facility_start or start,
        place_id,
        graph,
        all_facilities,
        explicit_food_key=requested_facility_start_food,
    )
    facility_start_node = facility_start_context["value"]
    facility_start_route_node = facility_start_context["node_id"]
    facility_start_options = build_facility_start_options(graph, all_facilities, place_id)
    facility_types = sorted({facility["type"] for facility in all_facilities if facility.get("type")})
    facility_query_submitted = bool(facility_query_requested or facility_type or facility_keyword or max_distance_raw)
    facilities_result = []
    if facility_query_submitted and facility_start_route_node:
        facilities_result = find_nearby_facilities(
            graph,
            facility_start_route_node,
            facility_type=facility_type,
            keyword=facility_keyword,
            max_distance=max_distance,
        )
    map_facility_results = [
        payload for payload in (
            facility_map_payload(facility, graph, id_prefix="facility-result")
            for facility in facilities_result
        )
        if payload
    ]
    facility_query_active = bool(facility_query_submitted and facility_start_route_node)

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
        "facility_start_food": requested_facility_start_food,
        "facility_query": "1" if facility_query_submitted else None,
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
        facility_id = str(facility.get("id") or "").strip()
        facility_start_value = f"facility:{facility_id}" if facility_id else nearest_node
        facility["set_start_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "start": nearest_node,
                "facility_start_node": facility_start_value,
                "facility_start_food": "",
            },
            anchor="routeSummary",
        )
        facility["set_end_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "end": nearest_node,
                "facility_start_node": facility_start_value,
                "facility_start_food": "",
            },
            anchor="routeSummary",
        )
        facility["focus_url"] = build_url_with_query(
            "route",
            {
                **route_state_params,
                "facility_start_node": facility_start_value,
                "facility_start_food": "",
            },
            anchor="facilityResults",
        )

    route_foods, route_food_stats = get_route_linked_foods(place_id, graph, start, limit=5)
    route_pinned_food_facility = pinned_food_facility_for_route(
        return_food_key,
        return_place_id or place_id,
        graph,
        origin_node=start,
    )
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
        route_pinned_food_facility=route_pinned_food_facility,
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
        facility_start_context=facility_start_context,
        facility_start_options=facility_start_options,
        facility_type=facility_type,
        facility_keyword=facility_keyword,
        max_distance=max_distance_raw,
        facility_types=facility_types,
        facilities=facilities_result,
        map_facility_results=map_facility_results,
        facility_query_active=facility_query_active,
        facility_query_submitted=facility_query_submitted,
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
            "facility_start_food": requested_facility_start_food,
            "facility_query": "1" if facility_query_submitted else "",
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
            "facility_start_food": requested_facility_start_food,
            "facility_query": "1" if facility_query_submitted else "",
            "facility_type": facility_type,
            "facility_keyword": facility_keyword,
            "max_distance": max_distance_raw,
        },
        facility_form_state={
            "place_id": place_id,
            "facility_start_node": facility_start_node,
            "facility_start_food": requested_facility_start_food,
            "facility_query": "1" if facility_query_submitted else "",
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
        return jsonify({"error": "请先登录"}), 401

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


configure_place_repository(
    PlaceRepositoryConfig(
        app_dir=lambda: globals()["APP_DIR"],
        db_path=lambda: globals()["DB_PATH"],
        places_file=lambda: globals()["PLACES_FILE"],
        place_media_dir=lambda: globals()["PLACE_MEDIA_DIR"],
        allowed_image_exts=lambda: globals()["DIARY_ALLOWED_IMAGE_EXTS"],
        places_cache=PLACES_CACHE,
        place_image_cache=PLACE_IMAGE_CACHE,
    ),
    PlaceRepositoryServices(get_db_connection=get_db_connection),
)
configure_collector_repository(
    CollectorRepositoryConfig(
        collector_dir=XMU_COLLECTOR_DIR,
        nodes_file=XMU_COLLECTOR_NODES_FILE,
        edges_file=XMU_COLLECTOR_EDGES_FILE,
        links_file=XMU_COLLECTOR_LINKS_FILE,
        facilities_file=XMU_COLLECTOR_FACILITIES_FILE,
        meta_file=XMU_COLLECTOR_META_FILE,
        source_files=XMU_COLLECTOR_SOURCE_FILES,
        manual_graph_file=XMU_MANUAL_GRAPH_FILE,
        manual_place_id=XMU_MANUAL_PLACE_ID,
        default_place_id=DEFAULT_PLACE_ID,
        road_snap_meters=XMU_ROAD_SNAP_METERS,
        signature_cache=COLLECTOR_SIGNATURE_CACHE,
    ),
    CollectorRepositoryServices(
        collector_source_summary=collector_source_summary,
        invalidate_facilities_cache=invalidate_facilities_cache,
        invalidate_route_graph_cache=invalidate_route_graph_cache,
        load_facilities=load_facilities,
    ),
)
ensure_collector_files()
if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
    rebuild_manual_graph()
configure_route_repository(
    RouteRepositoryConfig(
        route_graphs_dir=ROUTE_GRAPHS_DIR,
        manual_graph_file=XMU_MANUAL_GRAPH_FILE,
        default_place_id=DEFAULT_PLACE_ID,
        manual_place_id=XMU_MANUAL_PLACE_ID,
        route_graph_cache=ROUTE_GRAPH_CACHE,
    ),
    RouteRepositoryServices(
        collector_source_signature=lambda *args, **kwargs: globals()["collector_source_signature"](*args, **kwargs),
        ensure_manual_graph_current=lambda *args, **kwargs: globals()["ensure_manual_graph_current"](*args, **kwargs),
        load_collector_edges=lambda *args, **kwargs: globals()["load_collector_edges"](*args, **kwargs),
        load_collector_links=lambda *args, **kwargs: globals()["load_collector_links"](*args, **kwargs),
    ),
)
configure_food_repository(
    FoodRepositoryConfig(
        facilities_file=FACILITIES_FILE,
        collector_facilities_file=XMU_COLLECTOR_FACILITIES_FILE,
        food_media_file=XMU_FOOD_MEDIA_FILE,
        generated_facilities_file=XMU_XIANG_AN_GENERATED_FACILITIES_FILE,
        food_default_place_id=FOOD_DEFAULT_PLACE_ID,
        food_campus_contexts=FOOD_CAMPUS_CONTEXTS,
        food_candidates_cache=FOOD_CANDIDATES_CACHE,
        food_media_cache=FOOD_MEDIA_CACHE,
    ),
    FoodRepositoryServices(
        get_route_graph_path=get_route_graph_path,
        load_route_graph=load_route_graph,
        load_facilities=load_facilities,
        resolve_facility_nearest_node=resolve_facility_nearest_node,
    ),
)


configure_diary_repository(DiaryRepositoryServices(
    get_db_connection=get_db_connection,
    ensure_diaries_table=ensure_diaries_table,
    get_diary_index_cache=get_diary_index_cache,
    invalidate_diary_index_cache=invalidate_diary_index_cache,
    sync_diary_index_view_count=sync_diary_index_view_count,
    build_diary_comment_tree=build_diary_comment_tree,
    get_user_by_username=get_user_by_username,
    ensure_user_avatar_asset=ensure_user_avatar_asset,
))


configure_user_accounts(UserAccountServices(
    get_db_connection=get_db_connection,
    invalidate_diary_index_cache=invalidate_diary_index_cache,
    avatar_url_from_path=avatar_url_from_path,
))
configure_favorites(FavoriteServices(
    get_db_connection=get_db_connection,
    get_diary_by_id=get_diary_by_id,
    get_food_by_key=get_food_by_key,
    get_place_by_id=get_place_by_id,
    load_diaries=load_diaries,
))


configure_diary_media(
    DiaryMediaConfig(
        upload_dir=lambda: globals()["DIARY_UPLOAD_DIR"],
        generated_video_dir=lambda: globals()["DIARY_GENERATED_VIDEO_DIR"],
        thumbnail_dirname=lambda: globals()["DIARY_THUMBNAIL_DIRNAME"],
        thumbnail_version=lambda: globals()["DIARY_THUMBNAIL_VERSION"],
        thumbnail_max_size=lambda: globals()["DIARY_THUMBNAIL_MAX_SIZE"],
        thumbnail_jpeg_quality=lambda: globals()["DIARY_THUMBNAIL_JPEG_QUALITY"],
        allowed_image_exts=lambda: globals()["DIARY_ALLOWED_IMAGE_EXTS"],
        allowed_video_exts=lambda: globals()["DIARY_ALLOWED_VIDEO_EXTS"],
    ),
    DiaryMediaServices(
        get_db_connection=get_db_connection,
        invalidate_diary_index_cache=invalidate_diary_index_cache,
    ),
)
configure_diary_video(
    DiaryVideoConfig(
        model=lambda: globals()["DIARY_VIDEO_MODEL"],
        default_duration=lambda: globals()["DIARY_VIDEO_DEFAULT_DURATION"],
        default_resolution=lambda: globals()["DIARY_VIDEO_DEFAULT_RESOLUTION"],
    ),
    DiaryVideoServices(stored_diary_media_items=stored_diary_media_items),
)


configure_ai_assistant(AIAssistantServices(
    app_context=app.app_context,
    test_request_context=app.test_request_context,
    build_url_with_query=build_url_with_query,
    build_food_candidates_for_place=build_food_candidates_for_place,
    build_indoor_graph=build_indoor_graph,
    get_db_connection=get_db_connection,
    load_diaries=load_diaries,
    load_places=load_places,
    load_route_graph=load_route_graph,
    url_for=url_for,
    food_campus_contexts=FOOD_CAMPUS_CONTEXTS,
    indoor_route_steps=indoor_route_steps,
    indoor_shortest_path=indoor_shortest_path,
))


app.register_blueprint(create_auth_blueprint(AuthRouteServices(
    create_user=lambda *args, **kwargs: globals()["create_user"](*args, **kwargs),
    get_db_connection=lambda: globals()["get_db_connection"](),
    get_logged_in_user=lambda: globals()["get_logged_in_user"](),
    get_user_activity_stats=lambda *args, **kwargs: globals()["get_user_activity_stats"](*args, **kwargs),
    get_user_avatar_url=lambda *args, **kwargs: globals()["get_user_avatar_url"](*args, **kwargs),
    get_user_by_id=lambda *args, **kwargs: globals()["get_user_by_id"](*args, **kwargs),
    get_user_by_username=lambda *args, **kwargs: globals()["get_user_by_username"](*args, **kwargs),
    is_logged_in=lambda: globals()["is_logged_in"](),
    load_favorite_diaries=lambda *args, **kwargs: globals()["load_favorite_diaries"](*args, **kwargs),
    load_favorite_foods=lambda *args, **kwargs: globals()["load_favorite_foods"](*args, **kwargs),
    load_favorite_places=lambda *args, **kwargs: globals()["load_favorite_places"](*args, **kwargs),
    load_places=lambda *args, **kwargs: globals()["load_places"](*args, **kwargs),
    load_user_diaries=lambda *args, **kwargs: globals()["load_user_diaries"](*args, **kwargs),
    save_user_avatar_choice=lambda *args, **kwargs: globals()["save_user_avatar_choice"](*args, **kwargs),
    update_user_account=lambda *args, **kwargs: globals()["update_user_account"](*args, **kwargs),
    update_user_avatar_path=lambda *args, **kwargs: globals()["update_user_avatar_path"](*args, **kwargs),
)))
app.register_blueprint(create_places_blueprint(PlacesRouteServices(
    build_pagination=lambda *args, **kwargs: globals()["build_pagination"](*args, **kwargs),
    filter_and_sort_places=lambda *args, **kwargs: globals()["filter_and_sort_places"](*args, **kwargs),
    get_place_by_id=lambda *args, **kwargs: globals()["get_place_by_id"](*args, **kwargs),
    get_place_filter_options=lambda *args, **kwargs: globals()["get_place_filter_options"](*args, **kwargs),
    get_related_diaries_for_place=lambda *args, **kwargs: globals()["get_related_diaries_for_place"](*args, **kwargs),
    get_top_k_recommendations=lambda *args, **kwargs: globals()["get_top_k_recommendations"](*args, **kwargs),
    get_logged_in_user=lambda: globals()["get_logged_in_user"](),
    is_item_favorited=lambda *args, **kwargs: globals()["is_item_favorited"](*args, **kwargs),
    is_logged_in=lambda: globals()["is_logged_in"](),
    load_diaries=lambda *args, **kwargs: globals()["load_diaries"](*args, **kwargs),
    load_places=lambda *args, **kwargs: globals()["load_places"](*args, **kwargs),
    paginate_items=lambda *args, **kwargs: globals()["paginate_items"](*args, **kwargs),
    parse_positive_int=lambda *args, **kwargs: globals()["parse_positive_int"](*args, **kwargs),
    places_page_size=lambda: globals()["PLACES_PAGE_SIZE"],
    save_place_image_record=lambda *args, **kwargs: globals()["save_place_image_record"](*args, **kwargs),
    save_uploaded_place_cover=lambda *args, **kwargs: globals()["save_uploaded_place_cover"](*args, **kwargs),
    toggle_user_favorite=lambda *args, **kwargs: globals()["toggle_user_favorite"](*args, **kwargs),
)))
app.register_blueprint(create_foods_blueprint(FoodsRouteServices(
    build_food_candidates_for_place=lambda *args, **kwargs: globals()["build_food_candidates_for_place"](*args, **kwargs),
    build_pagination=lambda *args, **kwargs: globals()["build_pagination"](*args, **kwargs),
    build_url_with_query=lambda *args, **kwargs: globals()["build_url_with_query"](*args, **kwargs),
    food_campus_contexts=lambda: globals()["FOOD_CAMPUS_CONTEXTS"],
    food_cuisine_options=lambda: globals()["FOOD_CUISINE_OPTIONS"],
    food_default_place_id=lambda: globals()["FOOD_DEFAULT_PLACE_ID"],
    food_top_k=lambda: globals()["FOOD_TOP_K"],
    get_food_by_key=lambda *args, **kwargs: globals()["get_food_by_key"](*args, **kwargs),
    get_logged_in_user=lambda: globals()["get_logged_in_user"](),
    is_item_favorited=lambda *args, **kwargs: globals()["is_item_favorited"](*args, **kwargs),
    is_logged_in=lambda: globals()["is_logged_in"](),
    load_route_graph=lambda *args, **kwargs: globals()["load_route_graph"](*args, **kwargs),
    paginate_items=lambda *args, **kwargs: globals()["paginate_items"](*args, **kwargs),
    parse_positive_int=lambda *args, **kwargs: globals()["parse_positive_int"](*args, **kwargs),
    rank_food_candidates=lambda *args, **kwargs: globals()["rank_food_candidates"](*args, **kwargs),
    toggle_user_favorite=lambda *args, **kwargs: globals()["toggle_user_favorite"](*args, **kwargs),
)))
app.register_blueprint(create_diaries_blueprint(DiariesRouteServices(
    build_bailian_video_payload=lambda *args, **kwargs: globals()["build_bailian_video_payload"](*args, **kwargs),
    build_diary_video_prompt=lambda *args, **kwargs: globals()["build_diary_video_prompt"](*args, **kwargs),
    build_pagination=lambda *args, **kwargs: globals()["build_pagination"](*args, **kwargs),
    create_diary=lambda *args, **kwargs: globals()["create_diary"](*args, **kwargs),
    create_diary_comment=lambda *args, **kwargs: globals()["create_diary_comment"](*args, **kwargs),
    create_diary_video_task=lambda *args, **kwargs: globals()["create_diary_video_task"](*args, **kwargs),
    diary_image_data_url=lambda *args, **kwargs: globals()["diary_image_data_url"](*args, **kwargs),
    diary_visible_comment_threads=lambda: globals()["DIARY_VISIBLE_COMMENT_THREADS"],
    diary_visible_replies=lambda: globals()["DIARY_VISIBLE_REPLIES"],
    diaries_page_size=lambda: globals()["DIARIES_PAGE_SIZE"],
    download_diary_generated_video=lambda *args, **kwargs: globals()["download_diary_generated_video"](*args, **kwargs),
    find_place_match=lambda *args, **kwargs: globals()["find_place_match"](*args, **kwargs),
    flatten_diary_comment_replies=lambda *args, **kwargs: globals()["flatten_diary_comment_replies"](*args, **kwargs),
    get_dashscope_api_key=lambda: globals()["get_dashscope_api_key"](),
    get_db_connection=lambda: globals()["get_db_connection"](),
    get_diary_by_id=lambda *args, **kwargs: globals()["get_diary_by_id"](*args, **kwargs),
    get_diary_compression_preview=lambda *args, **kwargs: globals()["get_diary_compression_preview"](*args, **kwargs),
    get_diary_user_rating=lambda *args, **kwargs: globals()["get_diary_user_rating"](*args, **kwargs),
    get_diary_video_task=lambda *args, **kwargs: globals()["get_diary_video_task"](*args, **kwargs),
    get_latest_diary_video_task=lambda *args, **kwargs: globals()["get_latest_diary_video_task"](*args, **kwargs),
    get_logged_in_user=lambda: globals()["get_logged_in_user"](),
    get_place_name_options=lambda *args, **kwargs: globals()["get_place_name_options"](*args, **kwargs),
    get_related_places_for_diary=lambda *args, **kwargs: globals()["get_related_places_for_diary"](*args, **kwargs),
    get_user_avatar_url=lambda *args, **kwargs: globals()["get_user_avatar_url"](*args, **kwargs),
    get_user_by_username=lambda *args, **kwargs: globals()["get_user_by_username"](*args, **kwargs),
    is_item_favorited=lambda *args, **kwargs: globals()["is_item_favorited"](*args, **kwargs),
    is_logged_in=lambda: globals()["is_logged_in"](),
    load_diaries=lambda *args, **kwargs: globals()["load_diaries"](*args, **kwargs),
    load_diary_comments=lambda *args, **kwargs: globals()["load_diary_comments"](*args, **kwargs),
    load_places=lambda *args, **kwargs: globals()["load_places"](*args, **kwargs),
    normalize_diary_video_duration=lambda *args, **kwargs: globals()["normalize_diary_video_duration"](*args, **kwargs),
    normalize_diary_video_resolution=lambda *args, **kwargs: globals()["normalize_diary_video_resolution"](*args, **kwargs),
    normalize_diary_video_status=lambda *args, **kwargs: globals()["normalize_diary_video_status"](*args, **kwargs),
    paginate_items=lambda *args, **kwargs: globals()["paginate_items"](*args, **kwargs),
    parse_positive_int=lambda *args, **kwargs: globals()["parse_positive_int"](*args, **kwargs),
    poll_bailian_video_task=lambda *args, **kwargs: globals()["poll_bailian_video_task"](*args, **kwargs),
    rate_diary_once=lambda *args, **kwargs: globals()["rate_diary_once"](*args, **kwargs),
    save_diary_media_files=lambda *args, **kwargs: globals()["save_diary_media_files"](*args, **kwargs),
    select_diary_video_image=lambda *args, **kwargs: globals()["select_diary_video_image"](*args, **kwargs),
    stored_diary_media_items=lambda *args, **kwargs: globals()["stored_diary_media_items"](*args, **kwargs),
    submit_bailian_image_to_video_task=lambda *args, **kwargs: globals()["submit_bailian_image_to_video_task"](*args, **kwargs),
    toggle_diary_comment_like=lambda *args, **kwargs: globals()["toggle_diary_comment_like"](*args, **kwargs),
    toggle_user_favorite=lambda *args, **kwargs: globals()["toggle_user_favorite"](*args, **kwargs),
    update_diary_compression_algorithm=lambda *args, **kwargs: globals()["update_diary_compression_algorithm"](*args, **kwargs),
    update_diary_media=lambda *args, **kwargs: globals()["update_diary_media"](*args, **kwargs),
    update_diary_video_task=lambda *args, **kwargs: globals()["update_diary_video_task"](*args, **kwargs),
)))
app.register_blueprint(create_facilities_blueprint(FacilitiesRouteServices(
    is_logged_in=lambda: globals()["is_logged_in"](),
)))
app.register_blueprint(create_assistant_blueprint(AssistantRouteServices(
    ai_assistant_config=lambda: globals()["ai_assistant_config"](),
    ai_executable_route_answer=lambda *args, **kwargs: globals()["ai_executable_route_answer"](*args, **kwargs),
    ai_latest_conversation_id=lambda *args, **kwargs: globals()["ai_latest_conversation_id"](*args, **kwargs),
    ai_local_assistant_payload=lambda *args, **kwargs: globals()["ai_local_assistant_payload"](*args, **kwargs),
    ai_provider_answer=lambda *args, **kwargs: globals()["ai_provider_answer"](*args, **kwargs),
    ai_recent_chat_messages=lambda *args, **kwargs: globals()["ai_recent_chat_messages"](*args, **kwargs),
    ai_safe_text=lambda *args, **kwargs: globals()["ai_safe_text"](*args, **kwargs),
    ai_store_chat_message=lambda *args, **kwargs: globals()["ai_store_chat_message"](*args, **kwargs),
    get_logged_in_user=lambda: globals()["get_logged_in_user"](),
    is_logged_in=lambda: globals()["is_logged_in"](),
    history_limit=lambda: globals()["AI_CHAT_HISTORY_LIMIT"],
)))
app.register_blueprint(create_diary_media_blueprint(DiaryMediaRouteServices(
    ensure_diary_image_thumbnail=lambda *args, **kwargs: globals()["ensure_diary_image_thumbnail"](*args, **kwargs),
    resolve_diary_generated_video_path=lambda *args, **kwargs: globals()["resolve_diary_generated_video_path"](*args, **kwargs),
    resolve_diary_media_path=lambda *args, **kwargs: globals()["resolve_diary_media_path"](*args, **kwargs),
)))
app.add_url_rule(
    "/diary-media/<int:diary_id>/<path:filename>",
    endpoint="diary_media_file",
    view_func=app.view_functions["diary_media_routes.diary_media_file"],
)
app.add_url_rule(
    "/diary-generated-video/<int:diary_id>/<path:filename>",
    endpoint="diary_generated_video_file",
    view_func=app.view_functions["diary_media_routes.diary_generated_video_file"],
)
app.add_url_rule(
    "/diary-media-thumb/<int:diary_id>/<path:filename>",
    endpoint="diary_media_thumbnail_file",
    view_func=app.view_functions["diary_media_routes.diary_media_thumbnail_file"],
)
for legacy_endpoint, route_rule, route_methods in (
    ("diaries", "/diaries", ["GET", "POST"]),
    ("diary_search", "/diaries/search", None),
    ("diary_detail", "/diary/<int:diary_id>", ["GET", "POST"]),
    ("diary_video_generation_start", "/api/diary/<int:diary_id>/video-generation", ["POST"]),
    ("diary_video_generation_latest", "/api/diary/<int:diary_id>/video-generation/latest", None),
    ("diary_video_generation_status", "/api/diary/<int:diary_id>/video-generation/<int:task_db_id>", None),
    ("diary_favorite", "/diary/<int:diary_id>/favorite", ["POST"]),
    ("diary_comment_like", "/diary/<int:diary_id>/comments/<int:comment_id>/like", ["POST"]),
):
    app.add_url_rule(
        route_rule,
        endpoint=legacy_endpoint,
        view_func=app.view_functions[f"diaries_routes.{legacy_endpoint}"],
        methods=route_methods,
    )
for legacy_endpoint, route_rule, route_methods in (
    ("index", "/", None),
    ("register", "/register", ["GET", "POST"]),
    ("login", "/login", ["GET", "POST"]),
    ("home", "/home", None),
    ("logout", "/logout", None),
    ("profile", "/profile", ["GET", "POST"]),
    ("user_profile", "/user/<int:user_id>", None),
):
    app.add_url_rule(
        route_rule,
        endpoint=legacy_endpoint,
        view_func=app.view_functions[f"auth.{legacy_endpoint}"],
        methods=route_methods,
    )
for legacy_endpoint, route_rule, route_methods in (
    ("places", "/places", None),
    ("place_detail", "/place/<int:place_id>", None),
    ("place_favorite", "/place/<int:place_id>/favorite", ["POST"]),
    ("upload_place_image", "/place/<int:place_id>/image/upload", ["POST"]),
    ("recommend_places", "/places/recommend", ["GET", "POST"]),
):
    app.add_url_rule(
        route_rule,
        endpoint=legacy_endpoint,
        view_func=app.view_functions[f"places_routes.{legacy_endpoint}"],
        methods=route_methods,
    )
for legacy_endpoint, route_rule, route_methods in (
    ("foods", "/foods", None),
    ("food_detail", "/food/<food_key>", None),
    ("food_favorite", "/food/<food_key>/favorite", ["POST"]),
):
    app.add_url_rule(
        route_rule,
        endpoint=legacy_endpoint,
        view_func=app.view_functions[f"foods_routes.{legacy_endpoint}"],
        methods=route_methods,
    )
app.add_url_rule(
    "/facilities",
    endpoint="facilities",
    view_func=app.view_functions["facilities_routes.facilities"],
)
if __name__ == "__main__":
    # Start a background thumbnail prewarm task before launching Flask.
    import threading
    threading.Thread(target=prewarm_all_diary_thumbnails, daemon=True).start()

    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug, use_reloader=debug)
