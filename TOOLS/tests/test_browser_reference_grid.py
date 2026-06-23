import importlib.util
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "browser_reference_grid.py"
SPEC = importlib.util.spec_from_file_location("browser_reference_grid", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BrowserReferenceGridTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def args(self):
        return SimpleNamespace(
            min_valid_frames=4,
            ratio_tolerance=0.035,
            duplicate_delta=2.5,
            ui_risk_min_frames=2,
            computer_use_capture=False,
            computer_use_rect=None,
            rect=None,
        )

    def write_frame(self, name, offset):
        path = self.root / name
        height, width = 160, 90
        image = np.zeros((height, width, 3), dtype=np.uint8)
        for y in range(height):
            image[y, :, :] = (90 + (y + offset) % 80, 110 + offset, 130)
        cv2.circle(image, (45, 45 + offset % 40), 14, (180, 150, 120), -1)
        cv2.imwrite(str(path), image)
        return path

    def test_choose_capture_rect_uses_computer_use_source(self):
        args = self.args()
        args.computer_use_capture = True
        args.computer_use_rect = "10,20,90,160"

        rect = MODULE.choose_capture_rect(args, {"ok": False})

        self.assertEqual(rect, {"x": 10, "y": 20, "width": 90, "height": 160, "source": "computer-use-9x16-screen"})

    def test_mark_computer_use_required_keeps_tab_for_agent(self):
        report = {"warnings": []}
        tab_session = {"keep_tab": False}

        MODULE.mark_computer_use_required(report, tab_session, "no video")

        self.assertEqual(report["decision"], "computer_use_required")
        self.assertEqual(report["computer_use_required"]["reason"], "no video")
        self.assertTrue(tab_session["keep_tab"])
        self.assertTrue(report["chrome_tab"]["keep_tab"])

    def test_computer_use_capture_allows_zero_duration_natural_playback(self):
        frames = [self.write_frame(f"frame-{index:02d}.png", index * 9) for index in range(1, 5)]
        grid_path = self.write_frame("reference-grid.jpg", 55)
        report = {
            "duration_sec": 0,
            "capture_mode": "computer-use-9x16-screen",
            "chrome_js_unavailable": True,
            "frames": [{"path": str(path), "mode": "natural-playback", "capture": "computer-use-9x16-screen"} for path in frames],
        }

        validation = MODULE.validate_capture(frames, grid_path, report, self.args())

        self.assertEqual(validation["decision"], "pass", validation)
        self.assertEqual(validation["errors"], [])

    def test_non_computer_use_natural_playback_still_fails(self):
        frames = [self.write_frame(f"frame-{index:02d}.png", index * 9) for index in range(1, 5)]
        grid_path = self.write_frame("reference-grid.jpg", 55)
        report = {
            "duration_sec": 0,
            "capture_mode": "video-rect-estimate",
            "frames": [{"path": str(path), "mode": "natural-playback"} for path in frames],
        }

        validation = MODULE.validate_capture(frames, grid_path, report, self.args())

        self.assertEqual(validation["decision"], "fail")
        self.assertIn("视频时长为 0 或不可读，不能确认关键帧来自可控播放", validation["errors"])
        self.assertIn("使用自然播放间隔截图；正式宫格必须能按时长跳转或确认可控采样", validation["errors"])


if __name__ == "__main__":
    unittest.main()
