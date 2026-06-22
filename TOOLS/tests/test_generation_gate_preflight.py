#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "generation_gate.py"


class GenerationGatePreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "MATERIAL/fixed-role").mkdir(parents=True)
        (self.root / "TEMP/run").mkdir(parents=True)
        (self.root / "MATERIAL/fixed-role/anna.png").write_bytes(b"anna")
        (self.root / "TEMP/run/reference-grid.jpg").write_bytes(b"grid")
        (self.root / "TEMP/run/selected-confirmation.png").write_bytes(b"confirmation")
        (self.root / "TEMP/run/dreamina-prompt.txt").write_text("画面人物以 @图1 为身份锚点。", encoding="utf-8")
        (self.root / "TEMP/run/grid-report.json").write_text(json.dumps({
            "decision": "pass",
            "validation": {"decision": "pass"},
            "errors": [],
            "duration_sec": 5.0,
            "capture_mode": "video-canvas-frame",
            "has_current_src": True,
            "grid_path": "TEMP/run/reference-grid.jpg",
        }), encoding="utf-8")
        (self.root / "TEMP/run/prompt-lint.json").write_text(json.dumps({
            "results": [{
                "path": "TEMP/run/dreamina-prompt.txt",
                "decision": "pass",
                "route": "anna",
                "channel": "auto",
            }]
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_gate(self, *extra_args, prompt_text=None):
        if prompt_text is not None:
            (self.root / "TEMP/run/dreamina-prompt.txt").write_text(prompt_text, encoding="utf-8")
        base_args = [
            "python3", str(SCRIPT),
            "--engine", "dreamina",
            "--route", "anna",
            "--channel", "auto",
            "--reference-url", "https://www.douyin.com/video/1",
            "--grid-report", "TEMP/run/grid-report.json",
            "--prompt-file", "TEMP/run/dreamina-prompt.txt",
            "--confirmation-image", "TEMP/run/selected-confirmation.png",
            "--out-dir", "TEMP/run",
        ]
        return subprocess.run([*base_args, *extra_args], cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_anna_auto_passes(self):
        proc = self.run_gate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest = json.loads((self.root / "TEMP/run/dreamina-generation-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["route"], "anna")
        self.assertEqual(manifest["channel"], "auto")
        self.assertEqual(manifest["expected_duration"], "random 5-6s")
        self.assertEqual(manifest["expected_inputs"], [str((self.root / "TEMP/run/selected-confirmation.png").resolve())])

    def test_requires_graph1(self):
        proc = self.run_gate(prompt_text="画面人物保持 anna 身份锚点。")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("缺少 @图1", proc.stdout)

    def test_rejects_unsupported_prompt_terms(self):
        proc = self.run_gate(prompt_text="画面人物以 @图1 和 @图2 为身份锚点，包含模型参数。")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("不支持", proc.stdout)

    def test_tns_retry_requires_prompt_lint_report(self):
        proc = self.run_gate("--tns-retry")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("TNS 收敛重试必须提供 --prompt-lint-report", proc.stdout)

    def test_tns_retry_accepts_passing_prompt_lint(self):
        proc = self.run_gate("--tns-retry", "--prompt-lint-report", "TEMP/run/prompt-lint.json")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_parser_rejects_unknown_channel(self):
        proc = subprocess.run([
            "python3", str(SCRIPT),
            "--engine", "dreamina",
            "--route", "anna",
            "--channel", "other",
            "--reference-url", "https://www.douyin.com/video/1",
            "--grid-report", "TEMP/run/grid-report.json",
            "--prompt-file", "TEMP/run/dreamina-prompt.txt",
            "--confirmation-image", "TEMP/run/selected-confirmation.png",
            "--out-dir", "TEMP/run",
        ], cwd=self.root, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid choice", proc.stderr)


if __name__ == "__main__":
    unittest.main()
