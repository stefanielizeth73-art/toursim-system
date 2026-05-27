import io
import os
import tempfile
import unittest

import app as toursim_app


class DiaryDevEditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = toursim_app.DB_PATH
        self.old_seed_db_path = toursim_app.SEED_DB_PATH
        self.old_upload_dir = toursim_app.DIARY_UPLOAD_DIR
        self.old_cache = dict(toursim_app.DIARY_INDEX_CACHE)

        toursim_app.DB_PATH = os.path.join(self.temp_dir.name, "test-tourism.db")
        toursim_app.SEED_DB_PATH = os.path.join(self.temp_dir.name, "missing-seed.db")
        toursim_app.DIARY_UPLOAD_DIR = os.path.join(self.temp_dir.name, "diary-media")
        toursim_app.invalidate_diary_index_cache()
        toursim_app.initialize_database()

        self.client = toursim_app.app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "internal_tester"

    def tearDown(self):
        toursim_app.DB_PATH = self.old_db_path
        toursim_app.SEED_DB_PATH = self.old_seed_db_path
        toursim_app.DIARY_UPLOAD_DIR = self.old_upload_dir
        toursim_app.DIARY_INDEX_CACHE.clear()
        toursim_app.DIARY_INDEX_CACHE.update(self.old_cache)
        self.temp_dir.cleanup()

    def test_logged_in_user_can_update_diary_text_fields_from_temporary_editor(self):
        diary_id = toursim_app.create_diary(
            "原始标题",
            "原始目的地",
            "原始正文",
            "someone_else",
            compression_algorithm="huffman",
        )

        response = self.client.post(
            f"/diary/{diary_id}/dev-edit",
            data={
                "title": "答辩演示标题",
                "destination": "答辩演示地点",
                "content": "答辩演示正文，已经临时修改。",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(f"/diary/{diary_id}", response.headers["Location"])
        with toursim_app.app.test_request_context():
            edited = toursim_app.get_diary_by_id(diary_id, increase_views=False)
        self.assertEqual(edited["title"], "答辩演示标题")
        self.assertEqual(edited["destination"], "答辩演示地点")
        self.assertEqual(edited["content"], "答辩演示正文，已经临时修改。")
        self.assertEqual(edited["compression"]["algorithm"], "huffman")

    def test_temporary_editor_can_remove_existing_media_and_append_uploads(self):
        diary_id = toursim_app.create_diary(
            "带媒体日记",
            "校园",
            "正文",
            "someone_else",
        )
        existing_media = [
            {"filename": "keep.jpg", "original_name": "keep.jpg", "kind": "image", "size": 10},
            {"filename": "remove.jpg", "original_name": "remove.jpg", "kind": "image", "size": 10},
        ]
        toursim_app.update_diary_media(diary_id, existing_media)

        response = self.client.post(
            f"/diary/{diary_id}/dev-edit",
            data={
                "title": "带媒体日记",
                "destination": "校园",
                "content": "正文",
                "remove_media": ["remove.jpg"],
                "attachments": (io.BytesIO(b"demo image"), "new-demo.jpg"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        with toursim_app.app.test_request_context():
            edited = toursim_app.get_diary_by_id(diary_id, increase_views=False)
        filenames = [item["filename"] for item in edited["media_items"]]
        original_names = [item["original_name"] for item in edited["media_items"]]
        self.assertIn("keep.jpg", filenames)
        self.assertNotIn("remove.jpg", filenames)
        self.assertIn("new-demo.jpg", original_names)

    def test_temporary_editor_renders_application_media_manager_controls(self):
        diary_id = toursim_app.create_diary(
            "带媒体管理器日记",
            "校园",
            "正文",
            "someone_else",
        )
        toursim_app.update_diary_media(
            diary_id,
            [
                {"filename": "one.jpg", "original_name": "one.jpg", "kind": "image", "size": 10},
                {"filename": "two.jpg", "original_name": "two.jpg", "kind": "image", "size": 10},
            ],
        )

        response = self.client.get(f"/diary/{diary_id}/dev-edit")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("diary_dev_edit.js", html)
        self.assertIn("data-dev-media-manager", html)
        self.assertIn("data-dev-file-input", html)
        self.assertIn("data-dev-file-preview-list", html)
        self.assertIn("data-dev-select-all", html)
        self.assertIn("data-dev-clear-selection", html)
        self.assertIn("data-dev-remove-count", html)
        self.assertIn('name="attachments"', html)
        self.assertIn("multiple", html)


if __name__ == "__main__":
    unittest.main()
