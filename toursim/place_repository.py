import csv
import os
from dataclasses import dataclass
from datetime import datetime

from werkzeug.utils import secure_filename

from .filesystem import file_signature

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


@dataclass
class PlaceRepositoryConfig:
    app_dir: object
    db_path: object
    places_file: object
    place_media_dir: object
    allowed_image_exts: object
    places_cache: dict
    place_image_cache: dict


@dataclass
class PlaceRepositoryServices:
    get_db_connection: object


_config = PlaceRepositoryConfig(
    app_dir="",
    db_path="",
    places_file="",
    place_media_dir="",
    allowed_image_exts=set(),
    places_cache={},
    place_image_cache={},
)
_services = None


def configure_place_repository(config, services):
    global _config, _services
    _config = config
    _services = services


def _require_services():
    if _services is None:
        raise RuntimeError("place repository services have not been configured")
    return _services


def _value(name):
    raw_value = getattr(_config, name)
    return raw_value() if callable(raw_value) else raw_value


def get_db_connection():
    return _require_services().get_db_connection()


def load_place_image_map():
    db_path = _value("db_path")
    image_cache = _value("place_image_cache")
    signature = file_signature(db_path)
    cached = image_cache.get("signature")
    if signature == cached:
        return image_cache.get("records", {})

    image_map = {}
    if not os.path.exists(db_path):
        image_cache["signature"] = signature
        image_cache["records"] = image_map
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

    image_cache["signature"] = signature
    image_cache["records"] = image_map
    return image_map


def place_media_relative_path(place_id):
    return "/".join(["place_media", f"{int(place_id):03d}.jpg"])


def save_uploaded_place_cover(uploaded_file, place):
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("Please select an image file")
    if Image is None or ImageOps is None:
        raise ValueError("Pillow is required to process uploaded images")

    original_name = secure_filename(uploaded_file.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext and ext not in _value("allowed_image_exts"):
        raise ValueError("Unsupported image file format")

    try:
        uploaded_file.stream.seek(0)
    except Exception:
        pass

    try:
        image = Image.open(uploaded_file.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("涓婁紶鍥剧墖瑙ｆ瀽澶辫触锛岃閲嶆柊閫夋嫨鏂囦欢") from exc

    original_width, original_height = image.size
    cover = ImageOps.fit(
        image,
        (1920, 1080),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.42),
    )

    place_media_dir = _value("place_media_dir")
    os.makedirs(place_media_dir, exist_ok=True)
    filename = f"{int(place['id']):03d}.jpg"
    file_path = os.path.join(place_media_dir, filename)
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


def load_places():
    places_file = _value("places_file")
    places_cache = _value("places_cache")
    signature = file_signature(places_file)
    if signature == places_cache.get("signature"):
        return places_cache["records"]

    places = []
    if not os.path.exists(places_file):
        places_cache["signature"] = signature
        places_cache["records"] = places
        return places

    with open(places_file, "r", encoding="utf-8-sig") as f:
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

    app_dir = _value("app_dir")
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
            static_cover = place_media_relative_path(row["id"])
            static_cover_path = os.path.join(app_dir, "static", *static_cover.split("/"))
            row["cover_image"] = static_cover if os.path.exists(static_cover_path) else ""
            row["cover_image_source"] = ""
            row["cover_image_title"] = "鏈湴鏅偣鍥剧墖" if row["cover_image"] else ""
            row["cover_image_source_url"] = ""
            row["cover_image_width"] = 1920 if row["cover_image"] else 0
            row["cover_image_height"] = 1080 if row["cover_image"] else 0

    places_cache["signature"] = signature
    places_cache["records"] = places
    return places


def get_place_by_id(place_id):
    places = load_places()
    for place in places:
        if place["id"] == place_id:
            return place
    return None
