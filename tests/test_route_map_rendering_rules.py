import unittest
from pathlib import Path


class RouteMapRenderingRulesTests(unittest.TestCase):
    def test_mixed_route_rendering_smooths_snap_link_segments(self):
        script = Path("static/route_map.js").read_text(encoding="utf-8")

        self.assertIn("function isSnapLinkEdge(edge)", script)
        self.assertIn("function routeDisplaySegments(edges)", script)
        self.assertIn("routeModeForEdge(edge, index, edges)", script)
        self.assertIn("routeDisplaySegments(routeEdges)", script)


if __name__ == "__main__":
    unittest.main()
