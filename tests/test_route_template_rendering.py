import unittest

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


if __name__ == "__main__":
    unittest.main()
