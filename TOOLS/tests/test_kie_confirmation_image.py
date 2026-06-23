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
        self.reference = self.root / "reference.png"
        self.prompt = self.root / "prompt.txt"
        self.out_dir = self.root / "confirm-A-1200"
        self.role.write_bytes(PNG_1X1)
        self.reference.write_bytes(PNG_1X1)
        self.prompt.write_text("人物：使用 @图1 的人物替换 @图2 中的人物。\n环境：室内。\n其他：真实光影。", encoding="utf-8")

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
            "reference_image": str(self.reference),
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
            "aspect_ratio": "9:16",
            "resolution": "1K",
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
            FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/reference.png", "fileName": "reference.png"}}),
            FakeResponse({"code": 200, "msg": "success", "data": {"taskId": "task_nano-banana-pro_1234567890"}}),
        ]
        get_responses = [
            FakeResponse({"code": 200, "data": {"taskId": "task_nano-banana-pro_1234567890", "state": "generating"}}),
            FakeResponse({"code": 200, "data": {"taskId": "task_nano-banana-pro_1234567890", "state": "success", "resultJson": json.dumps({"resultUrls": ["https://result/image.png"]})}}),
            FakeResponse(status_code=200, content=PNG_1X1),
        ]
        with mock.patch.object(MODULE.requests, "post", side_effect=post_responses) as post, \
                mock.patch.object(MODULE.requests, "get", side_effect=get_responses) as get:
            result = MODULE.run_generation(self.args())

        self.assertEqual(post.call_count, 3)
        create_body = post.call_args_list[2].kwargs["json"]
        self.assertEqual(create_body["model"], "nano-banana-pro")
        self.assertEqual(create_body["input"]["image_input"], ["https://tmp/role.png", "https://tmp/reference.png"])
        self.assertEqual(create_body["input"]["aspect_ratio"], "9:16")
        self.assertEqual(create_body["input"]["resolution"], "1K")
        self.assertEqual(get.call_count, 3)
        entry = json.loads(Path(result["entry_json"]).read_text(encoding="utf-8"))
        self.assertEqual(entry["status"], "success")
        self.assertEqual(entry["submit_id"], "task_nano-banana-pro_1234567890")
        self.assertEqual(entry["model_version"], "nano-banana-pro-1K")
        self.assertTrue(Path(entry["image_path"]).exists())

    def test_failed_task_writes_failure_entry(self):
        post_responses = [
            FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/role.png"}}),
            FakeResponse({"success": True, "code": 200, "data": {"downloadUrl": "https://tmp/reference.png"}}),
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
