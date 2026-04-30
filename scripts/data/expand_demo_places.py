"""
Expand data/places.csv to a course-design-sized demo dataset.

Default behavior:
- keep every existing row exactly as it is
- append generated rows until the target size is reached

Rebuild behavior:
- keep only the first KEEP_EXISTING_ROWS rows from the current file
- regenerate the remaining rows from deterministic templates
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PLACES_FILE = ROOT_DIR / "data" / "places.csv"
TARGET_SIZE = 280
KEEP_EXISTING_ROWS = 15
TARGET_CAMPUS_SIZE = 140
TARGET_SCENIC_SIZE = TARGET_SIZE - TARGET_CAMPUS_SIZE

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "苏州", "成都", "重庆", "武汉",
    "西安", "天津", "青岛", "厦门", "长沙", "郑州", "济南", "合肥", "福州", "南昌",
    "昆明", "贵阳", "南宁", "海口", "三亚", "哈尔滨", "长春", "沈阳", "大连", "呼和浩特",
    "太原", "石家庄", "兰州", "银川", "西宁", "乌鲁木齐", "拉萨", "宁波", "温州", "无锡",
]

CAMPUS_THEMES = [
    ("理工大学创新校区", "校园;科技;现代", "以理工学科和创新实验空间为特色，适合科技主题参观。"),
    ("师范大学人文校区", "校园;人文;学术", "拥有浓厚的人文氛围和开放式校园空间，适合文化体验。"),
    ("交通大学智慧校区", "校园;工程;智慧", "校园道路规整，教学楼和实验中心分布清晰，适合路线规划演示。"),
    ("医科大学生命科学园", "校园;医学;学习", "以医学教学和生命科学展示为特色，适合研学游览。"),
    ("财经大学书香校区", "校园;财经;书香", "图书馆和教学区集中，适合学习型校园参观。"),
    ("艺术学院创意园区", "校园;艺术;创意", "具有展馆、工作室和公共艺术空间，适合艺术主题游览。"),
]

SCENIC_THEMES = [
    ("历史文化街区", "历史;文化;街区", "保留传统街巷和地方文化风貌，适合城市历史主题游览。"),
    ("滨水生态公园", "自然风光;湖泊;休闲", "拥有水岸步道和生态景观，适合休闲观光与摄影。"),
    ("古城遗址公园", "历史遗址;古城;教育", "结合遗址展示和城市记忆，兼具教育与观赏价值。"),
    ("山水风景区", "山水;自然风光;热门", "以山体、水系和观景步道为特色，适合自然风光游览。"),
    ("博物馆文化园", "博物馆;文化;展览", "集中展示地方历史和专题展览，适合文化研学。"),
    ("夜游商业街", "夜景;美食;热门", "夜间人流和餐饮资源丰富，适合美食与城市夜景体验。"),
    ("森林休闲公园", "森林;公园;亲子", "绿地覆盖较高，适合亲子游和慢行游览。"),
]

FIELDNAMES = ["id", "name", "type", "city", "rating", "popularity", "tags", "description"]


def read_existing_rows(places_file: Path) -> list[dict[str, str]]:
    with places_file.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized = []
    for row in rows:
        normalized.append({
            "id": row.get("id", ""),
            "name": row.get("name", "").strip(),
            "type": row.get("type", "").strip(),
            "city": row.get("city", "").strip(),
            "rating": row.get("rating", "").strip(),
            "popularity": row.get("popularity", "").strip(),
            "tags": row.get("tags", "").strip(),
            "description": row.get("description", "").strip(),
        })
    return normalized


def score_for(index: int, base: float = 4.2) -> tuple[str, str]:
    rating = round(base + (index % 8) * 0.08 + ((index // 7) % 3) * 0.03, 1)
    rating = min(rating, 4.9)
    popularity = 72 + (index * 7) % 29
    return f"{rating:.1f}", str(popularity)


def build_rows(
    start_id: int,
    existing_names: set[str],
    target_count: int,
    place_type: str,
    themes: list[tuple[str, str, str]],
    base_rating: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    next_id = start_id

    while len(rows) < target_count:
        round_index = len(rows) // (len(CITIES) * len(themes))
        for suffix, tags, detail in themes:
            for city in CITIES:
                extra = "" if round_index == 0 else f"{round_index + 1}期"
                name = f"{city}{suffix}{extra}"
                if name in existing_names:
                    continue

                rating, popularity = score_for(next_id, base=base_rating)
                rows.append({
                    "id": str(next_id),
                    "name": name,
                    "type": place_type,
                    "city": city,
                    "rating": rating,
                    "popularity": popularity,
                    "tags": tags,
                    "description": f"{name}位于{city}，{detail}",
                })
                existing_names.add(name)
                next_id += 1
                if len(rows) >= target_count:
                    return rows

    return rows


def build_generated_rows(start_id: int, existing_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_names = {row["name"] for row in existing_rows if row["name"]}
    campus_existing_count = sum(1 for row in existing_rows if row["type"] == "校园")
    scenic_existing_count = sum(1 for row in existing_rows if row["type"] == "景区")

    campus_needed = max(0, TARGET_CAMPUS_SIZE - campus_existing_count)
    scenic_needed = max(0, TARGET_SCENIC_SIZE - scenic_existing_count)

    campus_rows = build_rows(
        start_id=start_id,
        existing_names=existing_names,
        target_count=campus_needed,
        place_type="校园",
        themes=CAMPUS_THEMES,
        base_rating=4.25,
    )
    scenic_rows = build_rows(
        start_id=start_id + len(campus_rows),
        existing_names=existing_names,
        target_count=scenic_needed,
        place_type="景区",
        themes=SCENIC_THEMES,
        base_rating=4.15,
    )
    return campus_rows + scenic_rows


def write_rows(places_file: Path, rows: list[dict[str, str]]) -> None:
    for index, row in enumerate(rows, start=1):
        row["id"] = str(index)

    with places_file.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand places.csv without overwriting manual edits by default.")
    parser.add_argument("--target-size", type=int, default=TARGET_SIZE)
    parser.add_argument("--rebuild", action="store_true", help="Discard generated rows and rebuild from the first seed rows.")
    parser.add_argument("--file", type=Path, default=DEFAULT_PLACES_FILE, help="Target CSV file to expand.")
    args = parser.parse_args()

    existing_rows = normalize_rows(read_existing_rows(args.file))

    if args.rebuild:
        base_rows = existing_rows[:KEEP_EXISTING_ROWS]
    else:
        base_rows = existing_rows

    if len(base_rows) >= args.target_size:
        final_rows = base_rows
    else:
        generated_rows = build_generated_rows(len(base_rows) + 1, base_rows)
        final_rows = (base_rows + generated_rows)[:args.target_size]

    write_rows(args.file, final_rows)

    mode = "rebuild" if args.rebuild else "append-only"
    print(f"written {len(final_rows)} rows to {args.file} ({mode} mode)")


if __name__ == "__main__":
    main()
