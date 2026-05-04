from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from collections import defaultdict
import base64
import bisect
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

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

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


load_local_env()

RUNTIME_DATA_DIR = os.getenv("DATA_DIR", APP_DIR)
DB_NAME = os.getenv("DB_NAME", "tourism.db")
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(RUNTIME_DATA_DIR, DB_NAME)
SEED_DB_PATH = os.path.join(APP_DIR, "tourism.db")

PLACES_FILE = os.path.join(APP_DIR, "data", "places.csv")
FACILITIES_FILE = os.path.join(APP_DIR, "data", "facilities.csv")
ROUTE_GRAPHS_DIR = os.path.join(APP_DIR, "data", "graphs")
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
XMU_ROAD_SNAP_METERS = 0
XMU_XIANG_AN_GENERATED_FACILITIES_FILE = os.path.join(
    APP_DIR,
    "data",
    "generated",
    "facilities_厦门大学翔安校区_厦门_中国.csv",
)
FOOD_TOP_K = 10
FOOD_CAMPUS_CONTEXTS = {
    "xmu_xiang_an": {
        "place_id": "xmu_xiang_an",
        "place_name": "厦门大学翔安校区",
        "graph_place_name": "厦门大学翔安校区",
        "top_k": FOOD_TOP_K,
        "default_sort": "recommend_score_desc",
    }
}
DIARY_UPLOAD_DIR = os.path.join(APP_DIR, "data", "uploads", "diaries")
DIARY_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
DIARY_ALLOWED_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}
DIARY_ALLOWED_MEDIA_EXTS = DIARY_ALLOWED_IMAGE_EXTS | DIARY_ALLOWED_VIDEO_EXTS


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


def initialize_database():
    ensure_parent_dir(DB_PATH)

    if (
        not os.path.exists(DB_PATH)
        and os.path.exists(SEED_DB_PATH)
        and os.path.abspath(DB_PATH) != os.path.abspath(SEED_DB_PATH)
    ):
        shutil.copy2(SEED_DB_PATH, DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
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

    ensure_sqlite_column(cursor, "diaries", "media_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_sqlite_column(cursor, "diaries", "compressed_content", "TEXT NOT NULL DEFAULT ''")
    ensure_sqlite_column(cursor, "diaries", "compression_algorithm", "TEXT NOT NULL DEFAULT 'plain'")
    ensure_sqlite_column(cursor, "diaries", "compression_original_length", "INTEGER NOT NULL DEFAULT 0")
    ensure_sqlite_column(cursor, "diaries", "compression_compressed_length", "INTEGER NOT NULL DEFAULT 0")

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


def create_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_password = generate_password_hash(password)

    try:
        cursor.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed_password)
        )
        conn.commit()
        return True
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


def ensure_diaries_table():
    initialize_database()


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
        saved_items.append({
            "filename": final_name,
            "original_name": original_name,
            "kind": diary_media_kind(final_name),
            "size": os.path.getsize(file_path),
        })

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


def search_diaries_by_title(diaries, title_query, search_mode):
    if not title_query:
        return diaries

    normalized_query = normalize_search_text(title_query)
    exact_index, prefix_index, _term_index, _normalized_cache = build_diary_search_index(diaries)

    if search_mode == "prefix":
        titles = [item[0] for item in prefix_index]
        left = bisect.bisect_left(titles, normalized_query)
        right = bisect.bisect_left(titles, normalized_query + chr(0x10FFFF))
        return [prefix_index[index][2] for index in range(left, right) if titles[index].startswith(normalized_query)]

    if search_mode == "contains":
        return [diary for diary in diaries if normalized_query in normalize_search_text(diary["title"])]

    return list(exact_index.get(normalized_query, []))


def search_diaries_by_keyword(diaries, keyword):
    if not keyword:
        return diaries

    _, _, term_index, normalized_cache = build_diary_search_index(diaries)
    normalized_query = normalize_search_text(keyword)
    query_terms = split_search_terms(keyword)

    scores = defaultdict(int)
    if query_terms:
        for term in query_terms:
            for diary_id in term_index.get(term, set()):
                scores[diary_id] += 1

    if not scores:
        for diary in diaries:
            if normalized_query in normalized_cache[diary["id"]]["combined"]:
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
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    return graph


def collector_sources_are_newer_than_graph():
    if not os.path.exists(XMU_MANUAL_GRAPH_FILE):
        return True
    graph_mtime = os.path.getmtime(XMU_MANUAL_GRAPH_FILE)
    source_files = [
        XMU_COLLECTOR_NODES_FILE,
        XMU_COLLECTOR_EDGES_FILE,
        XMU_COLLECTOR_LINKS_FILE,
        XMU_COLLECTOR_FACILITIES_FILE,
        XMU_COLLECTOR_META_FILE,
    ]
    return any(os.path.exists(file_path) and os.path.getmtime(file_path) > graph_mtime for file_path in source_files)


def nearest_graph_node_id(point, graph, selectable_only=False):
    best = None
    for node in graph.get("nodes", []):
        if selectable_only and not is_selectable_node(node):
            continue
        if "amap_lng" not in node or "amap_lat" not in node:
            continue
        node_point = [float(node["amap_lng"]), float(node["amap_lat"])]
        distance = haversine_amap(point, node_point)
        if not best or distance < best[1]:
            best = (node["id"], distance)
    return best[0] if best else ""


def normalize_collector_facility(payload, existing_count=0, graph=None):
    point = normalize_collector_point(payload)
    facility_type = str(payload.get("type") or payload.get("category") or "服务设施").strip()
    facility_id = str(payload.get("id") or collector_facility_id(existing_count)).strip()
    nearest_node = str(payload.get("nearest_node") or "").strip()
    if graph and nearest_node not in graph.get("node_map", {}):
        nearest_node = nearest_graph_node_id(point, graph)
    return {
        "id": facility_id,
        "name": str(payload.get("name") or f"场所{existing_count + 1}").strip(),
        "type": facility_type,
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
    if not nodes:
        meta["default_start"] = ""
    elif meta.get("default_start") not in node_map or not node_map.get(meta.get("default_start"), {}).get("selectable", False):
        meta["default_start"] = selectable[0]["id"] if selectable else nodes[0]["id"]

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
    write_json_atomic(XMU_MANUAL_GRAPH_FILE, graph)
    write_json_atomic(XMU_COLLECTOR_META_FILE, meta)
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
    places = []

    if not os.path.exists(PLACES_FILE):
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

    return places


def get_place_by_id(place_id):
    places = load_places()
    for place in places:
        if place["id"] == place_id:
            return place
    return None

def get_food_by_key(food_key, place_id=""):
    food_key = str(food_key or "").strip()
    if not food_key:
        return None

    if place_id in FOOD_CAMPUS_CONTEXTS:
        for food in build_food_candidates_for_place(place_id):
            if food.get("food_key") == food_key:
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

    if "自动售货机" in name_text or "售货机" in name_text:
        return "补给"
    if "食堂" in category_text or "食堂" in name_text:
        return "食堂"
    if "咖啡" in category_text or "coffee" in name_text or "咖啡" in name_text:
        return "咖啡"
    if "超市" in category_text or "超市" in name_text:
        return "超市"
    if "窗口" in category_text or "窗口" in name_text:
        return "窗口"
    if "快餐" in category_text or "快餐" in name_text or "肯德基" in name_text or "kfc" in name_text:
        return "快餐"
    if "小吃" in category_text or "小吃" in name_text:
        return "小吃"
    if "餐饮" in category_text or "餐厅" in name_text or "餐饮" in name_text:
        return "餐饮"
    if "面" in category_text and "面" in name_text:
        return "面食"
    if "饮" in category_text or "饮" in name_text or "饮" in description_text:
        return "饮品"
    return str(category or "餐饮").strip() or "餐饮"


def food_default_profile(category, name=""):
    category_text = normalize_search_text(category)
    name_text = normalize_search_text(name)

    profile = {
        "食堂": (4.4, 82, 18),
        "餐饮": (4.3, 76, 28),
        "咖啡": (4.4, 78, 24),
        "超市": (4.0, 64, 15),
        "补给": (3.9, 60, 12),
        "窗口": (4.2, 70, 16),
        "快餐": (4.2, 80, 22),
        "小吃": (4.1, 72, 14),
        "面食": (4.2, 68, 20),
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


def food_search_blob(food):
    tags = food.get("tags_list", [])
    if isinstance(tags, str):
        tags = [tags]
    parts = [
        food.get("name", ""),
        food.get("category", ""),
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

    direct_type_hits = ("食堂", "餐饮", "咖啡", "快餐", "小吃", "餐厅")
    name_hits = ("餐厅", "食堂", "咖啡", "超市", "便利", "窗口", "小吃", "快餐", "面馆", "茶饮", "奶茶", "自动售货机", "售货机", "肯德基", "瑞幸", "蜜雪")

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
    category = normalize_food_category(raw_item.get("type") or raw_item.get("category"), candidate_name, description)
    rating, popularity, avg_cost = food_default_profile(category, candidate_name)
    tags_list = normalize_tags(raw_item.get("tags") or [place_name, category, "校园"])
    nearest_node = str(raw_item.get("nearest_node") or raw_item.get("anchor_node") or "").strip()
    graph_node_id = str(raw_item.get("id") or "").strip()
    source_label = "图节点补位" if source_kind == "graph_node" else "采集补位"

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
    return candidate


def build_food_candidates_for_place(place_id):
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        return []

    context = FOOD_CAMPUS_CONTEXTS[place_id]
    graph = load_route_graph(place_id)
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
        if existing_priority == priority and not existing.get("description") and candidate.get("description"):
            candidate["source_priority"] = priority
            candidate_map[key] = candidate

    for node in graph.get("nodes", []):
        if node.get("kind") != "facility":
            continue
        if not is_food_related_facility(node.get("name", ""), node.get("category", ""), node.get("source", "")):
            continue
        candidate = make_food_candidate(node, place_id, place_name, "graph_node", graph)
        if candidate:
            if not candidate.get("nearest_node"):
                candidate["nearest_node"] = node.get("id", "")
            maybe_store(candidate, 3)

    for facility in load_facilities(place_id):
        if not is_food_related_facility(facility.get("name", ""), facility.get("type", ""), facility.get("description", "")):
            continue
        candidate = make_food_candidate(facility, place_id, place_name, "facility_csv", graph)
        if candidate:
            if not candidate.get("nearest_node") and facility.get("nearest_node"):
                candidate["nearest_node"] = str(facility.get("nearest_node")).strip()
            maybe_store(candidate, 2)

    for row in load_csv_rows(XMU_XIANG_AN_GENERATED_FACILITIES_FILE):
        if not is_food_related_facility(row.get("name", ""), row.get("type", ""), row.get("description", "")):
            continue
        candidate = make_food_candidate(row, place_id, place_name, "generated_facility", graph)
        if candidate:
            maybe_store(candidate, 1)

    return list(candidate_map.values())


def get_food_origin_node(place_id):
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        return ""
    graph = load_route_graph(place_id)
    start = graph.get("default_start", "")
    if start in graph.get("node_map", {}):
        return start
    selectable_nodes = get_selectable_nodes(graph)
    return selectable_nodes[0]["id"] if selectable_nodes else ""


def enrich_food_distance(food, graph, origin_node):
    if not graph or not origin_node:
        food["distance_m"] = None
        food["distance_text"] = ""
        return food

    nearest_node = food.get("nearest_node") or food.get("graph_node_id")
    if nearest_node not in graph.get("node_map", {}):
        food["distance_m"] = None
        food["distance_text"] = "暂未映射"
        return food

    path = dijkstra_shortest_path(graph, origin_node, nearest_node, strategy="distance", transport="walk")
    if path is None:
        food["distance_m"] = None
        food["distance_text"] = "暂未连通"
        return food

    food["distance_m"] = round(path["total"], 1)
    food["distance_text"] = f"{food['distance_m']} 米"
    food["route_path_names"] = path.get("display_path_names", path.get("path_names", []))
    return food


def calculate_food_recommend_score(food, keyword_terms=None):
    keyword_terms = keyword_terms or []
    name_text = normalize_search_text(food.get("name", ""))
    blob = food_search_blob(food)
    matched_terms = sum(1 for term in keyword_terms if term and term in blob)
    keyword_bonus = matched_terms * 12
    if keyword_terms and name_text and any(term in name_text for term in keyword_terms):
        keyword_bonus += 8

    rating_score = float(food.get("rating", 0)) * 18
    popularity_score = float(food.get("popularity", 0)) * 0.35
    cost_score = max(0, 34 - float(food.get("avg_cost", 0)) * 0.6)
    distance = food.get("distance_m")
    distance_score = max(0, 40 - float(distance) / 30) if distance is not None else 0
    source_bonus = 8
    campus_bonus = 10 if food.get("graph_place_id") == "xmu_xiang_an" else 0
    return round(rating_score + popularity_score + cost_score + distance_score + keyword_bonus + source_bonus + campus_bonus, 2)


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
            enrich_food_distance(food_copy, graph, origin_node)
        else:
            food_copy["distance_m"] = food_copy.get("distance_m")
        food_copy["recommend_score"] = calculate_food_recommend_score(food_copy, keyword_terms=keyword_terms)
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

    stats = {
        "scanned_count": scanned_count,
        "candidate_count": candidate_count,
        "returned_count": len(ranked),
        "algorithm": "美食 Top-K（堆）" if limit else "美食排序",
    }
    return ranked, stats


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


def load_route_graph(place_id=None):
    graph_path = get_route_graph_path(place_id or DEFAULT_PLACE_ID)
    if not os.path.exists(graph_path):
        return {"default_start": "", "nodes": [], "edges": [], "node_map": {}, "adjacency": {}}

    with open(graph_path, "r", encoding="utf-8-sig") as f:
        graph = json.load(f)

    graph.setdefault("place_id", place_id or DEFAULT_PLACE_ID)
    graph.setdefault("place_name", "当前路线图")
    graph.setdefault("bounds", [])
    graph.setdefault("campus_bounds", graph.get("bounds", []))
    graph.setdefault("center", [])
    graph.setdefault("amap_center", [])
    graph.setdefault("amap_bounds", [])
    graph.setdefault("facility_parent_place", graph.get("place_id", place_id or DEFAULT_PLACE_ID))
    graph.setdefault("image_overlay", None)

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


def serialize_graph_for_map(graph):
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
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
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


def plan_multi_target_route(graph, start, targets, strategy="distance", transport="walk", return_to_start=False):
    unique_targets = []
    for target in targets:
        if target and target != start and target in graph["node_map"] and target not in unique_targets:
            unique_targets.append(target)

    if not unique_targets:
        return None
    if len(unique_targets) > MAX_ROUTE_TARGETS:
        return {
            "order": tuple(),
            "segments": [],
            "total": 0,
            "returns_to_start": return_to_start,
            "error": f"途经点最多支持 {MAX_ROUTE_TARGETS} 个，请减少目标点后重试。",
        }

    pair_paths = {}
    route_points = [start] + unique_targets
    for from_node in route_points:
        candidate_targets = list(unique_targets)
        if return_to_start and from_node != start:
            candidate_targets.append(start)
        for to_node in candidate_targets:
            if from_node == to_node:
                continue
            path = dijkstra_shortest_path(graph, from_node, to_node, strategy=strategy, transport=transport)
            if path is not None:
                pair_paths[(from_node, to_node)] = path

    best_plan = None
    for order in itertools.permutations(unique_targets):
        current = start
        segments = []
        total = 0
        feasible = True

        for target in order:
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
                "order": order,
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


def load_facilities(parent_place=None):
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

    if not parent_place or parent_place == XMU_MANUAL_PLACE_ID:
        for item in load_collector_facilities():
            facility = normalize_collector_facility(item, len(facilities))
            if parent_place and facility.get("parent_place") != parent_place:
                continue
            facility["tags_text"] = " ".join(facility.get("tags", []))
            facilities.append(facility)

    return facilities


def find_nearby_facilities(graph, start_node, facility_type="", keyword="", max_distance=None):
    result = []
    keyword_lower = keyword.lower()

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

        nearest_node = facility.get("nearest_node")
        if nearest_node not in graph.get("node_map", {}) and facility.get("amap_lng") and facility.get("amap_lat"):
            nearest_node = nearest_graph_node_id([float(facility["amap_lng"]), float(facility["amap_lat"])], graph)
        path = dijkstra_shortest_path(graph, start_node, nearest_node, strategy="distance", transport="walk")
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


def filter_and_sort_places(places, keyword="", tag_keyword="", place_type="", city="", sort_by="default"):
    result = places

    if keyword:
        keyword_lower = keyword.lower()
        result = [
            place for place in result
            if keyword_lower in (
                place.get("name", "")
                + place.get("city", "")
                + place.get("tags", "")
                + place.get("description", "")
            ).lower()
        ]

    if tag_keyword:
        query_tags = [
            item.strip().lower()
            for item in tag_keyword.replace("；", ";").replace("，", ";").replace(",", ";").split(";")
            if item.strip()
        ]
        result = [
            place for place in result
            if all(tag in place.get("tags", "").lower() for tag in query_tags)
        ]

    if place_type:
        result = [
            place for place in result
            if place["type"] == place_type
        ]

    if city:
        result = [
            place for place in result
            if place["city"] == city
        ]

    if sort_by == "rating_desc":
        result = sorted(result, key=lambda x: x["rating"], reverse=True)
    elif sort_by == "rating_asc":
        result = sorted(result, key=lambda x: x["rating"])
    elif sort_by == "popularity_desc":
        result = sorted(result, key=lambda x: x["popularity"], reverse=True)
    elif sort_by == "popularity_asc":
        result = sorted(result, key=lambda x: x["popularity"])
    elif sort_by == "recommend_score_desc":
        result = sorted(result, key=lambda x: x.get("recommend_score", 0), reverse=True)

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


def get_top_k_recommendations(places, preferred_tags=None, k=10, place_type="", city=""):
    if preferred_tags is None:
        preferred_tags = []

    heap = []
    scanned_count = 0
    candidate_count = 0

    for index, place in enumerate(places):
        scanned_count += 1
        if place_type and place.get("type") != place_type:
            continue
        if city and place.get("city") != city:
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
        "algorithm": "小根堆 Top-K",
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
    diary["media_count"] = len(diary["media_items"])
    diary["image_count"] = sum(1 for item in diary["media_items"] if item.get("kind") == "image")
    diary["video_count"] = sum(1 for item in diary["media_items"] if item.get("kind") == "video")
    diary["compression"] = diary_compression_summary(diary)
    return diary


def load_diaries(title_query="", search_mode="exact", keyword="", destination="", sort_by="created_desc"):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diaries")
    diaries = [attach_diary_stats(row) for row in cursor.fetchall()]
    conn.close()

    diaries = search_diaries_by_title(diaries, title_query, search_mode)
    diaries = search_diaries_by_keyword(diaries, keyword)
    diaries = filter_diaries_by_destination(diaries, destination)

    diaries = sort_diaries(diaries, sort_by)

    return diaries


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

        if not username or not password or not confirm_password:
            flash("用户名和密码不能为空")
            return render_template("register.html")

        if password != confirm_password:
            flash("两次输入的密码不一致")
            return render_template("register.html")

        success = create_user(username, password)
        if not success:
            flash("用户名已存在，请更换用户名")
            return render_template("register.html")

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

    return render_template("home.html", username=session["username"])


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("你已退出登录")
    return redirect(url_for("login"))


# =========================
# places 模块：列表查询
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

    return render_template(
        "places.html",
        username=session["username"],
        places=filtered_places,
        total_places=len(all_places),
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        city=city,
        sort_by=sort_by,
        cities=filter_options["cities"],
        place_types=filter_options["place_types"],
    )


# =========================
# places 模块：详情页
# =========================
@app.route("/place/<int:place_id>")
def place_detail(place_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place = get_place_by_id(place_id)
    if place is None:
        flash("未找到该景点/校园信息")
        return redirect(url_for("places"))

    return render_template(
        "place_detail.html",
        username=session["username"],
        place=place
    )


# =========================
# places 模块：推荐页
# =========================
@app.route("/places/recommend", methods=["GET", "POST"])
def recommend_places():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    all_places = load_places()
    filter_options = get_place_filter_options(all_places)
    selected_tags = request.form.getlist("preferred_tags") if request.method == "POST" else request.args.getlist("preferred_tags")
    place_type = request.values.get("type", "").strip()
    city = request.values.get("city", "").strip()
    try:
        k = int(request.values.get("k", "10"))
    except ValueError:
        k = 10
    k = max(1, min(k, 20))

    recommended_places, recommendation_stats = get_top_k_recommendations(
        all_places,
        preferred_tags=selected_tags,
        k=k,
        place_type=place_type,
        city=city
    )

    return render_template(
        "recommend_places.html",
        username=session["username"],
        recommended_places=recommended_places,
        recommendation_stats=recommendation_stats,
        selected_tags=selected_tags,
        all_available_tags=filter_options["tags"],
        cities=filter_options["cities"],
        place_types=filter_options["place_types"],
        place_type=place_type,
        city=city,
        k=k,
    )


@app.route("/route")
def route():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    collect_mode = request.args.get("collect", "").strip() in ("1", "true", "yes", "on")

    if place_id == XMU_MANUAL_PLACE_ID and collector_sources_are_newer_than_graph():
        rebuild_manual_graph()

    graph = load_route_graph(place_id)
    start = request.args.get("start", graph.get("default_start", "")).strip()
    end = request.args.get("end", "").strip()
    strategy = request.args.get("strategy", "distance").strip()
    transport = request.args.get("transport", "walk").strip()
    targets = request.args.getlist("targets")
    route_type = request.args.get("route_type", "single").strip()
    effective_targets = normalize_route_targets(start, end, targets, route_type)
    edit_roads = request.args.get("edit_roads", "").strip() in ("1", "true", "yes", "on")

    result = None
    multi_result = None
    if route_type in ("multi", "round_trip") and start and effective_targets:
        multi_result = plan_multi_target_route(
            graph,
            start,
            effective_targets[:MAX_ROUTE_TARGETS],
            strategy=strategy,
            transport=transport,
            return_to_start=route_type == "round_trip"
        )
    elif start and end:
        result = dijkstra_shortest_path(
            graph,
            start,
            end,
            strategy=strategy,
            transport=transport
        )

    return render_template(
        "route.html",
        username=session["username"],
        place_id=place_id,
        graph=serialize_graph_for_map(graph),
        nodes=get_selectable_nodes(graph),
        facilities=load_facilities(graph.get("facility_parent_place", graph.get("place_id"))),
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
        route_collect_mode=collect_mode
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
        multi_result = plan_multi_target_route(
            graph,
            start,
            effective_targets[:MAX_ROUTE_TARGETS],
            strategy=strategy,
            transport=transport,
            return_to_start=route_type == "round_trip"
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


@app.route("/facilities")
def facilities():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    place_id = request.args.get("place_id", DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    graph = load_route_graph(place_id)
    start_node = request.args.get("start_node", graph.get("default_start", "")).strip()
    facility_type = request.args.get("type", "").strip()
    keyword = request.args.get("keyword", "").strip()
    max_distance_raw = request.args.get("max_distance", "").strip()
    try:
        max_distance = float(max_distance_raw) if max_distance_raw else None
    except ValueError:
        max_distance = None
    all_facilities = load_facilities(graph.get("place_id"))
    facility_types = sorted({facility["type"] for facility in all_facilities})
    facilities_result = find_nearby_facilities(
        graph,
        start_node,
        facility_type=facility_type,
        keyword=keyword,
        max_distance=max_distance
    )

    return render_template(
        "facilities.html",
        username=session["username"],
        place_id=place_id,
        nodes=get_selectable_nodes(graph),
        start_node=start_node,
        facility_type=facility_type,
        keyword=keyword,
        max_distance=max_distance_raw,
        facility_types=facility_types,
        facilities=facilities_result
    )


@app.route("/diaries", methods=["GET", "POST"])
def diaries():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

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

    title_query = request.args.get("title_query", "").strip()
    search_mode = request.args.get("search_mode", "exact").strip()
    keyword = request.args.get("keyword", "").strip()
    destination = request.args.get("destination", "").strip()
    sort_by = request.args.get("sort_by", "created_desc").strip()
    if destination and sort_by == "created_desc":
        sort_by = "hot_rating_desc"
    diaries_list = load_diaries(
        title_query=title_query,
        search_mode=search_mode,
        keyword=keyword,
        destination=destination,
        sort_by=sort_by
    )

    return render_template(
        "diaries.html",
        username=session["username"],
        diaries=diaries_list,
        title_query=title_query,
        search_mode=search_mode,
        keyword=keyword,
        destination=destination,
        sort_by=sort_by,
        compression_preview=None,
        compression_algorithm="huffman",
    )


@app.route("/diary/<int:diary_id>", methods=["GET", "POST"])
def diary_detail(diary_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    if request.method == "POST":
        rating = request.form.get("rating", "5")
        rate_diary(diary_id, rating)
        flash("评分成功")
        return redirect(url_for("diary_detail", diary_id=diary_id))

    diary = get_diary_by_id(diary_id, increase_views=True)
    if diary is None:
        flash("未找到该旅游日记")
        return redirect(url_for("diaries"))

    compression_algorithm = request.args.get(
        "compress_algorithm",
        diary.get("compression", {}).get("algorithm", "huffman")
    ).strip().lower()
    compression_preview = get_diary_compression_preview(diary_id, compression_algorithm)

    return render_template(
        "diary_detail.html",
        username=session["username"],
        diary=diary,
        compression_preview=compression_preview,
        compression_algorithm=compression_algorithm
    )


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

    place_id = request.args.get("place_id", "xmu_xiang_an").strip() or "xmu_xiang_an"
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = "xmu_xiang_an"
    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()
    place_name = request.args.get("place_name", "").strip()
    sort_by = request.args.get("sort_by", "default").strip()

    food_context = FOOD_CAMPUS_CONTEXTS[place_id]
    campus_foods = build_food_candidates_for_place(place_id)
    graph = load_route_graph(place_id)
    origin_node = get_food_origin_node(place_id)
    if not sort_by or sort_by == "default":
        sort_by = food_context.get("default_sort", "recommend_score_desc")
    filtered_foods, food_stats = rank_food_candidates(
        campus_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by,
        limit=food_context.get("top_k", FOOD_TOP_K),
        graph=graph,
        origin_node=origin_node,
    )
    categories = sorted({food["category"] for food in campus_foods if food.get("category")})
    places = sorted({food["place_name"] for food in campus_foods if food.get("place_name")})

    return render_template(
        "foods.html",
        username=session["username"],
        foods=filtered_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by,
        categories=categories,
        places=places,
        place_id=place_id,
        food_context={
            **food_context,
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

    place_id = request.args.get("place_id", "xmu_xiang_an").strip() or "xmu_xiang_an"
    food = get_food_by_key(food_key, place_id=place_id)
    if food is None:
        flash("未找到该美食信息")
        return redirect(url_for("foods", place_id=place_id) if place_id else url_for("foods"))

    return render_template(
        "food_detail.html",
        username=session["username"],
        food=food,
        place_id=place_id,
    )


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug)

