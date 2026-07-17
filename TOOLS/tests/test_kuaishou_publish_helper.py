#!/usr/bin/env python3
import io
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "kuaishou_publish_helper.py"
SPEC = importlib.util.spec_from_file_location("kuaishou_publish_helper", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class KuaishouPublishHelperTest(unittest.TestCase):
    def test_publish_page_detection(self):
        self.assertTrue(MODULE.is_publish_page(MODULE.DEFAULT_UPLOAD_URL))
        self.assertFalse(MODULE.is_publish_page("https://cp.kuaishou.com/profile"))

    def test_default_upload_url_uses_regular_video_tab(self):
        self.assertIn("tabType=1", MODULE.DEFAULT_UPLOAD_URL)

    def test_build_caption_dedupes_existing_tags(self):
        caption = MODULE.build_caption("轻熟针织穿搭", "今天心情很轻松 #好心情", ["好心情", "#穿搭"])
        self.assertEqual(caption.count("#好心情"), 1)
        self.assertIn("#穿搭", caption)

    def test_build_caption_keeps_title_on_first_line(self):
        caption = MODULE.build_caption("轻熟针织穿搭", "今天心情很轻松", ["穿搭"])
        self.assertEqual(caption.splitlines()[0], "轻熟针织穿搭")

    def test_ai_declaration_detection(self):
        self.assertTrue(MODULE.ai_declaration_is_set("作品声明 内容由AI生成"))
        self.assertTrue(MODULE.ai_declaration_is_set("作者声明 内容为AI生成"))
        self.assertFalse(MODULE.ai_declaration_is_set("请选择作品声明"))

    def test_click_locator_flexibly_uses_force_after_intercept(self):
        class FakeLocator:
            def __init__(self):
                self.calls = []

            def click(self, timeout=3000, force=False):
                self.calls.append((timeout, force))
                if not force:
                    raise RuntimeError("intercepts pointer events")

        locator = FakeLocator()
        result = MODULE.click_locator_flexibly(locator)

        self.assertTrue(result["ok"])
        self.assertEqual(result["method"], "force")
        self.assertEqual(locator.calls, [(3000, False), (3000, True)])

    def test_publish_result_accepts_success_text(self):
        self.assertEqual(MODULE.classify_publish_snapshot({"text": "作品发布成功"}), "success")

    def test_publish_result_accepts_manage_redirect(self):
        self.assertEqual(
            MODULE.classify_publish_snapshot({"url": "https://cp.kuaishou.com/article/manage/video"}),
            "success",
        )

    def test_publish_result_rejects_hard_error(self):
        self.assertEqual(MODULE.classify_publish_snapshot({"text": "发布失败，请重试"}), "hard-error")

    def test_vr360_snapshot_is_blocked(self):
        self.assertTrue(MODULE.snapshot_has_vr360_mode({"textSample": "正在使用VR360°全景视频上传模式"}))
        self.assertFalse(MODULE.snapshot_has_vr360_mode({"textSample": "上传视频 作品描述"}))

    def test_main_help_includes_location_controls(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with mock.patch("sys.stdout", stdout):
                MODULE.main(["--help"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--location", stdout.getvalue())
        self.assertIn("--no-location", stdout.getvalue())
        self.assertIn("快手不设置发布地址", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
