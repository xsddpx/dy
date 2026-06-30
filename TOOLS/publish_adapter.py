#!/usr/bin/env python3
"""Unified command-line entry point for platform publish adapters."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from run_record import append_artifact, append_event, refresh_markdown

DUAL_PLATFORM_ORDER = ("douyin", "kuaishou")


@dataclass(frozen=True)
class AdapterSpec:
    name: str
    helper: Path
    environment_cdp_key: str

    def command(self, passthrough: list[str]) -> list[str]:
        return [sys.executable, str(self.helper), *passthrough]


ADAPTERS = {
    "douyin": AdapterSpec(
        name="douyin",
        helper=TOOLS_DIR / "douyin_publish_helper.py",
        environment_cdp_key="DOUYIN_CHROME_CDP_URL",
    ),
    "kuaishou": AdapterSpec(
        name="kuaishou",
        helper=TOOLS_DIR / "kuaishou_publish_helper.py",
        environment_cdp_key="KUAISHOU_CHROME_CDP_URL",
    ),
}


def option_value(args: list[str], option: str) -> str | None:
    for index, value in enumerate(args):
        if value == option and index + 1 < len(args):
            return args[index + 1]
        if value.startswith(option + "="):
            return value.split("=", 1)[1]
    return None


def option_present(args: list[str], option: str) -> bool:
    return any(value == option for value in args)


def ensure_option(args: list[str], option: str, value: str) -> list[str]:
    if option_value(args, option) is not None:
        return list(args)
    return [*args, option, value]


def get_adapter(name: str) -> AdapterSpec:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        choices = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"未知发布平台 {name!r}；可选：{choices}") from exc


def default_publish_out_dir() -> Path:
    return Path("TEMP/publish-runs") / datetime.now().strftime("%Y%m%d-%H%M%S")


def platform_report_path(out_dir: Path, platform: str) -> Path:
    return out_dir / f"{platform}-publish-report.json"


def load_platform_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"decision": "missing-report", "errors": [f"报告不存在：{path}"]}
    except json.JSONDecodeError as exc:
        return {"decision": "invalid-report", "errors": [f"报告 JSON 无法解析：{exc}"]}


def summarize_platform(
    platform: str,
    command: list[str],
    returncode: int,
    out_dir: Path,
) -> dict[str, Any]:
    report_json = platform_report_path(out_dir, platform)
    report = load_platform_report(report_json)
    return {
        "platform": platform,
        "returncode": returncode,
        "decision": report.get("decision"),
        "report_json": str(report_json),
        "report_md": str(report_json.with_suffix(".md")),
        "errors": report.get("errors", []),
        "warnings": report.get("warnings", []),
        "command": command,
    }


def overall_decision(platforms: list[dict[str, Any]]) -> str:
    if platforms and all(
        item.get("returncode") == 0 and item.get("decision") == "published"
        for item in platforms
    ):
        return "published"
    return "blocked"


def write_both_report(
    out_dir: Path,
    record_jsonl: str | None,
    report: dict[str, Any],
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "publish-both-report.json"
    md_path = out_dir / "publish-both-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 双平台发布聚合报告",
        "",
        f"- 结论：{report.get('decision')}",
        f"- 输出目录：{out_dir}",
        "",
        "## 平台结果",
    ]
    for item in report.get("platforms", []):
        lines.extend(
            [
                f"- {item.get('platform')}：{item.get('decision')} / returncode={item.get('returncode')}",
                f"  - 报告：{item.get('report_json')}",
            ]
        )
        for error in item.get("errors") or []:
            lines.append(f"  - Error：{error}")
        for warning in item.get("warnings") or []:
            lines.append(f"  - Warning：{warning}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if record_jsonl:
        append_event(
            record_jsonl,
            stage="publish",
            event="both_publish",
            status=report.get("decision"),
            summary=(
                "双平台发布 "
                + ", ".join(
                    f"{item.get('platform')}={item.get('decision')}"
                    for item in report.get("platforms", [])
                )
                + f", overall={report.get('decision')}"
            ),
            data={
                "overall": report.get("decision"),
                "platforms": report.get("platforms", []),
                "report_json": str(json_path),
            },
        )
        append_artifact(
            record_jsonl,
            stage="publish",
            path=str(json_path),
            kind="publish-both-report",
            status=report.get("decision"),
            keep=True,
            summary="双平台发布聚合 JSON 报告",
        )
        refresh_markdown(record_jsonl)
    return json_path, md_path


def run_both(passthrough: list[str]) -> int:
    out_dir = Path(option_value(passthrough, "--out-dir") or default_publish_out_dir())
    passthrough = ensure_option(passthrough, "--out-dir", str(out_dir))
    if option_value(passthrough, "--location") is None and not option_present(passthrough, "--no-location"):
        passthrough = [*passthrough, "--no-location"]
    record_jsonl = option_value(passthrough, "--record-jsonl")

    started_at = datetime.now().isoformat(timespec="seconds")
    platform_results: list[dict[str, Any]] = []
    for platform in DUAL_PLATFORM_ORDER:
        adapter = get_adapter(platform)
        command = adapter.command(passthrough)
        returncode = subprocess.call(command)
        platform_results.append(summarize_platform(platform, command, returncode, out_dir))

    decision = overall_decision(platform_results)
    report = {
        "decision": decision,
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "platform_order": list(DUAL_PLATFORM_ORDER),
        "out_dir": str(out_dir),
        "platforms": platform_results,
    }
    report["report_json"] = str(out_dir / "publish-both-report.json")
    report["report_md"] = str(out_dir / "publish-both-report.md")
    report_json, report_md = write_both_report(out_dir, record_jsonl, report)
    report["report_json"] = str(report_json)
    report["report_md"] = str(report_md)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if decision == "published":
        return 0
    return next((item["returncode"] for item in platform_results if item["returncode"]), 1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="统一发布入口；平台参数之后的选项会原样交给对应 adapter。",
    )
    parser.add_argument("platform", choices=[*sorted(ADAPTERS), "both"], help="发布平台")
    args, passthrough = parser.parse_known_args(argv)
    if args.platform == "both":
        return run_both(passthrough)
    adapter = get_adapter(args.platform)
    return subprocess.call(adapter.command(passthrough))


if __name__ == "__main__":
    raise SystemExit(main())
