import importlib.util
import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT_ROOT / "TOOLS" / "publish_tag_pool.py"
SPEC = importlib.util.spec_from_file_location("publish_tag_pool", SCRIPT)
PUBLISH_TAG_POOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PUBLISH_TAG_POOL)


class PublishTagPoolTest(unittest.TestCase):
    def setUp(self):
        self.pool = json.loads(
            (PROJECT_ROOT / "MATERIAL" / "publish-tag-pool.json").read_text(encoding="utf-8")
        )

    def test_pool_contains_only_general_outfit_tags(self):
        self.assertNotIn("scene_tags", self.pool)
        self.assertNotIn("旅行", self.pool["source"])
        self.assertNotIn("场景", self.pool["source"])
        self.assertGreaterEqual(len(self.pool["tags"]), self.pool["default_count"])

    def test_sampling_returns_unique_unblocked_tags(self):
        selected = PUBLISH_TAG_POOL.sample_tags(self.pool, self.pool["default_count"])
        self.assertEqual(len(selected), self.pool["default_count"])
        self.assertEqual(len(selected), len(set(selected)))
        self.assertTrue(set(selected).isdisjoint(self.pool["blocked_tags"]))


if __name__ == "__main__":
    unittest.main()
