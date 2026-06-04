from dataclasses import dataclass
from urllib.parse import urlencode

from flask import Blueprint, flash, redirect, render_template, request, session, url_for


@dataclass
class PlacesRouteServices:
    build_pagination: object
    filter_and_sort_places: object
    get_place_by_id: object
    get_place_filter_options: object
    get_related_diaries_for_place: object
    get_top_k_recommendations: object
    is_logged_in: object
    load_diaries: object
    load_places: object
    paginate_items: object
    parse_positive_int: object
    places_page_size: object
    save_place_image_record: object
    save_uploaded_place_cover: object


def create_places_blueprint(services):
    bp = Blueprint("places_routes", __name__)

    def places_page_size():
        value = services.places_page_size
        return value() if callable(value) else value

    @bp.route("/places")
    def places():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        keyword = request.args.get("keyword", "").strip()
        tag_keyword = request.args.get("tag_keyword", "").strip()
        place_type = request.args.get("type", "").strip()
        city = request.args.get("city", "").strip()
        sort_by = request.args.get("sort_by", "default").strip()
        selected_tags = request.args.getlist("preferred_tags")
        try:
            k = int(request.args.get("k", "10"))
        except ValueError:
            k = 10
        k = max(1, min(k, 20))

        all_places = services.load_places()
        filtered_places = services.filter_and_sort_places(
            all_places,
            keyword=keyword,
            tag_keyword=tag_keyword,
            place_type=place_type,
            city=city,
            sort_by=sort_by,
        )
        filter_options = services.get_place_filter_options(all_places)
        recommended_places, recommendation_stats = services.get_top_k_recommendations(
            all_places,
            preferred_tags=selected_tags,
            k=k,
            place_type=place_type,
            city=city,
            keyword=keyword,
            tag_keyword=tag_keyword,
        )
        page = services.parse_positive_int(request.args.get("page", 1))
        visible_places, pagination_state = services.paginate_items(filtered_places, page, places_page_size())
        pagination = services.build_pagination(
            "places",
            pagination_state["page"],
            pagination_state["total_pages"],
            {
                "keyword": keyword,
                "tag_keyword": tag_keyword,
                "type": place_type,
                "city": city,
                "sort_by": sort_by,
                "preferred_tags": selected_tags,
                "k": k,
            },
        )

        return render_template(
            "places.html",
            username=session["username"],
            places=visible_places,
            recommended_places=recommended_places,
            recommendation_stats=recommendation_stats,
            total_places=len(all_places),
            filtered_places_total=len(filtered_places),
            pagination=pagination,
            keyword=keyword,
            tag_keyword=tag_keyword,
            place_type=place_type,
            city=city,
            sort_by=sort_by,
            selected_tags=selected_tags,
            all_available_tags=filter_options["tags"],
            k=k,
            cities=filter_options["cities"],
            place_types=filter_options["place_types"],
        )

    @bp.route("/place/<int:place_id>")
    def place_detail(place_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        place = services.get_place_by_id(place_id)
        if place is None:
            flash("未找到该景点或学校")
            return redirect(url_for("places"))

        related_diaries = services.get_related_diaries_for_place(
            place,
            services.load_diaries(sort_by="hot_rating_desc"),
            limit=6,
        )

        return render_template(
            "place_detail.html",
            username=session["username"],
            place=place,
            related_diaries=related_diaries,
        )

    @bp.route("/place/<int:place_id>/image/upload", methods=["POST"])
    def upload_place_image(place_id):
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        place = services.get_place_by_id(place_id)
        if place is None:
            flash("未找到该景点或学校")
            return redirect(url_for("places"))

        try:
            local_path, original_width, original_height, original_name = services.save_uploaded_place_cover(
                request.files.get("image_file"),
                place,
            )
            services.save_place_image_record(place, local_path, original_width, original_height, original_name)
            flash("封面图片已更新")
        except ValueError as exc:
            flash(str(exc))

        return redirect(url_for("place_detail", place_id=place_id))

    @bp.route("/places/recommend", methods=["GET", "POST"])
    def recommend_places():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        params = []
        source = request.values if request.method == "POST" else request.args
        for key in source.keys():
            values = source.getlist(key)
            params.extend((key, value) for value in values if value not in ("", None))
        return redirect(url_for("places") + ("?" + urlencode(params, doseq=True) if params else ""))

    return bp
