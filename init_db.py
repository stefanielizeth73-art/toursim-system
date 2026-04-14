import os
import shutil
import sqlite3
from datetime import datetime

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DATA_DIR = os.getenv("DATA_DIR", APP_DIR)
DB_NAME = os.getenv("DB_NAME", "tourism.db")
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(RUNTIME_DATA_DIR, DB_NAME)
SEED_DB_PATH = os.path.join(APP_DIR, "tourism.db")


def ensure_parent_dir(file_path):
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def init_db():
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
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("SELECT COUNT(*) FROM diaries")
    if cursor.fetchone()[0] == 0:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        samples = [
            ("校园半日游", "北京邮电大学沙河校区", "从南门进入，先到中心广场，再经过图书馆和观景湖，最后在第一食堂休息。路线较短，适合首次参观校园。", "system"),
            ("故宫历史路线记录", "故宫", "适合喜欢历史文化的同学，建议提前规划路线并避开高峰时段，重点关注建筑轴线和展馆介绍。", "system"),
            ("西湖休闲游记", "西湖", "西湖适合按照湖边景点分段游览，下午可以结合美食推荐安排休息点。", "system"),
        ]
        cursor.executemany(
            """
            INSERT INTO diaries
            (title, destination, content, author, views, rating_total, rating_count, created_at)
            VALUES (?, ?, ?, ?, 0, 0, 0, ?)
            """,
            [(title, destination, content, author, now) for title, destination, content, author in samples]
        )

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    init_db()
