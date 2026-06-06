import os
import time

from PIL import Image

import app as toursim_app
from toursim.diary_media import diary_thumbnail_filename


def test_diary_thumbnail_filename_is_stable_across_mtime_changes(tmp_path):
    source = tmp_path / "cover.jpg"
    source.write_bytes(b"same-image-bytes")

    first_name = diary_thumbnail_filename(source)

    later = time.time() + 3600
    os.utime(source, (later, later))
    second_name = diary_thumbnail_filename(source)

    assert second_name == first_name


def test_ensure_diary_image_thumbnail_creates_usable_thumbnail(tmp_path):
    old_upload_dir = toursim_app.DIARY_UPLOAD_DIR
    old_thumbnail_dirname = toursim_app.DIARY_THUMBNAIL_DIRNAME
    old_thumbnail_version = toursim_app.DIARY_THUMBNAIL_VERSION
    old_thumbnail_max_size = toursim_app.DIARY_THUMBNAIL_MAX_SIZE
    old_thumbnail_quality = toursim_app.DIARY_THUMBNAIL_JPEG_QUALITY

    try:
        toursim_app.DIARY_UPLOAD_DIR = str(tmp_path)
        toursim_app.DIARY_THUMBNAIL_DIRNAME = "_thumbs_test"
        toursim_app.DIARY_THUMBNAIL_VERSION = "test"
        toursim_app.DIARY_THUMBNAIL_MAX_SIZE = (120, 90)
        toursim_app.DIARY_THUMBNAIL_JPEG_QUALITY = 75

        diary_folder = tmp_path / "7"
        diary_folder.mkdir()
        source = diary_folder / "cover.jpg"
        Image.new("RGB", (800, 600), color=(80, 120, 160)).save(source, "JPEG")

        thumb_path = toursim_app.ensure_diary_image_thumbnail(7, "cover.jpg")

        assert thumb_path
        assert os.path.exists(thumb_path)
        with Image.open(thumb_path) as image:
            assert image.size[0] <= 120
            assert image.size[1] <= 90
    finally:
        toursim_app.DIARY_UPLOAD_DIR = old_upload_dir
        toursim_app.DIARY_THUMBNAIL_DIRNAME = old_thumbnail_dirname
        toursim_app.DIARY_THUMBNAIL_VERSION = old_thumbnail_version
        toursim_app.DIARY_THUMBNAIL_MAX_SIZE = old_thumbnail_max_size
        toursim_app.DIARY_THUMBNAIL_JPEG_QUALITY = old_thumbnail_quality
