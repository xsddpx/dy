import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "face_similarity_gate.py"
SPEC = importlib.util.spec_from_file_location("face_similarity_gate", SCRIPT)
FACE_GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FACE_GATE)


class FaceSimilarityGateTest(unittest.TestCase):
    def slots(self):
        return [
            {"slot": "A-01", "resolved_image_path": "/tmp/a.png", "image_path": "/tmp/a.png", "display": True},
            {"slot": "A-02", "resolved_image_path": "/tmp/b.png", "image_path": "/tmp/b.png", "display": True},
            {"slot": "A-03", "resolved_image_path": "/tmp/c.png", "image_path": "/tmp/c.png", "display": False},
        ]

    def test_single_role_selects_highest_above_threshold(self):
        enriched = FACE_GATE.attach_similarity(self.slots(), {
            "/tmp/a.png": {"checks": {"anna": {"ok": True, "similarity_percent": 91}}, "face_similarity_min_percent": 91, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 1},
            "/tmp/b.png": {"checks": {"anna": {"ok": True, "similarity_percent": 96}}, "face_similarity_min_percent": 96, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 6},
            "/tmp/c.png": {"checks": {"anna": {"ok": True, "similarity_percent": 94}}, "face_similarity_min_percent": 94, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 4},
        }, 90)
        selected = FACE_GATE.choose_best_slot(enriched)
        self.assertEqual(selected["slot"], "A-02")

    def test_reference_slot_still_ranks_when_similarity_below_threshold(self):
        enriched = FACE_GATE.attach_similarity(self.slots(), {
            "/tmp/a.png": {"checks": {"anna": {"ok": True, "similarity_percent": 89.9}}, "face_similarity_min_percent": 89.9, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": -0.1},
            "/tmp/b.png": {"checks": {"anna": {"ok": False, "error": "no-face-detected"}}, "face_similarity_min_percent": None, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": None},
            "/tmp/c.png": {"checks": {"anna": {"ok": True, "similarity_percent": 50}}, "face_similarity_min_percent": 50, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": -40},
        }, 90)
        selected = FACE_GATE.choose_best_slot(enriched)
        self.assertEqual(selected["slot"], "A-01")

    def test_tie_prefers_display_then_slot_order(self):
        enriched = FACE_GATE.attach_similarity(self.slots(), {
            "/tmp/a.png": {"checks": {"anna": {"ok": True, "similarity_percent": 94}}, "face_similarity_min_percent": 94, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 4},
            "/tmp/b.png": {"checks": {"anna": {"ok": True, "similarity_percent": 94}}, "face_similarity_min_percent": 94, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 4},
            "/tmp/c.png": {"checks": {"anna": {"ok": True, "similarity_percent": 94}}, "face_similarity_min_percent": 94, "adjusted_threshold_min_percent": 90, "face_similarity_margin_min_percent": 4},
        }, 90)
        selected = FACE_GATE.choose_best_slot(enriched)
        self.assertEqual(selected["slot"], "A-01")

    def test_default_threshold_is_75_percent(self):
        parser = FACE_GATE.build_parser()
        args = parser.parse_args(["--manifest", "m.json", "--route", "anna", "--out", "out.json"])
        self.assertEqual(args.threshold, 75.0)
        self.assertEqual(args.min_threshold, 0.0)

    def test_parser_rejects_unknown_route(self):
        parser = FACE_GATE.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--manifest", "m.json", "--route", "other", "--out", "out.json"])

    def test_best_role_assignment_auto_passes_when_candidate_has_no_face(self):
        assignment, reason = FACE_GATE.best_role_assignment(
            {"anna": {"ok": True, "embedding": [1]}},
            [],
        )
        self.assertIsNone(reason)
        self.assertEqual(assignment["face_similarity_margin_min_percent"], 0.0)
        self.assertEqual(assignment["adjusted_threshold_min_percent"], 0.0)
        self.assertTrue(assignment["checks"]["anna"]["auto_pass"])
        self.assertEqual(assignment["checks"]["anna"]["auto_pass_reason"], "candidate has no comparable InsightFace face")

    def test_best_role_assignment_still_rejects_when_role_face_unavailable(self):
        assignment, reason = FACE_GATE.best_role_assignment(
            {"anna": {"ok": False, "error": "role image has no detectable face"}},
            [],
        )
        self.assertIsNone(assignment)
        self.assertEqual(reason, "role face unavailable")

    def test_adjusted_threshold_uses_visible_ratio_without_default_floor(self):
        self.assertEqual(FACE_GATE.adjusted_threshold(75, 1.0, 0), 75.0)
        self.assertEqual(FACE_GATE.adjusted_threshold(75, 0.5, 0), 37.5)
        self.assertEqual(FACE_GATE.adjusted_threshold(75, 0.2, 0), 15.0)
        self.assertEqual(FACE_GATE.adjusted_threshold(75, 0.0, 0), 0.0)

    def test_zero_mesh_visible_ratio_can_auto_pass_when_insightface_has_face(self):
        enriched = FACE_GATE.attach_similarity(self.slots(), {
            "/tmp/a.png": {
                "checks": {
                    "anna": {
                        "ok": True,
                        "similarity_percent": 7.52,
                        "face_visible_ratio": 0.0,
                        "mediapipe_visibility": {
                            "mediapipe_face_visible_ratio": 0.0,
                            "skin_occlusion": {"skin_visible_ratio": 0.7216},
                        },
                    }
                },
                "face_similarity_min_percent": 7.52,
                "adjusted_threshold_min_percent": 0.0,
                "face_similarity_margin_min_percent": 7.52,
            }
        }, 75)
        selected = FACE_GATE.choose_best_slot(enriched)
        self.assertEqual(selected["slot"], "A-01")

    def test_combine_visibility_uses_skin_coverage_even_without_occlusion_flag(self):
        visibility = FACE_GATE.combine_visibility(
            {"available": True, "face_visible_ratio": 0.98},
            {"available": True, "physical_visible_ratio": 0.55, "likely_physical_occlusion": False},
        )
        self.assertEqual(visibility["face_visible_ratio"], 0.55)
        self.assertEqual(visibility["mediapipe_face_visible_ratio"], 0.98)
        self.assertEqual(visibility["visibility_policy"], "mediapipe_face_mesh+skin_coverage")

    def test_combine_visibility_uses_physical_ratio_when_occluded(self):
        visibility = FACE_GATE.combine_visibility(
            {"available": True, "face_visible_ratio": 0.98},
            {"available": True, "physical_visible_ratio": 0.55, "likely_physical_occlusion": True},
        )
        self.assertEqual(visibility["face_visible_ratio"], 0.55)
        self.assertEqual(visibility["visibility_policy"], "mediapipe_face_mesh+skin_coverage")
        self.assertEqual(FACE_GATE.adjusted_threshold(75, visibility["face_visible_ratio"], 0), 41.25)

    def test_skin_occlusion_marks_low_lower_face_skin_as_occluded(self):
        import cv2
        import numpy as np

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:] = (145, 175, 210)
        image[55:95, 20:80] = (20, 20, 20)
        metrics = FACE_GATE.skin_occlusion_metrics(image, [0, 0, 100, 100])
        self.assertTrue(metrics["likely_physical_occlusion"])
        self.assertLess(metrics["mouth_chin_skin_ratio"], 0.35)
        self.assertLess(metrics["physical_visible_ratio"], 1.0)

    def test_expanded_bbox_clamps_to_image_bounds(self):
        box = FACE_GATE.expanded_bbox([80, 80, 100, 100], (100, 100, 3))
        self.assertEqual(box, (65, 65, 100, 100))

    def test_crop_retry_uses_single_bbox_crop_when_full_image_mesh_misses(self):
        import numpy as np

        original_detect = FACE_GATE.detect_face_meshes
        calls = []

        def fake_detect(image, model_path):
            calls.append(image.shape[:2])
            return {
                "available": True,
                "faces": [[
                    SimpleNamespace(x=0.4, y=0.4),
                    SimpleNamespace(x=0.45, y=0.45),
                ]],
                "model_path": str(model_path),
            }

        try:
            FACE_GATE.detect_face_meshes = fake_detect
            image = np.zeros((1000, 1000, 3), dtype=np.uint8)
            visibility = FACE_GATE.visibility_with_crop_retry(
                image,
                {"available": True, "faces": []},
                [400, 400, 500, 500],
                "face_landmarker.task",
            )
        finally:
            FACE_GATE.detect_face_meshes = original_detect

        self.assertEqual(calls, [(250, 250)])
        self.assertTrue(visibility["fallback_used"])
        self.assertEqual(visibility["mesh_detection_source"], "insightface_bbox_crop")
        self.assertEqual(visibility["crop_box_original_image"], [325, 325, 575, 575])
        self.assertEqual(visibility["face_visible_ratio"], 1.0)
        self.assertEqual(visibility["landmarks_total"], 2)
        self.assertEqual(visibility["landmarks_inside_bbox"], 2)

    def test_crop_retry_failure_is_attempted_once_and_reports_reason(self):
        import numpy as np

        original_detect = FACE_GATE.detect_face_meshes
        calls = []

        def fake_detect(image, model_path):
            calls.append(image.shape[:2])
            return {"available": True, "faces": []}

        try:
            FACE_GATE.detect_face_meshes = fake_detect
            image = np.zeros((1000, 1000, 3), dtype=np.uint8)
            visibility = FACE_GATE.visibility_with_crop_retry(
                image,
                {"available": True, "faces": []},
                [400, 400, 500, 500],
                "face_landmarker.task",
            )
        finally:
            FACE_GATE.detect_face_meshes = original_detect

        self.assertEqual(calls, [(250, 250)])
        self.assertTrue(visibility["fallback_used"])
        self.assertEqual(visibility["mesh_detection_source"], "insightface_bbox_crop")
        self.assertEqual(visibility["face_visible_ratio"], 0.0)
        self.assertEqual(visibility["reason"], "no mediapipe face mesh detected after one bbox crop retry")


if __name__ == "__main__":
    unittest.main()
