import importlib.util
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "reference_dedupe.py"
SPEC = importlib.util.spec_from_file_location("reference_dedupe", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class ReferenceDedupeTests(unittest.TestCase):
    def test_blocklist_match_blocks_reference(self):
        canonical = MODULE.canonicalize("https://www.douyin.com/video/1234567890")
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

        blocked = MODULE.find_blocked(blocklist, canonical)

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

    def test_canonicalize_prefers_video_id_from_query(self):
        canonical = MODULE.canonicalize(
            "https://www.douyin.com/share/video?aweme_id=1234567890&utm_source=copy"
        )

        self.assertEqual(canonical["video_id"], "1234567890")
        self.assertEqual(canonical["canonical_url"], "https://www.douyin.com/video/1234567890")
        self.assertEqual(canonical["match_key"], "id:1234567890")

    def test_cli_check_reports_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocklist = root / "blocklist.json"
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
                    "--blocklist",
                    str(blocklist),
                ]
            )

            output = StringIO()
            with redirect_stdout(output):
                code = args.func(args)

            result = json.loads(output.getvalue())
            self.assertEqual(code, 1)
            self.assertTrue(result["blocked"])
            self.assertEqual(result["decision"], "skip_autonomous")

    def test_cli_check_reports_use_for_unblocked_reference(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocklist = root / "blocklist.json"
            blocklist.write_text('{"version":1,"entries":[]}', encoding="utf-8")
            parser = MODULE.build_parser()
            args = parser.parse_args(
                [
                    "check",
                    "https://www.douyin.com/video/1234567890",
                    "--blocklist",
                    str(blocklist),
                ]
            )

            output = StringIO()
            with redirect_stdout(output):
                code = args.func(args)

            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertFalse(result["blocked"])
            self.assertEqual(result["decision"], "use")


if __name__ == "__main__":
    unittest.main()
