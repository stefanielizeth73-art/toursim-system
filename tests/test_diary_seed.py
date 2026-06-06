import json
import sqlite3

from toursim.diary_seed import seed_demo_diaries


def create_schema(cursor):
    cursor.execute(
        """
        CREATE TABLE diaries (
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
        """
    )
    cursor.execute(
        """
        CREATE TABLE diary_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diary_id INTEGER NOT NULL,
            parent_id INTEGER,
            author TEXT NOT NULL,
            avatar_path TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            like_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE diary_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diary_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            rating INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(diary_id, username)
        )
        """
    )


def test_seed_demo_diaries_imports_when_database_has_fewer_diaries(tmp_path):
    seed_path = tmp_path / "demo_diaries_seed.json"
    seed_path.write_text(
        json.dumps(
            {
                "diaries": [
                    {
                        "id": 1,
                        "title": "真实日记一",
                        "destination": "厦门大学",
                        "content": "海边散步。",
                        "author": "alice",
                        "views": 8,
                        "rating_total": 5.0,
                        "rating_count": 1,
                        "created_at": "2026-06-01 10:00",
                        "media_json": '[{"filename":"cover.jpg","kind":"image"}]',
                        "compressed_content": "",
                        "compression_algorithm": "plain",
                        "compression_original_length": 0,
                        "compression_compressed_length": 0,
                    },
                    {
                        "id": 2,
                        "title": "真实日记二",
                        "destination": "鼓浪屿",
                        "content": "慢慢逛。",
                        "author": "bob",
                        "views": 3,
                        "rating_total": 0,
                        "rating_count": 0,
                        "created_at": "2026-06-02 10:00",
                        "media_json": "[]",
                        "compressed_content": "",
                        "compression_algorithm": "plain",
                        "compression_original_length": 0,
                        "compression_compressed_length": 0,
                    },
                ],
                "diary_comments": [
                    {
                        "id": 1,
                        "diary_id": 1,
                        "parent_id": None,
                        "author": "bob",
                        "avatar_path": "",
                        "content": "好看",
                        "like_count": 2,
                        "created_at": "2026-06-03 10:00",
                    }
                ],
                "diary_ratings": [
                    {
                        "id": 1,
                        "diary_id": 1,
                        "username": "bob",
                        "rating": 5,
                        "created_at": "2026-06-03 11:00",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    create_schema(cursor)
    cursor.execute(
        """
        INSERT INTO diaries
        (id, title, destination, content, author, views, rating_total, rating_count, created_at)
        VALUES (1, '占位日记', '占位', '占位', 'system', 0, 0, 0, '2026-01-01 00:00')
        """
    )

    imported = seed_demo_diaries(cursor, seed_path)

    assert imported == 2
    cursor.execute("SELECT id, title, destination, media_json FROM diaries ORDER BY id")
    rows = cursor.fetchall()
    assert [row["title"] for row in rows] == ["真实日记一", "真实日记二"]
    assert rows[0]["media_json"] == '[{"filename":"cover.jpg","kind":"image"}]'

    cursor.execute("SELECT content, like_count FROM diary_comments WHERE diary_id = 1")
    comment = cursor.fetchone()
    assert dict(comment) == {"content": "好看", "like_count": 2}

    cursor.execute("SELECT username, rating FROM diary_ratings WHERE diary_id = 1")
    rating = cursor.fetchone()
    assert dict(rating) == {"username": "bob", "rating": 5}
