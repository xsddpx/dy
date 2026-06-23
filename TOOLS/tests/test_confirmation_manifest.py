#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "confirmation_manifest.py"


PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8ffff3f0005fe02fea73581e40000000049454e44ae426082"
)


class ConfirmationManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out_dir = self.root / "confirm-A-1200"
        self.image1 = self.root / "image1.png"
        self.image3 = self.root / "image3.png"
        self.image1.write_bytes(PNG_1X1)
        self.image3.write_bytes(PNG_1X1)

    def tearDown(self):
        self.tmp.cleanup()

    def run_manifest(self, entries):
        args = [
            "python3", str(SCRIPT),
            "--run-id", "20260617-1200-ck06171200测试",
            "--stamp", "20260617-1200",
            "--batch", "A",
            "--topic", "ck06171200测试",
            "--out-dir", str(self.out_dir),
        ]
        for entry in entries:
            args.extend(["--entry", json.dumps(entry, ensure_ascii=False)])
        return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_success_and_failure_slots_are_preserved(self):
        proc = self.run_manifest([
            {
                "slot": "A-01",
                "submit_id": "11111111-dddd",
                "status": "success",
                "image_path": str(self.image1),
                "model_version": "nano-banana-pro-1K",
            },
            {
                "slot": "A-02",
                "submit_id": "22222222-eeee",
                "status": "fail",
                "fail_reason": "generation failed",
                "model_version": "nano-banana-pro-1K",
            },
            {
                "slot": "A-03",
                "submit_id": "33333333-ffff",
                "status": "success",
                "image_path": str(self.image3),
                "model_version": "nano-banana-pro-1K",
            },
        ])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        manifest = json.loads((self.out_dir / "confirmation-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([item["slot"] for item in manifest["slots"]], ["A-01", "A-02", "A-03"])
        self.assertEqual([item["status"] for item in manifest["slots"]], ["success", "fail", "success"])
        self.assertNotIn("image_path", manifest["slots"][1])
        self.assertTrue((self.out_dir / "A-01" / "slot.json").exists())
        self.assertTrue((self.out_dir / "A-02" / "slot.json").exists())
        self.assertIn("11111111", manifest["slots"][0]["image_path"])
        self.assertIn("33333333", manifest["slots"][2]["proxy_path"])
        self.assertIn("A-01", manifest["slots"][0]["image_path"])

    def test_rejects_missing_slots_instead_of_backfilling(self):
        proc = self.run_manifest([
            {"slot": "A-01", "submit_id": "1", "status": "success", "image_path": str(self.image1)},
            {"slot": "A-03", "submit_id": "3", "status": "fail", "fail_reason": "failed"},
        ])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("每批必须正好 3 个提交位", proc.stderr)

    def test_rejects_legacy_slots(self):
        legacy_slot_4 = f"A-{4:02d}"
        legacy_slot_6 = f"A-{6:02d}"
        proc = self.run_manifest([
            {"slot": "A-01", "submit_id": "1", "status": "success", "image_path": str(self.image1)},
            {"slot": legacy_slot_4, "submit_id": "4", "status": "success", "image_path": str(self.image1)},
            {"slot": legacy_slot_6, "submit_id": "6", "status": "success", "image_path": str(self.image3)},
        ])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("提交位必须且只能是 A-01, A-02, A-03", proc.stderr)

    def test_failure_slot_cannot_have_image_path(self):
        proc = self.run_manifest([
            {"slot": "A-01", "submit_id": "1", "status": "success", "image_path": str(self.image1)},
            {"slot": "A-02", "submit_id": "2", "status": "fail", "image_path": str(self.image3)},
            {"slot": "A-03", "submit_id": "3", "status": "fail", "fail_reason": "failed"},
        ])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("失败提交位不得提供 image_path", proc.stderr)


if __name__ == "__main__":
    unittest.main()
