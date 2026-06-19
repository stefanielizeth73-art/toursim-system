import html
import re
import unittest
from urllib.parse import parse_qs, quote, urlencode, urlsplit

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

    def test_preferred_tag_results_come_before_random_fillers(self):
        tag = "\u4e61\u6751\u7530\u56ed"
        places = toursim_app.load_places()
        expected_matches = [place for place in places if tag in place.get("tags_list", [])]

        recommended, stats = toursim_app.get_top_k_recommendations(
            places,
            preferred_tags=[tag],
            k=5,
        )

        self.assertGreater(len(expected_matches), 0)
        self.assertEqual(stats["candidate_count"], len(expected_matches))
        self.assertEqual(stats["returned_count"], 5)
        self.assertEqual(stats["random_fill_count"], 5 - len(expected_matches))
        self.assertTrue(all(tag in place.get("tags_list", []) for place in recommended[:len(expected_matches)]))
        self.assertTrue(all(place.get("is_random_fill") for place in recommended[len(expected_matches):]))
        self.assertEqual(
            len({place.get("id") for place in recommended}),
            len(recommended),
        )

    def test_unknown_preferred_tag_is_not_rendered_as_selected(self):
        response = self.client.get("/places", query_string={"preferred_tags": "不存在的标签"})
        html_text = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("不存在的标签", html_text)

    def test_top_k_layout_follows_requested_k_even_with_few_tag_matches(self):
        response = self.client.get("/places", query_string={"preferred_tags": "乡村田园", "k": "10"})
        html_text = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("places-contact-sheet--has-ten", html_text)
        self.assertNotIn("places-contact-sheet--top-five", html_text)

    def test_multiple_preferred_tags_rank_complete_matches_first(self):
        tags = ["\u6821\u56ed\u6f2b\u6b65", "\u4fe1\u606f\u79d1\u6280"]
        recommended, _stats = toursim_app.get_top_k_recommendations(
            toursim_app.load_places(),
            preferred_tags=tags,
            k=20,
        )
        match_counts = [
            sum(1 for tag in tags if tag in place.get("tags_list", []))
            for place in recommended
        ]

        self.assertIn(2, match_counts)
        self.assertIn(1, match_counts)
        first_partial_index = match_counts.index(1)
        self.assertTrue(all(count == 2 for count in match_counts[:first_partial_index]))
        self.assertTrue(all(count <= 1 for count in match_counts[first_partial_index:]))

    def test_place_detail_return_keeps_explore_state(self):
        query = urlencode({
            "preferred_tags": "\u6821\u56ed\u6f2b\u6b65",
            "k": "15",
            "page": "2",
        })
        places_response = self.client.get(f"/places?{query}")
        places_html = places_response.get_data(as_text=True)
        match = re.search(r'href="([^"]*return_url=[^"]*)"', places_html)

        self.assertEqual(places_response.status_code, 200)
        self.assertIsNotNone(match)

        detail_href = html.unescape(match.group(1))
        detail_query = parse_qs(urlsplit(detail_href).query)
        expected_return = f"/places?{query}#places-rank"

        self.assertEqual(detail_query["return_url"][0], expected_return)

        detail_response = self.client.get(detail_href)
        detail_html = detail_response.get_data(as_text=True)

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn(f'href="{html.escape(expected_return, quote=True)}"', detail_html)


if __name__ == "__main__":
    unittest.main()
