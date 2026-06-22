#!/usr/bin/env python3
"""Check local prerequisites for the Douyin publish helper."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_USER_DATA_DIR = Path.home() / "Library/Application Support/Google/Chrome-Codex-CDP"


def check_playwright() -> dict[str, Any]:
    try:
        import playwright.async_api  # type: ignore  # noqa: F401
    except Exception as exc:
        return {
            "ok": False,
            "reason": str(exc),
            "fix": "python3 -m pip install playwright",
        }
    return {"ok": True}


def fetch_json(url: str, timeout: int) -> tuple[dict[str, Any] | list[Any] | None, str | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8")), None
    except urllib.error.URLError as exc:
        return None, str(exc)
    except Exception as exc:
        return None, str(exc)


def chrome_main_processes() -> list[dict[str, Any]]:
    current_user = getpass.getuser()
    try:
        proc = subprocess.run(
            ["ps", "-axo", "user=,pid=,command="],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except PermissionError:
        return [{"pid": None, "command": "__PROCESS_LIST_PERMISSION_DENIED__"}]
    processes = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        user, _, rest = stripped.partition(" ")
        if user != current_user:
            continue
        pid_text, _, command = rest.strip().partition(" ")
        if not command.startswith("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            pid = None
            command = stripped
        processes.append({"pid": pid, "command": command})
    return processes


def command_has_user_data(command: str, expected_user_data_dir: Path) -> bool:
    return f"--user-data-dir={expected_user_data_dir}" in command


def command_has_cdp_port(command: str, cdp_url: str) -> bool:
    port = cdp_url.rstrip("/").rsplit(":", 1)[-1]
    return f"--remote-debugging-port={port}" in command


def profile_lock_pid(expected_user_data_dir: Path) -> int | None:
    lock_path = expected_user_data_dir / "SingletonLock"
    try:
        target = os.readlink(lock_path)
    except OSError:
        return None
    match = re.search(r"-(\d+)$", target)
    return int(match.group(1)) if match else None


def cdp_listener_pids(cdp_url: str) -> tuple[set[int], str | None]:
    port = cdp_url.rstrip("/").rsplit(":", 1)[-1]
    try:
        proc = subprocess.run(
            ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except (FileNotFoundError, PermissionError) as exc:
        return set(), str(exc)
    pids = {
        int(line[1:])
        for line in proc.stdout.splitlines()
        if line.startswith("p") and line[1:].isdigit()
    }
    return pids, proc.stderr.strip() or None


def check_profile_lock_listener(cdp_url: str, expected_user_data_dir: Path) -> dict[str, Any]:
    lock_pid = profile_lock_pid(expected_user_data_dir)
    listener_pids, error = cdp_listener_pids(cdp_url)
    ok = lock_pid is not None and lock_pid in listener_pids
    return {
        "ok": ok,
        "method": "profile-lock-listener",
        "profile_lock_pid": lock_pid,
        "listener_pids": sorted(listener_pids),
        "error": error,
    }


def check_chrome_processes(cdp_url: str, expected_user_data_dir: Path) -> dict[str, Any]:
    processes = chrome_main_processes()
    if processes and processes[0].get("command") == "__PROCESS_LIST_PERMISSION_DENIED__":
        fallback = check_profile_lock_listener(cdp_url, expected_user_data_dir)
        return {
            "ok": fallback["ok"],
            "expected_user_data_dir": str(expected_user_data_dir),
            "target_count": 0,
            "wrong_count": 0,
            "target": [],
            "wrong": [],
            "fallback": fallback,
            "warning": "当前环境不允许读取 Chrome 进程列表，已改用 Profile 锁 PID 与 CDP 监听 PID 核对。"
            if fallback["ok"]
            else None,
            "error": None
            if fallback["ok"]
            else "当前环境不允许读取 Chrome 进程列表，且 Profile 锁 PID 与 CDP 监听 PID 不匹配。",
            "fix": None
            if fallback["ok"]
            else "请运行 TOOLS/open_cdp_chrome.sh 9222 启动当前账户本地 CDP Chrome。",
        }
    target = [
        item
        for item in processes
        if command_has_user_data(item["command"], expected_user_data_dir)
        and command_has_cdp_port(item["command"], cdp_url)
    ]
    wrong = [item for item in processes if item not in target]
    ok = len(target) == 1 and not wrong
    return {
        "ok": ok,
        "expected_user_data_dir": str(expected_user_data_dir),
        "target_count": len(target),
        "wrong_count": len(wrong),
        "target": target,
        "wrong": wrong,
        "fix": "请运行 TOOLS/open_cdp_chrome.sh；入口会用当前账户本地非共享 CDP 用户目录启动 Chrome"
        if not ok
        else None,
    }


def check_cdp(cdp_url: str, timeout: int, expected_user_data_dir: Path) -> dict[str, Any]:
    version, version_error = fetch_json(cdp_url.rstrip("/") + "/json/version", timeout)
    tabs, tabs_error = fetch_json(cdp_url.rstrip("/") + "/json", timeout)
    ok = isinstance(version, dict) and isinstance(tabs, list)
    process_check = check_chrome_processes(cdp_url, expected_user_data_dir)
    creator_tabs = []
    if isinstance(tabs, list):
        creator_tabs = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
            }
            for item in tabs
            if "creator.douyin.com" in str(item.get("url") or "")
        ]
    return {
        "ok": ok and process_check.get("ok"),
        "cdp_url": cdp_url,
        "browser": version.get("Browser") if isinstance(version, dict) else None,
        "tab_count": len(tabs) if isinstance(tabs, list) else 0,
        "creator_tab_count": len(creator_tabs),
        "creator_tabs": creator_tabs,
        "process": process_check,
        "errors": [item for item in [version_error, tabs_error] if item],
        "fix": (
            "请运行：TOOLS/open_cdp_chrome.sh "
            f"{cdp_url.rstrip('/').rsplit(':', 1)[-1]}"
        )
        if not (ok and process_check.get("ok"))
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查抖音发布自动化本地环境。")
    parser.add_argument(
        "--cdp-url",
        default=os.environ.get("DOUYIN_CHROME_CDP_URL") or DEFAULT_CDP_URL,
        help=f"Chrome DevTools Protocol 地址，默认 {DEFAULT_CDP_URL}",
    )
    parser.add_argument(
        "--user-data-dir",
        default=str(DEFAULT_USER_DATA_DIR),
        help=f"当前账户本地 CDP Chrome 用户目录，默认 {DEFAULT_USER_DATA_DIR}",
    )
    parser.add_argument("--timeout", type=int, default=3, help="CDP HTTP 检查超时秒数")
    args = parser.parse_args()
    expected_user_data_dir = Path(args.user_data_dir).expanduser().resolve()

    report = {
        "playwright": check_playwright(),
        "cdp": check_cdp(args.cdp_url, args.timeout, expected_user_data_dir),
    }
    report["ok"] = bool(report["playwright"].get("ok") and report["cdp"].get("ok"))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
