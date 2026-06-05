from dataclasses import dataclass

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for


@dataclass
class DiariesRouteServices:
    is_logged_in: object
    load_places: object
    get_place_name_options: object
    create_diary: object
    save_diary_media_files: object
    update_diary_media: object
    load_diaries: object
    parse_positive_int: object
    paginate_items: object
    build_pagination: object
    get_logged_in_user: object
    get_user_avatar_url: object
    get_diary_by_id: object
    create_diary_comment: object
    update_diary_compression_algorithm: object
    rate_diary_once: object
    find_place_match: object
    get_related_places_for_diary: object
    get_diary_compression_preview: object
    get_user_by_username: object
    load_diary_comments: object
    flatten_diary_comment_replies: object
    get_diary_user_rating: object
    is_item_favorited: object
    get_latest_diary_video_task: object
    build_diary_video_prompt: object
    get_dashscope_api_key: object
    select_diary_video_image: object
    diary_image_data_url: object
    normalize_diary_video_duration: object
    normalize_diary_video_resolution: object
    build_bailian_video_payload: object
    submit_bailian_image_to_video_task: object
    create_diary_video_task: object
    get_diary_video_task: object
    poll_bailian_video_task: object
    normalize_diary_video_status: object
    download_diary_generated_video: object
    update_diary_video_task: object
    stored_diary_media_items: object
    toggle_user_favorite: object
    get_db_connection: object
    toggle_diary_comment_like: object
    diaries_page_size: object
    diary_visible_comment_threads: object
    diary_visible_replies: object


def create_diaries_blueprint(services):
    bp = Blueprint("diaries_routes", __name__)

    def value(name):
        raw_value = getattr(services, name)
        return raw_value() if callable(raw_value) else raw_value

    @bp.route("/diaries", methods=["GET", "POST"])
    def diaries():
        if not services.is_logged_in():
            if request.args.get("ajax") == "1":
                return jsonify({"ok": False, "error": "auth_required"}), 401
            flash("请先登录")
            return redirect(url_for("login"))

        all_places = services.load_places()
        place_name_options = services.get_place_name_options(all_places)

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            destination = request.form.get("destination", "").strip()
            content = request.form.get("content", "").strip()
            compression_algorithm = request.form.get("compression_algorithm", "huffman").strip().lower()
            uploaded_files = request.files.getlist("attachments")
            if not title or not destination or not content:
                flash("标题、目的地和正文不能为空")
            else:
                diary_id = services.create_diary(
                    title,
                    destination,
                    content,
                    session["username"],
                    compression_algorithm=compression_algorithm
                )
                media_items = services.save_diary_media_files(diary_id, uploaded_files)
                if media_items:
                    services.update_diary_media(diary_id, media_items)
                flash("日记发布成功")
                return redirect(url_for("diaries"))

        all_diaries = services.load_diaries(sort_by="hot_rating_desc")
        page = services.parse_positive_int(request.args.get("page", 1))
        diaries_list, pagination_state = services.paginate_items(all_diaries, page, value("diaries_page_size"))
        pagination = services.build_pagination(
            "diaries",
            pagination_state["page"],
            pagination_state["total_pages"],
            {},
        )
        if request.args.get("ajax") == "1":
            html_content = render_template(
                "diary_feed_items.html",
                feed_diaries=diaries_list,
                eager_limit=0,
                show_diary_metrics=False,
            )
            return jsonify({
                "ok": True,
                "html": html_content,
                "has_next": pagination["has_next"],
                "next_url": pagination["next_url"] or "",
            })
        current_user = services.get_logged_in_user()
        return render_template(
            "diaries.html",
            username=session["username"],
            current_user=current_user,
            current_user_avatar_url=services.get_user_avatar_url(current_user) if current_user else "",
            diaries=diaries_list,
            diaries_total=len(all_diaries),
            pagination=pagination,
            place_name_options=place_name_options,
            publish_default_destination="",
        )


    @bp.route("/diaries/search")
    def diary_search():
        if not services.is_logged_in():
            if request.args.get("ajax") == "1":
                return jsonify({"ok": False, "error": "auth_required"}), 401
            flash("请先登录")
            return redirect(url_for("login"))

        query = request.args.get("q", "").strip()
        title_query = request.args.get("title_query", "").strip()
        keyword = request.args.get("keyword", "").strip()
        destination = request.args.get("destination", "").strip()
        search_mode = request.args.get("search_mode", "contains").strip().lower()
        sort_by = request.args.get("sort_by", "hot_rating_desc").strip().lower()
        if search_mode not in {"exact", "prefix", "contains"}:
            search_mode = "contains"
        if sort_by not in {"hot_rating_desc", "views_desc", "rating_desc", "created_desc", "title_asc"}:
            sort_by = "hot_rating_desc"
        if query and not title_query and not keyword and not destination:
            keyword = query

        all_places = services.load_places()
        place_name_options = services.get_place_name_options(all_places)
        has_search_filters = any([title_query, keyword, destination])
        if has_search_filters:
            filtered_diaries = services.load_diaries(
                title_query=title_query,
                search_mode=search_mode,
                keyword=keyword,
                destination=destination,
                sort_by=sort_by,
            )
        else:
            filtered_diaries = services.load_diaries(sort_by="hot_rating_desc")
        page = services.parse_positive_int(request.args.get("page", 1))
        diaries_list, pagination_state = services.paginate_items(filtered_diaries, page, value("diaries_page_size"))
        pagination = services.build_pagination(
            "diary_search",
            pagination_state["page"],
            pagination_state["total_pages"],
            {
                "q": query,
                "title_query": title_query,
                "keyword": keyword,
                "destination": destination,
                "search_mode": search_mode,
                "sort_by": sort_by,
            },
        )
        if request.args.get("ajax") == "1":
            html_content = render_template(
                "diary_feed_items.html",
                feed_diaries=diaries_list,
                eager_limit=0,
                show_diary_metrics=True,
            )
            return jsonify({
                "ok": True,
                "html": html_content,
                "has_next": pagination["has_next"],
                "next_url": pagination["next_url"] or "",
            })
        recommendations = services.load_diaries(sort_by="hot_rating_desc")[:12]
        search_mode_options = [
            {"value": "exact", "label": "精确查询", "note": "标题完全一致"},
            {"value": "prefix", "label": "前缀模糊", "note": "标题前缀快速匹配"},
            {"value": "contains", "label": "标题包含", "note": "标题内包含关键词"},
        ]
        sort_options = [
            {"value": "hot_rating_desc", "label": "综合推荐", "note": "热度、评分、评分人数"},
            {"value": "views_desc", "label": "热度优先", "note": "浏览量从高到低"},
            {"value": "rating_desc", "label": "评分优先", "note": "平均评分从高到低"},
            {"value": "created_desc", "label": "最新发布", "note": "发布时间倒序"},
            {"value": "title_asc", "label": "标题排序", "note": "标题字典序"},
        ]
        search_state = {
            "query": query,
            "title_query": title_query,
            "keyword": keyword,
            "destination": destination,
            "search_mode": search_mode,
            "sort_by": sort_by,
            "has_filters": has_search_filters,
            "result_count": len(filtered_diaries),
            "sort_label": next((item["label"] for item in sort_options if item["value"] == sort_by), "综合推荐"),
            "mode_label": next((item["label"] for item in search_mode_options if item["value"] == search_mode), "标题包含"),
        }
        current_user = services.get_logged_in_user()
        return render_template(
            "diary_search.html",
            username=session["username"],
            current_user=current_user,
            current_user_avatar_url=services.get_user_avatar_url(current_user) if current_user else "",
            diaries=diaries_list,
            query=query,
            recommendations=recommendations,
            pagination=pagination,
            place_name_options=place_name_options,
            search_state=search_state,
            search_mode_options=search_mode_options,
            sort_options=sort_options,
        )


    @bp.route("/diary/<int:diary_id>", methods=["GET", "POST"])
    def diary_detail(diary_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        if request.method == "POST":
            action = request.form.get("action", "rating").strip().lower()
            if action == "comment":
                content = request.form.get("content", "").strip()
                parent_id = services.parse_positive_int(request.form.get("parent_id", 0))
                if not content:
                    flash("评论内容不能为空")
                    return redirect(url_for("diary_detail", diary_id=diary_id))
                comment_id = services.create_diary_comment(diary_id, session["username"], content, parent_id=parent_id)
                flash("评论已发布")
                if comment_id:
                    return redirect(url_for("diary_detail", diary_id=diary_id, comment_posted=1, _anchor=f"comment-{comment_id}"))
                return redirect(url_for("diary_detail", diary_id=diary_id))

            if action == "compression":
                compression_algorithm = request.form.get("compress_algorithm", "huffman").strip().lower()
                updated_diary = services.update_diary_compression_algorithm(diary_id, compression_algorithm)
                if updated_diary is None:
                    flash("未找到该旅游日记")
                    return redirect(url_for("diaries"))
                flash("压缩算法已更新，正文内容不变")
                return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0))

            rating = request.form.get("rating", "5")
            rating_saved = services.rate_diary_once(diary_id, session["username"], rating)
            flash("\u8bc4\u5206\u6210\u529f" if rating_saved else "\u4f60\u5df2\u7ecf\u7ed9\u8fd9\u7bc7\u65e5\u8bb0\u8bc4\u5206\u8fc7\u4e86")
            return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0))

        increase_views = request.method == "GET" and request.args.get("count_view", "1") != "0"
        diary = services.get_diary_by_id(diary_id, increase_views=increase_views)
        if diary is None:
            flash("未找到该旅游日记")
            return redirect(url_for("diaries"))

        all_places = services.load_places()
        matched_place = services.find_place_match(diary.get("destination", ""), all_places)
        related_places = services.get_related_places_for_diary(diary, all_places, limit=4)
        if matched_place:
            related_places = [place for place in related_places if place["id"] != matched_place["id"]]

        compression_algorithm = request.args.get(
            "compress_algorithm",
            diary.get("compression", {}).get("algorithm", "huffman")
        ).strip().lower()
        compression_preview = services.get_diary_compression_preview(diary_id, compression_algorithm)
        current_user = services.get_logged_in_user()
        diary_author = services.get_user_by_username(diary.get("author", ""))
        comment_payload = services.load_diary_comments(diary_id, current_user["username"] if current_user else None)
        visible_threads = comment_payload["threads"][:value("diary_visible_comment_threads")]
        hidden_threads = comment_payload["threads"][value("diary_visible_comment_threads"):]
        for comment_group in (visible_threads, hidden_threads):
            for thread in comment_group:
                thread["flat_replies"] = services.flatten_diary_comment_replies(thread.get("replies", []))

        return render_template(
            "diary_detail.html",
            username=session["username"],
            current_user=current_user,
            current_user_avatar_url=services.get_user_avatar_url(current_user) if current_user else "",
            diary=diary,
            diary_author=diary_author,
            diary_author_avatar_url=services.get_user_avatar_url(diary.get("author", "")),
            diary_favorited=services.is_item_favorited(current_user["id"], "diary", diary_id) if current_user else False,
            diary_user_rating=services.get_diary_user_rating(diary_id, current_user["username"]) if current_user else None,
            place_name_options=services.get_place_name_options(all_places),
            matched_place=matched_place,
            related_places=related_places,
            compression_preview=compression_preview,
            compression_algorithm=compression_algorithm,
            comments=visible_threads,
            hidden_comments=hidden_threads,
            comment_total=comment_payload["total_count"],
            visible_comment_threads=value("diary_visible_comment_threads"),
            visible_comment_replies=value("diary_visible_replies"),
            comment_posted=request.args.get("comment_posted", "").strip() == "1",
            diary_video_task=services.get_latest_diary_video_task(diary_id),
            diary_video_default_prompt=services.build_diary_video_prompt(diary),
            diary_video_enabled=bool(services.get_dashscope_api_key()),
        )


    @bp.route("/api/diary/<int:diary_id>/video-generation", methods=["POST"])
    def diary_video_generation_start(diary_id):
        if not services.is_logged_in():
            return jsonify({"ok": False, "error": "请先登录"}), 401

        diary = services.get_diary_by_id(diary_id, increase_views=False)
        if diary is None:
            return jsonify({"ok": False, "error": "未找到这篇日记"}), 404

        payload = request.get_json(silent=True) or {}
        try:
            image_item = services.select_diary_video_image(diary, payload.get("image_filename", ""))
            image_data_url_value = services.diary_image_data_url(diary_id, image_item.get("filename", ""))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        if not services.get_dashscope_api_key():
            return jsonify({"ok": False, "error": "未配置 DASHSCOPE_API_KEY"}), 503

        prompt = str(payload.get("prompt") or "").strip() or services.build_diary_video_prompt(diary)
        duration = services.normalize_diary_video_duration(payload.get("duration"))
        resolution = services.normalize_diary_video_resolution(payload.get("resolution"))
        request_payload = services.build_bailian_video_payload(diary, image_data_url_value, prompt, duration, resolution)

        try:
            task_response = services.submit_bailian_image_to_video_task(request_payload)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        task = services.create_diary_video_task(
            diary_id=diary_id,
            task_id=task_response["task_id"],
            status=task_response.get("status", "PENDING"),
            prompt=prompt,
            image_filename=image_item.get("filename", ""),
            request_payload=request_payload,
            raw_response=task_response.get("raw_response") or {},
        )
        return jsonify({"ok": True, "task": task}), 202


    @bp.route("/api/diary/<int:diary_id>/video-generation/latest")
    def diary_video_generation_latest(diary_id):
        if not services.is_logged_in():
            return jsonify({"ok": False, "error": "请先登录"}), 401
        if services.get_diary_by_id(diary_id, increase_views=False) is None:
            return jsonify({"ok": False, "error": "未找到这篇日记"}), 404
        return jsonify({"ok": True, "task": services.get_latest_diary_video_task(diary_id)})


    @bp.route("/api/diary/<int:diary_id>/video-generation/<int:task_db_id>")
    def diary_video_generation_status(diary_id, task_db_id):
        if not services.is_logged_in():
            return jsonify({"ok": False, "error": "请先登录"}), 401

        task = services.get_diary_video_task(task_db_id, diary_id=diary_id)
        if task is None:
            return jsonify({"ok": False, "error": "未找到生成任务"}), 404

        terminal_statuses = {"SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}
        if task["status"] == "SUCCEEDED" and task.get("local_video_filename"):
            return jsonify({"ok": True, "task": task})
        if task["status"] in terminal_statuses and task["status"] != "SUCCEEDED":
            return jsonify({"ok": True, "task": task})

        try:
            poll_result = services.poll_bailian_video_task(task["task_id"])
            status = services.normalize_diary_video_status(poll_result.get("status"))
            local_video_filename = task.get("local_video_filename", "")
            if status == "SUCCEEDED" and poll_result.get("video_url") and not local_video_filename:
                local_video_filename = services.download_diary_generated_video(diary_id, task["task_id"], poll_result["video_url"])

            task = services.update_diary_video_task(
                task_db_id,
                status=status,
                result_url=poll_result.get("video_url", ""),
                local_video_filename=local_video_filename,
                error_message=poll_result.get("error_message", ""),
                response_json=poll_result.get("raw_response") or {},
            )
        except RuntimeError as exc:
            task = services.update_diary_video_task(task_db_id, status="FAILED", error_message=str(exc))
            return jsonify({"ok": False, "error": str(exc), "task": task}), 502

        return jsonify({"ok": True, "task": task})


    @bp.route("/diary/<int:diary_id>/favorite", methods=["POST"])
    def diary_favorite(diary_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        current_user = services.get_logged_in_user()
        diary = services.get_diary_by_id(diary_id, increase_views=False)
        if current_user is None or diary is None:
            flash("未找到该旅游日记")
            return redirect(url_for("diaries"))
        favorited = services.toggle_user_favorite(
            current_user["id"],
            "diary",
            diary_id,
            title=diary["title"],
            subtitle=f"{diary['destination']} · {diary['author']}",
            meta={"destination": diary["destination"], "author": diary["author"]},
        )
        flash("已收藏这篇日记" if favorited else "已取消收藏")
        return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0))


    @bp.route("/diary/<int:diary_id>/comments/<int:comment_id>/like", methods=["POST"])
    def diary_comment_like(diary_id, comment_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))
        conn = services.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM diary_comments WHERE id = ? AND diary_id = ?", (comment_id, diary_id))
        comment = cursor.fetchone()
        conn.close()
        if comment is None:
            flash("评论不存在")
            return redirect(url_for("diary_detail", diary_id=diary_id))
        services.toggle_diary_comment_like(comment_id, session["username"])
        return redirect(url_for("diary_detail", diary_id=diary_id, count_view=0, _anchor=f"comment-{comment_id}"))

    return bp
