from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import csv
import heapq
import itertools
import json
import os
import shutil
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RUNTIME_DATA_DIR = os.getenv("DATA_DIR", APP_DIR)
DB_NAME = os.getenv("DB_NAME", "tourism.db")
DB_PATH = DB_NAME if os.path.isabs(DB_NAME) else os.path.join(RUNTIME_DATA_DIR, DB_NAME)
SEED_DB_PATH = os.path.join(APP_DIR, "tourism.db")

PLACES_FILE = os.path.join(APP_DIR, "data", "places.csv")
FOODS_FILE = os.path.join(APP_DIR, "data", "foods.csv")
FACILITIES_FILE = os.path.join(APP_DIR, "data", "facilities.csv")
ROUTE_GRAPH_FILE = os.path.join(APP_DIR, "data", "route_graph.json")


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
        created_at TEXT NOT NULL
    )
    """)

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
            (title, destination, content, author, views, rating_total, rating_count, created_at)
            VALUES (?, ?, ?, ?, 0, 0, 0, ?)
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

# =========================
# 美食数据读取函数
# =========================
def load_foods():
    foods = []

    if not os.path.exists(FOODS_FILE):
        return foods

    with open(FOODS_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
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

            try:
                row["avg_cost"] = float(row["avg_cost"])
            except (ValueError, KeyError):
                row["avg_cost"] = 0.0

            row["tags_list"] = [tag.strip() for tag in row.get("tags", "").split(";") if tag.strip()]
            foods.append(row)

    return foods


def get_food_by_id(food_id):
    foods = load_foods()
    for food in foods:
        if food["id"] == food_id:
            return food
    return None


# =========================
# 图结构、设施与路线算法
# =========================
def load_route_graph():
    if not os.path.exists(ROUTE_GRAPH_FILE):
        return {"default_start": "", "nodes": [], "edges": [], "node_map": {}, "adjacency": {}}

    with open(ROUTE_GRAPH_FILE, "r", encoding="utf-8-sig") as f:
        graph = json.load(f)

    node_map = {node["id"]: node for node in graph.get("nodes", [])}
    adjacency = {node_id: [] for node_id in node_map}

    for edge in graph.get("edges", []):
        start = edge["from"]
        end = edge["to"]
        if start not in adjacency or end not in adjacency:
            continue
        adjacency[start].append({**edge, "neighbor": end})
        adjacency[end].append({**edge, "from": end, "to": start, "neighbor": start})

    graph["node_map"] = node_map
    graph["adjacency"] = adjacency
    return graph


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
        "edges": edges,
        "total": distances[end],
    }


def plan_multi_target_route(graph, start, targets, strategy="distance", transport="walk"):
    unique_targets = []
    for target in targets:
        if target and target != start and target in graph["node_map"] and target not in unique_targets:
            unique_targets.append(target)

    if not unique_targets:
        return None

    best_plan = None
    for order in itertools.permutations(unique_targets):
        current = start
        segments = []
        total = 0
        feasible = True

        for target in list(order) + [start]:
            segment = dijkstra_shortest_path(graph, current, target, strategy=strategy, transport=transport)
            if segment is None:
                feasible = False
                break
            segments.append(segment)
            total += segment["total"]
            current = target

        if feasible and (best_plan is None or total < best_plan["total"]):
            best_plan = {"order": order, "segments": segments, "total": total}

    return best_plan


def load_facilities():
    facilities = []
    if not os.path.exists(FACILITIES_FILE):
        return facilities

    with open(FACILITIES_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                row["id"] = int(row["id"])
            except (ValueError, KeyError):
                row["id"] = 0
            facilities.append(row)

    return facilities


def find_nearby_facilities(graph, start_node, facility_type="", keyword=""):
    result = []
    keyword_lower = keyword.lower()

    for facility in load_facilities():
        if facility_type and facility.get("type") != facility_type:
            continue
        if keyword and keyword_lower not in (facility.get("name", "") + facility.get("description", "")).lower():
            continue

        nearest_node = facility.get("nearest_node")
        path = dijkstra_shortest_path(graph, start_node, nearest_node, strategy="distance", transport="walk")
        if path is None:
            continue

        item = facility.copy()
        item["distance"] = round(path["total"], 1)
        item["path_names"] = " -> ".join(path["path_names"])
        result.append(item)

    return sorted(result, key=lambda item: item["distance"])


def filter_and_sort_foods(foods, keyword="", category="", place_name="", sort_by="default"):
    result = foods

    if keyword:
        keyword_lower = keyword.lower()
        result = [
            food for food in result
            if keyword_lower in food["name"].lower()
        ]

    if category:
        result = [
            food for food in result
            if food["category"] == category
        ]

    if place_name:
        place_name_lower = place_name.lower()
        result = [
            food for food in result
            if place_name_lower in food["place_name"].lower()
        ]

    if sort_by == "rating_desc":
        result = sorted(result, key=lambda x: x["rating"], reverse=True)
    elif sort_by == "rating_asc":
        result = sorted(result, key=lambda x: x["rating"])
    elif sort_by == "popularity_desc":
        result = sorted(result, key=lambda x: x["popularity"], reverse=True)
    elif sort_by == "popularity_asc":
        result = sorted(result, key=lambda x: x["popularity"])
    elif sort_by == "avg_cost_desc":
        result = sorted(result, key=lambda x: x["avg_cost"], reverse=True)
    elif sort_by == "avg_cost_asc":
        result = sorted(result, key=lambda x: x["avg_cost"])

    return result

def filter_and_sort_places(places, keyword="", tag_keyword="", place_type="", sort_by="default"):
    result = places

    if keyword:
        keyword_lower = keyword.lower()
        result = [
            place for place in result
            if keyword_lower in place["name"].lower()
        ]

    if tag_keyword:
        tag_keyword_lower = tag_keyword.lower()
        result = [
            place for place in result
            if tag_keyword_lower in place.get("tags", "").lower()
        ]

    if place_type:
        result = [
            place for place in result
            if place["type"] == place_type
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


def get_top_k_recommendations(places, preferred_tags=None, k=10):
    result = []

    if preferred_tags is None:
        preferred_tags = []

    for place in places:
        place_copy = place.copy()
        place_copy["recommend_score"] = calculate_personalized_score(place_copy, preferred_tags)
        result.append(place_copy)

    result = sorted(result, key=lambda x: x["recommend_score"], reverse=True)
    return result[:k]


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
    return diary


def load_diaries(keyword="", destination="", sort_by="created_desc"):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM diaries")
    diaries = [attach_diary_stats(row) for row in cursor.fetchall()]
    conn.close()

    if keyword:
        keyword_lower = keyword.lower()
        diaries = [
            diary for diary in diaries
            if keyword_lower in (diary["title"] + diary["destination"] + diary["content"]).lower()
        ]

    if destination:
        destination_lower = destination.lower()
        diaries = [
            diary for diary in diaries
            if destination_lower in diary["destination"].lower()
        ]

    if sort_by == "views_desc":
        diaries = sorted(diaries, key=lambda x: x["views"], reverse=True)
    elif sort_by == "rating_desc":
        diaries = sorted(diaries, key=lambda x: x["avg_rating"], reverse=True)
    elif sort_by == "title_asc":
        diaries = sorted(diaries, key=lambda x: x["title"])
    else:
        diaries = sorted(diaries, key=lambda x: x["created_at"], reverse=True)

    return diaries


def create_diary(title, destination, content, author):
    ensure_diaries_table()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO diaries
        (title, destination, content, author, views, rating_total, rating_count, created_at)
        VALUES (?, ?, ?, ?, 0, 0, 0, ?)
        """,
        (title, destination, content, author, datetime.now().strftime("%Y-%m-%d %H:%M"))
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
    sort_by = request.args.get("sort_by", "default").strip()

    all_places = load_places()
    filtered_places = filter_and_sort_places(
        all_places,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        sort_by=sort_by
    )

    return render_template(
        "places.html",
        username=session["username"],
        places=filtered_places,
        keyword=keyword,
        tag_keyword=tag_keyword,
        place_type=place_type,
        sort_by=sort_by
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
    selected_tags = []

    if request.method == "POST":
        selected_tags = request.form.getlist("preferred_tags")

    recommended_places = get_top_k_recommendations(
        all_places,
        preferred_tags=selected_tags,
        k=10
    )

    all_available_tags = sorted({
        tag
        for place in all_places
        for tag in place["tags_list"]
    })

    return render_template(
        "recommend_places.html",
        username=session["username"],
        recommended_places=recommended_places,
        selected_tags=selected_tags,
        all_available_tags=all_available_tags
    )


@app.route("/route")
def route():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    graph = load_route_graph()
    start = request.args.get("start", graph.get("default_start", "")).strip()
    end = request.args.get("end", "").strip()
    strategy = request.args.get("strategy", "distance").strip()
    transport = request.args.get("transport", "walk").strip()
    targets = request.args.getlist("targets")
    route_type = request.args.get("route_type", "single").strip()

    result = None
    multi_result = None
    if route_type == "multi" and start and targets:
        multi_result = plan_multi_target_route(
            graph,
            start,
            targets[:5],
            strategy=strategy,
            transport=transport
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
        nodes=graph["nodes"],
        start=start,
        end=end,
        targets=targets,
        strategy=strategy,
        transport=transport,
        route_type=route_type,
        result=result,
        multi_result=multi_result
    )


@app.route("/facilities")
def facilities():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    graph = load_route_graph()
    start_node = request.args.get("start_node", graph.get("default_start", "")).strip()
    facility_type = request.args.get("type", "").strip()
    keyword = request.args.get("keyword", "").strip()
    all_facilities = load_facilities()
    facility_types = sorted({facility["type"] for facility in all_facilities})
    facilities_result = find_nearby_facilities(
        graph,
        start_node,
        facility_type=facility_type,
        keyword=keyword
    )

    return render_template(
        "facilities.html",
        username=session["username"],
        nodes=graph["nodes"],
        start_node=start_node,
        facility_type=facility_type,
        keyword=keyword,
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
        if not title or not destination or not content:
            flash("标题、目的地和正文不能为空")
        else:
            create_diary(title, destination, content, session["username"])
            flash("日记发布成功")
            return redirect(url_for("diaries"))

    keyword = request.args.get("keyword", "").strip()
    destination = request.args.get("destination", "").strip()
    sort_by = request.args.get("sort_by", "created_desc").strip()
    diaries_list = load_diaries(keyword=keyword, destination=destination, sort_by=sort_by)

    return render_template(
        "diaries.html",
        username=session["username"],
        diaries=diaries_list,
        keyword=keyword,
        destination=destination,
        sort_by=sort_by
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

    return render_template(
        "diary_detail.html",
        username=session["username"],
        diary=diary
    )


@app.route("/foods")
def foods():
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    keyword = request.args.get("keyword", "").strip()
    category = request.args.get("category", "").strip()
    place_name = request.args.get("place_name", "").strip()
    sort_by = request.args.get("sort_by", "default").strip()

    all_foods = load_foods()
    filtered_foods = filter_and_sort_foods(
        all_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by
    )

    categories = sorted({food["category"] for food in all_foods})
    places = sorted({food["place_name"] for food in all_foods})

    return render_template(
        "foods.html",
        username=session["username"],
        foods=filtered_foods,
        keyword=keyword,
        category=category,
        place_name=place_name,
        sort_by=sort_by,
        categories=categories,
        places=places
    )


@app.route("/food/<int:food_id>")
def food_detail(food_id):
    if not is_logged_in():
        flash("请先登录")
        return redirect(url_for("login"))

    food = get_food_by_id(food_id)
    if food is None:
        flash("未找到该美食信息")
        return redirect(url_for("foods"))

    return render_template(
        "food_detail.html",
        username=session["username"],
        food=food
    )


if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))
    debug = os.getenv("FLASK_DEBUG", "1").lower() in ("1", "true", "yes", "on")
    app.run(host=host, port=port, debug=debug)
