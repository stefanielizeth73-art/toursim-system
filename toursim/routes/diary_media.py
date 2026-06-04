import os
from dataclasses import dataclass

from flask import Blueprint, abort, request, send_from_directory


@dataclass
class DiaryMediaRouteServices:
    ensure_diary_image_thumbnail: object
    resolve_diary_generated_video_path: object
    resolve_diary_media_path: object


def create_diary_media_blueprint(services):
    bp = Blueprint("diary_media_routes", __name__)

    @bp.route("/diary-media/<int:diary_id>/<path:filename>")
    def diary_media_file(diary_id, filename):
        media_folder, file_path = services.resolve_diary_media_path(diary_id, filename)
        if not file_path or not os.path.exists(file_path):
            abort(404)
        return send_from_directory(media_folder, os.path.basename(file_path))

    @bp.route("/diary-generated-video/<int:diary_id>/<path:filename>")
    def diary_generated_video_file(diary_id, filename):
        video_folder, file_path = services.resolve_diary_generated_video_path(diary_id, filename)
        if not file_path or not os.path.exists(file_path):
            abort(404)
        return send_from_directory(
            video_folder,
            os.path.basename(file_path),
            mimetype="video/mp4",
            as_attachment=request.args.get("download", "").strip() == "1",
        )

    @bp.route("/diary-media-thumb/<int:diary_id>/<path:filename>")
    def diary_media_thumbnail_file(diary_id, filename):
        thumb_path = services.ensure_diary_image_thumbnail(diary_id, filename)
        if not thumb_path:
            media_folder, file_path = services.resolve_diary_media_path(diary_id, filename)
            if not file_path or not os.path.exists(file_path):
                abort(404)
            return send_from_directory(media_folder, os.path.basename(file_path))
        return send_from_directory(os.path.dirname(thumb_path), os.path.basename(thumb_path))

    return bp
