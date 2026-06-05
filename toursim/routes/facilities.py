from dataclasses import dataclass
from urllib.parse import urlencode

from flask import Blueprint, flash, redirect, request, url_for


@dataclass
class FacilitiesRouteServices:
    is_logged_in: object


def create_facilities_blueprint(services):
    bp = Blueprint("facilities_routes", __name__)

    @bp.route("/facilities")
    def facilities():
        if not services.is_logged_in():
            flash("请先登录")
            return redirect(url_for("login"))

        params = []
        facility_start_node = request.args.get("facility_start_node", request.args.get("start_node", "")).strip()
        if facility_start_node:
            params.append(("facility_start_node", facility_start_node))
        facility_start_food = request.args.get("facility_start_food", "").strip()
        if facility_start_food:
            params.append(("facility_start_food", facility_start_food))
        facility_type = request.args.get("type", "").strip()
        if facility_type:
            params.append(("facility_type", facility_type))
        facility_keyword = request.args.get("keyword", "").strip()
        if facility_keyword:
            params.append(("facility_keyword", facility_keyword))
        max_distance = request.args.get("max_distance", "").strip()
        if max_distance:
            params.append(("max_distance", max_distance))
        if not request.args.get("active_panel"):
            params.append(("active_panel", "places"))
        for key in ("place_id", "start", "end", "strategy", "transport", "route_type", "collect", "food_pick", "edit_roads", "active_panel"):
            values = request.args.getlist(key)
            if values:
                params.extend((key, value) for value in values if value not in ("", None))
        for tag in request.args.getlist("preferred_tags"):
            if tag:
                params.append(("preferred_tags", tag))
        return redirect(url_for("route") + ("?" + urlencode(params, doseq=True) if params else ""))

    return bp
