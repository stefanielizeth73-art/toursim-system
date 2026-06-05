import unittest

import app as toursim_app
from app import app


class RouteTemplateRenderingTests(unittest.TestCase):
    def test_route_page_renders_executable_map_bootstrap_data(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get("/route?place_id=xmu_manual")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("window.routeMapData", html)
        self.assertNotIn("{ {", html)
        self.assertIn('placeId: "xmu_manual"', html)

    def test_route_sidebar_uses_rebuilt_console_sections(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get("/route?place_id=xmu_manual")
        html = response.get_data(as_text=True)

        self.assertIn("route-console-hero", html)
        self.assertIn("route-card route-card--planner", html)
        self.assertIn("route-endpoint-grid", html)
        self.assertIn("route-card route-card--places", html)

    def test_food_navigation_bootstrap_includes_pinned_target_facility(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        food = next(
            item for item in toursim_app.build_food_candidates_for_place("xmu_manual")
            if item.get("nearest_node")
        )
        response = client.get(
            "/route",
            query_string={
                "place_id": "xmu_manual",
                "start": toursim_app.get_food_origin_node("xmu_manual"),
                "end": food["nearest_node"],
                "strategy": "distance",
                "transport": "mixed",
                "return_to": "food_detail",
                "return_food_key": food["food_key"],
                "return_place_id": "xmu_manual",
            },
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("pinnedFacility", html)
        self.assertIn(food["food_key"], html)
        self.assertIn(food["name"], html)

    def test_facility_query_accepts_food_as_start_and_bootstraps_results(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        food = next(
            item for item in toursim_app.build_food_candidates_for_place("xmu_manual")
            if item.get("nearest_node")
        )
        response = client.get(
            "/route",
            query_string={
                "place_id": "xmu_manual",
                "active_panel": "places",
                "facility_start_node": f"food:{food['food_key']}",
                "facility_start_food": food["food_key"],
                "max_distance": "1000",
            },
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("facilityResults", html)
        self.assertIn("facilityQuery", html)
        self.assertIn(food["food_key"], html)
        self.assertIn("facilityStartSearch", html)
        self.assertIn(f'value="food:{food["food_key"]}"', html)

    def test_food_facility_entry_prefills_start_without_showing_results(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        food = next(
            item for item in toursim_app.build_food_candidates_for_place("xmu_manual")
            if item.get("nearest_node")
        )
        response = client.get(
            "/route",
            query_string={
                "place_id": "xmu_manual",
                "active_panel": "places",
                "facility_start_node": f"food:{food['food_key']}",
                "facility_start_food": food["food_key"],
            },
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("facilityStartSearch", html)
        self.assertIn(f'value="food:{food["food_key"]}"', html)
        self.assertIn("facilityResults: []", html)
        self.assertIn("active: false", html)
        self.assertIn('name="facility_query" value="1"', html)


if __name__ == "__main__":
    unittest.main()
