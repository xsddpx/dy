#!/usr/bin/env python3
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "publish_adapter.py"
SPEC = importlib.util.spec_from_file_location("publish_adapter", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PublishAdapterTest(unittest.TestCase):
    def test_registry_contains_existing_and_new_platform(self):
        self.assertEqual(set(MODULE.ADAPTERS), {"douyin", "kuaishou"})

    def test_kuaishou_adapter_forwards_arguments(self):
        adapter = MODULE.get_adapter("kuaishou")
        command = adapter.command(["demo.mp4", "--title", "测试"])
        self.assertEqual(Path(command[1]).name, "kuaishou_publish_helper.py")
        self.assertEqual(command[2:], ["demo.mp4", "--title", "测试"])

    def test_both_adapter_attempts_kuaishou_after_douyin_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            calls = []

            def fake_call(command):
                calls.append(command)
                platform = Path(command[1]).name.split("_", 1)[0]
                decision = "failed" if platform == "douyin" else "published"
                (out_dir / f"{platform}-publish-report.json").write_text(
                    f'{{"decision": "{decision}", "errors": []}}',
                    encoding="utf-8",
                )
                return 7 if platform == "douyin" else 0

            with mock.patch.object(MODULE.subprocess, "call", side_effect=fake_call):
                code = MODULE.main(
                    [
                        "both",
                        "demo.mp4",
                        "--title",
                        "测试",
                        "--out-dir",
                        str(out_dir),
                    ]
                )

        self.assertEqual([Path(call[1]).name for call in calls], ["douyin_publish_helper.py", "kuaishou_publish_helper.py"])
        self.assertEqual(code, 7)

    def test_both_adapter_succeeds_only_when_both_reports_are_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)

            def fake_call(command):
                platform = Path(command[1]).name.split("_", 1)[0]
                (out_dir / f"{platform}-publish-report.json").write_text(
                    '{"decision": "published", "errors": []}',
                    encoding="utf-8",
                )
                return 0

            with mock.patch.object(MODULE.subprocess, "call", side_effect=fake_call):
                code = MODULE.main(["both", "demo.mp4", "--title", "测试", "--out-dir", str(out_dir)])

            report = (out_dir / "publish-both-report.json").read_text(encoding="utf-8")

        self.assertEqual(code, 0)
        self.assertIn('"decision": "published"', report)
        self.assertIn('"platform": "douyin"', report)
        self.assertIn('"platform": "kuaishou"', report)

    def test_both_adapter_forwards_publish_arguments_to_each_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            calls = []

            def fake_call(command):
                calls.append(command)
                platform = Path(command[1]).name.split("_", 1)[0]
                (out_dir / f"{platform}-publish-report.json").write_text(
                    '{"decision": "published", "errors": []}',
                    encoding="utf-8",
                )
                return 0

            passthrough = [
                "demo.mp4",
                "--title",
                "窗边随拍",
                "--description",
                "旅行片段",
                "--tag",
                "旅行",
                "--tag",
                "穿搭",
                "--location",
                "杭州 湖滨",
                "--cdp-url",
                "http://127.0.0.1:9222",
                "--out-dir",
                str(out_dir),
                "--record-jsonl",
                str(out_dir / "run.jsonl"),
            ]
            with mock.patch.object(MODULE.subprocess, "call", side_effect=fake_call):
                MODULE.main(["both", *passthrough])

        self.assertEqual(len(calls), 2)
        for command in calls:
            self.assertEqual(command[2:], passthrough)

    def test_both_adapter_defaults_to_no_location(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            calls = []

            def fake_call(command):
                calls.append(command)
                platform = Path(command[1]).name.split("_", 1)[0]
                (out_dir / f"{platform}-publish-report.json").write_text(
                    '{"decision": "published", "errors": []}',
                    encoding="utf-8",
                )
                return 0

            passthrough = [
                "demo.mp4",
                "--title",
                "窗边随拍",
                "--out-dir",
                str(out_dir),
            ]
            with mock.patch.object(MODULE.subprocess, "call", side_effect=fake_call):
                MODULE.main(["both", *passthrough])

        self.assertEqual(len(calls), 2)
        for command in calls:
            self.assertIn("--no-location", command)
            self.assertNotIn("--location", command)

    def test_unknown_adapter_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "未知发布平台"):
            MODULE.get_adapter("unknown")


if __name__ == "__main__":
    unittest.main()
