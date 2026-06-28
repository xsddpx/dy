#!/usr/bin/env python3
import importlib.util
import io
import os
import tempfile
import unittest
from datetime import date
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

    def test_compact_location_query_dedupes_blank_parts(self):
        self.assertEqual(MODULE.compact_location_query("上海", " 武康路  与  安福路街区 ", "上海"), "上海 武康路 与 安福路街区")

    def test_location_query_attempts_split_compound_street_area(self):
        attempts = MODULE.location_query_attempts("上海 武康路与安福路街区")
        self.assertEqual(attempts[0], "上海 武康路与安福路街区")
        self.assertIn("上海 武康路", attempts)
        self.assertIn("上海 安福路", attempts)
        self.assertIn("武康路", attempts)
        self.assertIn("安福路街区", attempts)
        self.assertIn("安福路", attempts)
        self.assertEqual(attempts[-1], "上海")

    def test_location_query_attempts_include_known_poi_substrings(self):
        attempts = MODULE.location_query_attempts("苏州 金鸡湖月光码头与湖边步道")
        self.assertIn("苏州 月光码头", attempts)
        self.assertIn("月光码头", attempts)

    def test_location_match_tokens_prefer_specific_poi_terms(self):
        tokens = MODULE.location_match_tokens("上海 武康路与安福路街区", "上海 武康路")
        self.assertEqual(tokens[0], "安福路街区")
        self.assertIn("武康路", tokens)
        self.assertIn("安福路", tokens)
        self.assertNotIn("上海", tokens)

    def test_location_city_hint_reads_leading_city(self):
        self.assertEqual(MODULE.location_city_hint("苏州 金鸡湖月光码头"), "苏州")
        self.assertIsNone(MODULE.location_city_hint("月光码头"))

    def test_location_candidate_accepts_local_suzhou_poi(self):
        self.assertTrue(
            MODULE.location_candidate_is_plausible(
                "月光码头步行街 江苏省苏州市吴中区观枫街1号",
                "苏州 金鸡湖月光码头",
                "月光码头",
            )
        )

    def test_location_candidate_rejects_foreign_context_false_positive(self):
        self.assertFalse(
            MODULE.location_candidate_is_plausible(
                "Afun-game767 首尔西大门区苏州工业园区星湖街328号创意产业园4-B601单元附近企业, 西大门区, 首尔, 韩国",
                "苏州 苏州中心",
                "苏州中心",
            )
        )

    def test_infer_location_query_prefers_cli_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = MODULE.infer_location_query(Path(tmp), "上海 外滩")
        self.assertTrue(result["ok"])
        self.assertEqual(result["query"], "上海 外滩")
        self.assertEqual(result["source"], "cli")

    def test_infer_location_query_reads_today_itinerary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "MATERIAL"
            path.mkdir()
            (path / "anna-weekly-itinerary.json").write_text(
                """
{
  "status": "active",
  "days": [
    {
      "date": "2026-06-27",
      "city": "上海",
      "location": "武康路与安福路街区",
      "activity": "咖啡街拍"
    }
  ]
}
""".strip(),
                encoding="utf-8",
            )
            result = MODULE.infer_location_query(root, today=date(2026, 6, 27))
        self.assertTrue(result["ok"])
        self.assertEqual(result["query"], "上海 武康路与安福路街区")
        self.assertEqual(result["source"], "itinerary")

    def test_normalize_cover_frame_aliases(self):
        self.assertEqual(MODULE.normalize_cover_frame(None), "recommended")
        self.assertEqual(MODULE.normalize_cover_frame("recommend"), "recommended")
        self.assertEqual(MODULE.normalize_cover_frame("mid"), "middle")
        self.assertEqual(MODULE.normalize_cover_frame("skip"), "none")
        self.assertEqual(MODULE.normalize_cover_frame("ai"), "ai-recommended")
        self.assertEqual(MODULE.normalize_cover_frame("ai_recommended"), "ai-recommended")

    def test_classify_ai_cover_recommendation_snapshot(self):
        self.assertEqual(MODULE.classify_ai_cover_recommendation_snapshot({"hasSection": False}), "absent")
        self.assertEqual(
            MODULE.classify_ai_cover_recommendation_snapshot({"hasSection": True, "generating": True}),
            "generating",
        )
        self.assertEqual(
            MODULE.classify_ai_cover_recommendation_snapshot({"hasSection": True, "empty": True}),
            "empty",
        )
        self.assertEqual(
            MODULE.classify_ai_cover_recommendation_snapshot({"hasSection": True, "hasRecommendation": True}),
            "ready",
        )
        self.assertEqual(MODULE.classify_ai_cover_recommendation_snapshot({"hasSection": True}), "done")

    def test_main_help_includes_no_publish(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with mock.patch("sys.argv", ["douyin_publish_helper.py", "--help"]), mock.patch("sys.stdout", stdout):
                MODULE.main()
        self.assertEqual(cm.exception.code, 0)
        self.assertIn("--no-publish", stdout.getvalue())
        self.assertIn("--location", stdout.getvalue())
        self.assertIn("--ai-cover-recommendation-timeout", stdout.getvalue())

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
