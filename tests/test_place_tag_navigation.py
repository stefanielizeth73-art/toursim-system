import html
import re
import unittest
from urllib.parse import quote

import app as toursim_app
from app import app


class PlaceTagNavigationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "2024211326"

    def test_place_detail_tag_links_to_places_with_preferred_tag_checked(self):
        place = next(item for item in toursim_app.load_places() if item.get("tags_list"))
        tag = place["tags_list"][0]

        detail_response = self.client.get(f"/place/{place['id']}")
        detail_html = detail_response.get_data(as_text=True)

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(f"/places?preferred_tags={quote(tag)}", detail_html)
        self.assertNotIn(f"tag_keyword={quote(tag)}", detail_html)

        places_response = self.client.get("/places", query_string={"preferred_tags": tag})
        places_html = places_response.get_data(as_text=True)
        escaped_tag = html.escape(tag, quote=True)

        self.assertEqual(places_response.status_code, 200)
        self.assertRegex(
            places_html,
            rf'name="preferred_tags"\s+value="{re.escape(escaped_tag)}"\s+checked',
        )


if __name__ == "__main__":
    unittest.main()
