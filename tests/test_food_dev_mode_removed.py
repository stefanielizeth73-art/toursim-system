import os
import unittest

from app import app


class FoodDeveloperModeRemovedTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "2024211326"

    def test_food_pages_do_not_render_developer_mode_assets_or_controls(self):
        urls = [
            "/foods?place_id=xmu_manual&keyword=&category=%E9%A3%9F%E5%A0%82",
            "/food/xmu_manual_graph_node_route_point___116?place_id=xmu_manual",
        ]

        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                html = response.get_data(as_text=True)

                self.assertEqual(response.status_code, 200)
                self.assertNotIn("food_dev_tools.js", html)
                self.assertNotIn("data-food-dev", html)
                self.assertNotIn("food-dev-", html)

    def test_food_media_update_api_is_not_registered(self):
        rules = {rule.rule for rule in app.url_map.iter_rules()}

        self.assertNotIn("/api/food-media/<food_key>/update", rules)

    def test_food_dev_tools_script_is_removed(self):
        self.assertFalse(os.path.exists(os.path.join(app.root_path, "static", "food_dev_tools.js")))


if __name__ == "__main__":
    unittest.main()
