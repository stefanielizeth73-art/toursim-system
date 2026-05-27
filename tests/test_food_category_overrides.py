import unittest

from app import (
    build_food_candidates_for_place,
    load_route_graph,
    rank_food_candidates,
)


class FoodCategoryOverrideTests(unittest.TestCase):
    def test_media_cuisine_overrides_graph_node_category(self):
        foods = build_food_candidates_for_place("xmu_manual")
        target = next(
            food for food in foods if food.get("food_key") == "xmu_manual_graph_node_route_point___116"
        )

        self.assertEqual(target["name"], "一口星球")
        self.assertEqual(target["category"], "西餐")
        self.assertEqual(target["cuisine"], "西餐")
        self.assertNotIn("食堂", target.get("visible_tags", []))

    def test_yikou_planet_moves_from_canteen_to_western_filter(self):
        foods = build_food_candidates_for_place("xmu_manual")
        graph = load_route_graph("xmu_manual")

        canteen_foods, _ = rank_food_candidates(
            foods,
            category="食堂",
            sort_by="recommend_score_desc",
            graph=graph,
            origin_node="",
        )
        western_foods, _ = rank_food_candidates(
            foods,
            category="西餐",
            sort_by="recommend_score_desc",
            graph=graph,
            origin_node="",
        )

        self.assertNotIn("一口星球", {food["name"] for food in canteen_foods})
        self.assertIn("一口星球", {food["name"] for food in western_foods})


if __name__ == "__main__":
    unittest.main()
