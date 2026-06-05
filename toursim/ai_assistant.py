import itertools
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime

from .food_catalog import FOOD_DEFAULT_PLACE_ID, rank_food_candidates
from .indoor import INDOOR_DEFAULT_END, INDOOR_DEFAULT_START, INDOOR_VERTICAL_MODES
from .route_algorithms import dijkstra_shortest_path
from .search import normalize_search_text


AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-v4-pro")
AI_REASONING_MODEL = os.getenv("AI_REASONING_MODEL", AI_MODEL)
AI_ASSISTANT_ENABLED = os.getenv("AI_ASSISTANT_ENABLED", "1")
AI_CHAT_HISTORY_LIMIT = 12
DEEPSEEK_BASE_URL = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
DEFAULT_PLACE_ID = "xmu_manual"


@dataclass
class AIAssistantServices:
    app_context: object
    test_request_context: object
    build_url_with_query: object
    build_food_candidates_for_place: object
    build_indoor_graph: object
    get_db_connection: object
    load_diaries: object
    load_places: object
    load_route_graph: object
    url_for: object
    food_campus_contexts: dict
    indoor_route_steps: object
    indoor_shortest_path: object


_services = None


def configure_ai_assistant(services):
    global _services
    _services = services


def _require_services():
    if _services is None:
        raise RuntimeError("AI assistant services have not been configured")
    return _services


class _AppProxy:
    def app_context(self):
        return _require_services().app_context()

    def test_request_context(self):
        return _require_services().test_request_context()


class _ContextProxy:
    def __init__(self, attr_name):
        self.attr_name = attr_name

    def get(self, key, default=None):
        return (getattr(_require_services(), self.attr_name) or {}).get(key, default)

    def __contains__(self, key):
        return key in (getattr(_require_services(), self.attr_name) or {})

    def __getitem__(self, key):
        return (getattr(_require_services(), self.attr_name) or {})[key]


app = _AppProxy()
FOOD_CAMPUS_CONTEXTS = _ContextProxy("food_campus_contexts")


def url_for(endpoint, **values):
    return _require_services().url_for(endpoint, **values)


def build_url_with_query(endpoint, params, anchor=None):
    return _require_services().build_url_with_query(endpoint, params, anchor)


def build_food_candidates_for_place(*args, **kwargs):
    return _require_services().build_food_candidates_for_place(*args, **kwargs)


def build_indoor_graph(*args, **kwargs):
    return _require_services().build_indoor_graph(*args, **kwargs)


def get_db_connection(*args, **kwargs):
    return _require_services().get_db_connection(*args, **kwargs)


def load_diaries(*args, **kwargs):
    return _require_services().load_diaries(*args, **kwargs)


def load_places(*args, **kwargs):
    return _require_services().load_places(*args, **kwargs)


def load_route_graph(*args, **kwargs):
    return _require_services().load_route_graph(*args, **kwargs)


def indoor_route_steps(*args, **kwargs):
    return _require_services().indoor_route_steps(*args, **kwargs)


def indoor_shortest_path(*args, **kwargs):
    return _require_services().indoor_shortest_path(*args, **kwargs)

def ai_env_flag(name, default="0"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

def ai_assistant_config():
    provider = os.getenv("AI_PROVIDER", AI_PROVIDER).strip().lower() or "deepseek"
    default_model = "deepseek-v4-pro" if provider == "deepseek" else AI_MODEL
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() if provider == "deepseek" else os.getenv("OPENAI_API_KEY", "").strip()
    return {
        "enabled": ai_env_flag("AI_ASSISTANT_ENABLED", AI_ASSISTANT_ENABLED),
        "provider": provider,
        "model": os.getenv("AI_MODEL", default_model).strip() or default_model,
        "reasoning_model": os.getenv("AI_REASONING_MODEL", AI_REASONING_MODEL).strip() or AI_REASONING_MODEL,
        "api_key": api_key,
        "base_url": os.getenv("AI_BASE_URL", DEEPSEEK_BASE_URL).strip() or DEEPSEEK_BASE_URL,
        "thinking": os.getenv("AI_THINKING", "disabled").strip().lower() or "disabled",
        "reasoning_effort": os.getenv("AI_REASONING_EFFORT", "low").strip().lower() or "low",
        "router_mode": os.getenv("AI_ROUTER_MODE", "fast").strip().lower() or "fast",
    }

def ai_safe_text(value, limit=300):
    text = str(value or "").strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text

def ai_parse_budget(text):
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB|yuan|预算)", text or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None

def ai_food_intent_from_text(text):
    raw_text = str(text or "").strip()
    compact = normalize_search_text(raw_text)
    is_followup = any(word in raw_text for word in ("没有吗", "还有吗", "换一个", "再来", "别的", "更多"))
    food_words = ("吃", "饭", "饿", "美食", "食堂", "餐厅", "清淡", "夜宵", "奶茶", "咖啡", "预算", "便宜", "近一点")
    is_food = is_followup or any(word in raw_text for word in food_words)

    category = ""
    if any(word in raw_text for word in ("食堂", "饭堂", "餐厅", "吃饭")):
        category = "食堂"
    elif any(word in raw_text for word in ("咖啡", "拿铁", "美式")):
        category = "咖啡饮品"
    elif any(word in raw_text for word in ("超市", "便利", "零食", "饮料")):
        category = "超市便利"
    elif any(word in raw_text for word in ("西餐", "汉堡", "披萨")):
        category = "西餐"

    preference_notes = []
    if "清淡" in raw_text:
        preference_notes.append("清淡一点")
    if any(word in raw_text for word in ("便宜", "预算", "实惠", "不贵")):
        preference_notes.append("价格友好")
    if any(word in raw_text for word in ("近", "附近", "就近")):
        preference_notes.append("尽量近一点")
    if any(word in raw_text for word in ("快", "赶时间", "马上")):
        preference_notes.append("出餐快一点")

    # Only keep a keyword when it looks like a concrete shop/dish name. Full
    # sentences such as "我好饿，想吃清淡的" should not become hard search terms.
    keyword = raw_text
    generic_terms = ("我", "想", "现在", "好饿", "有点", "东西", "推荐", "帮我", "吃点", "吃饭", "清淡", "预算", "附近")
    if len(compact) > 12 or any(term in raw_text for term in generic_terms):
        keyword = ""
    if is_followup:
        keyword = ""
        category = ""

    return {
        "is_food": is_food,
        "is_followup": is_followup,
        "keyword": keyword,
        "category": category,
        "budget": ai_parse_budget(raw_text),
        "preference_notes": preference_notes,
    }

def ai_human_food_summary(result, original_text="", intent=None):
    cards = result.get("cards", [])
    intent = intent or {}
    notes = intent.get("preference_notes") or []
    relaxed = result.get("relaxed", False)
    if cards:
        if relaxed:
            opener = "有的。我刚才把条件放宽了一点，先挑几个更稳妥的校园选择给你。"
        elif notes:
            opener = "懂，你现在更像是想要" + "、".join(notes) + "的选择。"
        else:
            opener = "可以，我先按校园里比较稳的选择帮你筛了一轮。"
        names = [card.get("title", "") for card in cards[:3] if card.get("title")]
        if names:
            return f"{opener} 我翻了美食列表，先看这几个：{'、'.join(names)}。想少走路的话，可以点卡片进详情或直接打开美食推荐。"
        return f"{opener} 我翻了美食列表，下面这些可以先看。"
    if notes:
        return "我按你的偏好查了一轮，但条件太窄没有直接命中。我建议先放宽到食堂和餐厅范围，再按距离或评分挑。"
    return "我查了一轮，暂时没有直接命中的结果。你可以告诉我预算、当前位置，或者想吃食堂/咖啡/超市，我再帮你缩小范围。"

def ai_normalize_limit(value, default=5, max_limit=8):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        limit = default
    return max(1, min(limit, max_limit))

def ai_url_for(endpoint, **values):
    try:
        return url_for(endpoint, **values)
    except RuntimeError:
        with app.test_request_context():
            return url_for(endpoint, **values)

def ai_build_url(endpoint, params=None, anchor=None):
    try:
        return build_url_with_query(endpoint, params or {}, anchor=anchor)
    except RuntimeError:
        with app.test_request_context():
            return build_url_with_query(endpoint, params or {}, anchor=anchor)

def ai_action(kind, label, url, command=None):
    action = {
        "kind": kind,
        "label": label,
        "url": url,
    }
    if command:
        action["command"] = command
    return action

def ai_food_card(food, place_id, origin_node=""):
    url_args = {"place_id": place_id}
    if origin_node:
        url_args["origin_node"] = origin_node
    return {
        "type": "food",
        "title": food.get("name", "校园美食"),
        "subtitle": food.get("cuisine") or food.get("category") or food.get("source_label", ""),
        "description": ai_safe_text(food.get("display_description") or food.get("recommendation_note"), 140),
        "meta": {
            "rating": food.get("rating"),
            "avg_cost": food.get("avg_cost"),
            "distance_text": food.get("distance_text", ""),
            "score": food.get("recommend_score"),
        },
        "image": food.get("cover_image", ""),
        "url": ai_url_for("food_detail", food_key=food.get("food_key", ""), **url_args),
    }

def ai_tool_recommend_foods(arguments=None):
    args = arguments or {}
    place_id = str(args.get("place_id") or FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    if place_id not in FOOD_CAMPUS_CONTEXTS:
        place_id = FOOD_DEFAULT_PLACE_ID
    raw_keyword = str(args.get("keyword") or "").strip()
    intent = args.get("intent") if isinstance(args.get("intent"), dict) else ai_food_intent_from_text(raw_keyword)
    keyword_value = args.get("keyword_override") if args.get("keyword_override") is not None else intent.get("keyword", raw_keyword)
    keyword = str(keyword_value or "").strip()
    category = str(args.get("category") or intent.get("category") or "").strip()
    budget = args.get("budget")
    if budget in ("", None):
        budget = intent.get("budget")
    try:
        budget = float(budget) if budget not in ("", None) else None
    except (TypeError, ValueError):
        budget = None
    origin_node = str(args.get("origin_node") or "").strip()
    limit = ai_normalize_limit(args.get("limit"), default=5, max_limit=8)

    food_context = FOOD_CAMPUS_CONTEXTS[place_id]
    graph = load_route_graph(food_context.get("graph_place_id", place_id))
    if origin_node not in graph.get("node_map", {}):
        origin_node = ""
    foods = build_food_candidates_for_place(place_id)
    sort_by = "distance_asc" if origin_node else food_context.get("default_sort", "recommend_score_desc")

    def rank_with(active_keyword, active_category, active_budget):
        ranked_items, active_stats = rank_food_candidates(
            foods,
            keyword=active_keyword,
            category=active_category,
            sort_by=sort_by,
            graph=graph,
            origin_node=origin_node,
        )
        if active_budget is not None:
            budgeted = [food for food in ranked_items if float(food.get("avg_cost") or 0) <= active_budget]
            if budgeted:
                ranked_items = budgeted
        return ranked_items, active_stats

    ranked, stats = rank_with(keyword, category, budget)
    relaxed = False
    if not ranked and (keyword or category):
        relaxed = True
        ranked, stats = rank_with("", category, budget)
    if not ranked and budget is not None:
        relaxed = True
        ranked, stats = rank_with("", category, None)
    if not ranked:
        relaxed = True
        ranked, stats = rank_with("", "", None)

    cards = [ai_food_card(food, place_id, origin_node=origin_node) for food in ranked[:limit]]
    query = {
        "place_id": place_id,
        "keyword": keyword,
        "category": category,
        "sort_by": sort_by,
        "origin_node": origin_node,
    }
    result = {
        "type": "food_recommendations",
        "summary": "",
        "cards": cards,
        "actions": [
            ai_action(
                "apply_food_filter",
                "按条件筛选美食",
                ai_build_url("foods", query),
                {"type": "food_filter", "params": query},
            ),
        ],
        "stats": stats,
        "intent": intent,
        "relaxed": relaxed or bool(intent.get("is_followup")),
    }
    result["summary"] = ai_human_food_summary(result, raw_keyword, intent)
    return result

def ai_resolve_node_id(graph, raw_value):
    value = str(raw_value or "").strip()
    if not value:
        return ""
    node_map = graph.get("node_map", {})
    if value in node_map:
        return value
    normalized = normalize_search_text(value)
    for node in graph.get("nodes", []):
        node_name = str(node.get("name", ""))
        if normalized and normalized in normalize_search_text(node_name):
            return str(node.get("id", ""))
    return ""

def ai_route_card(result, graph, strategy="distance"):
    if not result or result.get("error"):
        return None
    unit = "米" if strategy == "distance" else "秒"
    return {
        "type": "route",
        "title": "路线规划结果",
        "subtitle": f"{float(result.get('total') or 0):.1f} {unit}",
        "description": " -> ".join(result.get("display_path_names") or result.get("path") or []),
        "meta": {
            "path": result.get("path", []),
            "total": result.get("total"),
            "place_id": graph.get("place_id", DEFAULT_PLACE_ID),
        },
        "url": ai_build_url(
            "route",
            {
                "place_id": graph.get("place_id", DEFAULT_PLACE_ID),
                "start": (result.get("path") or [""])[0],
                "end": (result.get("path") or [""])[-1],
                "strategy": strategy,
                "transport": result.get("transport") or "mixed",
            },
        ),
    }

def ai_extract_route_endpoints(text, graph):
    raw_text = str(text or "").strip()
    if not raw_text:
        return {}
    matches = ai_find_route_node_mentions(raw_text, graph)
    if len(matches) >= 2:
        return {"start": matches[0]["id"], "end": matches[1]["id"]}
    return {}

def ai_find_route_node_mentions(text, graph):
    raw_text = str(text or "").strip()
    if not raw_text:
        return []
    nodes = sorted(graph.get("nodes", []), key=lambda item: len(str(item.get("name", ""))), reverse=True)
    matches = []
    normalized_text = normalize_search_text(raw_text)
    occupied_ranges = []
    for node in nodes:
        node_id = str(node.get("id", ""))
        name = str(node.get("name", "")).strip()
        if not node_id or not name:
            continue
        index = raw_text.find(name)
        if index < 0:
            normalized_name = normalize_search_text(name)
            index = normalized_text.find(normalized_name) if normalized_name else -1
        if index >= 0:
            end_index = index + len(name)
            if any(index >= start and index < end for start, end in occupied_ranges):
                continue
            occupied_ranges.append((index, end_index))
            matches.append({"id": node_id, "name": name, "index": index})
    matches.sort(key=lambda item: item["index"])
    return matches

def ai_route_arguments_from_text(text, graph):
    extracted = ai_extract_route_endpoints(text, graph)
    if extracted.get("start") and extracted.get("end"):
        return {
            "start": extracted["start"],
            "end": extracted["end"],
            "transport": "mixed",
            "strategy": "distance",
        }
    return {}

def ai_route_node_name_from_id(graph, node_id):
    node = (graph.get("node_map") or {}).get(node_id)
    if node:
        return str(node.get("name") or node_id)
    return str(node_id or "")

def ai_tool_plan_route(arguments=None):
    args = arguments or {}
    place_id = str(args.get("place_id") or DEFAULT_PLACE_ID).strip() or DEFAULT_PLACE_ID
    graph = load_route_graph(place_id)
    strategy = str(args.get("strategy") or "distance").strip() or "distance"
    transport = str(args.get("transport") or "mixed").strip() or "mixed"
    extracted = ai_extract_route_endpoints(args.get("keyword") or args.get("message") or "", graph)
    start = ai_resolve_node_id(graph, args.get("start") or extracted.get("start") or graph.get("default_start", ""))
    end = ai_resolve_node_id(graph, args.get("end") or extracted.get("end"))
    if not start or not end:
        return {
            "type": "route_plan",
            "summary": "还需要明确起点和终点。",
            "cards": [],
            "actions": [ai_action("open_route", "打开路线规划", ai_url_for("route", place_id=place_id))],
        }
    result = dijkstra_shortest_path(graph, start, end, strategy=strategy, transport=transport)
    if result and not result.get("error"):
        result["transport"] = transport
    card = ai_route_card(result, graph, strategy=strategy)
    route_url = ai_url_for("route", place_id=place_id, start=start, end=end, strategy=strategy, transport=transport)
    return {
        "type": "route_plan",
        "summary": "已按当前图数据计算路线。" if card else "没有找到可达路线。",
        "cards": [card] if card else [],
        "actions": [
            ai_action(
                "apply_route_plan",
                "自动规划并高亮路线",
                route_url,
                {
                    "type": "route_plan",
                    "params": {
                        "place_id": place_id,
                        "start": start,
                        "end": end,
                        "strategy": strategy,
                        "transport": transport,
                        "route_type": "single",
                    },
                },
            )
        ],
    }

def ai_tool_plan_indoor(arguments=None):
    args = arguments or {}
    building_id = str(args.get("building_id") or "demo_building").strip() or "demo_building"
    graph = build_indoor_graph(building_id)
    start = str(args.get("start") or INDOOR_DEFAULT_START).strip() or INDOOR_DEFAULT_START
    end = str(args.get("end") or INDOOR_DEFAULT_END).strip() or INDOOR_DEFAULT_END
    vertical_mode = str(args.get("vertical_mode") or "auto").strip().lower()
    if start not in graph["node_map"]:
        start = INDOOR_DEFAULT_START
    if end not in graph["node_map"]:
        end = INDOOR_DEFAULT_END
    if vertical_mode not in INDOOR_VERTICAL_MODES:
        vertical_mode = "auto"
    result = indoor_shortest_path(graph, start, end, vertical_mode=vertical_mode)
    steps = indoor_route_steps(result, graph)
    return {
        "type": "indoor_route",
        "summary": "已生成室内导航步骤。" if result and not result.get("error") else "没有找到室内路线。",
        "cards": [{
            "type": "indoor",
            "title": "室内导航",
            "subtitle": f"{start} -> {end}",
            "description": "；".join(step.get("text", "") for step in steps[:6]),
            "meta": {"steps": steps, "vertical_mode": vertical_mode},
            "url": ai_url_for("indoor", building_id=building_id, start=start, end=end, vertical_mode=vertical_mode),
        }],
        "actions": [ai_action("open_indoor", "查看室内导航", ai_url_for("indoor", building_id=building_id, start=start, end=end, vertical_mode=vertical_mode))],
    }

def ai_tool_search_diaries(arguments=None):
    args = arguments or {}
    keyword = str(args.get("keyword") or args.get("query") or "").strip()
    limit = ai_normalize_limit(args.get("limit"), default=4, max_limit=6)
    diaries = load_diaries(keyword=keyword, sort_by="rating_desc") if keyword else load_diaries(sort_by="rating_desc")
    cards = []
    for diary in diaries[:limit]:
        cards.append({
            "type": "diary",
            "title": diary.get("title", "旅行日记"),
            "subtitle": diary.get("destination", ""),
            "description": ai_safe_text(diary.get("content", ""), 120),
            "meta": {"views": diary.get("views"), "avg_rating": diary.get("avg_rating")},
            "url": ai_url_for("diary_detail", diary_id=diary.get("id")),
        })
    return {
        "type": "diary_search",
        "summary": f"找到 {len(cards)} 篇可参考的日记。",
        "cards": cards,
        "actions": [
            ai_action(
                "apply_diary_search",
                "按关键词搜索日记",
                ai_build_url("diary_search", {"keyword": keyword, "sort_by": "hot_rating_desc"}),
                {"type": "diary_search", "params": {"keyword": keyword, "sort_by": "hot_rating_desc"}},
            )
        ],
    }

def ai_detect_system_module(text):
    raw_text = str(text or "").strip()
    module_keywords = {
        "food": (
            "校园美食", "美食推荐", "食堂", "饭堂", "餐厅", "附近吃饭", "附近美食",
            "校内吃饭", "查美食", "推荐吃饭", "预算", "少走路吃", "吃完顺路",
        ),
        "indoor": (
            "室内导航", "室内路线", "电梯", "楼梯", "教室", "教学楼", "从大门",
            "只坐电梯", "不走楼梯",
        ),
        "route": (
            "路线规划", "规划路线", "怎么走", "导航", "路径", "三点一线",
            "少走路逛", "半日游", "顺路去哪", "走完再",
        ),
        "diary": (
            "游记", "日记", "攻略", "参考别人", "热门日记", "拍照感", "按游记",
        ),
    }
    for module_name, keywords in module_keywords.items():
        if any(keyword in raw_text for keyword in keywords):
            return module_name
    return "general"

def ai_generic_local_answer(text):
    raw_text = str(text or "").strip()
    if any(word in raw_text for word in ("你好", "嗨", "hello", "Hello", "hi", "Hi")):
        return "你好呀，我在。想闲聊、问问题、整理想法都可以；如果你聊到校园美食、路线规划、室内导航或游记攻略，我再顺手翻 TourSim 里的资料。"
    if "清淡" in raw_text:
        return "听起来你现在想要清淡一点的选择。我可以先像普通助手一样帮你想口味和搭配；如果你想让我查 TourSim 里的校园美食数据，可以直接说“帮我查校园美食推荐，想吃清淡点”。"
    if any(word in raw_text for word in ("饿", "吃", "饭")):
        return "饿了先别硬扛。你可以告诉我想吃清淡、热乎、便宜还是近一点；要查 TourSim 里的推荐，直接说“校园美食”或“食堂”就行。"
    return "我在，可以直接聊。普通问题我直接回答；如果你聊到校园美食、路线规划、室内导航或游记攻略，我会去翻 TourSim 里的资料。"

def ai_json_from_text(text):
    raw_text = str(text or "").strip()
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        pass
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw_text[start:end + 1])
    except json.JSONDecodeError:
        return None

def ai_recent_chat_messages(user_id, conversation_id="", limit=AI_CHAT_HISTORY_LIMIT):
    if not user_id:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    if conversation_id:
        cursor.execute(
            """
            SELECT role, content, tool_calls_json, created_at
            FROM ai_chat_messages
            WHERE user_id = ? AND conversation_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, conversation_id, limit),
        )
    else:
        cursor.execute(
            """
            SELECT role, content, tool_calls_json, created_at
            FROM ai_chat_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
    rows = list(reversed(cursor.fetchall()))
    conn.close()
    messages = []
    for row in rows:
        metadata = ai_json_from_text(row["tool_calls_json"]) or {}
        if not isinstance(metadata, dict):
            metadata = {"tool_results": metadata}
        messages.append({
            "role": row["role"],
            "content": row["content"],
            "metadata": metadata,
            "created_at": row["created_at"],
        })
    return messages

def ai_latest_conversation_id(user_id):
    if not user_id:
        return ""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT conversation_id
        FROM ai_chat_messages
        WHERE user_id = ?
        GROUP BY conversation_id
        ORDER BY MAX(id) DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    conn.close()
    return row["conversation_id"] if row else ""

def ai_context_memory_bundle(history=None):
    history = history or []
    recent_messages = []
    last_system_modules = []
    last_cards = []
    last_actions = []
    for item in history[-AI_CHAT_HISTORY_LIMIT:]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        recent_messages.append({
            "role": item.get("role"),
            "content": ai_safe_text(item.get("content", ""), 500),
            "created_at": item.get("created_at", ""),
            "mode": metadata.get("mode", ""),
            "modules": metadata.get("modules", []),
        })
        if item.get("role") == "assistant" and metadata:
            for module in metadata.get("modules", []) or []:
                if module not in last_system_modules:
                    last_system_modules.append(module)
            for card in metadata.get("cards", []) or []:
                last_cards.append({
                    "type": card.get("type", ""),
                    "title": card.get("title", ""),
                    "subtitle": card.get("subtitle", ""),
                    "description": ai_safe_text(card.get("description", ""), 120),
                    "url": card.get("url", ""),
                })
            for action in metadata.get("actions", []) or []:
                command = action.get("command") if isinstance(action.get("command"), dict) else {}
                last_actions.append({
                    "kind": action.get("kind", ""),
                    "label": action.get("label", ""),
                    "url": action.get("url", ""),
                    "command": command,
                })
    return {
        "recent_messages": recent_messages[-8:],
        "last_system_modules": last_system_modules[-5:],
        "last_cards": last_cards[-6:],
        "last_actions": last_actions[-4:],
    }

def ai_last_system_modules(history=None):
    modules = []
    for item in history or []:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for module in metadata.get("modules", []) or []:
            module = str(module or "").strip()
            if module and module not in modules:
                modules.append(module)
    return modules[-5:]

def ai_last_action_command(history=None, command_type=""):
    command_type = str(command_type or "").strip()
    for item in reversed(history or []):
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for action in reversed(metadata.get("actions", []) or []):
            command = action.get("command") if isinstance(action.get("command"), dict) else {}
            if command_type and command.get("type") != command_type:
                continue
            params = command.get("params") if isinstance(command.get("params"), dict) else {}
            return {"command": command, "params": params, "action": action}
    return {}

def ai_recent_history_text(history=None, limit=6):
    parts = []
    for item in (history or [])[-limit:]:
        content = str(item.get("content") or "").strip()
        if content:
            parts.append(content)
    return "\n".join(parts)

def ai_is_context_followup(text):
    raw_text = str(text or "").strip()
    followup_words = (
        "这个", "这个路线", "该路线", "这条路线", "刚才", "上面", "前面", "继续",
        "直接", "就这个", "就按", "按刚才", "帮我打开", "打开", "显示", "高亮",
        "规划", "执行", "安排", "还有吗", "换一个", "再来", "别的",
    )
    return any(word in raw_text for word in followup_words)

def ai_route_arguments_from_history(history=None, graph=None, current_text=""):
    graph = graph or load_route_graph(DEFAULT_PLACE_ID)
    current_args = ai_route_arguments_from_text(current_text, graph)
    if current_args:
        return current_args

    action_context = ai_last_action_command(history, "route_plan")
    params = action_context.get("params") if isinstance(action_context.get("params"), dict) else {}
    start = ai_resolve_node_id(graph, params.get("start"))
    end = ai_resolve_node_id(graph, params.get("end"))
    if start and end:
        return {
            "start": start,
            "end": end,
            "transport": params.get("transport") or "mixed",
            "strategy": params.get("strategy") or "distance",
        }

    combined_text = "\n".join(
        item for item in [ai_recent_history_text(history), str(current_text or "").strip()] if item
    )
    return ai_route_arguments_from_text(combined_text, graph)

def ai_llm_chat_text(messages, temperature=0.2):
    config = ai_assistant_config()
    if not config.get("api_key"):
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    if config.get("provider") == "deepseek":
        client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        kwargs = {
            "model": config["model"],
            "messages": messages,
            "temperature": temperature,
            "reasoning_effort": config["reasoning_effort"],
        }
        if config["thinking"] != "disabled":
            kwargs["extra_body"] = {"thinking": {"type": config["thinking"]}}
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message_obj = getattr(choice, "message", None) if choice else None
        return getattr(message_obj, "content", "") or None

    if config.get("provider") == "openai":
        client = OpenAI(api_key=config["api_key"])
        response = client.chat.completions.create(
            model=config["model"],
            messages=messages,
            temperature=temperature,
        )
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message_obj = getattr(choice, "message", None) if choice else None
        return getattr(message_obj, "content", "") or None
    return None

def ai_model_route_decision(message, page_context=None, history=None):
    config = ai_assistant_config()
    if not config.get("api_key"):
        return None
    memory = ai_context_memory_bundle(history)
    prompt_payload = {
        "user_message": message,
        "page_context": page_context or {},
        "memory": memory,
        "available_modules": {
            "food": "校园美食、食堂、餐厅、口味、预算、少走路吃饭",
            "place": "景点、校园参观、拍照点、游览建议",
            "route": "室外路线规划、从A到B、三点一线、少走路",
            "indoor": "室内导航、电梯、楼梯、教学楼内路线",
            "diary": "游记、攻略、他人经验、参考日记",
        },
    }
    text = ai_llm_chat_text(
        [
            {
                "role": "system",
                "content": (
                    "你是 TourSim 助手的意图路由器。只输出 JSON，不要解释。"
                    "如果用户只是闲聊、写作、解释概念、常识问答，返回 mode=general 且 modules=[]。"
                    "如果用户的真实需求需要 TourSim 的本地数据或页面能力，返回 mode=system，并选择 modules。"
                    "要结合 memory.recent_messages 理解省略说法，例如“还有吗”“换一个”“就近点”“按刚才那个”。"
                    "如果 memory.last_system_modules 或 memory.last_cards 显示上一轮刚在某模块检索，用户追问时可延续该模块。"
                    "不要要求用户必须说固定关键词；要根据语义判断。"
                    "JSON 结构：{\"mode\":\"general|system\",\"modules\":[\"food|place|route|indoor|diary\"],"
                    "\"arguments\":{\"keyword\":\"\",\"budget\":null,\"start\":\"\",\"end\":\"\",\"vertical_mode\":\"auto\"},"
                    "\"reason\":\"short\"}"
                ),
            },
            {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
        ],
        temperature=0,
    )
    data = ai_json_from_text(text)
    if not isinstance(data, dict):
        return None
    modules = data.get("modules") if isinstance(data.get("modules"), list) else []
    clean_modules = []
    for module in modules:
        module = str(module or "").strip().lower()
        if module in ("food", "place", "route", "indoor", "diary") and module not in clean_modules:
            clean_modules.append(module)
    mode = "system" if data.get("mode") == "system" or clean_modules else "general"
    args = data.get("arguments") if isinstance(data.get("arguments"), dict) else {}
    return {
        "mode": mode,
        "modules": clean_modules if mode == "system" else [],
        "arguments": args,
        "reason": ai_safe_text(data.get("reason", ""), 180),
        "source": config.get("provider"),
    }

def ai_fallback_route_decision(message, page_context=None, history=None):
    text = str(message or "").strip()
    context = page_context or {}
    modules = []
    food_words = ("吃", "饿", "清淡", "口味", "食堂", "餐厅", "美食", "饭", "咖啡", "奶茶", "预算")
    route_words = ("路线", "怎么走", "导航", "从", "到", "三点", "少走路", "路径")
    indoor_words = ("室内", "电梯", "楼梯", "教学楼", "教室", "只坐电梯")
    diary_words = ("游记", "攻略", "日记", "参考", "别人", "经验")
    place_words = ("景点", "参观", "逛", "游览", "拍照", "去哪", "哪里好玩", "半日游")
    if any(word in text for word in food_words) or context.get("page") == "foods":
        modules.append("food")
    if any(word in text for word in indoor_words) or context.get("page") == "indoor":
        modules.append("indoor")
    if any(word in text for word in route_words) or context.get("page") == "route":
        modules.append("route")
    if any(word in text for word in diary_words) or context.get("page") == "diaries":
        modules.append("diary")
    if any(word in text for word in place_words) or context.get("page") == "places":
        modules.append("place")
    if "推荐" in text and not modules:
        modules.append("place")

    place_id = str(context.get("place_id") or FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    graph = load_route_graph(place_id)
    route_args = ai_route_arguments_from_history(history, graph, text)
    last_modules = ai_last_system_modules(history)
    is_followup = ai_is_context_followup(text)
    if route_args and (is_followup or any(word in text for word in route_words)):
        if "route" not in modules:
            modules.append("route")
    elif is_followup and not modules:
        for module in reversed(last_modules):
            if module in ("food", "place", "route", "indoor", "diary"):
                modules.append(module)
                break

    arguments = {"keyword": text}
    if "route" in modules and route_args:
        arguments.update(route_args)

    return {
        "mode": "system" if modules else "general",
        "modules": modules,
        "arguments": arguments,
        "reason": "fallback",
        "source": "local",
    }

def ai_place_card(place):
    return {
        "type": "place",
        "title": place.get("name", "景点"),
        "subtitle": " · ".join(part for part in (place.get("city", ""), place.get("type", "")) if part),
        "description": ai_safe_text(place.get("description", ""), 140),
        "meta": {
            "rating": place.get("rating"),
            "popularity": place.get("popularity"),
            "tags": place.get("tags_list", []),
        },
        "image": place.get("cover_image", ""),
        "url": ai_url_for("place_detail", place_id=place.get("id", 0)),
    }

def ai_tool_recommend_places(arguments=None):
    args = arguments or {}
    keyword = str(args.get("keyword") or args.get("query") or "").strip()
    limit = ai_normalize_limit(args.get("limit"), default=4, max_limit=6)
    normalized = normalize_search_text(keyword)
    places = load_places()
    scored = []
    for place in places:
        haystack = " ".join([
            place.get("name", ""),
            place.get("type", ""),
            place.get("city", ""),
            place.get("tags", ""),
            place.get("description", ""),
        ])
        score = float(place.get("rating") or 0) * 10 + float(place.get("popularity") or 0) / 10
        if normalized and normalized in normalize_search_text(haystack):
            score += 80
        for token in ("拍照", "校园", "湖", "建筑", "人文", "半日游", "安静"):
            if token in keyword and token in haystack:
                score += 20
        scored.append((score, place))
    scored.sort(key=lambda item: item[0], reverse=True)
    cards = [ai_place_card(place) for _, place in scored[:limit]]
    return {
        "type": "place_recommendations",
        "summary": f"我从景点库里筛出了 {len(cards)} 个可参考地点。",
        "cards": cards,
        "actions": [
            ai_action(
                "apply_place_filter",
                "按条件筛选景点",
                ai_build_url("places", {"keyword": keyword}),
                {"type": "place_filter", "params": {"keyword": keyword}},
            ),
            ai_action("open_recommend_places", "打开个性化推荐", ai_url_for("recommend_places")),
        ],
    }

def ai_run_rag_tools(message, page_context=None, route_decision=None):
    context = page_context or {}
    decision = route_decision or ai_fallback_route_decision(message, context)
    modules = decision.get("modules") or []
    args = decision.get("arguments") if isinstance(decision.get("arguments"), dict) else {}
    place_id = str(context.get("place_id") or FOOD_DEFAULT_PLACE_ID).strip() or FOOD_DEFAULT_PLACE_ID
    keyword = str(args.get("keyword") or message or "").strip()
    tool_results = []

    if "food" in modules:
        food_intent = ai_food_intent_from_text(keyword)
        tool_results.append(ai_tool_recommend_foods({
            "keyword": keyword,
            "intent": food_intent,
            "budget": args.get("budget") if args.get("budget") not in ("", None) else food_intent.get("budget"),
            "place_id": place_id,
            "origin_node": context.get("origin_node") or context.get("start") or "",
            "limit": 5,
        }))
    if "place" in modules:
        tool_results.append(ai_tool_recommend_places({"keyword": keyword, "limit": 4}))
    if "route" in modules:
        graph = load_route_graph(place_id)
        explicit_route_args = ai_route_arguments_from_text(" ".join([keyword, message]), graph)
        tool_results.append(ai_tool_plan_route({
            "place_id": place_id,
            "keyword": keyword,
            "message": message,
            "start": args.get("start") or explicit_route_args.get("start") or context.get("start", ""),
            "end": args.get("end") or explicit_route_args.get("end") or context.get("end", ""),
            "strategy": args.get("strategy") or explicit_route_args.get("strategy") or context.get("strategy", "distance"),
            "transport": args.get("transport") or explicit_route_args.get("transport") or context.get("transport") or "mixed",
        }))
    if "indoor" in modules:
        vertical_mode = str(args.get("vertical_mode") or context.get("vertical_mode", "auto")).strip() or "auto"
        tool_results.append(ai_tool_plan_indoor({
            "building_id": context.get("building_id", "demo_building"),
            "start": args.get("start") or context.get("start", INDOOR_DEFAULT_START),
            "end": args.get("end") or context.get("end", INDOOR_DEFAULT_END),
            "vertical_mode": vertical_mode,
        }))
    if "diary" in modules:
        tool_results.append(ai_tool_search_diaries({"keyword": keyword, "limit": 4}))

    cards = list(itertools.chain.from_iterable(result.get("cards", []) for result in tool_results))
    actions = list(itertools.chain.from_iterable(result.get("actions", []) for result in tool_results))
    retrieved_context = []
    for result in tool_results:
        retrieved_context.append({
            "type": result.get("type", ""),
            "summary": result.get("summary", ""),
            "items": [
                {
                    "title": card.get("title", ""),
                    "subtitle": card.get("subtitle", ""),
                    "description": card.get("description", ""),
                    "meta": card.get("meta", {}),
                    "url": card.get("url", ""),
                }
                for card in result.get("cards", [])[:5]
            ],
        })
    return {
        "mode": "system" if modules else "general",
        "module": ",".join(modules),
        "modules": modules,
        "routing": decision,
        "answer": " ".join(result.get("summary", "") for result in tool_results if result.get("summary")).strip(),
        "cards": cards[:8],
        "actions": actions[:6],
        "tool_results": tool_results,
        "retrieved_context": retrieved_context,
        "suggestions": [
            "按我的偏好继续细化",
            "给我更少走路的方案",
            "顺手规划下一站",
            "找几篇游记参考",
        ],
    }

def ai_local_assistant_payload(message, page_context=None, history=None):
    context = page_context or {}
    config = ai_assistant_config()
    decision = None
    if config.get("router_mode") == "llm":
        decision = ai_model_route_decision(message, context, history)
    if not decision:
        decision = ai_fallback_route_decision(message, context, history)
    if decision.get("mode") == "general":
        return {
            "mode": "general",
            "module": "general",
            "modules": [],
            "routing": decision,
            "answer": ai_generic_local_answer(message),
            "cards": [],
            "actions": [],
            "tool_results": [],
            "retrieved_context": [],
            "suggestions": [
                "随便聊聊",
                "帮我解释一个概念",
                "帮我查校园美食推荐",
                "帮我做路线规划",
            ],
        }
    payload = ai_run_rag_tools(message, context, decision)
    if not payload.get("answer"):
        payload["answer"] = "我先查了 TourSim 的本地数据，给你整理了这些可以继续点开的结果。"
    return payload

def ai_build_model_prompt(message, page_context, local_payload, history=None):
    memory = ai_context_memory_bundle(history)
    base = {
        "user_message": message,
        "page_context": page_context or {},
        "memory": memory,
        "routing": local_payload.get("routing", {}),
        "assistant_mode": local_payload.get("mode", "general"),
    }
    if local_payload.get("mode") == "general":
        base["instruction"] = (
            "你是一个通用人工智能助手，像真实同学一样自然交流。"
            "普通聊天、解释、写作、建议、常识问题都直接回答。"
            "回答前参考 memory.recent_messages，延续用户上一轮的称呼、偏好和话题。"
            "不要生硬提醒关键词，也不要假装查了 TourSim 数据。"
            "中文回答，语气亲切、简洁，不使用表情符号。"
        )
        return base
    base["local_tool_context"] = {
        "retrieved_context": local_payload.get("retrieved_context", []),
        "cards": local_payload.get("cards", [])[:5],
        "actions": local_payload.get("actions", [])[:4],
    }
    base["instruction"] = (
        "你是 TourSim 里的通用 AI 助手。你已经根据用户语义判断需要结合本地数据，"
        "并拿到了 RAG 检索结果 local_tool_context。"
        "回答前参考 memory.recent_messages、memory.last_cards 和 memory.last_actions，理解用户是否在追问上一轮结果。"
        "先像人一样回应用户当前需求，再把检索到的地点、美食、路线、室内导航或游记自然融入建议。"
        "只能基于 local_tool_context 里的真实结果说具体名称、价格、路线和链接，不要编造。"
        "如果结果不足，说明还差哪个关键信息，并给一个可继续操作的下一步。"
        "回答控制在 3 到 6 句。"
    )
    return base

def ai_openai_answer(message, page_context, local_payload, history=None):
    config = ai_assistant_config()
    if not config.get("api_key") or config.get("provider") != "openai":
        return None
    prompt = ai_build_model_prompt(message, page_context, local_payload, history)
    return ai_llm_chat_text(
        [
            {"role": "system", "content": "你是 TourSim 的通用 AI 助手，会在需要时基于系统检索上下文回答。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        temperature=0.4,
    )

def ai_deepseek_answer(message, page_context, local_payload, history=None):
    config = ai_assistant_config()
    if not config.get("api_key") or config.get("provider") != "deepseek":
        return None
    prompt = ai_build_model_prompt(message, page_context, local_payload, history)
    return ai_llm_chat_text(
        [
            {"role": "system", "content": "你是 TourSim 的通用 AI 助手，会在需要时基于系统检索上下文回答。"},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        temperature=0.4,
    )

def ai_provider_answer(message, page_context, local_payload, history=None):
    config = ai_assistant_config()
    if config.get("provider") == "deepseek":
        return ai_deepseek_answer(message, page_context, local_payload, history)
    if config.get("provider") == "openai":
        return ai_openai_answer(message, page_context, local_payload, history)
    return None

def ai_executable_route_answer(local_payload):
    for action in local_payload.get("actions", []) or []:
        command = action.get("command") if isinstance(action.get("command"), dict) else {}
        if command.get("type") != "route_plan":
            continue
        params = command.get("params") if isinstance(command.get("params"), dict) else {}
        place_id = params.get("place_id") or DEFAULT_PLACE_ID
        graph = load_route_graph(place_id)
        start = ai_route_node_name_from_id(graph, params.get("start"))
        end = ai_route_node_name_from_id(graph, params.get("end"))
        if start and end:
            return f"可以，这次已经按路网算好「{start}」到「{end}」。点下面的「自动规划并高亮路线」，地图就会把这条路线亮出来。"
    return ""

def ai_store_chat_message(user_id, conversation_id, role, content, tool_calls=None):
    if not user_id:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO ai_chat_messages
        (user_id, conversation_id, role, content, tool_calls_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            conversation_id,
            role,
            ai_safe_text(content, 4000),
            json.dumps(tool_calls or [], ensure_ascii=False),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    conn.commit()
    conn.close()
