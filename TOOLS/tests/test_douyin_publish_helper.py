#!/usr/bin/env python3
import importlib.util
import io
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

    def test_main_help_includes_no_publish(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with mock.patch("sys.argv", ["douyin_publish_helper.py", "--help"]), mock.patch("sys.stdout", stdout):
                MODULE.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--no-publish", stdout.getvalue())
        self.assertNotIn("--location", stdout.getvalue())
        self.assertNotIn("--cover-frame", stdout.getvalue())
        self.assertNotIn("--current-tab", stdout.getvalue())
        self.assertNotIn("--upload-mode", stdout.getvalue())
        self.assertNotIn("--ai-cover-recommendation-timeout", stdout.getvalue())

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

    def test_build_description_writes_first_four_raw_hashtags(self):
        description, applied = MODULE.build_description_with_tags(
            "简单记录今天的状态。 #旧话题",
            ["轻熟穿搭", "修身穿搭", "日常穿搭", "穿搭分享", "氛围感"],
        )
        self.assertEqual(applied, ["轻熟穿搭", "修身穿搭", "日常穿搭", "穿搭分享"])
        self.assertNotIn("#旧话题", description)
        self.assertEqual(MODULE.extract_hashtags(description), applied)

    def test_build_description_requires_four_unique_hashtags(self):
        with self.assertRaises(ValueError):
            MODULE.build_description_with_tags("正文", ["一", "二", "二", "三"])

    def test_topic_state_rejects_fewer_than_four_raw_hashtags(self):
        result = MODULE.validate_topic_state(
            final_text="简单记录今天的状态。 #轻熟穿搭 #穿搭分享 #身材比例",
            applied_tags=["轻熟穿搭", "修身穿搭", "穿搭分享", "身材比例"],
        )
        self.assertFalse(result["safe"])
        self.assertTrue(any("恰好为 4 个" in error for error in result["errors"]))

    def test_topic_state_accepts_exactly_four_raw_hashtags(self):
        result = MODULE.validate_topic_state(
            final_text="简单记录今天的状态。 #轻熟穿搭 #修身穿搭 #日常穿搭 #穿搭分享",
            applied_tags=["轻熟穿搭", "修身穿搭", "日常穿搭", "穿搭分享"],
        )
        self.assertTrue(result["safe"], result["errors"])

    def test_topic_state_rejects_unplanned_hashtag(self):
        result = MODULE.validate_topic_state(
            final_text="正文 #一 #二 #三 #计划外",
            applied_tags=["一", "二", "三", "四"],
        )
        self.assertFalse(result["safe"])
        self.assertEqual(result["missing_topics"], ["四"])
        self.assertEqual(result["unexpected_topics"], ["计划外"])

    def test_topic_state_rejects_more_than_four_hashtags(self):
        tags = ["一", "二", "三", "四", "五"]
        result = MODULE.validate_topic_state(
            final_text="正文 " + " ".join(f"#{tag}" for tag in tags),
            applied_tags=tags[:4],
        )
        self.assertFalse(result["safe"])
        self.assertTrue(any("恰好为 4 个" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
