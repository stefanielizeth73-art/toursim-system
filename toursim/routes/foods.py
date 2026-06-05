from dataclasses import dataclass

from flask import Blueprint, flash, redirect, render_template, request, session, url_for


@dataclass
class FoodsRouteServices:
    build_food_candidates_for_place: object
    build_pagination: object
    build_url_with_query: object
    food_campus_contexts: object
    food_cuisine_options: object
    food_default_place_id: object
    food_top_k: object
    get_food_by_key: object
    get_logged_in_user: object
    is_item_favorited: object
    is_logged_in: object
    load_route_graph: object
    paginate_items: object
    parse_positive_int: object
    rank_food_candidates: object
    toggle_user_favorite: object


def create_foods_blueprint(services):
    bp = Blueprint("foods_routes", __name__)

    def value(name):
        raw_value = getattr(services, name)
        return raw_value() if callable(raw_value) else raw_value

    @bp.route("/foods")
    def foods():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        food_default_place_id = value("food_default_place_id")
        food_campus_contexts = value("food_campus_contexts")
        food_top_k = value("food_top_k")
        place_id = request.args.get("place_id", food_default_place_id).strip() or food_default_place_id
        if place_id not in food_campus_contexts:
            place_id = food_default_place_id
        keyword = request.args.get("keyword", "").strip()
        category = request.args.get("category", "").strip()
        source_place_name = request.args.get("place_name", "").strip()
        food_page_title = f"{source_place_name}美食推荐" if source_place_name else "翔安校区美食推荐"
        sort_by = request.args.get("sort_by", "default").strip()
        requested_origin_node = request.args.get("origin_node", "").strip()

        food_context = food_campus_contexts[place_id]
        campus_foods = services.build_food_candidates_for_place(place_id)
        graph = services.load_route_graph(food_context.get("graph_place_id", place_id))
        origin_node = requested_origin_node if requested_origin_node in graph.get("node_map", {}) else ""
        if not sort_by or sort_by == "default":
            sort_by = food_context.get("default_sort", "recommend_score_desc")
        if not origin_node and sort_by == "distance_asc":
            sort_by = "recommend_score_desc"
        filtered_foods, food_stats = services.rank_food_candidates(
            campus_foods,
            keyword=keyword,
            category=category,
            place_name="",
            sort_by=sort_by,
            limit=None,
            graph=graph,
            origin_node=origin_node,
        )
        food_page = services.parse_positive_int(request.args.get("page", 1))
        paged_foods, page_info = services.paginate_items(filtered_foods, page=food_page, per_page=food_top_k)
        food_pagination = services.build_pagination(
            "foods",
            page_info["page"],
            page_info["total_pages"],
            {
                "place_id": place_id,
                "keyword": keyword,
                "category": category,
                "place_name": source_place_name,
                "sort_by": sort_by,
                "origin_node": origin_node,
            },
        )
        food_pagination["per_page"] = food_top_k
        food_pagination["total"] = len(filtered_foods)
        food_stats = dict(food_stats or {})
        food_stats["returned_count"] = len(paged_foods)
        food_stats["filtered_count"] = len(filtered_foods)
        food_stats["page"] = page_info["page"]
        food_stats["page_size"] = food_top_k
        present_categories = {food["category"] for food in campus_foods if food.get("category")}
        categories = [option for option in value("food_cuisine_options") if option in present_categories]
        categories.extend(sorted(present_categories - set(categories)))

        return render_template(
            "foods.html",
            username=session["username"],
            foods=paged_foods,
            keyword=keyword,
            category=category,
            place_name=source_place_name,
            food_page_title=food_page_title,
            sort_by=sort_by,
            categories=categories,
            place_id=place_id,
            origin_node=origin_node,
            food_pagination=food_pagination,
            food_context={
                **food_context,
                "top_k": food_top_k,
                "show_all": False,
                "origin_node": origin_node,
                "origin_node_name": graph.get("node_map", {}).get(origin_node, {}).get("name", ""),
            },
            food_stats=food_stats,
            food_mode="campus",
        )

    @bp.route("/food/<food_key>")
    def food_detail(food_key):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        food_default_place_id = value("food_default_place_id")
        food_campus_contexts = value("food_campus_contexts")
        place_id = request.args.get("place_id", food_default_place_id).strip() or food_default_place_id
        if place_id not in food_campus_contexts:
            place_id = food_default_place_id
        requested_origin_node = request.args.get("origin_node", "").strip()
        keyword = request.args.get("keyword", "").strip()
        category = request.args.get("category", "").strip()
        place_name = request.args.get("place_name", "").strip()
        sort_by = request.args.get("sort_by", "").strip()
        page = services.parse_positive_int(request.args.get("page", 1))
        food_context = food_campus_contexts[place_id]
        graph = services.load_route_graph(food_context.get("graph_place_id", place_id))
        origin_node = requested_origin_node if requested_origin_node in graph.get("node_map", {}) else ""
        food = services.get_food_by_key(food_key, place_id=place_id, origin_node=origin_node)
        if food is None:
            flash("未找到该美食信息")
            return redirect(url_for("foods", place_id=place_id) if place_id else url_for("foods"))
        current_user = services.get_logged_in_user()

        return render_template(
            "food_detail.html",
            username=session["username"],
            current_user=current_user,
            food=food,
            food_favorited=services.is_item_favorited(current_user["id"], "food", food_key) if current_user else False,
            place_id=place_id,
            place_name=place_name,
            origin_node=origin_node,
            keyword=keyword,
            category=category,
            sort_by=sort_by,
            page=page,
            return_to="food_detail",
            return_food_key=food_key,
            return_place_id=place_id,
            route_food_pick_url=services.build_url_with_query(
                "route",
                {
                    "place_id": place_id,
                    "food_pick": "1",
                    "return_to": "food_detail",
                    "return_food_key": food_key,
                    "return_place_id": place_id,
                },
            ),
            route_food_facilities_url=services.build_url_with_query(
                "route",
                {
                    "place_id": place_id,
                    "active_panel": "places",
                    "facility_start_node": f"food:{food_key}",
                    "facility_start_food": food_key,
                    "strategy": "distance",
                    "transport": "mixed",
                },
                anchor="facilityResults",
            ),
            food_context={
                **food_context,
                "origin_node": origin_node,
                "origin_node_name": graph.get("node_map", {}).get(origin_node, {}).get("name", ""),
            },
        )

    @bp.route("/food/<food_key>/favorite", methods=["POST"])
    def food_favorite(food_key):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        food_default_place_id = value("food_default_place_id")
        food_campus_contexts = value("food_campus_contexts")
        current_user = services.get_logged_in_user()
        place_id = request.form.get("place_id", request.args.get("place_id", food_default_place_id)).strip() or food_default_place_id
        if place_id not in food_campus_contexts:
            place_id = food_default_place_id
        origin_node = request.form.get("origin_node", request.args.get("origin_node", "")).strip()
        keyword = request.form.get("keyword", request.args.get("keyword", "")).strip()
        category = request.form.get("category", request.args.get("category", "")).strip()
        place_name = request.form.get("place_name", request.args.get("place_name", "")).strip()
        sort_by = request.form.get("sort_by", request.args.get("sort_by", "")).strip()
        page = services.parse_positive_int(request.form.get("page", request.args.get("page", 1)))
        food = services.get_food_by_key(food_key, place_id=place_id, origin_node=origin_node)
        if current_user is None or food is None:
            flash("未找到该美食信息")
            return redirect(url_for("foods", place_id=place_id))
        favorited = services.toggle_user_favorite(
            current_user["id"],
            "food",
            food_key,
            title=food["name"],
            subtitle=f"{food.get('cuisine') or food.get('category', '')} · 评分 {food.get('rating', 0)}",
            meta={
                "place_id": place_id,
                "place_name": place_name,
                "origin_node": origin_node,
                "keyword": keyword,
                "category": category,
                "sort_by": sort_by,
                "page": page,
                "cuisine": food.get("cuisine") or food.get("category", ""),
                "rating": food.get("rating", 0),
                "avg_cost": food.get("avg_cost", 0),
                "cover_image": food.get("cover_image", ""),
            },
        )
        flash("已收藏这家美食" if favorited else "已取消收藏")
        return redirect(url_for(
            "food_detail",
            food_key=food_key,
            place_id=place_id,
            place_name=place_name,
            origin_node=origin_node,
            keyword=keyword,
            category=category,
            sort_by=sort_by,
            page=page,
        ))

    return bp
