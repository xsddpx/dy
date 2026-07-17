import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "reference_mask.py"


class ReferenceMaskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.png"
        image = np.full((10, 12, 3), 255, dtype=np.uint8)
        cv2.imwrite(str(self.source), image)

    def tearDown(self):
        self.tmp.cleanup()

    def run_mask(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.source), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_single_rect_masks_target_area_black(self):
        out = self.root / "masked.png"
        proc = self.run_mask("--rect", "2,3,4,2", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        image = cv2.imread(str(out), cv2.IMREAD_COLOR)
        self.assertTrue(np.all(image[3:5, 2:6] == 0))
        self.assertTrue(np.all(image[0:2, 0:2] == 255))

    def test_multiple_rects_are_applied(self):
        out = self.root / "masked.png"
        proc = self.run_mask("--rect", "0,0,2,2", "--rect", "10,8,2,2", "--out", str(out))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        image = cv2.imread(str(out), cv2.IMREAD_COLOR)
        self.assertTrue(np.all(image[0:2, 0:2] == 0))
        self.assertTrue(np.all(image[8:10, 10:12] == 0))

    def test_out_of_bounds_rect_is_clamped(self):
        out = self.root / "masked.png"
        report = self.root / "report.json"
        proc = self.run_mask("--rect=-2,-1,5,4", "--out", str(out), "--report", str(report))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        image = cv2.imread(str(out), cv2.IMREAD_COLOR)
        self.assertTrue(np.all(image[0:3, 0:3] == 0))
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertEqual(data["rects"][0]["applied"], {"x": 0, "y": 0, "width": 3, "height": 3})

    def test_invalid_rect_size_fails(self):
        out = self.root / "masked.png"
        proc = self.run_mask("--rect", "1,1,0,2", "--out", str(out))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("width and height", proc.stderr)

    def test_grid_report_auto_masks_vision_face_box(self):
        out = self.root / "masked.png"
        report_path = self.root / "reference-grid-report.json"
        mask_report = self.root / "mask-report.json"
        report_path.write_text(
            json.dumps(
                {
                    "head_face_detection": {
                        "frames": [
                            {
                                "path": str(self.source),
                                "face_boxes": [
                                    {
                                        "x": 0.490953266620636,
                                        "y": 0.6888231039047241,
                                        "width": 0.07545451819896698,
                                        "height": 0.0424431636929512,
                                        "confidence": 0.79886394739151,
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )

        proc = self.run_mask("--grid-report", str(report_path), "--out", str(out), "--report", str(mask_report))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = json.loads(mask_report.read_text(encoding="utf-8"))
        self.assertEqual(data["mode"], "auto_from_grid_report")
        rect = data["rects"][0]
        self.assertEqual(rect["raw_top_left_rect"], {"x": 5.891, "y": 2.687, "width": 0.905, "height": 0.424})
        self.assertEqual(rect["input"], {"x": 5, "y": 2, "width": 2, "height": 1})
        self.assertEqual(rect["applied"], {"x": 5, "y": 2, "width": 2, "height": 1})

    def test_grid_report_without_face_boxes_fails(self):
        out = self.root / "masked.png"
        report_path = self.root / "reference-grid-report.json"
        report_path.write_text(
            json.dumps({"head_face_detection": {"frames": [{"path": str(self.source), "face_boxes": []}]}}),
            encoding="utf-8",
        )

        proc = self.run_mask("--grid-report", str(report_path), "--out", str(out))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no face_boxes", proc.stderr)

    def test_requires_auto_or_manual_rect(self):
        out = self.root / "masked.png"
        proc = self.run_mask("--out", str(out))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("provide --grid-report", proc.stderr)


if __name__ == "__main__":
    unittest.main()
