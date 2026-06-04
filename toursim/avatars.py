import hashlib
import os
import re
from datetime import datetime

from markupsafe import escape
from werkzeug.utils import secure_filename


PRESET_AVATAR_DIR = "images/avatars"
PRESET_AVATAR_OPTIONS = tuple(
    {
        "id": f"chrome-avatar-{index:02d}",
        "path": f"{PRESET_AVATAR_DIR}/chrome-avatar-{index:02d}.svg",
        "label": f"棰勮澶村儚 {index:02d}",
    }
    for index in range(1, 21)
)
PRESET_AVATAR_PATHS = {option["path"] for option in PRESET_AVATAR_OPTIONS}
LEGACY_GENERATED_AVATAR_RE = re.compile(r"^uploads/avatars/(?!user_)[^/]+_\w+\.svg$")


def avatar_relative_path(filename, app_dir, user_avatar_dir):
    return os.path.relpath(os.path.join(user_avatar_dir, filename), os.path.join(app_dir, "static")).replace("\\", "/")


def get_preset_avatar_options():
    return [dict(option) for option in PRESET_AVATAR_OPTIONS]


def is_preset_avatar_path(avatar_path):
    return (avatar_path or "").replace("\\", "/") in PRESET_AVATAR_PATHS


def default_preset_avatar_path(username="", user_id=None):
    seed = f"{username}:{user_id if user_id is not None else ''}"
    digest = hashlib.sha1((seed or "avatar").encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(PRESET_AVATAR_OPTIONS)
    return PRESET_AVATAR_OPTIONS[index]["path"]


def is_legacy_generated_avatar_path(avatar_path):
    normalized = (avatar_path or "").replace("\\", "/")
    return bool(LEGACY_GENERATED_AVATAR_RE.match(normalized))


def select_preset_avatar_path(selected_avatar_path, username="", user_id=None):
    normalized = (selected_avatar_path or "").replace("\\", "/").strip()
    if is_preset_avatar_path(normalized):
        return normalized
    return default_preset_avatar_path(username, user_id)


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
    label = escape((username or "User").strip()[:2] or "鐢ㄦ埛")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256" role="img" aria-label="{label} 鐨勫ご鍍?>
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


def ensure_user_avatar_asset(username, user_id=None, avatar_path="", app_dir=None):
    if avatar_path:
        normalized_avatar_path = avatar_path.replace("\\", "/")
        if is_preset_avatar_path(normalized_avatar_path):
            return normalized_avatar_path
        if app_dir:
            candidate_path = os.path.join(app_dir, "static", avatar_path)
            if os.path.exists(candidate_path) and not is_legacy_generated_avatar_path(normalized_avatar_path):
                return normalized_avatar_path

    return default_preset_avatar_path(username, user_id)


def save_uploaded_user_avatar(uploaded_file, username, user_id, app_dir, user_avatar_dir, allowed_avatar_exts):
    if not uploaded_file or not uploaded_file.filename:
        return ensure_user_avatar_asset(username, user_id, app_dir=app_dir)

    original_name = secure_filename(uploaded_file.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in allowed_avatar_exts:
        return ensure_user_avatar_asset(username, user_id, app_dir=app_dir)

    os.makedirs(user_avatar_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"user_{user_id}_{timestamp}{ext or '.svg'}"
    file_path = os.path.join(user_avatar_dir, filename)
    uploaded_file.save(file_path)
    return avatar_relative_path(filename, app_dir, user_avatar_dir)
