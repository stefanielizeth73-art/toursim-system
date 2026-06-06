import base64
import hashlib
import io
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import quote

from flask import has_request_context, url_for
from werkzeug.utils import secure_filename

from .compression import parse_diary_package

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


@dataclass
class DiaryMediaConfig:
    upload_dir: str
    generated_video_dir: str
    thumbnail_dirname: str = "_thumbs_v4"
    thumbnail_version: str = "4"
    thumbnail_max_size: tuple = (720, 900)
    thumbnail_jpeg_quality: int = 82
    allowed_image_exts: set = None
    allowed_video_exts: set = None


@dataclass
class DiaryMediaServices:
    get_db_connection: object
    invalidate_diary_index_cache: object


_config = DiaryMediaConfig("", "")
_services = None


def configure_diary_media(config, services=None):
    global _config, _services
    _config = config
    _services = services


def _image_exts():
    value = _config.allowed_image_exts
    value = value() if callable(value) else value
    return value or {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _video_exts():
    value = _config.allowed_video_exts
    value = value() if callable(value) else value
    return value or {".mp4", ".webm", ".mov", ".avi", ".mkv"}


class _DiaryConstantProxy:
    def __init__(self, attr_name):
        self.attr_name = attr_name

    def _value(self):
        value = (_image_exts() | _video_exts()) if self.attr_name == "allowed_media_exts" else getattr(_config, self.attr_name)
        return value() if callable(value) else value

    def __fspath__(self):
        return os.fspath(self._value())

    def __str__(self):
        return str(self._value())

    def __iter__(self):
        return iter(self._value())

    def __contains__(self, item):
        return item in self._value()


DIARY_UPLOAD_DIR = _DiaryConstantProxy("upload_dir")
DIARY_GENERATED_VIDEO_DIR = _DiaryConstantProxy("generated_video_dir")
DIARY_THUMBNAIL_DIRNAME = _DiaryConstantProxy("thumbnail_dirname")
DIARY_THUMBNAIL_VERSION = _DiaryConstantProxy("thumbnail_version")
DIARY_THUMBNAIL_MAX_SIZE = _DiaryConstantProxy("thumbnail_max_size")
DIARY_THUMBNAIL_JPEG_QUALITY = _DiaryConstantProxy("thumbnail_jpeg_quality")
DIARY_ALLOWED_IMAGE_EXTS = _DiaryConstantProxy("allowed_image_exts")
DIARY_ALLOWED_VIDEO_EXTS = _DiaryConstantProxy("allowed_video_exts")
DIARY_ALLOWED_MEDIA_EXTS = _DiaryConstantProxy("allowed_media_exts")


def get_db_connection():
    if _services is None:
        raise RuntimeError("Diary media services have not been configured")
    return _services.get_db_connection()


def invalidate_diary_index_cache():
    if _services is not None and _services.invalidate_diary_index_cache:
        return _services.invalidate_diary_index_cache()
    return None

def diary_media_folder(diary_id):
    return os.path.join(DIARY_UPLOAD_DIR, str(diary_id))

def diary_media_thumbnail_folder(diary_id):
    return os.path.join(diary_media_folder(diary_id), DIARY_THUMBNAIL_DIRNAME)

def diary_media_public_url(diary_id, filename):
    return url_for("diary_media_file", diary_id=diary_id, filename=filename)

def diary_media_thumbnail_public_url(diary_id, filename):
    return url_for("diary_media_thumbnail_file", diary_id=diary_id, filename=filename, v=DIARY_THUMBNAIL_VERSION)

def diary_generated_video_folder(diary_id):
    return os.path.join(DIARY_GENERATED_VIDEO_DIR, str(diary_id))

def diary_generated_video_public_url(diary_id, filename):
    if not has_request_context():
        return f"/diary-generated-video/{diary_id}/{quote(os.path.basename(filename or ''))}"
    return url_for("diary_generated_video_file", diary_id=diary_id, filename=filename)

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

def resolve_diary_media_path(diary_id, filename):
    media_folder = os.path.abspath(diary_media_folder(diary_id))
    safe_filename = os.path.basename(filename or "")
    if not safe_filename:
        return None, None
    file_path = os.path.abspath(os.path.join(media_folder, safe_filename))
    if os.path.dirname(file_path) != media_folder:
        return None, None
    return media_folder, file_path

def resolve_diary_generated_video_path(diary_id, filename):
    video_folder = os.path.abspath(diary_generated_video_folder(diary_id))
    safe_filename = os.path.basename(filename or "")
    if not safe_filename:
        return None, None
    file_path = os.path.abspath(os.path.join(video_folder, safe_filename))
    if os.path.dirname(file_path) != video_folder:
        return None, None
    return video_folder, file_path

def diary_thumbnail_filename(source_path):
    stat = os.stat(source_path)
    source_name = os.path.basename(source_path)
    digest = hashlib.sha1(f"{source_name}:{stat.st_size}".encode("utf-8")).hexdigest()[:16]
    stem = os.path.splitext(secure_filename(source_name) or "media")[0]
    return f"{stem}-{digest}.jpg"

def ensure_diary_image_thumbnail(diary_id, filename):
    if Image is None or ImageOps is None or diary_media_kind(filename) != "image":
        return None

    _media_folder, source_path = resolve_diary_media_path(diary_id, filename)
    if not source_path or not os.path.exists(source_path):
        return None

    thumb_folder = diary_media_thumbnail_folder(diary_id)
    os.makedirs(thumb_folder, exist_ok=True)
    thumb_path = os.path.join(thumb_folder, diary_thumbnail_filename(source_path))
    if os.path.exists(thumb_path):
        return thumb_path

    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            max_size = tuple(DIARY_THUMBNAIL_MAX_SIZE)
            jpeg_quality = int(str(DIARY_THUMBNAIL_JPEG_QUALITY))
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            image.save(thumb_path, "JPEG", quality=jpeg_quality, optimize=True, progressive=True)
    except Exception:
        return None
    return thumb_path

def generate_image_blur_base64(diary_id, filename):
    if Image is None or ImageOps is None:
        return ""
    _media_folder, source_path = resolve_diary_media_path(diary_id, filename)
    if not source_path or not os.path.exists(source_path):
        return ""
    try:
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.thumbnail((16, 16))
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=20)
            return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception:
        return ""

def prewarm_all_diary_thumbnails():
    import time
    time.sleep(2.5)  # 延迟启动，避免阻塞 Flask 初始化
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, media_json FROM diaries")
        rows = cursor.fetchall()
        conn.close()
    except Exception:
        return

    for row in rows:
        diary_id = row["id"]
        media_items = parse_diary_package(row["media_json"]) or []
        updated = False
        new_items = []
        for item in media_items:
            new_item = dict(item)
            if new_item.get("kind") == "image":
                filename = new_item.get("filename")
                if filename:
                    try:
                        # 确保物理缩略图已存在
                        ensure_diary_image_thumbnail(diary_id, filename)
                        # 补齐极微内联占位 Base64
                        if not new_item.get("blur_base64"):
                            new_item["blur_base64"] = generate_image_blur_base64(diary_id, filename)
                            updated = True
                    except Exception:
                        pass
            new_items.append(new_item)

        if updated:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE diaries SET media_json = ? WHERE id = ?",
                    (json.dumps(new_items, ensure_ascii=False), diary_id)
                )
                conn.commit()
                conn.close()
                invalidate_diary_index_cache()  # 刷新缓存
            except Exception:
                pass
