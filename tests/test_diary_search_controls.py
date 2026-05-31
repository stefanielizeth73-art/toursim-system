import os
import tempfile
import unittest

import app as toursim_app


class DiarySearchControlsTests(unittest.TestCase):
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
            session["username"] = "search_tester"

    def tearDown(self):
        toursim_app.DB_PATH = self.old_db_path
        toursim_app.SEED_DB_PATH = self.old_seed_db_path
        toursim_app.DIARY_UPLOAD_DIR = self.old_upload_dir
        toursim_app.DIARY_INDEX_CACHE.clear()
        toursim_app.DIARY_INDEX_CACHE.update(self.old_cache)
        self.temp_dir.cleanup()

    def test_search_page_exposes_all_algorithm_controls(self):
        response = self.client.get("/diaries/search")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-diary-search-console", html)
        self.assertIn('name="title_query"', html)
        self.assertIn('name="search_mode"', html)
        self.assertIn('value="exact"', html)
        self.assertIn('value="prefix"', html)
        self.assertIn('value="contains"', html)
        self.assertIn('name="keyword"', html)
        self.assertIn('name="destination"', html)
        self.assertIn('name="sort_by"', html)
        self.assertIn('value="hot_rating_desc"', html)
        self.assertIn('value="views_desc"', html)
        self.assertIn('value="rating_desc"', html)

    def test_diary_feed_uses_media_thumbnails_for_cover_images(self):
        diary_id = toursim_app.create_diary("thumbnail diary", "campus", "body", "alice")
        toursim_app.update_diary_media(
            diary_id,
            [{"filename": "cover.jpg", "original_name": "cover.jpg", "kind": "image", "size": 10}],
        )

        response = self.client.get("/diaries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(f"/diary-media-thumb/{diary_id}/cover.jpg?v=", html)
        self.assertIn('decoding="async"', html)

    def test_diary_feed_defers_images_after_initial_rows(self):
        for index in range(10):
            diary_id = toursim_app.create_diary(f"thumbnail diary {index}", "campus", "body", "alice")
            toursim_app.update_diary_media(
                diary_id,
                [{"filename": f"cover-{index}.jpg", "original_name": f"cover-{index}.jpg", "kind": "image", "size": 10}],
            )

        response = self.client.get("/diaries")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data-diary-lazy-src", html)
        self.assertIn("data:image/svg+xml", html)

    def test_diary_feed_paginates_cards_to_reduce_initial_render_cost(self):
        for index in range(15):
            toursim_app.create_diary(f"paged diary {index}", "campus", "body", "alice")

        total_diaries = len(toursim_app.load_diaries(sort_by="hot_rating_desc"))
        first_page = self.client.get("/diaries")
        second_page = self.client.get("/diaries?page=2")
        first_html = first_page.get_data(as_text=True)
        second_html = second_page.get_data(as_text=True)

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(first_html.count("js-diary-entry"), min(total_diaries, toursim_app.DIARIES_PAGE_SIZE))
        self.assertEqual(
            second_html.count("js-diary-entry"),
            min(toursim_app.DIARIES_PAGE_SIZE, max(total_diaries - toursim_app.DIARIES_PAGE_SIZE, 0)),
        )
        self.assertIn("diary-pagination", first_html)

    def test_search_page_applies_title_content_destination_and_sorting(self):
        toursim_app.create_diary("湖边慢游", "西湖", "沿着湖边看荷花", "alice")
        hot_id = toursim_app.create_diary("湖边夜游", "西湖", "夜晚灯光和湖面倒影", "bob")
        toursim_app.create_diary("校园散步", "厦门大学", "图书馆和芙蓉湖", "carol")
        for _ in range(4):
            toursim_app.get_diary_by_id(hot_id, increase_views=True)

        response = self.client.get(
            "/diaries/search?title_query=湖边&search_mode=prefix&keyword=湖面&destination=西湖&sort_by=views_desc"
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("湖边夜游", html)
        self.assertNotIn("湖边慢游", html)
        self.assertNotIn("校园散步", html)
        self.assertIn("热度优先", html)
        self.assertIn("前缀模糊", html)


if __name__ == "__main__":
    unittest.main()
