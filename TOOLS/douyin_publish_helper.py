#!/usr/bin/env python3
"""Automate the repetitive Douyin Creator Center publish-page steps.

The helper is intentionally conservative: it reports hard blockers and requires
the "内容由AI生成" declaration before clicking publish.
"""

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
    if not DOM_CDP_URL:
        raise RuntimeError("抖音发布只允许 CDP 直连，缺少 CDP 地址")
    out = dom_action_via_playwright(DOM_CDP_URL, js_body, timeout=timeout)
    return json.loads(out or "null")


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
        import playwright.sync_api  # type: ignore  # noqa: F401
    except Exception as exc:
        return str(exc)
    return None


def _set_file_input_via_playwright_sync(cdp_url: str, video: Path, upload_url: str, timeout_sec: int) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    timeout_ms = timeout_sec * 1000
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
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
            page = contexts[0].pages[0] if contexts[0].pages else contexts[0].new_page()
            page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_ms)

        page.bring_to_front()
        if not (is_upload_page(page.url) or is_video_publish_page(page.url)):
            page.goto(upload_url, wait_until="domcontentloaded", timeout=timeout_ms)

        file_input = page.locator('input[type="file"]').first
        if file_input.count() == 0:
            for selector in ('text=发布视频', 'button:has-text("发布视频")', '[role=tab]:has-text("发布视频")'):
                try:
                    page.locator(selector).first.click(timeout=3000)
                    page.wait_for_timeout(1000)
                    break
                except Exception:
                    continue
        file_input.wait_for(state="attached", timeout=timeout_ms)
        file_input.set_input_files(str(video))
        return {
            "ok": True,
            "method": "playwright-cdp",
            "url": page.url,
            "title": page.title(),
            "path_used": str(video),
            "connection": "sync",
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
        return _set_file_input_via_playwright_sync(cdp_url, video, upload_url, timeout_sec)
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
        return {"ok": True, "filled": 0, "requested_tags": [], "applied_tags": []}
    if not DOM_CDP_URL:
        return {"ok": False, "filled": 0, "requested_tags": clean_tags, "applied_tags": [], "reason": "抖音标签只允许通过 CDP 完整匹配写入"}
    return fill_tags_via_playwright(DOM_CDP_URL, clean_tags)


def apply_tag_candidates(tags: list[str], attempt: Any, target_count: int = 4) -> dict[str, Any]:
    applied: list[str] = []
    actions: list[dict[str, Any]] = []
    for tag in tags:
        if len(applied) >= target_count:
            break
        try:
            result = attempt(tag)
        except Exception as exc:
            result = {"tag": tag, "ok": False, "reason": str(exc)}
        action = {"tag": tag, **(result if isinstance(result, dict) else {"ok": bool(result)})}
        actions.append(action)
        if action.get("ok"):
            applied.append(tag)
    return {
        "ok": len(applied) >= min(target_count, len(tags)),
        "filled": len(applied),
        "requested_tags": tags,
        "applied_tags": applied,
        "actions": actions,
    }


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
        def attempt(tag: str) -> dict[str, Any]:
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
                    return {"ok": False, "reason": "没有找到完整匹配的话题建议"}

                suggestion.click(timeout=3000)

                page.wait_for_timeout(700)
                ok = has_highlighted_topic(page, tag)
                return {"ok": ok, "method": "topic-suggestion"}
            except Exception as exc:
                return {"ok": False, "reason": str(exc)}

        return {**apply_tag_candidates(tags, attempt), "method": "playwright-topic-token"}


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


def set_cover_frame_via_playwright(cdp_url: str, timeout_sec: int) -> dict[str, Any]:
    """Select the middle video frame for the visible Douyin cover editors."""
    from playwright.sync_api import sync_playwright

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
            return {"ok": False, "status": "failed", "mode": "middle", "reason": "没有找到抖音发布页"}
        page.bring_to_front()

        dialog = page.locator('[role="dialog"], .dy-creator-content-modal-body').first
        if dialog.count() > 0 and dialog.is_visible():
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        opened: dict[str, Any] = {"ok": False, "reason": "没有找到封面入口"}
        for selector in (".cover-Jg3T4p", ".coverControl-CjlzqC", ".filter-k_CjvJ"):
            target = page.locator(selector).first
            if target.count() == 0:
                continue
            opened = click_locator_center(page, target, timeout_ms)
            opened["selector"] = selector
            if not opened.get("ok"):
                continue
            try:
                dialog.wait_for(state="visible", timeout=3000)
                break
            except Exception as exc:
                opened = {"ok": False, "selector": selector, "reason": f"点击后未打开封面编辑器：{exc}"}
        actions.append({"step": "open_cover_editor", **opened})
        if not opened.get("ok"):
            return {"ok": False, "status": "failed", "mode": "middle", "reason": opened.get("reason"), "actions": actions}

        def select_middle(stage: str) -> dict[str, Any]:
            frames = page.locator(".preview-frame-rt7Mc1")
            try:
                frames.first.wait_for(state="visible", timeout=timeout_ms)
            except Exception as exc:
                return {"ok": False, "stage": stage, "reason": f"没有找到视频帧缩略图：{exc}"}
            count = frames.count()
            if count <= 0:
                return {"ok": False, "stage": stage, "reason": "没有找到视频帧缩略图"}
            index = count // 2
            click = click_locator_center(page, frames.nth(index), timeout_ms)
            return {"ok": bool(click.get("ok")), "stage": stage, "frame_index": index, "frame_count": count, "selection": "middle-frame", **click}

        vertical = select_middle("vertical")
        actions.append({"step": "select_vertical_middle_frame", **vertical})
        if not vertical.get("ok"):
            return {"ok": False, "status": "failed", "mode": "middle", "reason": vertical.get("reason"), "actions": actions}
        horizontal = {"ok": True, "skipped": True, "reason": "页面没有独立横封面入口"}
        horizontal_button = page.get_by_text("设置横封面", exact=True).last
        if horizontal_button.count() > 0 and horizontal_button.is_visible():
            horizontal_button.click(timeout=timeout_ms)
            page.wait_for_timeout(500)
            horizontal = select_middle("horizontal")
        actions.append({"step": "select_horizontal_middle_frame", **horizontal})
        if not horizontal.get("ok"):
            return {"ok": False, "status": "failed", "mode": "middle", "reason": horizontal.get("reason"), "actions": actions}
        finish = {"ok": False, "reason": "没有找到封面完成按钮"}
        finish_button = dialog.get_by_text("完成", exact=True).last
        if finish_button.count() > 0:
            try:
                finish_button.click(timeout=timeout_ms)
                page.wait_for_timeout(800)
                finish = {"ok": True, "text": "完成"}
            except Exception as exc:
                finish = {"ok": False, "reason": str(exc)}
        actions.append({"step": "finish_cover_editor", **finish})
        if not finish.get("ok"):
            return {"ok": False, "status": "failed", "mode": "middle", "reason": finish.get("reason"), "actions": actions}
        return {"ok": True, "status": "set", "mode": "middle", "method": "playwright-cdp", "actions": actions, "elapsed_sec": round(time.time() - started, 3)}


def set_cover_frame(frame_mode: str, timeout_sec: int) -> dict[str, Any]:
    if frame_mode != "middle":
        return {"ok": False, "status": "failed", "reason": "抖音封面固定为中间帧"}
    if not DOM_CDP_URL:
        return {"ok": False, "status": "failed", "reason": "抖音封面只允许通过 CDP 设置"}
    return set_cover_frame_via_playwright(DOM_CDP_URL, timeout_sec)


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
        f"- 候选标签：{', '.join(report.get('requested_tags') or []) or '无'}",
        f"- 已应用标签：{', '.join(report.get('applied_tags') or []) or '无'}",
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
        warnings.append(f"候选标签数量 {len(clean)} 个，少于目标 4 个")
    if len(clean) > 8:
        warnings.append(f"标签数量 {len(clean)} 个，多于候选池上限 8 个；本次只尝试前 8 个")
        clean = clean[:8]
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
        "requested_tags": tags,
        "applied_tags": [],
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
    }


def fail(report: dict[str, Any], out_dir: Path, message: str, code: int) -> int:
    report["decision"] = "failed"
    report["errors"].append(message)
    if "登录" in message or "验证码" in message or "安全验证" in message:
        report["error_category"] = "authentication"
    elif "自主声明" in message:
        report["error_category"] = "declaration"
    elif "超时" in message and any(token in message for token in ("页面", "导航", "CDP", "上传表单")):
        report["error_category"] = "navigation_timeout"
    else:
        report["error_category"] = "unknown"
    report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


def main() -> int:
    global DOM_CDP_URL
    parser = argparse.ArgumentParser(description="自动完成抖音创作者中心发布页的重复操作。")
    parser.add_argument("video", help="待发布 MP4 路径")
    parser.add_argument("--title", required=True, help="作品标题")
    parser.add_argument("--description", default="", help="作品简介")
    parser.add_argument("--tag", action="append", default=[], help="候选标签，可重复传入，最多尝试 8 个并应用 4 个完整匹配")
    parser.add_argument("--out-dir", default=None, help="报告输出目录，默认 TEMP/publish-runs/YYYYMMDD-HHMMSS")
    parser.add_argument("--upload-url", default=DEFAULT_UPLOAD_URL, help="抖音创作者中心上传页")
    parser.add_argument("--dry-run", action="store_true", help="只校验参数和报告输出，不接管 Chrome")
    parser.add_argument("--no-publish", action="store_true", help="执行到发布按钮前停止；用于验证上传、封面、文案和声明")
    parser.add_argument(
        "--cdp-url",
        default=DEFAULT_CDP_URL,
        help=f"Chrome DevTools Protocol 地址，也可用 DOUYIN_CHROME_CDP_URL；常见值 {DEFAULT_CDP_URL}",
    )
    parser.add_argument("--cdp-timeout", type=int, default=20, help="CDP 直传查找文件输入框的秒数")
    parser.add_argument("--upload-timeout", type=int, default=300, help="等待上传/表单出现的秒数")
    parser.add_argument("--publish-timeout", type=int, default=90, help="点击发布后等待结果的秒数")
    parser.add_argument("--declaration-timeout", type=int, default=20, help="自主声明尝试秒数；失败会阻断发布")
    parser.add_argument("--cover-timeout", type=int, default=15, help="封面帧选择尝试秒数；失败不阻断发布")
    args = parser.parse_args()

    root = Path.cwd()
    out_dir = Path(args.out_dir) if args.out_dir else root / "TEMP/publish-runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    video = Path(args.video).expanduser().resolve()
    tags, tag_warnings = normalize_tags(args.tag)
    report = build_base_report(args, video, tags, tag_warnings)
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

    cdp_url = resolve_cdp_url(args.cdp_url) or DEFAULT_CDP_URL
    preflight = run_cdp_preflight(cdp_url)
    report["steps"]["upload"]["cdp_preflight"] = preflight
    if not preflight.get("ok"):
        return fail(report, out_dir, "CDP Chrome 预检失败；请运行 TOOLS/open_cdp_chrome.sh 启动", 3)

    page = {
        "method": "playwright-cdp",
        "cdp_url": cdp_url,
        "upload_url": args.upload_url,
    }
    report["chrome_tab"] = page

    ready = {"skipped": True, "reason": "CDP 直传先由 Playwright 打开上传页"}
    report["steps"]["upload"]["page_ready"] = ready
    cdp_result = set_file_input_via_playwright(cdp_url, video, args.upload_url, args.cdp_timeout)
    report["steps"]["upload"]["cdp"] = cdp_result
    if not cdp_result.get("ok"):
        return fail(report, out_dir, f"CDP 直传失败：{cdp_result.get('reason')}", 4)
    report["steps"]["upload"]["entry"] = {"ok": True, "method": "playwright-cdp"}

    upload_form = wait_for_upload_form(args.upload_timeout)
    report["steps"]["upload"]["form"] = upload_form
    if upload_form.get("loginOrVerify"):
        return fail(report, out_dir, "上传后出现登录、验证码或账号安全验证", 3)
    if upload_form.get("hardError"):
        return fail(report, out_dir, "视频上传或处理出现硬错误", 4)
    if not (upload_form.get("uploadDone") or upload_form.get("hasTitleLikeField") or upload_form.get("hasDescLikeField")):
        return fail(report, out_dir, "等待上传表单超时", 4)
    report["steps"]["upload"]["status"] = "uploaded-or-form-ready"

    try:
        cover_result = set_cover_frame("middle", args.cover_timeout)
    except Exception as exc:
        cover_result = {"ok": False, "status": "failed", "mode": "middle", "reason": str(exc)}
    report["steps"]["cover"].update(cover_result)
    if not cover_result.get("ok"):
        report["warnings"].append(f"封面帧未设置：{cover_result.get('reason') or cover_result.get('status')}")

    copywriting = set_text_fields(args.title, args.description)
    tag_result = fill_tags(tags)
    report["applied_tags"] = tag_result.get("applied_tags", tag_result.get("tags", []))
    report["steps"]["copywriting"].update({"status": "filled", "fields": copywriting, "tags": tag_result})
    if not copywriting.get("title"):
        return fail(report, out_dir, "没有成功填写标题", 5)
    if tags and not tag_result.get("ok"):
        report["warnings"].append("候选标签已耗尽，未获得四个完整匹配；不会写入粘连标签")

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
    report["warnings"].append("点击发布后未在等待时间内确认成功页面；需人工复查当前 Chrome 页面")
    report["steps"]["publish"]["status"] = "unknown"
    report["report_json"], report["report_md"] = [str(p) for p in write_report(out_dir, report)]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 8


if __name__ == "__main__":
    raise SystemExit(main())
