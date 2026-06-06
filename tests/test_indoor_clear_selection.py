import unittest
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

from app import app


class ClearActionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.clear_actions = []
        self.form_stack = []
        self.home_links = []
        self.node_links = []
        self.pick_mode_links = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "form":
            self.form_stack.append(attrs_dict.get("id", ""))
        classes = attrs_dict.get("class", "").split()
        if "indoor-clear-action" in classes:
            attrs_dict["_form_id"] = self.form_stack[-1] if self.form_stack else ""
            self.clear_actions.append((tag, attrs_dict))
        if "indoor-home-pill" in classes:
            self.home_links.append((tag, attrs_dict))
        if "indoor-node-link" in classes:
            self.node_links.append((tag, attrs_dict))
        if tag == "a" and attrs_dict.get("data-indoor-pick-mode"):
            self.pick_mode_links.append((tag, attrs_dict))

    def handle_endtag(self, tag):
        if tag == "form" and self.form_stack:
            self.form_stack.pop()


def query_for(href):
    return parse_qs(urlparse(href).query)


class IndoorClearSelectionTests(unittest.TestCase):
    def test_clear_selection_is_a_local_button_outside_route_form(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get("/indoor?building_id=demo_building&building_name=Demo&vertical_mode=stairs")
        html = response.get_data(as_text=True)
        parser = ClearActionParser()
        parser.feed(html)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("重新规划", html)
        self.assertNotIn('form="indoorRouteForm"', html)
        self.assertEqual(len(parser.clear_actions), 1)
        tag, attrs = parser.clear_actions[0]
        self.assertEqual(tag, "button")
        self.assertEqual(attrs.get("type"), "button")
        self.assertNotIn("onclick", attrs)
        self.assertNotIn("href", attrs)
        self.assertNotIn("data-indoor-clear", attrs)
        self.assertIn("data-indoor-clear-selection", attrs)
        self.assertNotEqual(attrs.get("_form_id"), "indoorRouteForm")

    def test_indoor_script_keeps_clear_local_and_point_links_clickable(self):
        with open("static/interaction.js", "r", encoding="utf-8") as file:
            script = file.read()

        self.assertNotIn("clearIndoorRouteSelection", script)
        self.assertNotIn("indoor-clear-action", script)
        self.assertNotIn("clear=1", script)
        self.assertIn('document.querySelector("[data-indoor-clear-selection]")', script)
        self.assertIn('url.searchParams.delete("start")', script)
        self.assertIn('url.searchParams.delete("end")', script)
        self.assertIn('url.searchParams.delete("clear")', script)
        self.assertIn("is-near-cursor", script)
        self.assertIn("indoor-node-focus-tooltip", script)
        self.assertIn('document.querySelectorAll(".indoor-node-link[data-node-id]")', script)
        self.assertIn('window.location.assign(href)', script)
        self.assertNotIn("selectIndoorMarker", script)
        self.assertNotIn("findNearestIndoorMarker", script)
        self.assertNotIn("nodeFocusTooltip", script)
        self.assertNotIn("stopImmediatePropagation", script)
        self.assertNotIn(".indoor-node-marker[data-node-id]", script)

    def test_map_nodes_are_real_links_for_no_js_selection(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get(
            "/indoor?building_id=demo_building&building_name=Demo"
            "&vertical_mode=stairs&clear=1"
        )
        html = response.get_data(as_text=True)
        parser = ClearActionParser()
        parser.feed(html)
        start_link = next(
            attrs for tag, attrs in parser.node_links
            if attrs.get("data-node-id") == "indoor_1f_005"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(start_link.get("data-node-pick-target"), "start")
        start_query = query_for(start_link.get("href", ""))
        self.assertEqual(start_query.get("start"), ["indoor_1f_005"])
        self.assertEqual(start_query.get("pick_mode"), ["end"])
        self.assertNotIn("end", start_query)

        response = client.get(
            "/indoor?building_id=demo_building&building_name=Demo"
            "&vertical_mode=stairs&start=indoor_1f_005&pick_mode=end"
        )
        html = response.get_data(as_text=True)
        parser = ClearActionParser()
        parser.feed(html)
        end_link = next(
            attrs for tag, attrs in parser.node_links
            if attrs.get("data-node-id") == "indoor_1f_012"
        )
        end_query = query_for(end_link.get("href", ""))
        self.assertEqual(end_link.get("data-node-pick-target"), "end")
        self.assertEqual(end_query.get("start"), ["indoor_1f_005"])
        self.assertEqual(end_query.get("end"), ["indoor_1f_012"])
        self.assertEqual(end_query.get("pick_mode"), ["start"])

    def test_selected_core_nodes_render_endpoint_state_classes(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get(
            "/indoor?building_id=demo_building&building_name=Demo"
            "&start=indoor_1f_001&end=indoor_1f_003&vertical_mode=stairs"
        )
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            html,
            re.compile(
                r'class="indoor-node-marker[^"]*\bis-elevator\b[^"]*\bis-start\b[^"]*"'
                r'[^>]*data-node-id="indoor_1f_001"',
                re.S,
            ),
        )
        self.assertRegex(
            html,
            re.compile(
                r'class="indoor-node-marker[^"]*\bis-stairs\b[^"]*\bis-end\b[^"]*"'
                r'[^>]*data-node-id="indoor_1f_003"',
                re.S,
            ),
        )

    def test_clear_result_page_does_not_render_home_link(self):
        client = app.test_client()
        with client.session_transaction() as session:
            session["username"] = "2024211326"

        response = client.get("/indoor?building_id=demo_building&building_name=Demo&vertical_mode=stairs&clear=1")
        html = response.get_data(as_text=True)
        parser = ClearActionParser()
        parser.feed(html)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(parser.home_links, [])
        self.assertNotIn('href="/home"', html)


if __name__ == "__main__":
    unittest.main()
