import os
import tempfile
import unittest
from unittest.mock import patch

import app as toursim_app


class DiaryVideoGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_db_path = toursim_app.DB_PATH
        self.old_seed_db_path = toursim_app.SEED_DB_PATH
        self.old_upload_dir = toursim_app.DIARY_UPLOAD_DIR
        self.old_generated_video_dir = toursim_app.DIARY_GENERATED_VIDEO_DIR
        self.old_cache = dict(toursim_app.DIARY_INDEX_CACHE)
        self.old_key = os.environ.get("DASHSCOPE_API_KEY")

        toursim_app.DB_PATH = os.path.join(self.temp_dir.name, "test-tourism.db")
        toursim_app.SEED_DB_PATH = os.path.join(self.temp_dir.name, "missing-seed.db")
        toursim_app.DIARY_UPLOAD_DIR = os.path.join(self.temp_dir.name, "diary-media")
        toursim_app.DIARY_GENERATED_VIDEO_DIR = os.path.join(self.temp_dir.name, "generated-video")
        os.environ["DASHSCOPE_API_KEY"] = "test-key"
        toursim_app.invalidate_diary_index_cache()
        toursim_app.initialize_database()

        self.client = toursim_app.app.test_client()
        with self.client.session_transaction() as session:
            session["username"] = "video_tester"

    def tearDown(self):
        toursim_app.DB_PATH = self.old_db_path
        toursim_app.SEED_DB_PATH = self.old_seed_db_path
        toursim_app.DIARY_UPLOAD_DIR = self.old_upload_dir
        toursim_app.DIARY_GENERATED_VIDEO_DIR = self.old_generated_video_dir
        toursim_app.DIARY_INDEX_CACHE.clear()
        toursim_app.DIARY_INDEX_CACHE.update(self.old_cache)
        if self.old_key is None:
            os.environ.pop("DASHSCOPE_API_KEY", None)
        else:
            os.environ["DASHSCOPE_API_KEY"] = self.old_key
        self.temp_dir.cleanup()

    def create_diary_with_image(self):
        diary_id = toursim_app.create_diary(
            "图文生视频测试",
            "浙江大学紫金港校区",
            "从校门进入，镜头沿着树影和教学楼慢慢推进。",
            "video_tester",
        )
        media_dir = toursim_app.diary_media_folder(diary_id)
        os.makedirs(media_dir, exist_ok=True)
        image_path = os.path.join(media_dir, "cover.jpg")
        if toursim_app.Image is not None:
            image = toursim_app.Image.new("RGB", (320, 240), (96, 132, 122))
            image.save(image_path, "JPEG")
        else:
            with open(image_path, "wb") as f:
                f.write(b"fake-image")
        toursim_app.update_diary_media(
            diary_id,
            [{"filename": "cover.jpg", "original_name": "cover.jpg", "kind": "image", "size": os.path.getsize(image_path)}],
        )
        return diary_id

    def test_start_video_generation_uses_first_diary_image_and_stores_task(self):
        diary_id = self.create_diary_with_image()

        with patch.object(toursim_app, "submit_bailian_image_to_video_task") as submit_task:
            submit_task.return_value = {"task_id": "task-123", "status": "PENDING", "raw_response": {"request_id": "req-1"}}
            response = self.client.post(
                f"/api/diary/{diary_id}/video-generation",
                json={"prompt": "镜头缓慢前推，校园树影轻轻摇动。", "duration": 5, "resolution": "720P"},
            )

        payload = response.get_json()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["task"]["task_id"], "task-123")
        self.assertEqual(payload["task"]["status"], "PENDING")
        submit_payload = submit_task.call_args.args[0]
        self.assertEqual(submit_payload["input"]["media"][0]["type"], "first_frame")
        self.assertTrue(submit_payload["input"]["media"][0]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(submit_payload["parameters"]["duration"], 5)
        self.assertEqual(submit_payload["parameters"]["resolution"], "720P")

    def test_poll_video_generation_downloads_successful_result_to_local_media(self):
        diary_id = self.create_diary_with_image()
        task = toursim_app.create_diary_video_task(
            diary_id=diary_id,
            task_id="task-done",
            prompt="生成校园视频",
            image_filename="cover.jpg",
            request_payload={"model": "wan2.7-i2v-2026-04-25"},
            raw_response={"request_id": "req-2"},
        )

        with patch.object(toursim_app, "poll_bailian_video_task") as poll_task, patch.object(
            toursim_app, "download_diary_generated_video"
        ) as download_video:
            poll_task.return_value = {
                "task_id": "task-done",
                "status": "SUCCEEDED",
                "video_url": "https://example.com/result.mp4",
                "raw_response": {"output": {"task_status": "SUCCEEDED"}},
            }
            download_video.return_value = "generated.mp4"
            response = self.client.get(f"/api/diary/{diary_id}/video-generation/{task['id']}")

        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["task"]["status"], "SUCCEEDED")
        self.assertEqual(payload["task"]["local_video_url"], f"/diary-generated-video/{diary_id}/generated.mp4")
        download_video.assert_called_once_with(diary_id, "task-done", "https://example.com/result.mp4")

    def test_start_video_generation_requires_a_diary_image(self):
        diary_id = toursim_app.create_diary("无图日记", "校园", "只有文字，没有图片。", "video_tester")

        response = self.client.post(f"/api/diary/{diary_id}/video-generation", json={})
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertIn("至少一张图片", payload["error"])


    def test_diary_detail_renders_quiet_video_generation_entry(self):
        diary_id = self.create_diary_with_image()

        response = self.client.get(f"/diary/{diary_id}?count_view=0")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"data-diary-video-panel", response.data)
        self.assertIn(f"/api/diary/{diary_id}/video-generation".encode("utf-8"), response.data)
        self.assertIn(b"diary-video-button", response.data)

    def test_completed_video_is_collapsed_and_downloadable_on_detail_page(self):
        diary_id = self.create_diary_with_image()
        video_dir = toursim_app.diary_generated_video_folder(diary_id)
        os.makedirs(video_dir, exist_ok=True)
        with open(os.path.join(video_dir, "generated.mp4"), "wb") as f:
            f.write(b"video-bytes")
        toursim_app.create_diary_video_task(
            diary_id=diary_id,
            task_id="task-rendered",
            status="SUCCEEDED",
            prompt="生成校园视频",
            image_filename="cover.jpg",
            request_payload={},
            raw_response={},
        )
        task = toursim_app.get_latest_diary_video_task(diary_id)
        toursim_app.update_diary_video_task(task["id"], status="SUCCEEDED", local_video_filename="generated.mp4")

        response = self.client.get(f"/diary/{diary_id}?count_view=0")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"class=\"diary-video-result\"", response.data)
        self.assertIn(f"/diary-generated-video/{diary_id}/generated.mp4?download=1".encode("utf-8"), response.data)
        self.assertIn(b"data-video-download", response.data)

    def test_generated_video_route_can_return_attachment(self):
        diary_id = self.create_diary_with_image()
        video_dir = toursim_app.diary_generated_video_folder(diary_id)
        os.makedirs(video_dir, exist_ok=True)
        with open(os.path.join(video_dir, "generated.mp4"), "wb") as f:
            f.write(b"video-bytes")

        response = self.client.get(f"/diary-generated-video/{diary_id}/generated.mp4?download=1")

        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))


if __name__ == "__main__":
    unittest.main()
