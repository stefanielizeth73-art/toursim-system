import base64
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from .diary_media import (
    diary_generated_video_folder,
    diary_generated_video_public_url,
    diary_media_kind,
    resolve_diary_media_path,
)

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


@dataclass
class DiaryVideoConfig:
    model: str
    default_duration: int = 5
    default_resolution: str = "720P"


@dataclass
class DiaryVideoServices:
    stored_diary_media_items: object


_config = DiaryVideoConfig(os.getenv("DASHSCOPE_VIDEO_MODEL", "wan2.7-i2v-2026-04-25"))
_services = None


def configure_diary_video(config, services=None):
    global _config, _services
    _config = config
    _services = services


def stored_diary_media_items(*args, **kwargs):
    if _services is None:
        raise RuntimeError("Diary video services have not been configured")
    return _services.stored_diary_media_items(*args, **kwargs)


class _VideoConstantProxy:
    def __init__(self, attr_name):
        self.attr_name = attr_name

    def _value(self):
        value = getattr(_config, self.attr_name)
        return value() if callable(value) else value

    def __str__(self):
        return str(self._value())

    def __int__(self):
        return int(self._value())


DIARY_VIDEO_MODEL = _VideoConstantProxy("model")
DIARY_VIDEO_DEFAULT_DURATION = _VideoConstantProxy("default_duration")
DIARY_VIDEO_DEFAULT_RESOLUTION = _VideoConstantProxy("default_resolution")

def get_dashscope_api_key():
    return (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("BAILIAN_API_KEY")
        or os.getenv("ALIBABA_CLOUD_BAILIAN_API_KEY")
        or ""
    ).strip()

def dashscope_base_url():
    return os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")

def normalize_diary_video_duration(value):
    try:
        duration = int(value)
    except (TypeError, ValueError):
        duration = DIARY_VIDEO_DEFAULT_DURATION
    return max(2, min(15, duration))

def normalize_diary_video_resolution(value):
    resolution = str(value or DIARY_VIDEO_DEFAULT_RESOLUTION).upper().strip()
    return resolution if resolution in {"720P", "1080P"} else DIARY_VIDEO_DEFAULT_RESOLUTION

def normalize_diary_video_status(value):
    status = str(value or "PENDING").upper().strip()
    return status if status in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"} else "PENDING"

def select_diary_video_image(diary, requested_filename=""):
    media_items = diary.get("media_items") or stored_diary_media_items(diary)
    image_items = [item for item in media_items if item.get("kind") == "image" and item.get("filename")]
    if not image_items:
        raise ValueError("至少一张图片才能生成视频")

    requested_basename = os.path.basename(requested_filename or "")
    if requested_basename:
        for item in image_items:
            if item.get("filename") == requested_basename:
                return item
        raise ValueError("选择的图片不存在")
    return image_items[0]

def diary_image_data_url(diary_id, filename):
    _media_folder, image_path = resolve_diary_media_path(diary_id, filename)
    if not image_path or not os.path.exists(image_path):
        raise ValueError("图片文件不存在，无法生成视频")
    if diary_media_kind(filename) != "image":
        raise ValueError("请选择图片作为视频首帧")

    if Image is not None and ImageOps is not None:
        try:
            with Image.open(image_path) as image:
                image = ImageOps.exif_transpose(image)
                if image.width < 240 or image.height < 240:
                    raise ValueError("图片宽高至少需要 240px")
                image = image.convert("RGB")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=88, optimize=True, progressive=True)
            return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("utf-8")
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("图片无法读取，请更换图片后重试") from exc

    mime_type = mimetypes.guess_type(filename)[0] or "image/jpeg"
    with open(image_path, "rb") as image_file:
        encoded = base64.b64encode(image_file.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"

def build_diary_video_prompt(diary):
    title = str(diary.get("title") or "").strip()
    destination = str(diary.get("destination") or "").strip()
    content = re.sub(r"\s+", " ", str(diary.get("content") or "")).strip()
    content = content[:360]
    prompt = (
        f"根据这篇旅行日记生成一段安静、真实、有校园漫步感的短视频。"
        f"地点：{destination}。标题：{title}。日记内容：{content}。"
        "镜头从首帧自然延展，缓慢推进，保留真实光线和空间层次，不要夸张特效，不要出现文字水印。"
    )
    return prompt[:900]

def build_bailian_video_payload(diary, image_data_url_value, prompt, duration, resolution):
    return {
        "model": str(DIARY_VIDEO_MODEL),
        "input": {
            "prompt": (prompt or build_diary_video_prompt(diary))[:5000],
            "media": [
                {
                    "type": "first_frame",
                    "url": image_data_url_value,
                }
            ],
        },
        "parameters": {
            "resolution": resolution,
            "duration": duration,
            "prompt_extend": True,
            "watermark": False,
        },
    }

def dashscope_json_request(method, path, payload=None, timeout=45):
    api_key = get_dashscope_api_key()
    if not api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY")

    url = dashscope_base_url() + "/" + path.lstrip("/")
    data = None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["X-DashScope-Async"] = "enable"

    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_raw = exc.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(error_raw)
            message = error_payload.get("message") or error_payload.get("code") or error_raw
        except json.JSONDecodeError:
            message = error_raw or str(exc)
        raise RuntimeError(f"百炼 API 请求失败：{message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"百炼 API 无法连接：{exc.reason}") from exc

    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError("百炼 API 返回了无法解析的数据") from exc

def submit_bailian_image_to_video_task(request_payload):
    response_payload = dashscope_json_request(
        "POST",
        "/services/aigc/video-generation/video-synthesis",
        payload=request_payload,
        timeout=60,
    )
    output = response_payload.get("output") or {}
    task_id = output.get("task_id") or response_payload.get("task_id") or ""
    if not task_id:
        message = response_payload.get("message") or output.get("message") or "未返回 task_id"
        raise RuntimeError(f"百炼任务创建失败：{message}")
    return {
        "task_id": task_id,
        "status": normalize_diary_video_status(output.get("task_status")),
        "raw_response": response_payload,
    }

def poll_bailian_video_task(task_id):
    response_payload = dashscope_json_request("GET", f"/tasks/{task_id}", timeout=30)
    output = response_payload.get("output") or {}
    status = normalize_diary_video_status(output.get("task_status"))
    return {
        "task_id": output.get("task_id") or task_id,
        "status": status,
        "video_url": output.get("video_url") or response_payload.get("video_url") or "",
        "error_message": output.get("message") or response_payload.get("message") or "",
        "raw_response": response_payload,
    }

def download_diary_generated_video(diary_id, task_id, video_url):
    if not video_url:
        raise RuntimeError("百炼任务未返回视频地址")

    video_folder = diary_generated_video_folder(diary_id)
    os.makedirs(video_folder, exist_ok=True)
    safe_task = re.sub(r"[^A-Za-z0-9_-]+", "-", task_id or str(uuid.uuid4())).strip("-")[:80]
    if not safe_task:
        safe_task = hashlib.sha1(video_url.encode("utf-8")).hexdigest()[:16]
    filename = f"{safe_task}.mp4"
    file_path = os.path.join(video_folder, filename)

    req = urllib.request.Request(video_url, headers={"User-Agent": "TourSim/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as response, open(file_path, "wb") as output_file:
            shutil.copyfileobj(response, output_file)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"下载生成视频失败：{exc.reason}") from exc

    if not os.path.exists(file_path) or os.path.getsize(file_path) <= 0:
        raise RuntimeError("生成视频下载为空")
    return filename

def serialize_diary_video_task(row):
    if row is None:
        return None
    task = dict(row)
    task["status"] = normalize_diary_video_status(task.get("status"))
    task["local_video_url"] = ""
    if task.get("local_video_filename"):
        task["local_video_url"] = diary_generated_video_public_url(task["diary_id"], task["local_video_filename"])
    return task
