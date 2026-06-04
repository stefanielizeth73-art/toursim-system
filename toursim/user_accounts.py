import sqlite3
from dataclasses import dataclass

from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class UserAccountServices:
    get_db_connection: object
    invalidate_diary_index_cache: object
    avatar_url_from_path: object


_services = None


def configure_user_accounts(services):
    global _services
    _services = services


def _require_services():
    if _services is None:
        raise RuntimeError("User account services have not been configured")
    return _services


def get_db_connection():
    return _require_services().get_db_connection()


def invalidate_diary_index_cache():
    return _require_services().invalidate_diary_index_cache()


def avatar_url_from_path(*args, **kwargs):
    return _require_services().avatar_url_from_path(*args, **kwargs)

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
            cursor.execute("UPDATE diary_ratings SET username = ? WHERE username = ?", (new_username, old_username))
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

def diary_comment_avatar_url(comment):
    avatar_path = ""
    if isinstance(comment, dict):
        avatar_path = comment.get("resolved_avatar_path") or comment.get("avatar_path", "")
    author = comment.get("author", "") if isinstance(comment, dict) else ""
    return avatar_url_from_path(avatar_path, author, comment.get("author_user_id") if isinstance(comment, dict) else None)
