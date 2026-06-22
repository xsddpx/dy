#!/usr/bin/env python3
import importlib.util
import os
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "douyin_publish_helper.py"
SPEC = importlib.util.spec_from_file_location("douyin_publish_helper", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DouyinPublishHelperTest(unittest.TestCase):
    def test_declaration_snapshot_requires_field_level_match(self):
        ok, matched = MODULE.declaration_snapshot_is_set({
            "fieldText": "自主声明 请选择自主声明 页面别处提到AI生成工具",
            "matched": "AI生成",
        })
        self.assertFalse(ok)
        self.assertIsNone(matched)

    def test_declaration_snapshot_accepts_ai_generated_selection(self):
        ok, matched = MODULE.declaration_snapshot_is_set({
            "fieldText": "自主声明 内容由AI生成",
            "matched": "内容由AI生成",
        })
        self.assertTrue(ok)
        self.assertEqual(matched, "内容由AI生成")

    def test_declaration_snapshot_accepts_neighbor_or_preview_text(self):
        ok, matched = MODULE.declaration_snapshot_is_set({
            "fieldText": "自主声明",
            "contextText": "自主声明 内容由AI生成",
            "previewText": "作者声明：内容由AI生成",
            "placeholderVisible": False,
        })
        self.assertTrue(ok)
        self.assertEqual(matched, "内容由AI生成")

    def test_declaration_snapshot_rejects_visible_placeholder_even_with_preview(self):
        ok, matched = MODULE.declaration_snapshot_is_set({
            "fieldText": "自主声明 请选择自主声明",
            "previewText": "作者声明：内容由AI生成",
            "placeholderVisible": True,
        })
        self.assertFalse(ok)
        self.assertIsNone(matched)

    def test_declaration_snapshot_rejects_missing_snapshot(self):
        ok, matched = MODULE.declaration_snapshot_is_set(None)
        self.assertFalse(ok)
        self.assertIsNone(matched)

    def test_description_contains_tags(self):
        self.assertTrue(MODULE.description_contains_tags("今天很好看 #纯欲 #穿搭", ["纯欲", "穿搭"]))
        self.assertFalse(MODULE.description_contains_tags("今天很好看 #纯欲", ["纯欲", "穿搭"]))

    def test_resolve_cdp_url_prefers_cli_value(self):
        with mock.patch.dict(os.environ, {"DOUYIN_CHROME_CDP_URL": "http://127.0.0.1:9222"}):
            self.assertEqual(MODULE.resolve_cdp_url("http://127.0.0.1:9333"), "http://127.0.0.1:9333")

    def test_resolve_cdp_url_reads_environment(self):
        with mock.patch.dict(os.environ, {"DOUYIN_CHROME_CDP_URL": "http://127.0.0.1:9222"}):
            self.assertEqual(MODULE.resolve_cdp_url(None), "http://127.0.0.1:9222")

    def test_resolve_cdp_url_returns_none_when_missing(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(MODULE.resolve_cdp_url(None))

    def test_playwright_upload_skips_when_cdp_missing(self):
        result = MODULE.set_file_input_via_playwright(None, Path("/tmp/demo.mp4"), MODULE.DEFAULT_UPLOAD_URL)
        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["method"], "playwright-cdp")

    def test_upload_page_url_detection(self):
        self.assertTrue(MODULE.is_upload_page("https://creator.douyin.com/creator-micro/content/upload?default-tab=5"))
        self.assertFalse(MODULE.is_upload_page("https://creator.douyin.com/creator-micro/content/manage"))

    def test_video_publish_page_url_detection(self):
        self.assertTrue(MODULE.is_video_publish_page("https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page"))
        self.assertFalse(MODULE.is_video_publish_page("https://creator.douyin.com/creator-micro/content/upload"))

    def test_playwright_upload_reports_missing_dependency(self):
        with mock.patch.object(MODULE, "playwright_import_error", return_value="missing playwright"):
            result = MODULE.set_file_input_via_playwright(
                "http://127.0.0.1:9222",
                Path("/tmp/demo.mp4"),
                MODULE.DEFAULT_UPLOAD_URL,
            )
        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("missing playwright", result["reason"])

    def test_activate_video_publish_page_reports_missing_dependency(self):
        with mock.patch.object(MODULE, "playwright_import_error", return_value="missing playwright"):
            result = MODULE.activate_video_publish_page_via_playwright("http://127.0.0.1:9222")
        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("missing playwright", result["reason"])

    def test_publish_snapshot_does_not_treat_uploading_manage_page_as_success(self):
        status = MODULE.classify_publish_snapshot({
            "url": "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish",
            "textSample": "作品上传中，请勿关闭页面 上传完成后将自动发布 0%",
        })
        self.assertEqual(status, "uploading")

    def test_publish_snapshot_accepts_stable_manage_page(self):
        status = MODULE.classify_publish_snapshot({
            "url": "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish",
            "textSample": "作品管理 合集管理 共创中心",
        })
        self.assertEqual(status, "success")


if __name__ == "__main__":
    unittest.main()
