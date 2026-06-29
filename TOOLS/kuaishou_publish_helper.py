#!/usr/bin/env python3
"""Publish one video through Kuaishou Creator Center using the CDP Chrome."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from douyin_publish_preflight import DEFAULT_USER_DATA_DIR, check_cdp, check_playwright
from run_record import append_artifact, append_event, refresh_markdown


DEFAULT_UPLOAD_URL = "https://cp.kuaishou.com/article/publish/video?tabType=1"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
AI_DECLARATION_WORDS = ("内容为AI生成", "内容由AI生成", "AI生成", "人工智能生成", "AIGC")
LOGIN_WORDS = ("立即登录", "扫码登录", "验证码登录", "手机号登录", "请先登录")
HARD_ERROR_WORDS = ("发布失败", "上传失败", "禁止发布", "无法发布", "安全验证", "账号异常")
VR360_MODE_WORDS = ("正在使用VR360°全景视频上传模式", "VR360°全景视频上传模式")
UPLOAD_IN_PROGRESS_WORDS = ("上传中", "预览转码中", "转码过程也可以发布")


def is_kuaishou_page(url: str) -> bool:
    return "cp.kuaishou.com" in url


def is_publish_page(url: str) -> bool:
    return "cp.kuaishou.com/article/publish/video" in url


def normalize_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    for raw in tags:
        value = raw.strip().lstrip("#")
        if value and value not in result:
            result.append(value)
    return result[:5]


def build_caption(title: str, description: str, tags: list[str]) -> str:
    parts = [title.strip(), description.strip()]
    caption = "\n".join(part for part in parts if part)
    missing = [tag for tag in normalize_tags(tags) if f"#{tag}" not in caption]
    suffix = " ".join(f"#{tag}" for tag in missing)
    return "\n".join(part for part in (caption, suffix) if part)


def classify_publish_snapshot(snapshot: dict[str, Any]) -> str:
    text = str(snapshot.get("text") or snapshot.get("textSample") or "")
    url = str(snapshot.get("url") or "")
    if any(word in text for word in HARD_ERROR_WORDS):
        return "hard-error"
    if any(word in text for word in ("发布成功", "作品发布成功", "上传成功")):
        return "success"
    if "/article/manage" in url or "/content/manage" in url:
        return "success"
    if any(word in text for word in ("上传中", "处理中", "发布中")):
        return "pending"
    return "unknown"


def ai_declaration_is_set(text: str) -> bool:
    return any(word in text for word in AI_DECLARATION_WORDS)


def click_locator_flexibly(locator: Any, timeout_ms: int = 3000) -> dict[str, Any]:
    errors: list[str] = []
    for force in (False, True):
        try:
            locator.click(timeout=timeout_ms, force=force)
            return {"ok": True, "method": "force" if force else "normal"}
        except Exception as exc:
            errors.append(str(exc))

    try:
        container = locator.locator(
            "xpath=ancestor::*[contains(@class, 'ant-select') or contains(@class, 'ant-select-selector')][1]"
        )
        if container.count() > 0:
            for force in (False, True):
                try:
                    container.click(timeout=timeout_ms, force=force)
                    return {"ok": True, "method": "ancestor-force" if force else "ancestor"}
                except Exception as exc:
                    errors.append(str(exc))
    except Exception as exc:
        errors.append(str(exc))

    return {"ok": False, "errors": errors[-3:]}


def run_preflight(cdp_url: str) -> dict[str, Any]:
    playwright = check_playwright()
    cdp = check_cdp(cdp_url, timeout=3, expected_user_data_dir=DEFAULT_USER_DATA_DIR)
    return {
        "ok": bool(playwright.get("ok") and cdp.get("ok")),
        "playwright": playwright,
        "cdp": cdp,
    }


def find_or_open_page(browser: Any, upload_url: str, timeout_ms: int) -> Any:
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("CDP 已连接，但没有可用浏览器上下文")
    page = contexts[0].new_page()
    page.bring_to_front()
    page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_ms)
    discard_unpublished_draft(page)
    return page


def discard_unpublished_draft(page: Any) -> dict[str, Any]:
    try:
        text = page.locator("body").inner_text(timeout=5000)
    except Exception as exc:
        return {"status": "skipped", "reason": f"读取页面失败：{exc}"}
    if "还有上次未发布的视频" not in text:
        return {"status": "skipped", "reason": "没有未发布草稿提示"}
    discard = page.get_by_text("放弃", exact=True).last
    if discard.count() == 0 or not discard.is_visible():
        return {"status": "failed", "reason": "未找到放弃草稿按钮"}
    discard.click(timeout=3000)
    page.wait_for_timeout(1000)
    return {"status": "discarded"}


def snapshot_has_vr360_mode(snapshot: dict[str, Any]) -> bool:
    text = str(snapshot.get("text") or snapshot.get("textSample") or "")
    return any(word in text for word in VR360_MODE_WORDS)


def page_login_blocker(page: Any) -> str | None:
    text = page.locator("body").inner_text(timeout=10_000)
    for word in LOGIN_WORDS:
        if word in text:
            return word
    return None


def upload_video(page: Any, video: Path, timeout_ms: int) -> dict[str, Any]:
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 30_000))
    except Exception:
        pass

    upload_buttons = (
        'button:has-text("上传视频")',
        'text=点击上传视频',
        'text=上传视频',
    )
    for selector in upload_buttons:
        trigger = page.locator(selector).last
        if trigger.count() == 0:
            continue
        try:
            if not trigger.is_visible():
                continue
            with page.expect_file_chooser(timeout=5000) as chooser_info:
                trigger.click(timeout=3000, force=True)
            chooser_info.value.set_files(str(video))
            return {"status": "submitted", "path": str(video), "selector": selector, "method": "file-chooser"}
        except Exception:
            continue

    selectors = (
        'input[type="file"][accept*="video"]',
        'input[type="file"][accept*=".mp4"]',
        'input[type="file"]',
    )
    deadline = time.time() + timeout_ms / 1000
    last_error = ""
    clicked_upload = False
    while time.time() < deadline:
        for selector in selectors:
            locator = page.locator(selector)
            count = locator.count()
            if count == 0:
                continue
            for index in range(count):
                candidate = locator.nth(index)
                accept = ""
                try:
                    accept = candidate.get_attribute("accept") or ""
                    if selector == 'input[type="file"]' and accept and "image" in accept and "video" not in accept:
                        continue
                    candidate.set_input_files(str(video), timeout=10_000)
                    return {"status": "submitted", "path": str(video), "selector": selector, "index": index, "accept": accept}
                except Exception as exc:
                    last_error = str(exc)
                    continue

        if not clicked_upload:
            clicked_upload = True
            try:
                button = page.get_by_text("上传视频", exact=False).last
                if button.count() > 0 and button.is_visible():
                    button.click(timeout=3000)
                    page.wait_for_timeout(500)
                    continue
            except Exception as exc:
                last_error = str(exc)
        page.wait_for_timeout(800)

    raise RuntimeError(f"没有找到可用的视频上传 input：{last_error or 'timeout'}")


def wait_for_publish_form(page: Any, timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        text = page.locator("body").inner_text(timeout=10_000)
        fields = page.locator("textarea, input, [contenteditable=true]")
        description = page.locator("#work-description-edit")
        description_ready = description.count() > 0 and description.first.is_visible()
        snapshot = {
            "url": page.url,
            "field_count": fields.count(),
            "textSample": text[:1200],
            "hardError": any(word in text for word in ("上传失败", "格式不支持", "视频处理失败")),
            "vrMode": any(word in text for word in VR360_MODE_WORDS),
            "loginOrVerify": any(word in text for word in LOGIN_WORDS + ("安全验证",)),
            "ready": description_ready
            or (
                fields.count() > 0
                and any(word in text for word in ("作品描述", "作品标题", "添加描述"))
            ),
        }
        if snapshot["hardError"] or snapshot["vrMode"] or snapshot["loginOrVerify"] or snapshot["ready"]:
            return snapshot
        page.wait_for_timeout(1500)
    return snapshot


def wait_for_upload_complete(page: Any, timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        text = page.locator("body").inner_text(timeout=10_000)
        upload_in_progress = any(word in text for word in UPLOAD_IN_PROGRESS_WORDS)
        snapshot = {
            "url": page.url,
            "textSample": text[:1200],
            "hardError": any(word in text for word in ("上传失败", "格式不支持", "视频处理失败")),
            "vrMode": any(word in text for word in VR360_MODE_WORDS),
            "loginOrVerify": any(word in text for word in LOGIN_WORDS + ("安全验证",)),
            "uploadInProgress": upload_in_progress,
            "complete": not upload_in_progress and "重新上传" in text,
        }
        if snapshot["hardError"] or snapshot["vrMode"] or snapshot["loginOrVerify"] or snapshot["complete"]:
            return snapshot
        page.wait_for_timeout(1500)
    return snapshot


def fill_caption(page: Any, caption: str) -> dict[str, Any]:
    guide_close = page.locator('[role="button"][class*="close"]')
    if page.locator(".react-joyride__overlay").count() > 0:
        for index in range(guide_close.count()):
            candidate = guide_close.nth(index)
            if candidate.is_visible():
                candidate.click()
                page.wait_for_timeout(300)
                break

    selectors = (
        "#work-description-edit",
        'textarea[placeholder*="描述"]',
        'textarea[placeholder*="标题"]',
        'input[placeholder*="描述"]',
        'input[placeholder*="标题"]',
        '[contenteditable=true]',
        "textarea",
    )
    for selector in selectors:
        matches = page.locator(selector)
        for index in range(matches.count()):
            locator = matches.nth(index)
            if not locator.is_visible():
                continue
            locator.click()
            try:
                locator.fill(caption)
            except Exception:
                locator.press("Meta+A")
                locator.type(caption)
            return {"status": "filled", "selector": selector, "caption": caption}
    return {"status": "failed", "reason": "没有找到作品描述或标题输入框"}


def set_ai_declaration(page: Any, timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    page_text = page.locator("body").inner_text(timeout=10_000)
    if ai_declaration_is_set(page_text) and "请选择" not in page_text:
        return {"status": "set", "method": "already-selected"}

    placeholder = page.get_by_text("为作品添加补充说明", exact=True)
    if placeholder.count() > 0 and placeholder.last.is_visible():
        click_locator_flexibly(placeholder.last)

    trigger_patterns = ("作品声明", "内容声明", "自主声明", "AI生成", "人工智能生成")
    for pattern in trigger_patterns:
        trigger = page.get_by_text(pattern, exact=False).last
        if trigger.count() == 0 or not trigger.is_visible():
            continue
        result = click_locator_flexibly(trigger)
        if result.get("ok"):
            break

    while time.time() < deadline:
        for word in AI_DECLARATION_WORDS:
            option = page.get_by_text(word, exact=False).last
            if option.count() == 0 or not option.is_visible():
                continue
            result = click_locator_flexibly(option)
            if not result.get("ok"):
                continue
            page.wait_for_timeout(500)
            text = page.locator("body").inner_text(timeout=10_000)
            if ai_declaration_is_set(text):
                return {"status": "set", "method": result.get("method") or "text-option", "matched": word}
        page.wait_for_timeout(500)
    return {"status": "failed", "reason": "未能确认快手页面已设置“内容由AI生成”声明"}


def click_publish(page: Any) -> dict[str, Any]:
    for label in ("发布", "立即发布", "发布作品"):
        button = page.get_by_role("button", name=label, exact=True).last
        if button.count() == 0:
            button = page.get_by_text(label, exact=True).last
        if button.count() == 0 or not button.is_visible():
            continue
        if not button.is_enabled():
            return {"status": "failed", "reason": f"{label}按钮禁用"}
        button.click()
        return {"status": "clicked", "label": label}
    return {"status": "failed", "reason": "没有找到快手发布按钮"}


def wait_for_publish_result(page: Any, timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    snapshot: dict[str, Any] = {}
    while time.time() < deadline:
        text = page.locator("body").inner_text(timeout=10_000)
        snapshot = {"url": page.url, "textSample": text[:1600]}
        status = classify_publish_snapshot(snapshot)
        snapshot["status"] = status
        if status in {"success", "hard-error"}:
            return snapshot
        page.wait_for_timeout(1500)
    return snapshot


def write_report(out_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "kuaishou-publish-report.json"
    md_path = out_dir / "kuaishou-publish-report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(
        "\n".join(
            [
                "# 快手发布 Adapter 报告",
                "",
                f"- 结论：{report.get('decision')}",
                f"- 视频：{report.get('video')}",
                f"- 标题：{report.get('title')}",
                f"- 上传：{report.get('steps', {}).get('upload', {}).get('status')}",
                f"- 文案：{report.get('steps', {}).get('copywriting', {}).get('status')}",
                f"- AI 声明：{report.get('steps', {}).get('declaration', {}).get('status')}",
                f"- 位置：{report.get('steps', {}).get('location', {}).get('status')}",
                f"- 发布：{report.get('steps', {}).get('publish', {}).get('status')}",
                "",
                "## Errors",
                *([f"- {item}" for item in report.get("errors", [])] or ["- 无"]),
                "",
                "## Warnings",
                *([f"- {item}" for item in report.get("warnings", [])] or ["- 无"]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    if report.get("record_jsonl"):
        append_event(
            report["record_jsonl"],
            stage="publish",
            event="kuaishou_publish",
            status=report.get("decision"),
            summary=f"快手发布 {report.get('decision')}",
            data={"video": report.get("video"), "report_json": str(json_path), "steps": report.get("steps", {})},
        )
        append_artifact(
            report["record_jsonl"],
            stage="publish",
            path=str(json_path),
            kind="kuaishou-publish-report",
            status=report.get("decision"),
            keep=True,
            summary="快手发布 JSON 报告",
        )
        refresh_markdown(report["record_jsonl"])
    return json_path, md_path


def fail(report: dict[str, Any], out_dir: Path, message: str, code: int) -> int:
    report["decision"] = "blocked"
    report["errors"].append(message)
    write_report(out_dir, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="通过 CDP Chrome 发布快手视频。")
    parser.add_argument("video", help="待发布 MP4")
    parser.add_argument("--title", required=True, help="作品标题")
    parser.add_argument("--description", default="", help="作品描述")
    parser.add_argument("--tag", action="append", default=[], help="话题标签，可重复")
    parser.add_argument("--cdp-url", default=os.environ.get("KUAISHOU_CHROME_CDP_URL") or DEFAULT_CDP_URL)
    parser.add_argument("--upload-url", default=DEFAULT_UPLOAD_URL)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--record-jsonl", default=None)
    parser.add_argument("--upload-timeout", type=int, default=300)
    parser.add_argument("--publish-timeout", type=int, default=90)
    parser.add_argument("--declaration-timeout", type=int, default=20)
    parser.add_argument("--location", default=None, help="兼容双平台入口；快手不设置发布地址，会忽略该参数")
    parser.add_argument("--no-location", action="store_true", help="兼容双平台入口；快手固定不设置发布地址")
    parser.add_argument("--location-timeout", type=int, default=15, help="兼容双平台入口；快手固定不设置发布地址")
    parser.add_argument("--no-publish", action="store_true", help="停在发布按钮前")
    parser.add_argument("--dry-run", action="store_true", help="只校验参数并生成报告")
    args = parser.parse_args(argv)

    video = Path(args.video).expanduser().resolve()
    out_dir = Path(args.out_dir) if args.out_dir else Path("TEMP/publish-runs") / datetime.now().strftime("%Y%m%d-%H%M%S")
    report = {
        "platform": "kuaishou",
        "decision": "pending",
        "video": str(video),
        "title": args.title,
        "description": args.description,
        "tags": normalize_tags(args.tag),
        "location": {"status": "skipped", "reason": "快手不设置发布地址"},
        "record_jsonl": args.record_jsonl,
        "steps": {"preflight": {}, "upload": {}, "copywriting": {}, "declaration": {}, "location": {}, "publish": {}},
        "errors": [],
        "warnings": [],
    }
    if not video.is_file():
        return fail(report, out_dir, f"视频文件不存在：{video}", 2)
    if not args.title.strip():
        return fail(report, out_dir, "标题不能为空", 2)
    if args.dry_run:
        report["decision"] = "dry-run-pass"
        write_report(out_dir, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    preflight = run_preflight(args.cdp_url)
    report["steps"]["preflight"] = preflight
    if not preflight["ok"]:
        return fail(report, out_dir, "当前账户本地 CDP Chrome 预检失败", 3)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(args.cdp_url)
            page = find_or_open_page(browser, args.upload_url, 30_000)
            blocker = page_login_blocker(page)
            if blocker:
                return fail(report, out_dir, f"快手创作者中心需要登录或验证：{blocker}", 3)

            report["steps"]["upload"].update(upload_video(page, video, 30_000))
            form = wait_for_publish_form(page, args.upload_timeout)
            report["steps"]["upload"]["form"] = form
            if form.get("vrMode") or snapshot_has_vr360_mode(form):
                return fail(report, out_dir, "快手当前处于 VR360 全景视频上传模式，已阻断发布", 4)
            if form.get("loginOrVerify") or form.get("hardError") or not form.get("ready"):
                return fail(report, out_dir, "快手上传后未进入可发布表单", 4)
            report["steps"]["upload"]["status"] = "uploaded-or-form-ready"

            copywriting = fill_caption(page, build_caption(args.title, args.description, args.tag))
            report["steps"]["copywriting"].update(copywriting)
            if copywriting["status"] != "filled":
                return fail(report, out_dir, copywriting["reason"], 5)

            declaration = set_ai_declaration(page, args.declaration_timeout)
            report["steps"]["declaration"].update(declaration)
            if declaration["status"] != "set":
                return fail(report, out_dir, declaration["reason"], 6)

            report["steps"]["location"].update({"status": "skipped", "reason": "快手不设置发布地址"})

            upload_complete = wait_for_upload_complete(page, args.upload_timeout)
            report["steps"]["upload"]["complete"] = upload_complete
            if upload_complete.get("vrMode") or snapshot_has_vr360_mode(upload_complete):
                return fail(report, out_dir, "快手当前处于 VR360 全景视频上传模式，已阻断发布", 4)
            if upload_complete.get("loginOrVerify") or upload_complete.get("hardError"):
                return fail(report, out_dir, "快手上传完成前出现阻断状态", 4)
            if not upload_complete.get("complete"):
                return fail(report, out_dir, "快手视频上传未完成，已阻断发布", 4)

            if args.no_publish:
                report["decision"] = "ready-not-published"
                report["steps"]["publish"]["status"] = "skipped-by-no-publish"
                write_report(out_dir, report)
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return 0

            publish = click_publish(page)
            report["steps"]["publish"].update(publish)
            if publish["status"] != "clicked":
                return fail(report, out_dir, publish["reason"], 7)
            result = wait_for_publish_result(page, args.publish_timeout)
            report["steps"]["publish"]["result"] = result
            if result.get("status") == "hard-error":
                return fail(report, out_dir, "点击发布后页面出现硬错误", 7)
            # 项目规则以发布按钮成功点击为发布成功判定；页面结果仅作为证据。
            report["decision"] = "published"
            report["steps"]["publish"]["status"] = "published"
            write_report(out_dir, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        return fail(report, out_dir, f"快手发布 adapter 异常：{exc}", 8)


if __name__ == "__main__":
    raise SystemExit(main())
