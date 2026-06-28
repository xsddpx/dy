#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "kie_confirmation_image.py"
SPEC = importlib.util.spec_from_file_location("kie_confirmation_image", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8ffff3f0005fe02fea73581e40000000049454e44ae426082"
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content=b""):
        self.payload = payload
        self.status_code = status_code
        self.content = content
        self.text = json.dumps(payload or {}, ensure_ascii=False)

    def json(self):
        return self.payload


class KieConfirmationImageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.role = self.root / "role.png"
        self.prompt = self.root / "prompt.txt"
        self.out_dir = self.root / "confirm-A-1200"
        self.role.write_bytes(PNG_1X1)
        self.prompt.write_text(
            "人物：以 @图1 中的人物作为身份依据。\n"
            "穿搭：修身短上衣，高腰半裙，腰线清晰。\n"
            "姿态镜头：正面站姿，平视半身近景。\n"
            "环境：室内客厅，自然窗光。\n"
            "其他：真实光影。",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, **overrides):
        values = {
            "run_id": "20260623-1200-test",
            "stamp": "20260623-1200",
            "batch": "A",
            "slot": "A-01",
            "topic": "smoke测试",
            "role_image": str(self.role),
            "prompt": None,
            "prompt_path": str(self.prompt),
            "prompt_note": "smoke",
            "out_dir": str(self.out_dir),
            "raw_dir": None,
            "entry_out": None,
            "env_file": str(self.root / ".env"),
            "api_key": "test-token",
            "upload_path": None,
            "callback_url": None,
            "aspect_ratio": "auto",
            "resolution": None,
            "output_format": "png",
            "poll_seconds": 0,
            "max_wait_seconds": 1,
            "timeout": 5,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_success_generates_entry_and_downloads_image(self):
        post_responses = [
            FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/role.png", "fileName": "role.png"}}),
            FakeResponse({"code": 200, "msg": "success", "data": {"taskId": "task_gpt-image-2_1234567890"}}),
        ]
        get_responses = [
            FakeResponse({"code": 200, "data": {"taskId": "task_gpt-image-2_1234567890", "state": "generating"}}),
            FakeResponse({"code": 200, "data": {"taskId": "task_gpt-image-2_1234567890", "state": "success", "resultJson": json.dumps({"resultUrls": ["https://result/image.png"]})}}),
            FakeResponse(status_code=200, content=PNG_1X1),
        ]
        with mock.patch.object(MODULE.requests, "post", side_effect=post_responses) as post, \
                mock.patch.object(MODULE.requests, "get", side_effect=get_responses) as get:
            result = MODULE.run_generation(self.args())

        self.assertEqual(post.call_count, 2)
        create_body = post.call_args_list[1].kwargs["json"]
        self.assertEqual(create_body["model"], "gpt-image-2-image-to-image")
        create_input = json.loads(create_body["input"])
        self.assertEqual(create_input["input_urls"], ["https://tmp/role.png"])
        self.assertEqual(create_input["aspect_ratio"], "auto")
        self.assertEqual(get.call_count, 3)
        entry = json.loads(Path(result["entry_json"]).read_text(encoding="utf-8"))
        self.assertEqual(entry["status"], "success")
        self.assertEqual(entry["submit_id"], "task_gpt-image-2_1234567890")
        self.assertEqual(entry["model_version"], "gpt-image-2-image-to-image")
        self.assertTrue(Path(entry["image_path"]).exists())
        self.assertIn("role_upload", entry["kie"])
        self.assertNotIn("reference_upload", entry["kie"])

    def test_failed_task_writes_failure_entry(self):
        post_responses = [
            FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/role.png"}}),
            FakeResponse({"code": 200, "data": {"taskId": "task_fail"}}),
        ]
        get_responses = [
            FakeResponse({"code": 200, "data": {"taskId": "task_fail", "state": "fail", "failMsg": "content rejected"}}),
        ]
        with mock.patch.object(MODULE.requests, "post", side_effect=post_responses), \
                mock.patch.object(MODULE.requests, "get", side_effect=get_responses):
            result = MODULE.run_generation(self.args())

        entry = json.loads(Path(result["entry_json"]).read_text(encoding="utf-8"))
        self.assertEqual(entry["status"], "fail")
        self.assertEqual(entry["submit_id"], "task_fail")
        self.assertIn("content rejected", entry["fail_reason"])

    def test_missing_api_key_is_rejected(self):
        with self.assertRaisesRegex(MODULE.KieError, "缺少 KIE_API_KEY"):
            MODULE.require_api_key("")

    def test_wait_for_task_times_out(self):
        with mock.patch.object(
            MODULE,
            "query_task",
            return_value={"taskId": "task_timeout", "state": "generating"},
        ), mock.patch.object(MODULE.time, "sleep", return_value=None):
            with self.assertRaisesRegex(MODULE.KieError, "超时"):
                MODULE.wait_for_task("task_timeout", "token", poll_seconds=0, max_wait_seconds=0, timeout=1)


if __name__ == "__main__":
    unittest.main()
