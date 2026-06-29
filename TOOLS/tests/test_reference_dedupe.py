import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "reference_dedupe.py"
SPEC = importlib.util.spec_from_file_location("reference_dedupe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReferenceDedupeTests(unittest.TestCase):
    def test_blocklist_match_blocks_outside_window(self):
        canonical = MODULE.canonicalize("https://www.douyin.com/video/1234567890")
        history = {
            "entries": [
                {
                    "recorded_at": "2020-01-01T00:00:00+00:00",
                    "route": "anna",
                    "status": "used",
                    "video_id": "1234567890",
                    "canonical_url": "https://www.douyin.com/video/1234567890",
                }
            ]
        }
        blocklist = {
            "entries": [
                {
                    "route": "anna",
                    "status": "blocked_by_user",
                    "video_id": "1234567890",
                    "canonical_url": "https://www.douyin.com/video/1234567890",
                    "reason": "user rejected",
                }
            ]
        }

        duplicate = MODULE.find_duplicate(
            history,
            canonical,
            MODULE.parse_time("2026-06-29T00:00:00+00:00"),
            7,
        )
        blocked = MODULE.find_blocked(blocklist, canonical)

        self.assertIsNone(duplicate)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked["status"], "blocked_by_user")

    def test_disabled_blocklist_entry_is_ignored(self):
        canonical = MODULE.canonicalize("https://www.douyin.com/video/1234567890")
        blocklist = {
            "entries": [
                {
                    "enabled": False,
                    "video_id": "1234567890",
                    "canonical_url": "https://www.douyin.com/video/1234567890",
                }
            ]
        }

        self.assertIsNone(MODULE.find_blocked(blocklist, canonical))

    def test_cli_check_reports_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = root / "history.json"
            blocklist = root / "blocklist.json"
            history.write_text('{"version":1,"entries":[]}', encoding="utf-8")
            blocklist.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "entries": [
                            {
                                "video_id": "1234567890",
                                "canonical_url": "https://www.douyin.com/video/1234567890",
                                "status": "blocked_by_user",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            parser = MODULE.build_parser()
            args = parser.parse_args(
                [
                    "check",
                    "https://www.douyin.com/video/1234567890",
                    "--history",
                    str(history),
                    "--blocklist",
                    str(blocklist),
                    "--now",
                    "2026-06-29T00:00:00+00:00",
                ]
            )

            self.assertEqual(args.func(args), 1)


if __name__ == "__main__":
    unittest.main()
