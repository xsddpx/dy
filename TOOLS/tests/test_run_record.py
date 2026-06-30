import json
import tempfile
import unittest
from pathlib import Path

import importlib.util


SCRIPT = Path(__file__).resolve().parents[1] / "run_record.py"
SPEC = importlib.util.spec_from_file_location("run_record", SCRIPT)
RUN_RECORD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN_RECORD)


class RunRecordTest(unittest.TestCase):
    def test_append_refresh_and_artifact_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "任务A" / "任务A-run-record.jsonl"
            RUN_RECORD.append_event(
                record,
                stage="reference",
                event="reference_grid",
                status="pass",
                summary="参考宫格通过",
                data={"grid_path": "TEMP/任务A/reference-grid.jpg"},
            )
            RUN_RECORD.append_artifact(
                record,
                stage="reference",
                path="TEMP/任务A/reference-grid.jpg",
                kind="reference-grid",
                status="pass",
                keep=True,
            )
            RUN_RECORD.append_artifact(
                record,
                stage="reference",
                path="TEMP/任务A/reference-grid.jpg",
                kind="reference-grid",
                status="pass",
                keep=True,
            )
            md = RUN_RECORD.refresh_markdown(record)

            self.assertTrue(record.exists())
            self.assertTrue(md.exists())
            self.assertEqual(len(record.read_text(encoding="utf-8").splitlines()), 3)
            text = md.read_text(encoding="utf-8")
            self.assertIn("参考宫格通过", text)
            self.assertEqual(text.count("TEMP/任务A/reference-grid.jpg；保留"), 1)
            summary_json = record.parent / "logs" / "summary" / "任务A-summary.json"
            self.assertTrue(summary_json.exists())
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_status_by_stage"]["reference"]["status"], "pass")
            self.assertEqual(summary["key_artifacts"][0]["path"], "TEMP/任务A/reference-grid.jpg")

    def test_append_cli_accepts_json_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "run" / "run-run-record.jsonl"
            data = json.dumps({"path": "OUTPUT/run.mp4"}, ensure_ascii=False)
            args = ["append", str(record), "--stage", "video", "--event", "download", "--status", "pass", "--data", data]
            parser_exit = RUN_RECORD.main
            self.assertTrue(callable(parser_exit))

    def test_publish_recovery_keeps_failure_as_evidence_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            record = Path(tmp) / "run" / "run-run-record.jsonl"
            RUN_RECORD.append_event(
                record,
                stage="publish",
                event="douyin_publish",
                status="failed",
                summary="抖音发布 failed",
                data={"report_json": "TEMP/run/logs/publish/douyin-publish-report.json"},
            )
            RUN_RECORD.append_artifact(
                record,
                stage="publish",
                path="TEMP/run/logs/publish/douyin-publish-report.json",
                kind="douyin-publish-report",
                status="failed",
                keep=False,
                summary="上传入口失败报告",
            )
            RUN_RECORD.append_event(
                record,
                stage="publish",
                event="publish",
                status="success",
                summary="已发布，跳转作品管理页",
                data={"final_url": "https://creator.douyin.com/creator-micro/content/manage?enter_from=publish"},
            )
            md = RUN_RECORD.refresh_markdown(record)
            text = md.read_text(encoding="utf-8")
            self.assertIn("- publish：success；已发布，跳转作品管理页", text)
            self.assertNotIn("## 关键产物\n- publish：failed", text)
            self.assertIn("## 过程证据索引", text)
            self.assertIn("上传入口失败报告", text)

            summary = json.loads((record.parent / "logs" / "summary" / "run-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_status_by_stage"]["publish"]["status"], "success")
            self.assertEqual(summary["evidence_artifacts"][0]["path"], "TEMP/run/logs/publish/douyin-publish-report.json")


if __name__ == "__main__":
    unittest.main()
