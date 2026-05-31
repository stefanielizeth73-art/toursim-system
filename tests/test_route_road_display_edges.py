import unittest
from unittest import mock

from app import (
    XMU_MANUAL_PLACE_ID,
    calculate_edge_weight,
    enforce_walk_only_snap_link,
    normalize_collector_link,
    road_display_edges_for_map,
)


class RouteRoadDisplayEdgesTests(unittest.TestCase):
    def test_manual_snap_links_default_to_walk_only(self):
        nodes = [
            {
                "id": "poi_a",
                "amap_lng": 118.1,
                "amap_lat": 24.1,
            }
        ]
        edges = [
            {
                "id": "edge_a",
                "amap_geometry": [[118.101, 24.101], [118.102, 24.102]],
            }
        ]

        link = normalize_collector_link({
            "a": {"type": "poi", "id": "poi_a"},
            "b": {"type": "road", "edge": "edge_a", "point_index": 0},
        }, nodes, edges)

        self.assertIs(link["walk"], True)
        self.assertIs(link["bike"], False)

    def test_saved_snap_link_edges_are_forced_to_walk_only_before_routing(self):
        edge = {
            "source": "manual_collector_link",
            "walk": False,
            "bike": True,
            "distance": 10,
            "congestion": 1,
        }

        enforce_walk_only_snap_link(edge)

        self.assertIs(edge["walk"], True)
        self.assertIs(edge["bike"], False)
        self.assertIsNone(calculate_edge_weight(edge, transport="bike"))

    def test_manual_road_display_edges_include_saved_snap_links(self):
        road_edge = {
            "id": "edge_a",
            "name": "Main walk",
            "road_type": "walkway",
            "walk": True,
            "bike": True,
            "amap_geometry": [[118.1, 24.1], [118.2, 24.2]],
        }
        snap_link = {
            "id": "link_a",
            "kind": "road_road",
            "walk": True,
            "bike": True,
            "amap_geometry": [[118.2, 24.2], [118.21, 24.21]],
            "source": "manual_collector_link",
        }

        with mock.patch("app.load_collector_edges", return_value=[road_edge]), \
                mock.patch("app.load_collector_links", return_value=[snap_link]):
            display_edges = road_display_edges_for_map({"place_id": XMU_MANUAL_PLACE_ID})

        self.assertEqual(["edge_a", "link_a"], [edge["id"] for edge in display_edges])
        self.assertEqual("manual_collector_link", display_edges[1]["source"])
        self.assertIs(display_edges[1]["bike"], False)


if __name__ == "__main__":
    unittest.main()
