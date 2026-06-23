#!/usr/bin/env python3
"""Automate the repetitive Douyin Creator Center publish-page steps.

The helper is intentionally conservative: it reports hard blockers and requires
the "内容由AI生成" declaration before clicking publish.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from douyin_publish_preflight import DEFAULT_USER_DATA_DIR, check_cdp, check_playwright
from run_record import append_artifact, append_event, refresh_markdown


DEFAULT_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"
HARD_ASSISTANT_WORDS = ("违规", "禁止发布", "无法发布", "发布失败", "审核不通过", "请修改后发布")
SOFT_ASSISTANT_WORDS = ("建议", "可优化", "推荐", "提示", "风险提醒")
AI_DECLARATION_WORDS = ("内容由AI生成", "AI生成", "人工智能生成", "AIGC")
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DOM_CDP_URL: str | None = None


def is_video_publish_page(url: str) -> bool:
    return "creator.douyin.com/creator-micro/content/post/video" in url


def is_upload_page(url: str) -> bool:
    return "creator.douyin.com/creator-micro/content/upload" in url


def run(cmd: list[str], timeout: int = 30) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "elapsed_sec": round(time.time() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or f"timeout after {timeout}s").strip(),
            "elapsed_sec": round(time.time() - started, 3),
        }


def osascript(script: str, timeout: int = 30) -> str:
    result = run(["osascript", "-e", script], timeout=timeout)
    if result["returncode"] != 0:
        raise RuntimeError((result["stderr"] or result["stdout"] or "osascript failed").strip())
    return result["stdout"].strip()


def chrome_js(js: str, timeout: int = 30) -> str:
    script = f'''
tell application "Google Chrome"
    if not (exists window 1) then error "Chrome 没有打开窗口"
    execute active tab of window 1 javascript {json.dumps(js, ensure_ascii=False)}
end tell
'''
    try:
        return osascript(script, timeout=timeout)
    except RuntimeError as exc:
        message = str(exc)
        if "执行 JavaScript 的功能已关闭" in message or "JavaScript from Apple Events" in message:
            raise RuntimeError(
                "Chrome 禁止 Apple 事件执行 JavaScript；请在 Chrome 菜单栏打开 "
                "查看 > 开发者 > 允许 Apple 事件中的 JavaScript 后重试"
            ) from exc
        raise


def chrome_json(js: str, timeout: int = 30) -> Any:
    out = chrome_js(f"JSON.stringify((function(){{{js}}})())", timeout=timeout)
    return json.loads(out or "null")


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def open_upload_page(url: str) -> dict[str, str]:
    script = f'''
tell application "Google Chrome"
    activate
    if not (exists window 1) then error "Chrome 没有打开窗口，请先运行 TOOLS/open_cdp_chrome.sh"
    set w to window 1
    set originalIndex to active tab index of w
    set tempTab to make new tab at end of tabs of w
    set active tab index of w to count tabs of w
    set URL of active tab of w to {json.dumps(url)}
    delay 1
    return "original_index=" & originalIndex & linefeed & "temp_index=" & (active tab index of w)
end tell
'''
    return parse_key_values(osascript(script))


def activate_chrome_tab(index: str | int | None) -> dict[str, Any]:
    if index is None or index == "":
        return {"ok": False, "reason": "missing tab index"}
    script = f'''
tell application "Google Chrome"
    if not (exists window 1) then error "Chrome 没有打开窗口"
    set active tab index of window 1 to {int(index)}
    return "active_index=" & (active tab index of window 1) & linefeed & "url=" & (URL of active tab of window 1) & linefeed & "title=" & (title of active tab of window 1)
end tell
'''
    try:
        values = parse_key_values(osascript(script))
        values["ok"] = True
        return values
    except Exception as exc:
        return {"ok": False, "reason": str(exc), "requested_index": index}


def wait_for_page_ready(timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = dom_action(
            r'''
var text = document.body ? document.body.innerText : "";
return {
  url: location.href,
  title: document.title,
  readyState: document.readyState,
  hasBody: Boolean(document.body),
  onTargetSite: /creator\.douyin\.com/.test(location.href),
  loggedOut: /登录|扫码|验证码|安全验证|账号安全/.test(text),
  hasUploadHint: /上传|发布视频|选择视频|点击上传/.test(text),
  textSample: text.slice(0, 500)
};
'''
        )
        if last.get("loggedOut"):
            return last
        if last.get("readyState") == "complete" and last.get("hasBody") and (last.get("onTargetSite") or last.get("hasUploadHint")):
            return last
        time.sleep(1)
    return last


def dom_action_via_playwright(cdp_url: str, js_body: str, timeout: int = 30) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout * 1000)
        pages = [page for context in browser.contexts for page in context.pages]
        page = None
        for candidate in pages:
            if is_video_publish_page(candidate.url) or is_upload_page(candidate.url):
                page = candidate
                break
        if page is None:
            for candidate in pages:
                if "creator.douyin.com" in candidate.url:
                    page = candidate
                    break
        if page is None and pages:
            page = pages[0]
        if page is None:
            raise RuntimeError("CDP 已连接，但没有可用页面")

        page.bring_to_front()
        return page.evaluate(f"() => JSON.stringify((function(){{{js_body}}})())")


def dom_action(js_body: str, timeout: int = 30) -> dict[str, Any]:
    if DOM_CDP_URL:
        out = dom_action_via_playwright(DOM_CDP_URL, js_body, timeout=timeout)
        return json.loads(out or "null")
    return chrome_json(js_body, timeout=timeout)


def resolve_cdp_url(cli_value: str | None) -> str | None:
    value = (cli_value or os.environ.get("DOUYIN_CHROME_CDP_URL") or "").strip()
    return value or None


def run_cdp_preflight(cdp_url: str) -> dict[str, Any]:
    playwright = check_playwright()
    cdp = check_cdp(cdp_url, timeout=3, expected_user_data_dir=DEFAULT_USER_DATA_DIR)
    return {
        "ok": bool(playwright.get("ok") and cdp.get("ok")),
        "playwright": playwright,
        "cdp": cdp,
    }


def playwright_import_error() -> str | None:
    try:
        import playwright.async_api  # type: ignore  # noqa: F401
    except Exception as exc:
        return str(exc)
    return None


async def _set_file_input_via_playwright(cdp_url: str, video: Path, upload_url: str, timeout_sec: int) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        contexts = browser.contexts
        if not contexts:
            return {"ok": False, "method": "playwright-cdp", "reason": "CDP 已连接，但没有可用浏览器上下文"}

        page = None
        for context in contexts:
            for candidate in context.pages:
                if is_upload_page(candidate.url) or is_video_publish_page(candidate.url):
                    page = candidate
                    break
            if page:
                break

        if page is None:
            for context in contexts:
                for candidate in context.pages:
                    if "creator.douyin.com" in candidate.url:
                        page = candidate
                        break
                if page:
                    break

        if page is None:
            page = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
            await page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        await page.bring_to_front()
        if not (is_upload_page(page.url) or is_video_publish_page(page.url)):
            await page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)

        file_input = page.locator('input[type="file"]').first
        if await file_input.count() == 0:
            for selector in ('text=发布视频', 'button:has-text("发布视频")', '[role=tab]:has-text("发布视频")'):
                try:
                    await page.locator(selector).first.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                    break
                except Exception:
                    continue
        await file_input.wait_for(state="attached", timeout=timeout_sec * 1000)
        await file_input.set_input_files(str(video))
        return {
            "ok": True,
            "method": "playwright-cdp",
            "url": page.url,
            "title": await page.title(),
            "path_used": str(video),
        }


def set_file_input_via_playwright(cdp_url: str | None, video: Path, upload_url: str, timeout_sec: int = 20) -> dict[str, Any]:
    if not cdp_url:
        return {"ok": False, "method": "playwright-cdp", "skipped": True, "reason": "未配置 CDP 地址"}

    import_error = playwright_import_error()
    if import_error:
        return {
            "ok": False,
            "method": "playwright-cdp",
            "skipped": True,
            "reason": f"Python Playwright 不可用：{import_error}",
        }

    try:
        return asyncio.run(_set_file_input_via_playwright(cdp_url, video, upload_url, timeout_sec))
    except Exception as exc:
        return {"ok": False, "method": "playwright-cdp", "reason": str(exc), "cdp_url": cdp_url}


async def _activate_video_publish_page_via_playwright(cdp_url: str) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(cdp_url)
        for context in browser.contexts:
            for page in context.pages:
                if is_video_publish_page(page.url):
                    await page.bring_to_front()
                    return {
                        "ok": True,
                        "method": "playwright-cdp",
                        "url": page.url,
                        "title": await page.title(),
                    }
        return {"ok": False, "method": "playwright-cdp", "reason": "没有找到已上传投稿页"}


def activate_video_publish_page_via_playwright(cdp_url: str | None) -> dict[str, Any]:
    if not cdp_url:
        return {"ok": False, "method": "playwright-cdp", "skipped": True, "reason": "未配置 CDP 地址"}
    import_error = playwright_import_error()
    if import_error:
        return {
            "ok": False,
            "method": "playwright-cdp",
            "skipped": True,
            "reason": f"Python Playwright 不可用：{import_error}",
        }
    try:
        return asyncio.run(_activate_video_publish_page_via_playwright(cdp_url))
    except Exception as exc:
        return {"ok": False, "method": "playwright-cdp", "reason": str(exc), "cdp_url": cdp_url}


def declaration_snapshot_is_set(snapshot: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not isinstance(snapshot, dict):
        return False, None

    field_text = str(snapshot.get("fieldText") or "")
    context_text = str(snapshot.get("contextText") or "")
    preview_text = str(snapshot.get("previewText") or "")
    page_text = str(snapshot.get("pageText") or "")
    combined_text = " ".join([field_text, context_text, preview_text, page_text])
    placeholder_visible = bool(snapshot.get("placeholderVisible"))
    if not placeholder_visible:
        placeholder_visible = "请选择自主声明" in field_text
    if placeholder_visible:
        return False, None

    for word in AI_DECLARATION_WORDS:
        if word in combined_text:
            return True, word
    return False, None


def detect_file_dialog_state() -> dict[str, Any]:
    state: dict[str, Any] = {
        "open": False,
        "checks": [],
        "accessibility_denied": False,
    }
    script = r'''
tell application "System Events"
    tell process "Google Chrome"
        set sheetCount to 0
        set windowNames to {}
        try
            repeat with w in windows
                set sheetCount to sheetCount + (count of sheets of w)
                set end of windowNames to (name of w as string)
                repeat with s in sheets of w
                    set end of windowNames to (name of s as string)
                end repeat
            end repeat
        end try
        return "sheet_count=" & sheetCount & linefeed & "window_names=" & windowNames
    end tell
end tell
'''
    try:
        values = parse_key_values(osascript(script, timeout=5))
        sheet_count = int(values.get("sheet_count") or "0")
        window_names = values.get("window_names") or ""
        matched_title = bool(
            any(word in window_names for word in ("打开", "选择", "上传", "Open", "Choose", "Upload", "Select"))
        )
        state["checks"].append(
            {
                "method": "system-events-chrome-sheets",
                "ok": True,
                "sheet_count": sheet_count,
                "window_names": window_names,
                "matched_title": matched_title,
            }
        )
        if sheet_count > 0 or matched_title:
            state["open"] = True
    except Exception as exc:
        message = str(exc)
        state["checks"].append({"method": "system-events-chrome-sheets", "ok": False, "reason": message})
        if "-25211" in message or "辅助访问" in message or "not allowed assistive access" in message.lower():
            state["accessibility_denied"] = True

    frontmost_script = r'''
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set frontWindow to ""
    try
        set frontWindow to name of front window of process frontApp
    end try
    return "front_app=" & frontApp & linefeed & "front_window=" & frontWindow
end tell
'''
    try:
        values = parse_key_values(osascript(frontmost_script, timeout=5))
        front_app = values.get("front_app") or ""
        front_window = values.get("front_window") or ""
        matched = front_app in ("Google Chrome", "Finder") and any(
            word in front_window for word in ("打开", "选择", "上传", "Open", "Choose", "Upload", "Select")
        )
        state["checks"].append(
            {
                "method": "system-events-frontmost-window",
                "ok": True,
                "front_app": front_app,
                "front_window": front_window,
                "matched_title": matched,
            }
        )
        if matched:
            state["open"] = True
    except Exception as exc:
        message = str(exc)
        state["checks"].append({"method": "system-events-frontmost-window", "ok": False, "reason": message})
        if "-25211" in message or "辅助访问" in message or "not allowed assistive access" in message.lower():
            state["accessibility_denied"] = True

    return state


def file_dialog_is_open() -> bool:
    return bool(detect_file_dialog_state().get("open"))


def upload_entry_dialog_confirmed(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("dialog_opened"):
        return True
    state = entry.get("dialog_state")
    return isinstance(state, dict) and bool(state.get("open"))


def native_click_screen_point(x: int, y: int) -> dict[str, Any]:
    script = f'''
tell application "Google Chrome" to activate
tell application "System Events"
    click at {{{x}, {y}}}
end tell
'''
    try:
        osascript(script, timeout=10)
        return {"ok": True, "x": x, "y": y}
    except RuntimeError as exc:
        return {"ok": False, "x": x, "y": y, "reason": str(exc)}


def cliclick_screen_point(x: int, y: int) -> dict[str, Any]:
    binary = shutil.which("cliclick")
    if not binary:
        return {"ok": False, "x": x, "y": y, "reason": "cliclick 未安装"}
    result = run([binary, f"c:{x},{y}"], timeout=10)
    return {
        "ok": result.get("returncode") == 0,
        "x": x,
        "y": y,
        "cmd": result.get("cmd"),
        "stdout": result.get("stdout"),
        "stderr": result.get("stderr"),
        "returncode": result.get("returncode"),
    }


def click_upload_entry() -> dict[str, Any]:
    result = dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function pointFor(el) {
  var rect = el.getBoundingClientRect();
  var frameY = window.outerHeight - window.innerHeight;
  return {
    x: Math.round(window.screenX + rect.left + rect.width / 2),
    y: Math.round(window.screenY + frameY + rect.top + rect.height / 2)
  };
}
var fileInput = Array.from(document.querySelectorAll('input[type=file]')).find(visible);
if (fileInput) {
  fileInput.scrollIntoView({block: 'center'});
  fileInput.click();
  return {ok: true, method: 'file-input', native_click_point: pointFor(fileInput)};
}
var words = ['上传视频', '点击上传', '选择视频', '上传'];
var nodes = Array.from(document.querySelectorAll('button, [role=button], div, span, a, label'));
var target = nodes.find(function(el) {
  if (!visible(el)) return false;
  var t = (el.innerText || el.textContent || '').trim();
  return el.tagName === 'BUTTON' && /^上传视频$/.test(t);
}) || nodes.find(function(el) {
  if (!visible(el)) return false;
  var t = (el.innerText || el.textContent || '').trim();
  return (el.tagName === 'BUTTON' || el.tagName === 'LABEL' || el.getAttribute('role') === 'button') &&
    words.some(function(w) { return t.indexOf(w) >= 0; });
}) || nodes.find(function(el) {
  if (!visible(el)) return false;
  var t = (el.innerText || el.textContent || '').trim();
  return t && words.some(function(w) { return t.indexOf(w) >= 0; });
});
if (!target) return {ok: false, reason: '没有找到上传入口'};
target.scrollIntoView({block: 'center'});
target.focus();
target.click();
return {
  ok: true,
  method: 'text-click',
  text: (target.innerText || target.textContent || '').trim().slice(0, 80),
  native_click_point: pointFor(target)
};
'''
    )
    if not result.get("ok"):
        return result

    time.sleep(0.6)
    dialog_state = detect_file_dialog_state()
    result["dialog_state"] = dialog_state
    if dialog_state.get("open"):
        result["dialog_opened"] = True
        return result

    point = result.get("native_click_point") or {}
    x = point.get("x")
    y = point.get("y")
    if isinstance(x, int) and isinstance(y, int):
        cliclick_fallback = cliclick_screen_point(x, y)
        result["cliclick_fallback"] = cliclick_fallback
        time.sleep(0.6)
        dialog_state = detect_file_dialog_state()
        result["dialog_state_after_cliclick"] = dialog_state
        if dialog_state.get("open"):
            result["dialog_opened"] = True
            result["method"] = f"{result.get('method')}+cliclick"
            return result

        fallback = native_click_screen_point(x, y)
        result["native_click_fallback"] = fallback
        time.sleep(0.6)
        dialog_state = detect_file_dialog_state()
        result["dialog_state_after_native"] = dialog_state
        if dialog_state.get("open"):
            result["dialog_opened"] = True
            result["method"] = f"{result.get('method')}+native-fallback"
            return result

    result["dialog_opened"] = False
    result["ok"] = False
    result["reason"] = "上传入口点击后未检测到系统文件选择器，停止避免误向非弹窗输入文件路径"
    return result


def ascii_upload_path(path: Path) -> Path:
    """Return an ASCII temp copy for macOS file chooser path entry."""
    raw = str(path)
    if raw.isascii():
        return path
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    target = Path(tempfile.gettempdir()) / f"douyin-upload-{digest}{path.suffix.lower() or '.mp4'}"
    if not target.exists() or target.stat().st_size != path.stat().st_size:
        shutil.copy2(path, target)
    return target


def choose_file_in_dialog(path: Path) -> dict[str, Any]:
    dialog_state = detect_file_dialog_state()
    if not dialog_state.get("open"):
        return {
            "ok": False,
            "reason": "未检测到系统文件选择器，已跳过路径输入",
            "dialog_state": dialog_state,
            "original_path": str(path),
        }

    upload_path = ascii_upload_path(path)
    quoted_path = json.dumps(str(upload_path))
    script = f'''
tell application "System Events"
    delay 0.6
    keystroke "g" using {{command down, shift down}}
    delay 0.6
    set the clipboard to {quoted_path}
    keystroke "v" using {{command down}}
    delay 0.3
    keystroke return
    delay 0.8
    keystroke return
end tell
'''
    try:
        osascript(script, timeout=15)
        return {"ok": True, "path_used": str(upload_path), "original_path": str(path)}
    except RuntimeError as exc:
        return {"ok": False, "reason": str(exc), "path_used": str(upload_path), "original_path": str(path)}


def wait_for_upload_form(timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = dom_action(
            r'''
var text = document.body ? document.body.innerText : "";
var fields = Array.from(document.querySelectorAll('input, textarea, [contenteditable=true]'));
var uploadInProgress = /上传过程中请不要删除\/移动文件|文件解析中|取消上传|作品上传中|上传完成后将自动发布|请勿关闭页面|\\b([0-9]|[1-9][0-9])%/.test(text);
return {
  url: location.href,
  title: document.title,
  hasTitleLikeField: fields.some(function(el) {
    var p = [el.placeholder, el.getAttribute('aria-label'), el.getAttribute('data-placeholder'), el.innerText].join(' ');
    return /标题|作品标题/.test(p || '');
  }),
  hasDescLikeField: fields.some(function(el) {
    var p = [el.placeholder, el.getAttribute('aria-label'), el.getAttribute('data-placeholder'), el.innerText].join(' ');
    return /简介|描述|添加作品简介|说点什么/.test(p || '');
  }),
  uploadDone: /上传成功|上传完成|重新上传|封面|作品标题|发布设置|发文助手/.test(text),
  uploadInProgress: uploadInProgress,
  hardError: /上传失败|格式不支持|文件过大|视频处理失败/.test(text),
  loginOrVerify: /登录|扫码|验证码|安全验证|账号安全/.test(text),
  textSample: text.slice(0, 700)
};
'''
        )
        if last.get("hardError") or last.get("loginOrVerify"):
            return last
        if not last.get("uploadInProgress") and (
            last.get("uploadDone") or last.get("hasTitleLikeField") or last.get("hasDescLikeField")
        ):
            return last
        time.sleep(2)
    return last


def set_text_fields(title: str, description: str) -> dict[str, Any]:
    payload = json.dumps({"title": title, "description": description}, ensure_ascii=False)
    return dom_action(
        rf'''
var payload = {payload};
function visible(el) {{
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}}
function labelText(el) {{
  return [el.placeholder, el.getAttribute('aria-label'), el.getAttribute('data-placeholder'), el.innerText, el.textContent].join(' ');
}}
function setValue(el, value) {{
  el.scrollIntoView({{block: 'center'}});
  el.focus();
  if (el.isContentEditable) {{
    document.execCommand('selectAll', false, null);
    document.execCommand('insertText', false, value);
  }} else {{
    el.value = value;
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
  }}
}}
var fields = Array.from(document.querySelectorAll('input, textarea, [contenteditable=true]')).filter(visible);
var titleField = fields.find(function(el) {{ return /标题|作品标题/.test(labelText(el)); }}) || fields[0];
var descField = fields.find(function(el) {{ return /简介|描述|添加作品简介|说点什么/.test(labelText(el)); }}) || fields.find(function(el) {{ return el !== titleField && (el.tagName === 'TEXTAREA' || el.isContentEditable); }});
var result = {{title: false, description: false}};
if (titleField) {{ setValue(titleField, payload.title); result.title = true; }}
if (payload.description && descField) {{ setValue(descField, payload.description); result.description = true; }}
return result;
'''
    )


def fill_tags(tags: list[str]) -> dict[str, Any]:
    clean_tags = [tag.strip().lstrip("#") for tag in tags if tag.strip()]
    if not clean_tags:
        return {"ok": True, "filled": 0, "tags": []}
    if DOM_CDP_URL:
        return fill_tags_via_playwright(DOM_CDP_URL, clean_tags)

    payload = json.dumps(clean_tags, ensure_ascii=False)
    return dom_action(
        rf'''
var tags = {payload};
function visible(el) {{
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}}
function setValue(el, value) {{
  el.scrollIntoView({{block: 'center'}});
  el.focus();
  if (el.isContentEditable) {{
    document.execCommand('insertText', false, value);
  }} else {{
    el.value = (el.value || '') + value;
    el.dispatchEvent(new Event('input', {{bubbles: true}}));
    el.dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', bubbles: true}}));
    el.dispatchEvent(new Event('change', {{bubbles: true}}));
  }}
}}
var fields = Array.from(document.querySelectorAll('input, textarea, [contenteditable=true]')).filter(visible);
var tagField = fields.find(function(el) {{
  var t = [el.placeholder, el.getAttribute('aria-label'), el.getAttribute('data-placeholder'), el.innerText].join(' ');
  return /标签|话题|添加话题|添加标签/.test(t || '');
}});
if (!tagField) {{
  return {{ok: false, reason: '没有找到标签输入框', filled: 0, tags: tags}};
}}
tags.forEach(function(tag) {{
  setValue(tagField, '#' + tag + ' ');
}});
return {{ok: true, filled: tags.length, tags: tags}};
'''
    )


def fill_tags_via_playwright(cdp_url: str, tags: list[str], timeout_sec: int = 10) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    def body_text(page: Any) -> str:
        try:
            return page.locator("body").inner_text(timeout=3000)
        except Exception:
            return ""

    def has_highlighted_topic(page: Any, tag: str) -> bool:
        return bool(page.evaluate(
            """(tag) => {
              function visible(el) {
                const s = getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 1 && r.height > 1;
              }
              const editor = Array.from(document.querySelectorAll(
                '[contenteditable=true], .editor-kit-root-container, .editor-comp-publish-container-d4oeQI, .zone-container'
              )).find(visible);
              if (!editor) return false;
              const target = '#' + tag;
              return Array.from(editor.querySelectorAll('*')).some((el) => {
                const text = (el.innerText || el.textContent || '').replace(/\\s+/g, '').trim();
                const bg = getComputedStyle(el).backgroundColor;
                return text === target && /rgba?\\(1,\\s*118,\\s*247/.test(bg);
              });
            }""",
            tag,
        ))

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_sec * 1000)
        pages = [page for context in browser.contexts for page in context.pages]
        page = next((item for item in pages if "creator.douyin.com/creator-micro/content/publish" in item.url), None)
        if page is None:
            page = next((item for item in pages if "creator.douyin.com" in item.url), None)
        if page is None:
            return {"ok": False, "filled": 0, "tags": tags, "reason": "没有找到抖音发布页"}

        page.bring_to_front()
        filled: list[str] = []
        actions: list[dict[str, Any]] = []

        for tag in tags:
            try:
                add_topic = page.get_by_text("#添加话题", exact=True).first
                add_topic.click(timeout=timeout_sec * 1000)
                page.wait_for_timeout(400)

                page.keyboard.type(tag, delay=35)
                page.wait_for_timeout(800)

                suggestion = page.get_by_text(f"#{tag}", exact=True).first
                if suggestion.count() == 0 or not suggestion.is_visible(timeout=2000):
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(300)
                    actions.append({"tag": tag, "ok": False, "reason": "没有找到完整匹配的话题建议"})
                    continue

                suggestion.click(timeout=3000)

                page.wait_for_timeout(700)
                ok = has_highlighted_topic(page, tag)
                actions.append({"tag": tag, "ok": ok, "method": "topic-suggestion"})
                if ok:
                    filled.append(tag)
            except Exception as exc:
                actions.append({"tag": tag, "ok": False, "reason": str(exc)})

        return {
            "ok": len(filled) == len(tags),
            "filled": len(filled),
            "tags": tags,
            "method": "playwright-topic-token",
            "actions": actions,
        }


def normalize_cover_frame(value: str | None) -> str:
    normalized = (value or "recommended").strip().lower()
    aliases = {
        "skip": "none",
        "off": "none",
        "false": "none",
        "recommend": "recommended",
        "suggested": "recommended",
        "mid": "middle",
        "center": "middle",
        "ai": "ai-recommended",
        "ai_recommended": "ai-recommended",
        "airecommended": "ai-recommended",
        "ai-generated": "ai-recommended",
    }
    return aliases.get(normalized, normalized)


def click_locator_center(page: Any, locator: Any, timeout_ms: int) -> dict[str, Any]:
    try:
        locator.wait_for(state="visible", timeout=timeout_ms)
        box = locator.bounding_box(timeout=timeout_ms)
        if not box:
            return {"ok": False, "reason": "目标元素没有可点击区域"}
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(150)
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        return {"ok": True, "box": box}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def set_cover_frame_via_playwright(cdp_url: str, frame_mode: str, timeout_sec: int) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    mode = normalize_cover_frame(frame_mode)
    timeout_ms = max(5, timeout_sec) * 1000
    started = time.time()
    actions: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
        pages = [page for context in browser.contexts for page in context.pages]
        page = next((item for item in pages if is_video_publish_page(item.url)), None)
        if page is None:
            page = next((item for item in pages if "creator.douyin.com" in item.url), None)
        if page is None:
            return {"ok": False, "status": "failed", "mode": mode, "reason": "没有找到抖音发布页"}

        page.bring_to_front()
        cover_texts = page.locator(".coverControl-CjlzqC").all_inner_texts()
        vertical_set = any("竖封面3:4" in text and "选择封面" not in text for text in cover_texts)
        horizontal_set = any("横封面4:3" in text and "选择封面" not in text for text in cover_texts)
        if vertical_set and horizontal_set and mode != "ai-recommended":
            page_text = page.locator("body").inner_text(timeout=timeout_ms)
            return {
                "ok": True,
                "status": "set",
                "mode": mode,
                "method": "playwright-cdp",
                "actions": [{"step": "detect_existing_cover", "ok": True, "cover_texts": cover_texts}],
                "cover_missing_warning": "横/竖双封面缺失" in page_text,
                "elapsed_sec": round(time.time() - started, 3),
            }

        dialog = page.locator('[role="dialog"], .dy-creator-content-modal-body').first
        if dialog.count() > 0 and dialog.is_visible():
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            dialog = page.locator('[role="dialog"], .dy-creator-content-modal-body').first
        if dialog.count() == 0 or not dialog.is_visible():
            open_result = {"ok": False, "reason": "没有找到可打开的封面入口"}
            for selector in (".cover-Jg3T4p", ".coverControl-CjlzqC", ".filter-k_CjvJ"):
                target = page.locator(selector).first
                if target.count() == 0:
                    continue
                open_result = click_locator_center(page, target, timeout_ms)
                open_result["selector"] = selector
                if not open_result.get("ok"):
                    continue
                try:
                    dialog.wait_for(state="visible", timeout=3000)
                    break
                except Exception as exc:
                    open_result = {"ok": False, "selector": selector, "reason": f"点击后未打开封面编辑器：{exc}"}
            actions.append({"step": "open_cover_editor", **open_result})
            if not open_result.get("ok"):
                return {"ok": False, "status": "failed", "mode": mode, "reason": open_result.get("reason"), "actions": actions}
        else:
            actions.append({"step": "open_cover_editor", "ok": True, "method": "already-open"})

        def open_cover_editor_from_main(stage: str) -> dict[str, Any]:
            targets: list[Any] = []
            if stage == "horizontal":
                controls = page.locator(".coverControl-CjlzqC")
                for idx in range(controls.count()):
                    candidate = controls.nth(idx)
                    try:
                        text = candidate.inner_text(timeout=1000)
                    except Exception:
                        continue
                    if "横封面4:3" in text:
                        targets.append(candidate)
                buttons = page.locator(".cover-Jg3T4p")
                if buttons.count() > 1:
                    targets.append(buttons.nth(1))
            else:
                buttons = page.locator(".cover-Jg3T4p")
                if buttons.count() > 0:
                    targets.append(buttons.first)

            for target in targets:
                click = click_locator_center(page, target, timeout_ms)
                if not click.get("ok"):
                    continue
                try:
                    dialog.wait_for(state="visible", timeout=3000)
                    expected_title = "设置横封面" if stage == "horizontal" else "设置竖封面"
                    deadline = time.time() + 5
                    while time.time() < deadline:
                        dialog_text = dialog.inner_text(timeout=timeout_ms)
                        if expected_title in dialog_text:
                            return {"ok": True, **click, "title": expected_title}
                        page.wait_for_timeout(300)
                    return {"ok": True, **click}
                except Exception:
                    continue
            return {"ok": False, "reason": f"没有找到可打开的{stage}封面入口"}

        def ensure_ai_cover_tab() -> dict[str, Any]:
            tab = dialog.get_by_text("AI封面", exact=True).first
            if tab.count() == 0:
                return {"ok": False, "reason": "没有找到 AI封面 入口"}
            click = click_locator_center(page, tab, timeout_ms)
            if not click.get("ok"):
                return {"ok": False, "reason": click.get("reason")}
            page.wait_for_timeout(500)
            return {"ok": True, **click}

        def trigger_ai_cover(stage: str) -> dict[str, Any]:
            expected_title = "设置横封面" if stage == "horizontal" else "设置竖封面"
            try:
                dialog_text = dialog.inner_text(timeout=timeout_ms)
            except Exception:
                dialog_text = ""
            if expected_title not in dialog_text:
                return {"ok": False, "stage": stage, "reason": f"当前封面弹层不是{expected_title}"}

            tab_result = ensure_ai_cover_tab()
            if not tab_result.get("ok"):
                return {"ok": False, "stage": stage, "reason": tab_result.get("reason")}

            button = dialog.get_by_text("AI生成封面", exact=True).last
            if button.count() == 0:
                return {"ok": False, "stage": stage, "reason": "没有找到 AI生成封面 按钮"}

            click = click_locator_center(page, button, timeout_ms)
            if not click.get("ok"):
                return {"ok": False, "stage": stage, "reason": click.get("reason")}

            deadline = time.time() + min(max(6, timeout_sec), 20)
            observed_text = ""
            while time.time() < deadline:
                dialog_text = dialog.inner_text(timeout=timeout_ms)
                observed_text = dialog_text
                if "继续生成" in dialog_text or "取消生成" in dialog_text or "生成中" in dialog_text:
                    return {
                        "ok": True,
                        "stage": stage,
                        "selection": "ai-generated-cover",
                        "signal": "continue-generate" if "继续生成" in dialog_text else "generating",
                        "dialog_text": dialog_text[:400],
                        **click,
                    }
                page.wait_for_timeout(500)

            return {
                "ok": False,
                "stage": stage,
                "reason": "点击 AI生成封面 后未观察到生成状态",
                "dialog_text": observed_text[:400],
            }

        def select_video_frame(stage: str) -> dict[str, Any]:
            expected_title = "设置横封面" if stage == "horizontal" else "设置竖封面"
            try:
                dialog_text = dialog.inner_text(timeout=timeout_ms)
            except Exception:
                dialog_text = ""
            if expected_title not in dialog_text:
                return {"ok": False, "stage": stage, "reason": f"当前封面弹层不是{expected_title}"}

            frames = page.locator(".preview-frame-rt7Mc1")
            frames.first.wait_for(state="visible", timeout=timeout_ms)
            count = frames.count()
            if count <= 0:
                return {"ok": False, "stage": stage, "reason": "没有找到视频帧缩略图"}
            index = count // 2 if mode in {"middle", "recommended"} else 0
            click = click_locator_center(page, frames.nth(index), timeout_ms)
            return {
                "ok": bool(click.get("ok")),
                "stage": stage,
                "frame_index": index,
                "frame_count": count,
                "selection": "middle-frame" if mode == "middle" else "middle-frame-fallback",
                **click,
            }

        def select_with_optional_ai_fallback(stage: str) -> dict[str, Any]:
            if mode != "ai-recommended":
                return select_video_frame(stage)
            ai_result = trigger_ai_cover(stage)
            if ai_result.get("ok"):
                return ai_result
            fallback = select_video_frame(stage)
            fallback["fallback_from_ai"] = True
            fallback["fallback_reason"] = ai_result.get("reason")
            return fallback

        def finish_editor() -> dict[str, Any]:
            finish_button = dialog.get_by_text("完成", exact=True).last
            deadline = time.time() + min(max(8, timeout_sec), 30)
            last_error = ""
            while time.time() < deadline:
                try:
                    if finish_button.count() > 0 and finish_button.is_visible() and finish_button.is_enabled():
                        finish_button.click(timeout=3000)
                        page.wait_for_timeout(1500)
                        return {"ok": True, "text": "完成"}
                except Exception as exc:
                    last_error = str(exc)
                    if dialog.count() == 0 or not dialog.is_visible():
                        return {"ok": True, "text": "完成", "note": "点击时弹层已关闭，按成功处理"}
                page.wait_for_timeout(500)

            if dialog.count() == 0 or not dialog.is_visible():
                return {"ok": True, "text": "完成", "note": "等待完成按钮时弹层已关闭，按成功处理"}
            return {"ok": False, "reason": last_error or "完成按钮在等待窗口内不可点击"}

        vertical = select_with_optional_ai_fallback("vertical")
        actions.append({"step": "select_vertical_frame", **vertical})
        if not vertical.get("ok"):
            return {"ok": False, "status": "failed", "mode": mode, "reason": vertical.get("reason"), "actions": actions}

        horizontal_button = page.get_by_text("设置横封面", exact=True).last
        if horizontal_button.count() > 0 and horizontal_button.is_visible():
            horizontal_button.click(timeout=timeout_ms)
            page.wait_for_timeout(800)
            horizontal = select_with_optional_ai_fallback("horizontal")
            actions.append({"step": "select_horizontal_frame", **horizontal})
            if not horizontal.get("ok"):
                return {"ok": False, "status": "failed", "mode": mode, "reason": horizontal.get("reason"), "actions": actions}
            finish = finish_editor()
            actions.append({"step": "finish_cover_editor", **finish})
            if not finish.get("ok"):
                return {"ok": False, "status": "failed", "mode": mode, "reason": finish.get("reason"), "actions": actions}
        else:
            if mode == "ai-recommended":
                finish = finish_editor()
                actions.append({"step": "finish_cover_editor", **finish})
                if not finish.get("ok"):
                    return {"ok": False, "status": "failed", "mode": mode, "reason": finish.get("reason"), "actions": actions}
                reopen = open_cover_editor_from_main("horizontal")
                actions.append({"step": "open_horizontal_cover_editor", **reopen})
                if reopen.get("ok"):
                    horizontal = select_with_optional_ai_fallback("horizontal")
                    actions.append({"step": "select_horizontal_frame", **horizontal})
                    if not horizontal.get("ok"):
                        return {"ok": False, "status": "failed", "mode": mode, "reason": horizontal.get("reason"), "actions": actions}
                    finish = finish_editor()
                    actions.append({"step": "finish_horizontal_cover_editor", **finish})
                    if not finish.get("ok"):
                        return {"ok": False, "status": "failed", "mode": mode, "reason": finish.get("reason"), "actions": actions}
                else:
                    actions.append({"step": "select_horizontal_frame", "ok": True, "skipped": True, "reason": "没有设置横封面按钮且无法从主页面重开横封面编辑器"})
            else:
                actions.append({"step": "select_horizontal_frame", "ok": True, "skipped": True, "reason": "没有设置横封面按钮"})
                finish = finish_editor()
                actions.append({"step": "finish_cover_editor", **finish})
                if not finish.get("ok"):
                    return {"ok": False, "status": "failed", "mode": mode, "reason": finish.get("reason"), "actions": actions}

        page_text = page.locator("body").inner_text(timeout=timeout_ms)
        cover_missing = "横/竖双封面缺失" in page_text
        return {
            "ok": True,
            "status": "set",
            "mode": mode,
            "method": "playwright-cdp",
            "actions": actions,
            "cover_missing_warning": cover_missing,
            "elapsed_sec": round(time.time() - started, 3),
        }


def set_cover_frame(frame_mode: str, timeout_sec: int) -> dict[str, Any]:
    mode = normalize_cover_frame(frame_mode)
    if mode == "none":
        return {"ok": True, "status": "skipped", "reason": "cover-frame=none"}
    if mode not in {"recommended", "middle", "ai-recommended"}:
        return {"ok": False, "status": "failed", "reason": f"未知封面模式：{frame_mode}"}
    if DOM_CDP_URL:
        return set_cover_frame_via_playwright(DOM_CDP_URL, mode, timeout_sec)

    started = time.time()
    open_result = dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function textOf(el) {
  return (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
}
function clickable(el) {
  if (!el || !visible(el)) return false;
  if (el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button') return true;
  if (typeof el.onclick === 'function') return true;
  var cls = String(el.className || '');
  return /(cover|poster|thumb|edit|button|action|trigger)/i.test(cls);
}
function pickControl(el) {
  var current = el;
  while (current && current !== document.body) {
    var r = current.getBoundingClientRect();
    if (clickable(current) && r.width < Math.max(window.innerWidth * 0.95, 900) && r.height < 180) {
      return current;
    }
    current = current.parentElement;
  }
  return el;
}
function clickLike(el) {
  el.scrollIntoView({block: 'center'});
  el.focus && el.focus();
  ['mousedown', 'mouseup', 'click'].forEach(function(type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
  });
}
var nodes = Array.from(document.querySelectorAll('button, [role=button], a, div, span, label'));
var candidates = nodes.map(function(el) {
  if (!visible(el)) return null;
  var text = textOf(el);
  var cls = String(el.className || '');
  var aria = el.getAttribute('aria-label') || '';
  var combined = [text, cls, aria].join(' ');
  if (!/封面|cover|poster/i.test(combined)) return null;
  if (/上传封面|本地上传|上传图片|upload/i.test(combined)) return null;
  var control = pickControl(el);
  var r = control.getBoundingClientRect();
  return {
    el: control,
    text: text,
    exact: /^(设置封面|选择封面|编辑封面|封面)$/.test(text),
    action: /设置封面|选择封面|编辑封面|更换封面/.test(text),
    area: r.width * r.height,
    top: r.top
  };
}).filter(Boolean).sort(function(a, b) {
  return (Number(b.action) - Number(a.action)) ||
    (Number(b.exact) - Number(a.exact)) ||
    (a.area - b.area) ||
    (a.top - b.top);
});
if (!candidates.length) return {ok: false, reason: '没有找到封面入口'};
var target = candidates[0];
clickLike(target.el);
return {ok: true, text: target.text, candidate_count: candidates.length};
''',
        timeout=max(5, timeout_sec),
    )
    if not open_result.get("ok"):
        open_result.update({"status": "failed", "mode": mode})
        return open_result

    time.sleep(1)
    select_result: dict[str, Any] = {}
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        select_result = dom_action(
            rf'''
var mode = {json.dumps(mode)};
function visible(el) {{
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}}
function textOf(el) {{
  return (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
}}
function clickLike(el) {{
  el.scrollIntoView({{block: 'center'}});
  el.focus && el.focus();
  ['mousedown', 'mouseup', 'click'].forEach(function(type) {{
    el.dispatchEvent(new MouseEvent(type, {{bubbles: true, cancelable: true, view: window}}));
  }});
}}
function rootNode() {{
  var roots = Array.from(document.querySelectorAll('[role=dialog], [class*=modal], [class*=Modal], [class*=drawer], [class*=Drawer]')).filter(visible);
  roots.sort(function(a, b) {{
    var ar = a.getBoundingClientRect();
    var br = b.getBoundingClientRect();
    return (br.width * br.height) - (ar.width * ar.height);
  }});
  return roots[0] || document.body;
}}
function setRangeToMiddle(root) {{
  var ranges = Array.from(root.querySelectorAll('input[type=range]')).filter(visible);
  if (!ranges.length) return null;
  var range = ranges[0];
  var min = Number(range.min || 0);
  var max = Number(range.max || 100);
  var value = String(min + (max - min) / 2);
  var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(range, value);
  range.dispatchEvent(new Event('input', {{bubbles: true}}));
  range.dispatchEvent(new Event('change', {{bubbles: true}}));
  return {{ok: true, value: value}};
}}
function clickTab(root, pattern) {{
  var tabs = Array.from(root.querySelectorAll('button, [role=button], [role=tab], div, span, a')).filter(visible);
  var target = tabs.find(function(el) {{
    var text = textOf(el);
    return pattern.test(text) && !/上传|本地|图片/.test(text);
  }});
  if (!target) return null;
  clickLike(target);
  return textOf(target);
}}
function mediaCandidates(root) {{
  var nodes = Array.from(root.querySelectorAll('img, canvas, video, button, [role=button], div, span')).filter(visible);
  return nodes.map(function(el) {{
    var r = el.getBoundingClientRect();
    var text = textOf(el);
    var cls = String(el.className || '');
    var style = String(el.getAttribute('style') || '');
    var mediaLike = /IMG|CANVAS|VIDEO/.test(el.tagName) ||
      /cover|poster|thumb|frame|image/i.test(cls + ' ' + style + ' ' + text);
    var blocked = /上传|本地|图片上传|选择图片|upload/i.test(text + ' ' + cls);
    var control = el;
    var current = el;
    while (current && current !== root && current !== document.body) {{
      var cr = current.getBoundingClientRect();
      var ccls = String(current.className || '');
      if ((current.tagName === 'BUTTON' || current.getAttribute('role') === 'button' || /item|card|thumb|cover|frame|select/i.test(ccls)) &&
          cr.width > 10 && cr.height > 10 && cr.width < window.innerWidth * 0.95) {{
        control = current;
      }}
      current = current.parentElement;
    }}
    return {{
      el: control,
      text: text,
      area: r.width * r.height,
      centerX: r.left + r.width / 2,
      centerY: r.top + r.height / 2,
      mediaLike: mediaLike,
      blocked: blocked,
      recommended: /推荐|智能|最佳/.test(text + ' ' + cls)
    }};
  }}).filter(function(item) {{
    return item.mediaLike && !item.blocked && item.area > 600 && item.area < window.innerWidth * window.innerHeight * 0.5;
  }});
}}
function clickConfirm(root) {{
  var buttons = Array.from(root.querySelectorAll('button, [role=button], a, div, span')).filter(visible);
  var target = buttons.reverse().find(function(el) {{
    var text = textOf(el);
    return /确定|完成|保存|使用|确认|应用/.test(text) && !/取消|返回/.test(text);
  }});
  if (!target) return null;
  clickLike(target);
  return textOf(target);
}}
var root = rootNode();
var rootText = textOf(root).slice(0, 800);
var tabClicked = null;
var rangeResult = null;
if (mode === 'recommended') {{
  tabClicked = clickTab(root, /推荐|智能|最佳/);
}} else {{
  tabClicked = clickTab(root, /视频帧|视频封面|从视频|选择封面|封面/);
  rangeResult = setRangeToMiddle(root);
}}
var candidates = mediaCandidates(root);
if (!candidates.length) {{
  return {{ok: false, reason: '没有找到可选封面帧', mode: mode, tab_clicked: tabClicked, range: rangeResult, root_text: rootText}};
}}
var target = null;
if (mode === 'recommended') {{
  target = candidates.find(function(item) {{ return item.recommended; }}) || candidates[0];
}} else {{
  var viewportMid = window.innerWidth / 2;
  candidates.sort(function(a, b) {{
    return Math.abs(a.centerX - viewportMid) - Math.abs(b.centerX - viewportMid);
  }});
  target = candidates[0];
}}
clickLike(target.el);
var confirmText = clickConfirm(root);
return {{
  ok: true,
  mode: mode,
  tab_clicked: tabClicked,
  range: rangeResult,
  selected_text: target.text,
  candidate_count: candidates.length,
  confirm_text: confirmText
}};
''',
            timeout=max(5, timeout_sec),
        )
        if select_result.get("ok"):
            select_result.update({
                "status": "set",
                "mode": mode,
                "open": open_result,
                "elapsed_sec": round(time.time() - started, 3),
            })
            return select_result
        time.sleep(1)

    select_result.update({
        "status": "failed",
        "mode": mode,
        "open": open_result,
        "elapsed_sec": round(time.time() - started, 3),
    })
    return select_result


def try_set_ai_declaration(timeout_sec: int) -> dict[str, Any]:
    started = time.time()
    attempts = []

    open_result = dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function textOf(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
function clickable(el) {
  if (!el || !visible(el)) return false;
  if (el.tagName === 'BUTTON' || el.tagName === 'LABEL' || el.tagName === 'A') return true;
  if (el.getAttribute('role') === 'button' || el.getAttribute('role') === 'combobox') return true;
  if (typeof el.onclick === 'function') return true;
  var cls = String(el.className || '');
  return /(select|picker|dropdown|trigger|control|option)/i.test(cls);
}
function pickControl(el) {
  var current = el;
  while (current && current !== document.body) {
    var r = current.getBoundingClientRect();
    if (clickable(current) && r.width < Math.max(window.innerWidth * 0.95, 900) && r.height < 140) {
      return current;
    }
    current = current.parentElement;
  }
  return el;
}
function clickLike(el) {
  el.scrollIntoView({block: 'center'});
  el.focus && el.focus();
  ['mousedown', 'mouseup', 'click'].forEach(function(type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
  });
}
var nodes = Array.from(document.querySelectorAll('button, [role=button], div, span, label, a'));
var target = nodes
  .map(function(el) {
    if (!visible(el)) return null;
    var sourceText = textOf(el);
    if (!/请选择自主声明|自主声明|作品声明|内容声明/.test(sourceText)) return null;
    var control = pickControl(el);
    var r = control.getBoundingClientRect();
    return {
      control: control,
      sourceText: sourceText,
      exactPlaceholder: /^请选择自主声明$/.test(sourceText),
      exactLabel: /^自主声明$/.test(sourceText),
      area: r.width * r.height
    };
  })
  .filter(Boolean)
  .sort(function(a, b) {
    if (a.exactPlaceholder !== b.exactPlaceholder) return a.exactPlaceholder ? -1 : 1;
    if (a.exactLabel !== b.exactLabel) return a.exactLabel ? -1 : 1;
    return a.area - b.area;
  })[0];
if (!target) return {ok: false, reason: '没有找到自主声明入口'};
clickLike(target.control);
return {ok: true, text: textOf(target.control).slice(0, 80), source_text: target.sourceText.slice(0, 80)};
'''
    )
    attempts.append({"step": "open_declaration", **open_result})
    if not open_result.get("ok"):
        return {"status": "skipped", "blocking": False, "attempts": attempts}

    while time.time() - started < timeout_sec:
        select_result = dom_action(
            r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function textOf(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
function clickLike(el) {
  el.scrollIntoView({block: 'center'});
  el.focus && el.focus();
  ['mousedown', 'mouseup', 'click'].forEach(function(type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
  });
}
var nodes = Array.from(document.querySelectorAll('button, [role=button], div, span, label, li, a'));
var target = nodes
  .map(function(el) {
    if (!visible(el)) return null;
    var r = el.getBoundingClientRect();
    var t = textOf(el);
    if (!/内容由AI生成|AI生成|人工智能生成|AIGC/.test(t)) return null;
    if (r.width >= Math.max(window.innerWidth * 0.95, 900) || r.height >= 140) return null;
    return {el: el, text: t, exact: /^内容由AI生成$/.test(t), area: r.width * r.height};
  })
  .filter(Boolean)
  .sort(function(a, b) {
    if (a.exact !== b.exact) return a.exact ? -1 : 1;
    return a.area - b.area;
  })[0];
if (!target) return {ok: false, reason: '没有找到内容由AI生成选项'};
clickLike(target.el);
return {ok: true, text: target.text.slice(0, 80)};
'''
        )
        attempts.append({"step": "select_ai_generated", **select_result})
        if select_result.get("ok"):
            break
        time.sleep(1)

    confirm_result = dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function textOf(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
function clickLike(el) {
  el.scrollIntoView({block: 'center'});
  el.focus && el.focus();
  ['mousedown', 'mouseup', 'click'].forEach(function(type) {
    el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
  });
}
var nodes = Array.from(document.querySelectorAll('button, [role=button], div, span, a'));
var target = nodes
  .map(function(el) {
    if (!visible(el)) return null;
    var r = el.getBoundingClientRect();
    var t = textOf(el);
    if (!/^(确定|确认|保存|完成)$/.test(t)) return null;
    if (r.width >= 240 || r.height >= 100) return null;
    return {el: el, text: t, area: r.width * r.height};
  })
  .filter(Boolean)
  .sort(function(a, b) { return a.area - b.area; })[0];
if (!target) return {ok: true, skipped: true, reason: '没有找到声明确认按钮'};
clickLike(target.el);
return {ok: true, text: target.text.slice(0, 80)};
'''
    )
    attempts.append({"step": "confirm_declaration", **confirm_result})

    verify = dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
function textOf(el) {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
}
var nodes = Array.from(document.querySelectorAll('div, span, label, section, li, p')).filter(visible);
var containers = [];
var pageText = textOf(document.body || document.documentElement);
var placeholderVisible = false;
nodes.forEach(function(el) {
  var ownText = textOf(el);
  if (/请选择自主声明/.test(ownText)) placeholderVisible = true;
  if (!/自主声明/.test(ownText)) return;
  [el, el.parentElement, el.parentElement && el.parentElement.parentElement].forEach(function(node) {
    if (!node || !visible(node)) return;
    var rect = node.getBoundingClientRect();
    if (rect.width >= Math.max(window.innerWidth * 0.95, 1200) || rect.height >= 220) return;
    var text = textOf(node);
    if (!text || !/自主声明/.test(text)) return;
    containers.push({text: text, area: rect.width * rect.height});
  });
});
containers.sort(function(a, b) { return a.area - b.area; });
var fieldText = containers.length ? containers[0].text : '';
var contextText = containers.slice(0, 5).map(function(item) { return item.text; }).join(' ');
var previewNodes = nodes.filter(function(el) {
  var text = textOf(el);
  return /作者声明|预览|内容由AI生成|AI生成/.test(text);
}).map(function(el) { return textOf(el); }).slice(0, 12);
var previewText = previewNodes.join(' ');
var combinedText = [fieldText, contextText, previewText, pageText].join(' ');
var matched = /内容由AI生成/.test(combinedText) ? '内容由AI生成'
  : (/AI生成|人工智能生成|AIGC/.test(combinedText) ? 'AI生成' : null);
return {
  fieldText: fieldText,
  contextText: contextText,
  previewText: previewText,
  pageText: pageText.slice(0, 3000),
  matched: matched,
  placeholderVisible: placeholderVisible,
  candidate_count: containers.length
};
'''
    )
    verify["ok"], verify["matched"] = declaration_snapshot_is_set(verify)
    attempts.append({"step": "verify_declaration", **verify})

    return {
        "status": "set" if verify.get("ok") else "failed",
        "blocking": False,
        "attempts": attempts,
    }


def check_assistant() -> dict[str, Any]:
    return dom_action(
        rf'''
var text = document.body ? document.body.innerText : "";
var hardWords = {json.dumps(HARD_ASSISTANT_WORDS, ensure_ascii=False)};
var softWords = {json.dumps(SOFT_ASSISTANT_WORDS, ensure_ascii=False)};
var hard = hardWords.filter(function(word) {{ return text.indexOf(word) >= 0; }});
var soft = softWords.filter(function(word) {{ return text.indexOf(word) >= 0; }});
return {{
  ok: hard.length === 0,
  hard_matches: hard,
  soft_matches: soft,
  has_publish_assistant: /发文助手|发布助手|作品检测/.test(text)
}};
'''
    )


def click_publish() -> dict[str, Any]:
    return dom_action(
        r'''
function visible(el) {
  var r = el.getBoundingClientRect();
  var s = getComputedStyle(el);
  return r.width > 1 && r.height > 1 && s.visibility !== 'hidden' && s.display !== 'none';
}
var nodes = Array.from(document.querySelectorAll('button, [role=button], a'));
var target = nodes.reverse().find(function(el) {
  if (!visible(el)) return false;
  var t = (el.innerText || el.textContent || '').trim();
  return /发布|立即发布/.test(t) && !/定时|预约/.test(t);
});
if (!target) return {ok: false, reason: '没有找到发布按钮'};
if (target.disabled || target.getAttribute('aria-disabled') === 'true') {
  return {ok: false, reason: '发布按钮禁用', text: (target.innerText || target.textContent || '').trim()};
}
target.scrollIntoView({block: 'center'});
target.click();
return {ok: true, text: (target.innerText || target.textContent || '').trim().slice(0, 80)};
'''
    )


def classify_publish_snapshot(snapshot: dict[str, Any]) -> str:
    text = str(snapshot.get("textSample") or snapshot.get("text") or "")
    url = str(snapshot.get("url") or "")
    if snapshot.get("hardError"):
        return "hard-error"
    upload_in_progress = any(
        word in text
        for word in (
            "作品上传中",
            "上传完成后将自动发布",
            "上传过程中请不要删除/移动文件",
            "文件解析中",
            "请勿关闭页面",
        )
    )
    if upload_in_progress:
        return "uploading"
    if "发布成功" in text:
        return "success"
    if "加载中，请稍候" in text:
        return "loading"
    if "/content/manage" in url or "/manage" in url:
        return "success"
    return "pending"


def wait_for_publish_result(timeout_sec: int) -> dict[str, Any]:
    deadline = time.time() + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = dom_action(
            r'''
var text = document.body ? document.body.innerText : "";
return {
  url: location.href,
  title: document.title,
  hardError: /发布失败|禁止发布|无法发布|验证码|安全验证|账号安全|请修改后发布/.test(text),
  textSample: text.slice(0, 1200)
};
'''
        )
        status = classify_publish_snapshot(last)
        last["status"] = status
        last["success"] = status == "success"
        if status in {"success", "hard-error"}:
            return last
        time.sleep(2)
    return last


def write_report(out_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "douyin-publish-report.json"
    report_md = out_dir / "douyin-publish-report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 抖音发布 Helper 报告",
        "",
        f"- 结论：{report.get('decision')}",
        f"- 视频：{report.get('video')}",
        f"- 标题：{report.get('title')}",
        f"- 标签：{', '.join(report.get('tags') or []) or '无'}",
        f"- 上传：{report.get('steps', {}).get('upload', {}).get('status')}",
        f"- 封面：{report.get('steps', {}).get('cover', {}).get('status')}",
        f"- 文案：{report.get('steps', {}).get('copywriting', {}).get('status')}",
        f"- 自主声明：{report.get('steps', {}).get('declaration', {}).get('status')}",
        f"- 发文助手：{report.get('steps', {}).get('assistant', {}).get('status')}",
        f"- 发布：{report.get('steps', {}).get('publish', {}).get('status')}",
        "",
        "## Errors",
    ]
    lines.extend([f"- {item}" for item in report.get("errors", [])] or ["- 无"])
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in report.get("warnings", [])] or ["- 无"])
    if report.get("final_url"):
        lines.extend(["", f"最终页面：{report['final_url']}"])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    record_jsonl = report.get("record_jsonl")
    if record_jsonl:
        append_event(
            record_jsonl,
            stage="publish",
            event="douyin_publish",
            status=report.get("decision"),
            summary=f"抖音发布 {report.get('decision')}",
            data={
                "video": report.get("video"),
                "title": report.get("title"),
                "tags": report.get("tags"),
                "final_url": report.get("final_url"),
                "report_json": str(report_json),
                "errors": report.get("errors", []),
                "warnings": report.get("warnings", []),
                "steps": report.get("steps", {}),
            },
        )
        append_artifact(
            record_jsonl,
            stage="publish",
            path=str(report_json),
            kind="douyin-publish-report",
            status=report.get("decision"),
            keep=True,
            summary="抖音发布 JSON 报告",
        )
        refresh_markdown(record_jsonl)
    return report_json, report_md


def normalize_tags(tags: list[str]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    clean = []
    seen = set()
    for tag in tags:
        value = tag.strip().lstrip("#")
        if not value or value in seen:
            continue
        clean.append(value)
        seen.add(value)
    if len(clean) < 4:
        warnings.append(f"标签数量 {len(clean)} 个，少于建议的 4-5 个")
    if len(clean) > 5:
        warnings.append(f"标签数量 {len(clean)} 个，多于建议的 4-5 个；本次只填写前 5 个")
        clean = clean[:5]
    return clean, warnings


def description_contains_tags(description: str, tags: list[str]) -> bool:
    if not tags:
        return False
    compact = "".join(description.split())
    return all(f"#{tag}" in compact or tag in compact for tag in tags)


def build_base_report(args: argparse.Namespace, video: Path, tags: list[str], warnings: list[str]) -> dict[str, Any]:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "decision": "pending",
        "dry_run": args.dry_run,
        "video": str(video),
        "title": args.title,
        "description": args.description,
        "tags": tags,
        "upload_url": args.upload_url,
        "final_url": None,
        "steps": {
            "upload": {"status": "pending"},
            "cover": {"status": "pending"},
            "copywriting": {"status": "pending"},
            "declaration": {"status": "pending", "blocking": False},
            "assistant": {"status": "pending"},
            "publish": {"status": "pending"},
        },
        "errors": [],
        "warnings": warnings,
        "record_jsonl": args.record_jsonl,
    }


def fail(report: dict[str, Any], out_dir: Path, message: str, code: int) -> int:
    report["decision"] = "failed"
    report["errors"].append(message)
    report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


def main() -> int:
    global DOM_CDP_URL
    parser = argparse.ArgumentParser(description="自动完成抖音创作者中心发布页的重复操作。")
    parser.add_argument("video", help="待发布 MP4 路径")
    parser.add_argument("--title", required=True, help="作品标题")
    parser.add_argument("--description", default="", help="作品简介")
    parser.add_argument("--tag", action="append", default=[], help="标签，可重复传入 4-5 个")
    parser.add_argument("--out-dir", default=None, help="报告输出目录，默认 TEMP/publish-runs/YYYYMMDD-HHMMSS")
    parser.add_argument("--upload-url", default=DEFAULT_UPLOAD_URL, help="抖音创作者中心上传页")
    parser.add_argument("--current-tab", action="store_true", help="接管当前已上传完成的发布表单，不重新打开上传页")
    parser.add_argument("--dry-run", action="store_true", help="只校验参数和报告输出，不接管 Chrome")
    parser.add_argument("--no-publish", action="store_true", help="执行到发布按钮前停止；用于验证上传、封面、文案和声明")
    parser.add_argument(
        "--upload-mode",
        choices=["auto", "cdp", "dialog"],
        default="cdp",
        help="上传方式：默认 cdp，使用当前账户本地 CDP Chrome；auto/dialog 仅保留人工排障兼容",
    )
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help=f"Chrome DevTools Protocol 地址，也可用 DOUYIN_CHROME_CDP_URL；常见值 {DEFAULT_CDP_URL}",
    )
    parser.add_argument("--cdp-timeout", type=int, default=20, help="CDP 直传查找文件输入框的秒数")
    parser.add_argument("--upload-timeout", type=int, default=300, help="等待上传/表单出现的秒数")
    parser.add_argument("--publish-timeout", type=int, default=90, help="点击发布后等待结果的秒数")
    parser.add_argument("--declaration-timeout", type=int, default=20, help="自主声明尝试秒数；失败会阻断发布")
    parser.add_argument(
        "--cover-frame",
        choices=["recommended", "middle", "ai-recommended", "none"],
        default="recommended",
        help="封面帧选择：recommended 选网站推荐帧；middle 选视频中间帧；ai-recommended 走 AI封面 生成；none 跳过",
    )
    parser.add_argument("--cover-timeout", type=int, default=15, help="封面帧选择尝试秒数；失败不阻断发布")
    parser.add_argument("--record-jsonl", default=None, help="可选：追加写入 TEMP/RUN_ID/RUN_ID-run-record.jsonl")
    args = parser.parse_args()

    root = Path.cwd()
    out_dir = Path(args.out_dir) if args.out_dir else root / "TEMP/publish-runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    video = Path(args.video).expanduser().resolve()
    tags, tag_warnings = normalize_tags(args.tag)
    report = build_base_report(args, video, tags, tag_warnings)
    if args.upload_mode in {"auto", "cdp"} or args.current_tab:
        DOM_CDP_URL = resolve_cdp_url(args.cdp_url) or DEFAULT_CDP_URL

    if not video.exists():
        return fail(report, out_dir, f"视频文件不存在：{video}", 2)
    if not args.title.strip():
        return fail(report, out_dir, "标题不能为空", 2)

    if args.dry_run:
        report["decision"] = "dry-run-pass"
        for step in report["steps"].values():
            step["status"] = "skipped-by-dry-run"
        report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.upload_mode == "cdp":
        cdp_url = resolve_cdp_url(args.cdp_url) or DEFAULT_CDP_URL
        preflight = run_cdp_preflight(cdp_url)
        report["steps"]["upload"]["cdp_preflight"] = preflight
        if not preflight.get("ok"):
            return fail(report, out_dir, "当前账户本地 CDP Chrome 预检失败；请运行 TOOLS/open_cdp_chrome.sh 启动", 3)

    cdp_first_upload = (not args.current_tab) and args.upload_mode == "cdp"

    if cdp_first_upload:
        page = {
            "method": "playwright-cdp",
            "cdp_url": resolve_cdp_url(args.cdp_url),
            "upload_url": args.upload_url,
        }
    elif args.current_tab:
        cdp_url = resolve_cdp_url(args.cdp_url) or DEFAULT_CDP_URL
        report["steps"]["upload"]["activate_post_tab"] = activate_video_publish_page_via_playwright(cdp_url)
        page = dom_action(
            r'''
return {
  current_tab: true,
  url: location.href,
  title: document.title
};
'''
        )
    else:
        page = open_upload_page(args.upload_url)
    report["chrome_tab"] = page

    ready = {"skipped": True, "reason": "upload-mode=cdp 先由 Playwright 打开上传页"} if cdp_first_upload else wait_for_page_ready(60)
    report["steps"]["upload"]["page_ready"] = ready
    if ready.get("loggedOut"):
        return fail(report, out_dir, "抖音创作者中心需要登录、验证码或账号安全验证", 3)

    if args.current_tab:
        report["steps"]["upload"]["entry"] = {"ok": True, "method": "current-tab"}
        report["steps"]["upload"]["file_dialog"] = {"ok": True, "method": "already-uploaded"}
    else:
        cdp_result = {"ok": False, "method": "playwright-cdp", "skipped": True, "reason": "upload-mode=dialog"}
        if args.upload_mode in {"auto", "cdp"}:
            cdp_result = set_file_input_via_playwright(
                resolve_cdp_url(args.cdp_url),
                video,
                args.upload_url,
                args.cdp_timeout,
            )
        report["steps"]["upload"]["cdp"] = cdp_result

        if cdp_result.get("ok"):
            report["steps"]["upload"]["entry"] = {"ok": True, "method": "playwright-cdp"}
            report["steps"]["upload"]["file_dialog"] = {"ok": True, "method": "playwright-cdp"}
        elif args.upload_mode == "cdp":
            return fail(report, out_dir, f"CDP 直传失败：{cdp_result.get('reason')}", 4)
        else:
            upload_entry = click_upload_entry()
            report["steps"]["upload"]["entry"] = upload_entry
            if not upload_entry.get("ok"):
                return fail(report, out_dir, f"无法打开上传入口：{upload_entry.get('reason')}", 4)

            dialog = choose_file_in_dialog(video)
            report["steps"]["upload"]["file_dialog"] = dialog
            if not dialog.get("ok"):
                return fail(report, out_dir, f"系统文件选择器失败：{dialog.get('reason')}", 4)
            if page.get("temp_index"):
                report["steps"]["upload"]["restore_upload_tab"] = activate_chrome_tab(page.get("temp_index"))

    upload_form = wait_for_upload_form(args.upload_timeout)
    report["steps"]["upload"]["form"] = upload_form
    if upload_form.get("loginOrVerify"):
        return fail(report, out_dir, "上传后出现登录、验证码或账号安全验证", 3)
    if upload_form.get("hardError"):
        return fail(report, out_dir, "视频上传或处理出现硬错误", 4)
    if not (upload_form.get("uploadDone") or upload_form.get("hasTitleLikeField") or upload_form.get("hasDescLikeField")):
        return fail(report, out_dir, "等待上传表单超时", 4)
    report["steps"]["upload"]["status"] = "uploaded-or-form-ready"

    cover = set_cover_frame(args.cover_frame, args.cover_timeout)
    report["steps"]["cover"].update(cover)
    if cover.get("status") == "skipped":
        report["steps"]["cover"]["status"] = "skipped"
    elif cover.get("ok"):
        report["steps"]["cover"]["status"] = "set"
    else:
        report["steps"]["cover"]["status"] = "warning"
        report["warnings"].append(f"封面帧选择失败，继续发布：{cover.get('reason')}")

    copywriting = set_text_fields(args.title, args.description)
    tag_result = fill_tags(tags)
    report["steps"]["copywriting"].update({"status": "filled", "fields": copywriting, "tags": tag_result})
    if not copywriting.get("title"):
        return fail(report, out_dir, "没有成功填写标题", 5)
    if tags and not tag_result.get("ok"):
        if description_contains_tags(args.description, tags):
            tag_result["ok"] = True
            tag_result["degraded"] = True
            tag_result["degraded_reason"] = tag_result.get("reason")
            tag_result["reason"] = "标签控件不可用，话题已写入简介，按模块 04 降级通过"
            report["warnings"].append("标签控件未找到；本次按简介内话题降级通过")
        else:
            report["warnings"].append(f"标签填写失败：{tag_result.get('reason')}")

    declaration = try_set_ai_declaration(args.declaration_timeout)
    report["steps"]["declaration"].update(declaration)
    if declaration.get("status") != "set":
        return fail(report, out_dir, "自主声明未成功设置为内容由AI生成，按项目规则阻断发布", 6)

    assistant = check_assistant()
    report["steps"]["assistant"].update({"status": "pass" if assistant.get("ok") else "blocked", "result": assistant})
    if not assistant.get("ok"):
        return fail(report, out_dir, f"发文助手或页面出现硬错误：{assistant.get('hard_matches')}", 6)

    if args.no_publish:
        report["decision"] = "ready-not-published"
        report["steps"]["publish"]["status"] = "skipped-by-no-publish"
        report["warnings"].append("已按 --no-publish 停在发布按钮前，未点击发布")
        report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    publish_click = click_publish()
    report["steps"]["publish"]["click"] = publish_click
    if not publish_click.get("ok"):
        return fail(report, out_dir, f"发布按钮点击失败：{publish_click.get('reason')}", 7)

    publish_result = wait_for_publish_result(args.publish_timeout)
    report["steps"]["publish"]["result"] = publish_result
    report["final_url"] = publish_result.get("url")
    if publish_result.get("hardError"):
        return fail(report, out_dir, "点击发布后页面出现硬错误", 7)
    if publish_result.get("success"):
        report["decision"] = "published"
        report["steps"]["publish"]["status"] = "published"
        report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    report["decision"] = "unknown"
    report["warnings"].append("点击发布后未在等待时间内确认成功页面；需主流程复查当前 Chrome 页面")
    report["steps"]["publish"]["status"] = "unknown"
    report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
