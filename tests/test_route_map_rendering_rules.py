import unittest
from pathlib import Path


class RouteMapRenderingRulesTests(unittest.TestCase):
    def test_mixed_route_rendering_smooths_snap_link_segments(self):
        script = Path("static/route_map.js").read_text(encoding="utf-8")

        self.assertIn("function isSnapLinkEdge(edge)", script)
        self.assertIn("function routeDisplaySegments(edges)", script)
        self.assertIn("routeModeForEdge(edge, index, edges)", script)
        self.assertIn("routeDisplaySegments(routeEdges)", script)

    def test_food_route_target_marker_renders_independent_of_facility_layer(self):
        script = Path("static/route_map.js").read_text(encoding="utf-8")

        self.assertIn("const pinnedFacility = data.pinnedFacility || null", script)
        self.assertIn("const pinnedFacilityMarkers = []", script)
        self.assertIn("function redrawPinnedFacilityMarker()", script)
        self.assertIn("redrawPinnedFacilityMarker();", script)
        self.assertIn("if (isPinnedFacility(facility))", script)
        self.assertIn("route-planning-badge is-end is-food-target", script)
        self.assertIn("\\u7ec8", script)

    def test_facility_query_results_auto_render_on_map(self):
        script = Path("static/route_map.js").read_text(encoding="utf-8")

        self.assertIn("const facilityQuery = data.facilityQuery || {}", script)
        self.assertIn("const queryFacilityResults = data.facilityResults || []", script)
        self.assertIn("facilityQuery.active && queryFacilityResults.length", script)
        self.assertIn("function redrawFacilityQueryStartMarker()", script)
        self.assertIn("route-planning-badge is-start is-facility-query-start", script)
        self.assertIn("facilityStartSearch", script)

    def test_food_facility_entry_uses_temporary_current_location_hint(self):
        script = Path("static/route_map.js").read_text(encoding="utf-8")

        self.assertIn("const facilityEntryStartMarkers = []", script)
        self.assertIn("const facilityEntryHintMarkers = []", script)
        self.assertIn("function showFacilityEntryHint()", script)
        self.assertIn("route-current-location-hint", script)
        self.assertIn("map.add(facilityEntryStartMarkers)", script)
        self.assertIn("您当前在这", script)
        self.assertIn("}, 2000);", script)


if __name__ == "__main__":
    unittest.main()
