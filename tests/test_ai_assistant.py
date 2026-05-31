import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

from app import app


class AiAssistantTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def login(self):
        with self.client.session_transaction() as session:
            session["username"] = "2024211326"

    def test_assistant_chat_requires_login(self):
        response = self.client.post("/api/assistant/chat", json={"message": "想吃饭"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"], "请先登录")

    @mock.patch.dict(os.environ, {"AI_ASSISTANT_ENABLED": "1"}, clear=False)
    def test_assistant_chat_without_api_key_returns_local_food_cards(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        self.login()

        response = self.client.post(
            "/api/assistant/chat",
            json={
                "message": "我现在想找一个近一点的食堂吃饭，预算15元",
                "page_context": {"page": "foods", "place_id": "xmu_manual"},
            },
        )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["provider"], "local")
        self.assertGreaterEqual(len(payload["cards"]), 1)
        self.assertEqual(payload["cards"][0]["type"], "food")
        self.assertIn("/food/", payload["cards"][0]["url"])
        self.assertIn("suggestions", payload)

    def test_food_tool_returns_structured_cards_and_actions(self):
        from app import ai_tool_recommend_foods

        result = ai_tool_recommend_foods(
            {
                "keyword": "食堂",
                "budget": 15,
                "place_id": "xmu_manual",
                "limit": 3,
            }
        )

        self.assertEqual(result["type"], "food_recommendations")
        self.assertGreaterEqual(len(result["cards"]), 1)
        self.assertLessEqual(len(result["cards"]), 3)
        self.assertIn("title", result["cards"][0])
        self.assertIn("url", result["cards"][0])
        self.assertTrue(any(action["kind"] == "apply_food_filter" for action in result["actions"]))
        self.assertEqual(result["actions"][0]["command"]["type"], "food_filter")

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_local_assistant_handles_natural_light_food_request(self):
        from app import ai_local_assistant_payload

        result = ai_local_assistant_payload(
            "我现在好饿，想吃点清淡的东西",
            {"page": "home", "place_id": "xmu_manual"},
        )

        self.assertEqual(result["mode"], "system")
        self.assertIn("food", result["modules"])
        self.assertGreaterEqual(len(result["cards"]), 1)
        self.assertIn("清淡", result["answer"])

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_local_assistant_does_not_trigger_tools_for_greeting(self):
        from app import ai_local_assistant_payload

        result = ai_local_assistant_payload(
            "你好呀",
            {"page": "home", "place_id": "xmu_manual"},
        )

        self.assertEqual(result["mode"], "general")
        self.assertEqual(result["cards"], [])
        self.assertEqual(result["tool_results"], [])
        self.assertIn("你好", result["answer"])

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_local_assistant_triggers_food_tool_with_explicit_module_keywords(self):
        from app import ai_local_assistant_payload

        result = ai_local_assistant_payload(
            "帮我查一下校园美食推荐，想吃清淡点",
            {"page": "home", "place_id": "xmu_manual"},
        )

        self.assertEqual(result["mode"], "system")
        self.assertGreaterEqual(len(result["cards"]), 1)
        self.assertTrue(result["tool_results"])

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_rag_fallback_triggers_food_for_natural_recommendation(self):
        from app import ai_local_assistant_payload

        result = ai_local_assistant_payload(
            "想吃点清淡的，有啥推荐吗",
            {"page": "home", "place_id": "xmu_manual"},
        )

        self.assertEqual(result["mode"], "system")
        self.assertIn("food", result["modules"])
        self.assertGreaterEqual(len(result["cards"]), 1)
        self.assertTrue(result["retrieved_context"])

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_assistant_history_restores_latest_conversation(self):
        self.login()

        chat_response = self.client.post(
            "/api/assistant/chat",
            json={
                "message": "想吃点清淡的，有啥推荐吗",
                "page_context": {"page": "home", "place_id": "xmu_manual"},
            },
        )
        chat_payload = chat_response.get_json()
        conversation_id = chat_payload["conversation_id"]

        history_response = self.client.get(
            f"/api/assistant/history?conversation_id={conversation_id}"
        )
        history_payload = history_response.get_json()

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_payload["conversation_id"], conversation_id)
        self.assertGreaterEqual(len(history_payload["messages"]), 2)
        self.assertEqual(history_payload["messages"][-2]["role"], "user")
        self.assertEqual(history_payload["messages"][-1]["role"], "assistant")
        self.assertEqual(history_payload["messages"][-1]["metadata"]["provider"], "local")

        latest_response = self.client.get("/api/assistant/history")
        latest_payload = latest_response.get_json()
        self.assertEqual(latest_payload["conversation_id"], conversation_id)

    def test_context_memory_bundle_keeps_previous_system_results(self):
        from app import ai_context_memory_bundle

        bundle = ai_context_memory_bundle([
            {"role": "user", "content": "想吃清淡点", "metadata": {}, "created_at": "2026-05-27 10:00:00"},
            {
                "role": "assistant",
                "content": "可以看看一树",
                "created_at": "2026-05-27 10:00:01",
                "metadata": {
                    "mode": "system",
                    "modules": ["food"],
                    "cards": [{"type": "food", "title": "一树", "description": "清淡茶饮", "url": "/food/demo"}],
                    "actions": [{"kind": "open_foods", "label": "打开美食推荐", "url": "/foods"}],
                },
            },
        ])

        self.assertEqual(bundle["last_system_modules"], ["food"])
        self.assertEqual(bundle["last_cards"][0]["title"], "一树")
        self.assertEqual(bundle["last_actions"][0]["kind"], "open_foods")

    def test_route_tool_extracts_names_and_defaults_to_mixed_command(self):
        from app import ai_tool_plan_route, load_route_graph

        graph = load_route_graph("xmu_manual")
        names = [node["name"] for node in graph.get("nodes", []) if node.get("name")]
        self.assertGreaterEqual(len(names), 2)

        result = ai_tool_plan_route({
            "place_id": "xmu_manual",
            "keyword": f"从{names[0]}到{names[1]}怎么走",
        })

        self.assertEqual(result["type"], "route_plan")
        self.assertTrue(result["actions"])
        action = result["actions"][0]
        self.assertEqual(action["kind"], "apply_route_plan")
        self.assertEqual(action["command"]["type"], "route_plan")
        self.assertEqual(action["command"]["params"]["transport"], "mixed")

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_route_message_overrides_stale_page_context(self):
        from app import ai_local_assistant_payload

        result = ai_local_assistant_payload(
            "帮我看看从快递服务中心到金泉楼怎么走",
            {
                "page": "route",
                "place_id": "xmu_manual",
                "start": "route_point_南门_099",
                "end": "route_point_德旺图书馆_100",
                "transport": "mixed",
            },
            [],
        )

        action = result["actions"][0]
        params = action["command"]["params"]
        self.assertEqual(params["start"], "route_point_快递服务中心_080")
        self.assertEqual(params["end"], "route_point_金泉楼_130")
        self.assertTrue(result["cards"])

    @mock.patch("app.ai_provider_answer", return_value="现在看到的路线还是上一轮南门到德旺图书馆，暂时没法规划。")
    def test_chat_api_keeps_executable_route_answer_over_model_contradiction(self, mocked_answer):
        self.login()

        response = self.client.post(
            "/api/assistant/chat",
            json={
                "message": "帮我看看从快递服务中心到金泉楼怎么走",
                "page_context": {
                    "page": "route",
                    "place_id": "xmu_manual",
                    "start": "route_point_南门_099",
                    "end": "route_point_德旺图书馆_100",
                },
            },
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        mocked_answer.assert_not_called()
        self.assertEqual(payload["provider"], "local")
        self.assertIn("快递服务中心", payload["answer"])
        self.assertIn("金泉楼", payload["answer"])
        params = payload["actions"][0]["command"]["params"]
        self.assertEqual(params["start"], "route_point_快递服务中心_080")
        self.assertEqual(params["end"], "route_point_金泉楼_130")

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_route_followup_reuses_recent_chat_endpoints(self):
        from app import ai_local_assistant_payload

        history = [
            {
                "role": "user",
                "content": "从南门到主馆怎么走",
                "metadata": {},
                "created_at": "2026-05-29 10:00:00",
            },
            {
                "role": "assistant",
                "content": "如果你说的是德旺图书馆，那就是从南门到德旺图书馆。",
                "metadata": {"mode": "general", "modules": []},
                "created_at": "2026-05-29 10:00:01",
            },
        ]

        result = ai_local_assistant_payload(
            "直接规划该路线",
            {"page": "home", "place_id": "xmu_manual"},
            history,
        )

        self.assertEqual(result["mode"], "system")
        self.assertIn("route", result["modules"])
        self.assertTrue(result["cards"])
        action = result["actions"][0]
        self.assertEqual(action["kind"], "apply_route_plan")
        params = action["command"]["params"]
        self.assertIn("南门", params["start"])
        self.assertIn("德旺图书馆", params["end"])
        self.assertEqual(params["transport"], "mixed")

    @mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "", "OPENAI_API_KEY": "", "AI_PROVIDER": "deepseek"}, clear=False)
    def test_route_followup_reuses_last_route_action(self):
        from app import ai_local_assistant_payload

        history = [
            {
                "role": "assistant",
                "content": "已按当前图数据计算路线。",
                "metadata": {
                    "mode": "system",
                    "modules": ["route"],
                    "actions": [
                        {
                            "kind": "apply_route_plan",
                            "label": "自动规划并高亮路线",
                            "command": {
                                "type": "route_plan",
                                "params": {
                                    "place_id": "xmu_manual",
                                    "start": "route_point_南门_099",
                                    "end": "route_point_德旺图书馆_100",
                                    "transport": "mixed",
                                },
                            },
                        }
                    ],
                },
                "created_at": "2026-05-29 10:00:01",
            },
        ]

        result = ai_local_assistant_payload(
            "帮我打开并高亮",
            {"page": "home", "place_id": "xmu_manual"},
            history,
        )

        action = result["actions"][0]
        self.assertEqual(result["modules"], ["route"])
        self.assertEqual(action["command"]["params"]["end"], "route_point_德旺图书馆_100")

    def test_home_page_loads_assistant_assets_without_api_key(self):
        self.login()

        response = self.client.get("/home")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("ai_assistant.css", html)
        self.assertIn("ai_assistant.js", html)
        self.assertNotIn("OPENAI_API_KEY=", html)

    def test_deepseek_provider_uses_chat_completions_and_v4_pro_model(self):
        from app import ai_provider_answer

        captured = {}

        class FakeChatCompletions:
            def create(self, **kwargs):
                captured["create"] = kwargs
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content="DeepSeek answer")
                        )
                    ]
                )

        class FakeOpenAI:
            def __init__(self, **kwargs):
                captured["client"] = kwargs
                self.chat = SimpleNamespace(completions=FakeChatCompletions())

        fake_openai_module = SimpleNamespace(OpenAI=FakeOpenAI)
        env = {
            "AI_PROVIDER": "deepseek",
            "AI_MODEL": "deepseek-v4-pro",
            "AI_BASE_URL": "https://api.deepseek.com",
            "DEEPSEEK_API_KEY": "test-deepseek-key",
        }
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.dict(sys.modules, {"openai": fake_openai_module}):
            answer = ai_provider_answer(
                "我想吃饭",
                {"page": "foods"},
                {"answer": "local summary", "cards": [], "actions": []},
            )

        self.assertEqual(answer, "DeepSeek answer")
        self.assertEqual(captured["client"]["api_key"], "test-deepseek-key")
        self.assertEqual(captured["client"]["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["create"]["model"], "deepseek-v4-pro")
        self.assertIn("messages", captured["create"])
        self.assertNotIn("extra_body", captured["create"])
        self.assertEqual(captured["create"]["reasoning_effort"], "low")

    @mock.patch("app.ai_provider_answer", side_effect=RuntimeError("sdk missing"))
    def test_assistant_chat_reports_model_error_when_provider_fails(self, _mock_answer):
        self.login()

        response = self.client.post(
            "/api/assistant/chat",
            json={"message": "你好呀", "page_context": {"page": "home"}},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["provider"], "local")
        self.assertIn("sdk missing", payload["model_error"])


if __name__ == "__main__":
    unittest.main()
