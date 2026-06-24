#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "image_proxy.py"


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8ffff3f0005fe02fea73581e40000000049454e44ae426082"
)


class ImageProxyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out_dir = self.root / "out"
        self.small = self.root / "small.png"
        self.large = self.root / "large.ppm"
        self.invalid = self.root / "invalid.jpg"
        self.small.write_bytes(PNG_1X1)
        self.large.write_bytes(b"P6\n800 800\n255\n" + (b"\x88\x88\x88" * 800 * 800))
        self.invalid.write_text("not an image", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_proxy(self, images, *extra_args):
        args = ["python3", str(SCRIPT), "--out-dir", str(self.out_dir), *extra_args]
        args.extend(str(image) for image in images)
        return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def read_report(self):
        return json.loads((self.out_dir / "image-proxy-report.json").read_text(encoding="utf-8"))

    def test_skips_original_under_limit_and_uses_original_display_path(self):
        proc = self.run_proxy([self.small])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        summary = json.loads(proc.stdout)
        report = self.read_report()

        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["pass"], 0)
        self.assertFalse((self.out_dir / "small-proxy.jpg").exists())
        self.assertTrue(report[0]["skipped"])
        self.assertEqual(report[0]["skip_reason"], "skipped_original_under_limit")
        self.assertEqual(report[0]["display_path"], str(self.small.resolve()))

    def test_large_original_generates_proxy_under_target(self):
        proc = self.run_proxy([self.large])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = self.read_report()

        proxy = Path(report[0]["proxy"])
        self.assertFalse(report[0]["skipped"])
        self.assertEqual(report[0]["display_path"], str(proxy))
        self.assertTrue(proxy.exists())
        self.assertLessEqual(proxy.stat().st_size, 100_000)

    def test_force_proxy_overrides_small_original_skip(self):
        proc = self.run_proxy([self.small], "--force-proxy")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = self.read_report()

        proxy = Path(report[0]["proxy"])
        self.assertFalse(report[0]["skipped"])
        self.assertEqual(report[0]["display_path"], str(proxy))
        self.assertTrue(proxy.exists())

    def test_markdown_report_distinguishes_skipped_pass_and_fail(self):
        proc = self.run_proxy([self.small, self.large, self.invalid])
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        markdown = (self.out_dir / "image-proxy-report.md").read_text(encoding="utf-8")
        self.assertIn("| skipped | small.png | small.png |", markdown)
        self.assertIn("| pass | large.ppm | large-proxy.jpg | large-proxy.jpg |", markdown)
        self.assertIn("| fail | invalid.jpg |", markdown)


if __name__ == "__main__":
    unittest.main()
