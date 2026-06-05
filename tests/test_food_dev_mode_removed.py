import os
import re
import unittest

import app as toursim_app
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

    def test_food_page_title_uses_source_place_name(self):
        response = self.client.get("/foods?place_id=xmu_manual&place_name=%E9%BC%93%E6%B5%AA%E5%B1%BF")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("<title>鼓浪屿美食推荐</title>", html)
        self.assertIn('<h1 id="foodPageTitle">鼓浪屿美食推荐</h1>', html)
        self.assertIn('name="place_name" value="鼓浪屿"', html)
        self.assertIn("place_name=%E9%BC%93%E6%B5%AA%E5%B1%BF", html)
        self.assertIn("food-card", html)

    def test_food_detail_navigation_preserves_food_target_for_route_map(self):
        food = next(
            item for item in toursim_app.build_food_candidates_for_place("xmu_manual")
            if item.get("nearest_node")
        )
        response = self.client.get(
            f"/food/{food['food_key']}",
            query_string={
                "place_id": "xmu_manual",
                "origin_node": toursim_app.get_food_origin_node("xmu_manual"),
            },
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("return_to=food_detail", html)
        self.assertIn(f"return_food_key={food['food_key']}", html)
        self.assertIn("return_place_id=xmu_manual", html)

    def test_food_detail_facility_link_uses_restaurant_as_facility_query_start(self):
        food = next(
            item for item in toursim_app.build_food_candidates_for_place("xmu_manual")
            if item.get("nearest_node")
        )
        response = self.client.get(
            f"/food/{food['food_key']}",
            query_string={"place_id": "xmu_manual"},
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("active_panel=places", html)
        self.assertIn(f"facility_start_node=food%3A{food['food_key']}", html)
        self.assertIn(f"facility_start_food={food['food_key']}", html)
        self.assertNotIn("facility_query=1", html)
        self.assertIn("#facilityResults", html)
        facility_href = re.search(r'href="([^"]*active_panel=places[^"]*#facilityResults)"', html)
        self.assertIsNotNone(facility_href)
        self.assertNotIn("return_to=food_detail", facility_href.group(1))
        self.assertNotIn("return_food_key=", facility_href.group(1))


if __name__ == "__main__":
    unittest.main()
