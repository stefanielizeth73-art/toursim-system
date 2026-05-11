import base64
import csv
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import DIARY_UPLOAD_DIR, compress_diary_text, initialize_database, invalidate_diary_index_cache  # noqa: E402


PLACE_NAMES = [
    "北京大学", "清华大学", "厦门大学", "武汉大学", "南京大学", "浙江大学", "复旦大学", "上海交通大学", "中山大学", "四川大学",
    "西湖", "故宫", "鼓浪屿", "黄山", "张家界国家森林公园", "九寨沟", "丽江古城", "秦始皇帝陵博物院", "苏州园林", "上海外滩",
    "厦门大学翔安校区", "北京邮电大学沙河校区", "华南理工大学", "重庆大学", "南开大学", "同济大学", "哈尔滨工业大学", "中国科学技术大学", "山东大学", "兰州大学",
    "泰山", "庐山", "峨眉山", "都江堰", "颐和园", "天坛", "长城", "南京夫子庙", "成都宽窄巷子", "杭州灵隐寺",
    "香港大学", "澳门大学", "云南大学", "郑州大学", "湖南大学", "东南大学", "天津大学", "吉林大学", "大连理工大学", "华中科技大学",
]

AUTHORS = ["林鹿", "南乔", "阿岚", "星河", "纪远", "小满", "沈知行", "叶清", "陆微", "苏禾"]
STYLES = ["轻松散步", "历史观察", "摄影路线", "美食补给", "亲子慢游", "雨天备用", "高效打卡", "深度体验", "夜景记录", "学习参访"]
KEYWORDS = ["湖边", "建筑", "人文", "路线", "食堂", "博物馆", "山路", "夜景", "书店", "交通", "拍照", "清晨", "黄昏", "展馆", "校园"]
WEATHER = ["晴朗", "多云", "小雨", "微风", "傍晚转凉", "阳光很足"]
TITLE_PREFIXES = ["清晨", "午后", "黄昏", "周末", "雨后", "夜游", "慢行", "研学", "摄影", "避峰"]


def load_places():
    places = {}
    with (ROOT / "data" / "places.csv").open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, skipinitialspace=True)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            places[name] = {
                "name": name,
                "type": (row.get("type") or "").strip(),
                "city": (row.get("city") or "").strip(),
                "tags": [tag.strip() for tag in (row.get("tags") or "").split(";") if tag.strip()],
            }
    return places


def clear_uploads(upload_root):
    expected_upload_root = (ROOT / "data" / "uploads" / "diaries").resolve()
    upload_root = upload_root.resolve()
    if upload_root != expected_upload_root or ROOT.resolve() not in upload_root.parents:
        raise RuntimeError(f"Refuse to clear unexpected upload path: {upload_root}")
    upload_root.mkdir(parents=True, exist_ok=True)
    for child in upload_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def build_seed_rows():
    places = load_places()
    upload_root = Path(DIARY_UPLOAD_DIR).resolve()
    png_bytes = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    rows = []
    base_time = datetime(2026, 5, 1, 8, 20)

    for index, place_name in enumerate(PLACE_NAMES, start=1):
        place = places.get(place_name, {"name": place_name, "type": "景区", "city": "目的地", "tags": ["旅行", "记录", "风景"]})
        tags = place["tags"] or ["旅行", "记录", "风景"]
        tag_text = "、".join(tags[:3])
        style = STYLES[(index - 1) % len(STYLES)]
        author = AUTHORS[(index - 1) % len(AUTHORS)]
        city = place.get("city") or "目的地"
        keyword_one = KEYWORDS[(index * 2) % len(KEYWORDS)]
        keyword_two = KEYWORDS[(index * 2 + 5) % len(KEYWORDS)]
        weather = WEATHER[index % len(WEATHER)]
        title = f"{TITLE_PREFIXES[(index - 1) % len(TITLE_PREFIXES)]}{place_name}旅行日记{index:02d}"
        content = (
            f"今天按{style}的节奏游览{place_name}，地点在{city}，天气{weather}。"
            f"出发前我把路线拆成入口、核心景点、休息点和返程四段，方便后续和推荐模块联动测试。"
            f"这里最明显的印象是{tag_text}，沿途能看到{keyword_one}和{keyword_two}相关的细节。"
            f"如果时间有限，建议先看评分较高的主景点，再根据热度避开人流；如果想深度游，可以把周边餐饮、设施和交通一起查询。"
            f"本篇日记特意保留了目的地名称、类别关键词、个人兴趣词和完整描述，用来测试标题精确查询、前缀查询、全文检索、目的地排序、热度评分排序以及无损压缩。"
            f"我的个人感受是{place_name}适合喜欢{tag_text}的同学，下一次会补充更多照片和短视频素材。"
        )
        algorithm = "huffman" if index % 3 else "dictionary"
        package, original_length, compressed_length = compress_diary_text(content, algorithm)
        views = (index * 37) % 240 + (80 if index % 7 == 0 else 0)
        rating_count = (index * 5) % 19 + 1
        avg_rating = [3.6, 3.8, 4.0, 4.2, 4.4, 4.6, 4.8][index % 7]
        rating_total = round(avg_rating * rating_count, 1)
        created_at = (base_time + timedelta(hours=index * 7, minutes=index * 3)).strftime("%Y-%m-%d %H:%M")

        media_items = []
        if index % 4 == 0 or index % 9 == 0:
            media_folder = upload_root / str(index)
            media_folder.mkdir(parents=True, exist_ok=True)
            filename = f"seed_{index:02d}_cover.png"
            (media_folder / filename).write_bytes(png_bytes)
            media_items.append({
                "filename": filename,
                "original_name": f"{place_name}_测试图片.png",
                "kind": "image",
                "size": len(png_bytes),
            })
        if index % 10 == 0:
            media_folder = upload_root / str(index)
            media_folder.mkdir(parents=True, exist_ok=True)
            filename = f"seed_{index:02d}_extra.png"
            (media_folder / filename).write_bytes(png_bytes)
            media_items.append({
                "filename": filename,
                "original_name": f"{place_name}_补充图片.png",
                "kind": "image",
                "size": len(png_bytes),
            })

        rows.append((
            index,
            title,
            place_name,
            content,
            author,
            views,
            rating_total,
            rating_count,
            created_at,
            json.dumps(media_items, ensure_ascii=False),
            json.dumps(package, ensure_ascii=False),
            package["algorithm"],
            original_length,
            compressed_length,
        ))
    return rows


def main():
    initialize_database()
    upload_root = Path(DIARY_UPLOAD_DIR)
    clear_uploads(upload_root)
    rows = build_seed_rows()

    conn = sqlite3.connect(ROOT / "tourism.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM diaries")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name = 'diaries'")
    cursor.executemany(
        """
        INSERT INTO diaries
        (id, title, destination, content, author, views, rating_total, rating_count, created_at,
         media_json, compressed_content, compression_algorithm, compression_original_length,
         compression_compressed_length)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM diaries").fetchone()[0]
    compression = cursor.execute(
        "SELECT compression_algorithm, COUNT(*) FROM diaries GROUP BY compression_algorithm ORDER BY compression_algorithm"
    ).fetchall()
    media_count = cursor.execute("SELECT COUNT(*) FROM diaries WHERE media_json <> '[]'").fetchone()[0]
    first_last = cursor.execute("SELECT MIN(id), MAX(id), MIN(created_at), MAX(created_at) FROM diaries").fetchone()
    conn.close()
    invalidate_diary_index_cache()
    print({
        "count": count,
        "compression": compression,
        "diaries_with_media": media_count,
        "range": first_last,
    })


if __name__ == "__main__":
    main()
