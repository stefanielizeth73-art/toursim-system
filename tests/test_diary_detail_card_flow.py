import os
import tempfile
import unittest

import app as toursim_app


class DiaryDetailCardFlowTests(unittest.TestCase):
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
        toursim_app.create_user("detail_tester", "pass")

        self.client = toursim_app.app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "detail_tester"

    def tearDown(self):
        toursim_app.DB_PATH = self.old_db_path
        toursim_app.SEED_DB_PATH = self.old_seed_db_path
        toursim_app.DIARY_UPLOAD_DIR = self.old_upload_dir
        toursim_app.DIARY_INDEX_CACHE.clear()
        toursim_app.DIARY_INDEX_CACHE.update(self.old_cache)
        self.temp_dir.cleanup()

    def test_detail_page_uses_single_story_flow_card_for_right_rail_actions(self):
        diary_id = toursim_app.create_diary(
            "右侧信息流日记",
            "浙江大学紫金港校区",
            "校园里的路并不复杂，但真正走起来才发现，每一段都有自己的节奏。",
            "detail_tester",
            compression_algorithm="huffman",
        )

        response = self.client.get(f"/diary/{diary_id}?count_view=0")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("story-flow-card", html)
        self.assertIn("story-flow-section--rating", html)
        self.assertIn("story-flow-section--comments", html)
        self.assertIn("story-flow-section--compression", html)
        self.assertIn("<summary class=\"section-headline section-headline--compression\">", html)
        self.assertIn("文本压缩", html)
        self.assertIn("name=\"action\" value=\"compression\"", html)
        self.assertNotIn("story-surface-card story-surface-card--rating", html)
        self.assertNotIn("story-surface-card comments-panel", html)

    def test_detail_page_can_apply_compression_algorithm_without_changing_content(self):
        diary_id = toursim_app.create_diary(
            "压缩切换日记",
            "校园",
            "这一段正文用来验证压缩算法切换，但正文内容本身不能被改写。",
            "detail_tester",
            compression_algorithm="huffman",
        )
        before = toursim_app.get_diary_by_id(diary_id, increase_views=False)

        response = self.client.post(
            f"/diary/{diary_id}",
            data={"action": "compression", "compress_algorithm": "dictionary"},
            follow_redirects=True,
        )
        after = toursim_app.get_diary_by_id(diary_id, increase_views=False)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(after["content"], before["content"])
        self.assertEqual(after["compression"]["algorithm"], "dictionary")
        self.assertIn("文本压缩", response.get_data(as_text=True))

    def test_detail_page_does_not_expose_temporary_edit_entry(self):
        diary_id = toursim_app.create_diary(
            "普通详情日记",
            "校园",
            "详情页只保留正式的用户操作入口。",
            "detail_tester",
            compression_algorithm="huffman",
        )

        response = self.client.get(f"/diary/{diary_id}?count_view=0")
        html = response.get_data(as_text=True)
        legacy_response = self.client.get(f"/diary/{diary_id}/dev-edit")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("临时编辑", html)
        self.assertNotIn("diary_dev_edit", html)
        self.assertEqual(legacy_response.status_code, 404)

    def test_detail_page_allows_one_rating_per_user_per_diary(self):
        diary_id = toursim_app.create_diary(
            "单次评分日记",
            "校园",
            "用于验证同一个账号不能对同一篇日记反复评分。",
            "detail_tester",
            compression_algorithm="huffman",
        )

        first = self.client.post(
            f"/diary/{diary_id}",
            data={"action": "rating", "rating": "5"},
            follow_redirects=False,
        )
        second = self.client.post(
            f"/diary/{diary_id}",
            data={"action": "rating", "rating": "1"},
            follow_redirects=True,
        )

        conn = toursim_app.get_db_connection()
        row = conn.execute(
            "SELECT rating_total, rating_count FROM diaries WHERE id = ?",
            (diary_id,),
        ).fetchone()
        stored_rating = conn.execute(
            "SELECT rating FROM diary_ratings WHERE diary_id = ? AND username = ?",
            (diary_id, "detail_tester"),
        ).fetchone()
        conn.close()

        html = second.get_data(as_text=True)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(row["rating_total"], 5)
        self.assertEqual(row["rating_count"], 1)
        self.assertEqual(stored_rating["rating"], 5)
        self.assertIn("rating-bubbles-form is-rated", html)
        self.assertIn("disabled", html)


if __name__ == "__main__":
    unittest.main()
