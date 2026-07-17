#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "TOOLS" / "douyin_publish_preflight.py"
SPEC = importlib.util.spec_from_file_location("douyin_publish_preflight", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class DouyinPublishPreflightTest(unittest.TestCase):
    def test_profile_lock_listener_fallback_passes_when_pids_match(self):
        with mock.patch.object(
            MODULE,
            "chrome_main_processes",
            return_value=[{"pid": None, "command": "__PROCESS_LIST_PERMISSION_DENIED__"}],
        ), mock.patch.object(MODULE, "profile_lock_pid", return_value=123), mock.patch.object(
            MODULE, "cdp_listener_pids", return_value=({123}, None)
        ):
            result = MODULE.check_chrome_processes(
                "http://127.0.0.1:9222", MODULE.DEFAULT_USER_DATA_DIR
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["fallback"]["method"], "profile-lock-listener")

    def test_profile_lock_listener_fallback_rejects_pid_mismatch(self):
        with mock.patch.object(
            MODULE,
            "chrome_main_processes",
            return_value=[{"pid": None, "command": "__PROCESS_LIST_PERMISSION_DENIED__"}],
        ), mock.patch.object(MODULE, "profile_lock_pid", return_value=123), mock.patch.object(
            MODULE, "cdp_listener_pids", return_value=({456}, None)
        ):
            result = MODULE.check_chrome_processes(
                "http://127.0.0.1:9222", MODULE.DEFAULT_USER_DATA_DIR
            )
        self.assertFalse(result["ok"])
        self.assertIn("不匹配", result["error"])

    def test_local_cdp_process_with_user_data_matches(self):
        with mock.patch.object(
            MODULE,
            "chrome_main_processes",
            return_value=[{
                "pid": 123,
                "command": (
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome "
                    f"--user-data-dir={MODULE.DEFAULT_USER_DATA_DIR} --remote-debugging-port=9222"
                ),
            }],
        ):
            result = MODULE.check_chrome_processes(
                "http://127.0.0.1:9222", MODULE.DEFAULT_USER_DATA_DIR
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["target_count"], 1)

    def test_default_profile_process_without_user_data_rejected(self):
        with mock.patch.object(
            MODULE,
            "chrome_main_processes",
            return_value=[{
                "pid": 123,
                "command": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --remote-debugging-port=9222",
            }],
        ):
            result = MODULE.check_chrome_processes(
                "http://127.0.0.1:9222", MODULE.DEFAULT_USER_DATA_DIR
            )
        self.assertFalse(result["ok"])

    def test_local_cdp_and_regular_chrome_can_coexist(self):
        with mock.patch.object(
            MODULE,
            "chrome_main_processes",
            return_value=[
                {
                    "pid": 123,
                    "command": (
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome "
                        f"--user-data-dir={MODULE.DEFAULT_USER_DATA_DIR} --remote-debugging-port=9222"
                    ),
                },
                {
                    "pid": 456,
                    "command": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                },
            ],
        ):
            result = MODULE.check_chrome_processes(
                "http://127.0.0.1:9222", MODULE.DEFAULT_USER_DATA_DIR
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["target_count"], 1)
        self.assertEqual(result["auxiliary_count"], 1)


if __name__ == "__main__":
    unittest.main()
