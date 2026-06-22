#!/usr/bin/env python3
"""Create and validate a reference-video grid from real Chrome screenshots.

This helper assumes Douyin reference videos usually cannot be downloaded
reliably. It opens the detail page in the user's real Chrome, seeks the page
video when possible, captures lightweight screenshots, validates that the
capture is suitable as a pure video-body reference, and tiles it into a 2x3
reference grid.
"""

import argparse
import base64
import json
import math
import shutil
import subprocess
import sys
import time
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from douyin_publish_preflight import DEFAULT_CDP_URL, DEFAULT_USER_DATA_DIR, check_cdp
from run_record import append_artifact, append_event, refresh_markdown


def run(cmd, text=True):
    started = time.time()
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_sec": round(time.time() - started, 3),
    }


def stream_text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def load_sync_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError(f"Playwright 不可用，无法使用 CDP 抽帧：{exc}") from exc
    return sync_playwright


def osascript(script):
    result = run(["osascript", "-e", script])
    if result["returncode"] != 0:
        raise RuntimeError((result["stderr"] or result["stdout"] or "osascript failed").strip())
    return result["stdout"].strip()


def chrome_js(js):
    script = f'''
tell application "Google Chrome"
    if not (exists window 1) then error "Chrome 没有打开窗口"
    execute active tab of window 1 javascript {json.dumps(js, ensure_ascii=False)}
end tell
'''
    try:
        return osascript(script)
    except RuntimeError as exc:
        message = str(exc)
        if "执行 JavaScript 的功能已关闭" in message or "JavaScript from Apple Events" in message:
            raise RuntimeError(
                "Chrome 禁止 Apple 事件执行 JavaScript；请在 Chrome 菜单栏打开 "
                "查看 > 开发者 > 允许 Apple 事件中的 JavaScript 后重试"
            ) from exc
        raise


def chrome_bounds():
    out = osascript('tell application "Google Chrome" to get bounds of window 1')
    parts = [int(p.strip()) for p in out.split(",")]
    if len(parts) != 4:
        raise RuntimeError(f"无法读取 Chrome 窗口边界：{out}")
    left, top, right, bottom = parts
    return {"x": left, "y": top, "width": right - left, "height": bottom - top}


def parse_key_values(text):
    values = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def open_in_chrome(url, keep_tab=False):
    script = f'''
tell application "Google Chrome"
    activate
    if not (exists window 1) then error "Chrome 没有打开窗口，请先运行 TOOLS/open_cdp_chrome.sh"
    set w to window 1
    set originalIndex to active tab index of w
    set beforeCount to count tabs of w
    set tempTab to make new tab at end of tabs of w with properties {{URL:{json.dumps(url)}}}
    set tempIndex to count tabs of w
    set active tab index of w to tempIndex
    return "mode=temp-tab" & linefeed & "keep_tab={str(bool(keep_tab)).lower()}" & linefeed & "original_index=" & originalIndex & linefeed & "temp_index=" & tempIndex & linefeed & "before_count=" & beforeCount
end tell
'''
    status = parse_key_values(osascript(script))
    status["keep_tab"] = keep_tab
    return status


def cleanup_chrome_tab(tab_session):
    if not tab_session:
        return None
    if tab_session.get("keep_tab"):
        return {"cleanup": "kept", "reason": "--keep-tab"}

    original_index = int(tab_session["original_index"])
    temp_index = int(tab_session["temp_index"])
    script = f'''
tell application "Google Chrome"
    if not (exists window 1) then return "cleanup=no-window"
    set w to window 1
    set beforeCloseCount to count tabs of w
    if beforeCloseCount is greater than or equal to {temp_index} then close tab {temp_index} of w
    delay 0.2
    set afterCloseCount to count tabs of w
    if afterCloseCount > 0 then
        if afterCloseCount is greater than or equal to {original_index} then
            set active tab index of w to {original_index}
        else
            set active tab index of w to afterCloseCount
        end if
    end if
    return "cleanup=closed" & linefeed & "before_close_count=" & beforeCloseCount & linefeed & "after_close_count=" & afterCloseCount & linefeed & "restored_index=" & (active tab index of w)
end tell
'''
    try:
        return parse_key_values(osascript(script))
    except RuntimeError as exc:
        return {"cleanup": "failed", "error": str(exc)}


def finish(report, out_dir, tab_session, exit_code, stderr=False):
    cleanup = cleanup_chrome_tab(tab_session)
    if cleanup:
        report.setdefault("chrome_tab", {}).update(cleanup)
    report_json, report_md = write_report(out_dir, report)
    report["report_json"] = str(report_json)
    report["report_md"] = str(report_md)
    record_jsonl = report.get("record_jsonl")
    if record_jsonl:
        append_event(
            record_jsonl,
            stage="reference",
            event="reference_grid",
            status=report.get("decision"),
            summary=f"参考宫格 {report.get('decision') or 'unknown'}",
            data={
                "reference_url": report.get("input_url"),
                "grid_path": report.get("grid_path"),
                "report_json": str(report_json),
                "capture_mode": report.get("capture_mode"),
                "duration_sec": report.get("duration_sec"),
                "errors": report.get("errors", []),
                "warnings": report.get("warnings", []),
            },
        )
        if report.get("grid_path"):
            append_artifact(
                record_jsonl,
                stage="reference",
                path=str(report.get("grid_path")),
                kind="reference-grid",
                status=report.get("decision"),
                keep=True,
                summary="参考宫格",
            )
        refresh_markdown(record_jsonl)
    stream = sys.stderr if stderr else sys.stdout
    print(json.dumps(report, ensure_ascii=False, indent=2), file=stream)
    return exit_code


def read_video_state():
    js = r'''
JSON.stringify((function() {
  var video = document.querySelector('video');
  if (!video) {
    return { ok: false, reason: '页面未找到 video 元素', url: location.href, title: document.title };
  }
  var rect = video.getBoundingClientRect();
  try { video.pause(); } catch (_) {}
  return {
    ok: true,
    url: location.href,
    title: document.title,
    duration: Number.isFinite(video.duration) ? video.duration : 0,
    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
    readyState: video.readyState,
    paused: video.paused,
    hasCurrentSrc: Boolean(video.currentSrc || video.src),
    rect: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    }
  };
}()))
'''
    out = chrome_js(js)
    return json.loads(out)


def seek_video(seconds):
    js = f'''
(function() {{
  var video = document.querySelector('video');
  if (!video) return 'no-video';
  try {{
    video.pause();
    video.currentTime = {seconds:.3f};
    return 'ok';
  }} catch (err) {{
    return 'seek-error:' + err.message;
  }}
}}())
'''
    return chrome_js(js)


def play_video():
    js = r'''
(function() {
  var video = document.querySelector('video');
  if (!video) return 'no-video';
  try {
    video.muted = true;
    var p = video.play();
    return p && typeof p.then === 'function' ? 'play-requested' : 'play-called';
  } catch (err) {
    return 'play-error:' + err.message;
  }
}())
'''
    return chrome_js(js)


def parse_rect(value):
    if not value:
        return None
    parts = [int(p.strip()) for p in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--rect 格式必须是 x,y,w,h")
    x, y, width, height = parts
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--rect 宽高必须大于 0")
    return {"x": x, "y": y, "width": width, "height": height}


def choose_capture_rect(args, state):
    if args.rect:
        rect = parse_rect(args.rect)
        rect["source"] = "custom-rect"
        return rect

    bounds = chrome_bounds()
    if args.crop_mode == "window" or not state.get("ok"):
        return {**bounds, "source": "chrome-window"}

    video_rect = state.get("rect") or {}
    if video_rect.get("width", 0) >= 120 and video_rect.get("height", 0) >= 120:
        target_ratio = 9 / 16
        video_ratio = video_rect["width"] / video_rect["height"]
        if video_ratio > target_ratio * 1.15:
            subject_width = round(video_rect["height"] * target_ratio)
            rect = {
                "x": bounds["x"] + args.viewport_offset_x + round(video_rect["x"] + (video_rect["width"] - subject_width) / 2),
                "y": bounds["y"] + args.viewport_offset_y + video_rect["y"],
                "width": subject_width,
                "height": video_rect["height"],
                "source": "video-subject-9x16-estimate",
            }
            return rect
        rect = {
            "x": bounds["x"] + args.viewport_offset_x + video_rect["x"],
            "y": bounds["y"] + args.viewport_offset_y + video_rect["y"],
            "width": video_rect["width"],
            "height": video_rect["height"],
            "source": "video-rect-estimate",
        }
        return rect
    return {**bounds, "source": "chrome-window"}


def capture(rect, path):
    spec = f"{rect['x']},{rect['y']},{rect['width']},{rect['height']}"
    return run(["screencapture", "-x", "-R", spec, str(path)])


def capture_video_frame(path):
    js = r'''
JSON.stringify((function() {
  var video = document.querySelector('video');
  if (!video) return { ok: false, reason: '页面未找到 video 元素' };
  if (!video.videoWidth || !video.videoHeight) {
    return { ok: false, reason: 'video 元素还没有可读像素尺寸' };
  }

  var sourceWidth = video.videoWidth;
  var sourceHeight = video.videoHeight;
  var targetRatio = 9 / 16;
  var sourceRatio = sourceWidth / sourceHeight;
  var sx = 0;
  var sy = 0;
  var sw = sourceWidth;
  var sh = sourceHeight;

  if (sourceRatio > targetRatio) {
    sw = Math.round(sourceHeight * targetRatio);
    sx = Math.round((sourceWidth - sw) / 2);
  } else if (sourceRatio < targetRatio) {
    sh = Math.round(sourceWidth / targetRatio);
    sy = Math.round((sourceHeight - sh) / 2);
  }

  var canvas = document.createElement('canvas');
  canvas.width = sw;
  canvas.height = sh;
  var ctx = canvas.getContext('2d');
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, sw, sh);
  return {
    ok: true,
    width: sw,
    height: sh,
    sourceWidth: sourceWidth,
    sourceHeight: sourceHeight,
    crop: { x: sx, y: sy, width: sw, height: sh },
    dataUrl: canvas.toDataURL('image/png')
  };
}()))
'''
    out = chrome_js(js)
    result = json.loads(out)
    if not result.get("ok"):
        return {"returncode": 1, "stderr": result.get("reason") or "video canvas 抽帧失败"}
    data_url = result.get("dataUrl") or ""
    prefix = "data:image/png;base64,"
    if not data_url.startswith(prefix):
        return {"returncode": 1, "stderr": "video canvas 返回了非 PNG data URL"}
    try:
        path.write_bytes(base64.b64decode(data_url[len(prefix):]))
    except Exception as exc:
        return {"returncode": 1, "stderr": f"写入 canvas 抽帧失败：{exc}"}
    return {
        "returncode": 0,
        "stdout": json.dumps({k: v for k, v in result.items() if k != "dataUrl"}, ensure_ascii=False),
        "stderr": "",
    }


def capture_video_frames_cdp(url, out_dir, args, report):
    sync_playwright = load_sync_playwright()
    frames = []
    page = None
    tab_session = open_in_chrome(url, keep_tab=args.keep_tab)
    report["chrome_tab"] = dict(tab_session)
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(DEFAULT_CDP_URL)
            if not browser.contexts:
                raise RuntimeError("当前账户本地 CDP Chrome 没有可用浏览器上下文")
            context = browser.contexts[0]
            deadline = time.time() + max(8.0, args.initial_wait_sec)
            while time.time() < deadline and page is None:
                for candidate in context.pages:
                    if candidate.url.split("?")[0] == url.split("?")[0]:
                        page = candidate
                        break
                if page is None:
                    time.sleep(0.5)
            if page is None:
                raise RuntimeError("CDP 未找到 AppleScript 打开的参考标签页")
            page.bring_to_front()
            page.wait_for_timeout(int(max(0.0, args.initial_wait_sec) * 1000))
            state_js = r'''
() => {
  const video = document.querySelector('video');
  if (!video) {
    return { ok: false, reason: '页面未找到 video 元素', url: location.href, title: document.title };
  }
  try { video.pause(); } catch (_) {}
  const rect = video.getBoundingClientRect();
  return {
    ok: true,
    url: location.href,
    title: document.title,
    duration: Number.isFinite(video.duration) ? video.duration : 0,
    currentTime: Number.isFinite(video.currentTime) ? video.currentTime : 0,
    readyState: video.readyState,
    paused: video.paused,
    hasCurrentSrc: Boolean(video.currentSrc || video.src),
    videoWidth: video.videoWidth || 0,
    videoHeight: video.videoHeight || 0,
    rect: {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height)
    }
  };
}
'''
            state = None
            deadline = time.time() + max(12.0, args.initial_wait_sec)
            while time.time() < deadline:
                state = page.evaluate(state_js)
                if (
                    state.get("ok")
                    and float(state.get("duration") or 0) > 0
                    and int(state.get("videoWidth") or 0) > 0
                    and int(state.get("videoHeight") or 0) > 0
                ):
                    break
                page.wait_for_timeout(1000)
            if state is None:
                state = page.evaluate(state_js)
            report.update({
                "url": state.get("url"),
                "title": state.get("title"),
                "duration_sec": float(state.get("duration") or 0),
                "ready_state": state.get("readyState"),
                "has_current_src": state.get("hasCurrentSrc"),
                "video_size": {
                    "width": int(state.get("videoWidth") or 0),
                    "height": int(state.get("videoHeight") or 0),
                },
                "capture_mode": "video-canvas-frame-cdp-playwright",
                "capture_rect": {
                    "source": "video-canvas-frame-cdp-playwright",
                    "note": "从当前账户本地 CDP Chrome video 元素直接抽取 9:16 当前帧像素，未下载原视频",
                },
            })
            if not state.get("ok"):
                raise RuntimeError(state.get("reason") or "页面未找到可播放视频")
            duration = report["duration_sec"]
            if duration <= 0:
                raise RuntimeError("视频时长为 0 或不可读，不能确认关键帧来自可控播放")

            for index, seconds in enumerate(target_times(duration, args.frames), start=1):
                path = out_dir / f"frame-{index:02d}.png"
                result = page.evaluate(r'''
async ({ seconds, settleMs }) => {
  const video = document.querySelector('video');
  if (!video) return { ok: false, reason: '页面未找到 video 元素' };
  await new Promise(resolve => {
    let resolved = false;
    const done = () => {
      if (resolved) return;
      resolved = true;
      video.removeEventListener('seeked', done);
      resolve();
    };
    try {
      video.pause();
      video.addEventListener('seeked', done, { once: true });
      video.currentTime = seconds;
      setTimeout(done, Math.max(1200, settleMs + 800));
    } catch (err) {
      resolve();
    }
  });
  await new Promise(resolve => setTimeout(resolve, settleMs));
  if (!video.videoWidth || !video.videoHeight) {
    return { ok: false, reason: 'video 元素还没有可读像素尺寸' };
  }

  const sourceWidth = video.videoWidth;
  const sourceHeight = video.videoHeight;
  const targetRatio = 9 / 16;
  const sourceRatio = sourceWidth / sourceHeight;
  let sx = 0;
  let sy = 0;
  let sw = sourceWidth;
  let sh = sourceHeight;

  if (sourceRatio > targetRatio) {
    sw = Math.round(sourceHeight * targetRatio);
    sx = Math.round((sourceWidth - sw) / 2);
  } else if (sourceRatio < targetRatio) {
    sh = Math.round(sourceWidth / targetRatio);
    sy = Math.round((sourceHeight - sh) / 2);
  }

  const canvas = document.createElement('canvas');
  canvas.width = sw;
  canvas.height = sh;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, sw, sh);
  return {
    ok: true,
    width: sw,
    height: sh,
    sourceWidth,
    sourceHeight,
    crop: { x: sx, y: sy, width: sw, height: sh },
    dataUrl: canvas.toDataURL('image/png')
  };
}
''', {"seconds": seconds, "settleMs": int(max(0.0, args.settle_sec) * 1000)})
                if not result.get("ok"):
                    report["errors"].append(f"第 {index} 帧 CDP 抽帧失败：{result.get('reason') or 'unknown'}")
                    continue
                data_url = result.get("dataUrl") or ""
                prefix = "data:image/png;base64,"
                if not data_url.startswith(prefix):
                    report["errors"].append(f"第 {index} 帧 CDP 抽帧返回了非 PNG data URL")
                    continue
                path.write_bytes(base64.b64decode(data_url[len(prefix):]))
                frames.append(path)
                report["frames"].append({
                    "path": str(path),
                    "target_time_sec": round(seconds, 3),
                    "capture": "video-canvas-frame-cdp-playwright",
                    "canvas": {k: v for k, v in result.items() if k != "dataUrl"},
                })
        finally:
            cleanup = cleanup_chrome_tab(tab_session)
            if cleanup:
                report.setdefault("chrome_tab", {}).update(cleanup)
        return frames


def make_grid(frames, out_path, tile, frame_width, quality):
    pattern = str(frames[0].parent / "frame-%02d.png")
    return run([
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-framerate",
        "1",
        "-i",
        pattern,
        "-frames:v",
        "1",
        "-vf",
        f"scale={frame_width}:-1,tile={tile}",
        "-q:v",
        str(quality),
        str(out_path),
    ])


def image_info(path):
    result = run([
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(path),
    ])
    if result["returncode"] != 0:
        return None
    try:
        parsed = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return None
    streams = parsed.get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
    }


def read_gray_pixels(path, width=64, height=112):
    result = run([
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(path),
        "-vf",
        f"scale={width}:{height},format=gray",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "pipe:1",
    ], text=False)
    if result["returncode"] != 0:
        raise RuntimeError(stream_text(result["stderr"]).strip() or "ffmpeg 读取灰度像素失败")
    data = result["stdout"]
    if len(data) != width * height:
        raise RuntimeError(f"灰度像素长度异常：{len(data)} != {width * height}")
    return data


def mean_abs_delta(left, right):
    if not left or not right or len(left) != len(right):
        return math.inf
    return sum(abs(a - b) for a, b in zip(left, right)) / len(left)


def band_mean(pixels, width, height, x0, x1, y0, y1):
    total = 0
    count = 0
    for y in range(max(0, y0), min(height, y1)):
        row = y * width
        for x in range(max(0, x0), min(width, x1)):
            total += pixels[row + x]
            count += 1
    return total / count if count else 0


def boundary_delta(pixels, width, height, x):
    if x <= 0 or x >= width:
        return 0
    total = 0
    for y in range(height):
        total += abs(pixels[y * width + x] - pixels[y * width + x - 1])
    return total / height if height else 0


def frame_ui_risks(path):
    width = 64
    height = 112
    pixels = read_gray_pixels(path, width, height)
    center = band_mean(pixels, width, height, 16, 48, 22, 90)
    left = band_mean(pixels, width, height, 0, 7, 12, 100)
    right = band_mean(pixels, width, height, 57, 64, 12, 100)
    bottom = band_mean(pixels, width, height, 0, 64, 102, 112)
    top = band_mean(pixels, width, height, 0, 64, 0, 8)
    left_edge = boundary_delta(pixels, width, height, 7)
    right_edge = boundary_delta(pixels, width, height, 57)

    risks = []
    if abs(right - center) > 35 and right_edge > 22:
        risks.append("右侧疑似推荐栏/侧边 UI")
    if abs(left - center) > 35 and left_edge > 22:
        risks.append("左侧疑似非视频主体边栏")
    if bottom + 28 < center:
        risks.append("底部疑似播放器控制条或浏览器栏")
    if top + 35 < center:
        risks.append("顶部疑似浏览器栏或页面遮罩")
    return risks


VISION_HEAD_FACE_SWIFT = r'''
import Foundation
import Vision
import AppKit

let threshold: Float = 0.1
let headJoints: [(String, VNHumanBodyPoseObservation.JointName)] = [
    ("nose", .nose),
    ("leftEye", .leftEye),
    ("rightEye", .rightEye),
    ("leftEar", .leftEar),
    ("rightEar", .rightEar)
]
let paths = CommandLine.arguments.dropFirst()
var results: [[String: Any]] = []

for path in paths {
    let url = URL(fileURLWithPath: path)
    guard let image = NSImage(contentsOf: url), let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff), let cgImage = bitmap.cgImage else {
        results.append(["path": path, "error": "cannot-load-image"])
        continue
    }

    let faceRequest = VNDetectFaceRectanglesRequest()
    let poseRequest = VNDetectHumanBodyPoseRequest()
    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    do {
        try handler.perform([faceRequest, poseRequest])
        let faces = (faceRequest.results ?? []).map { obs -> [String: Any] in
            let b = obs.boundingBox
            return [
                "x": b.origin.x,
                "y": b.origin.y,
                "width": b.width,
                "height": b.height,
                "confidence": obs.confidence
            ]
        }

        var people: [[String: Any]] = []
        for obs in poseRequest.results ?? [] {
            let points = try obs.recognizedPoints(.all)
            var head: [[String: Any]] = []
            for (name, key) in headJoints {
                if let p = points[key], p.confidence > threshold {
                    head.append([
                        "name": name,
                        "confidence": p.confidence,
                        "x": p.location.x,
                        "y": p.location.y
                    ])
                }
            }
            people.append(["confidence": obs.confidence, "head_points": head])
        }

        let headCount = people.reduce(0) { partial, item in
            partial + ((item["head_points"] as? [[String: Any]])?.count ?? 0)
        }
        results.append([
            "path": path,
            "faces": faces.count,
            "face_boxes": faces,
            "people": people.count,
            "head_points": headCount,
            "pose_observations": people
        ])
    } catch {
        results.append(["path": path, "error": String(describing: error)])
    }
}

let data = try JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
print("")
'''


def detect_head_face_info(frames):
    if not frames:
        return {
            "available": False,
            "decision": "unavailable",
            "method": "macos_vision_face_and_body_pose",
            "scope": "slow_confirmation_prompt_reference_only",
            "reason": "no frames",
        }
    if not shutil.which("swift"):
        return {
            "available": False,
            "decision": "unavailable",
            "method": "macos_vision_face_and_body_pose",
            "scope": "slow_confirmation_prompt_reference_only",
            "reason": "swift executable not found",
        }

    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False, encoding="utf-8") as handle:
            handle.write(VISION_HEAD_FACE_SWIFT)
            script_path = Path(handle.name)
        result = run(["swift", str(script_path), *[str(frame) for frame in frames]])
        if result["returncode"] != 0:
            return {
                "available": False,
                "decision": "error",
                "method": "macos_vision_face_and_body_pose",
                "scope": "slow_confirmation_prompt_reference_only",
                "error": stream_text(result["stderr"]).strip() or stream_text(result["stdout"]).strip(),
            }
        try:
            frame_results = json.loads(result["stdout"])
        except json.JSONDecodeError as exc:
            return {
                "available": False,
                "decision": "error",
                "method": "macos_vision_face_and_body_pose",
                "scope": "slow_confirmation_prompt_reference_only",
                "error": f"vision result json parse failed: {exc}",
            }
    finally:
        if script_path:
            try:
                script_path.unlink()
            except OSError:
                pass

    total_faces = sum(int(item.get("faces") or 0) for item in frame_results)
    total_head_points = sum(int(item.get("head_points") or 0) for item in frame_results)
    errored = [item for item in frame_results if item.get("error")]
    has_head_face_info = total_faces > 0 or total_head_points > 0
    return {
        "available": True,
        "method": "macos_vision_face_and_body_pose",
        "scope": "slow_confirmation_prompt_reference_only",
        "basis": "reference-grid sampled frames",
        "frame_count": len(frame_results),
        "frames_with_faces": sum(1 for item in frame_results if int(item.get("faces") or 0) > 0),
        "frames_with_head_points": sum(1 for item in frame_results if int(item.get("head_points") or 0) > 0),
        "total_faces": total_faces,
        "total_head_points": total_head_points,
        "has_head_face_info": has_head_face_info,
        "decision": "head_face_present" if has_head_face_info else "no_head_face_info",
        "errors": [item for item in errored],
        "frames": frame_results,
    }


def validate_capture(frames, grid_path, report, args):
    errors = []
    warnings = []
    frame_details = []

    if len(frames) < args.min_valid_frames:
        errors.append(f"有效截图 {len(frames)} 张，少于正式宫格最低要求 {args.min_valid_frames} 张")

    grid_info = image_info(grid_path)
    if not grid_info:
        errors.append("无法读取宫格图宽高")
    gray_frames = []
    ui_risk_counts = {}
    canvas_frame_paths = {
        str(Path(frame.get("path", "")))
        for frame in report.get("frames", [])
        if str(frame.get("capture", "")).startswith("video-canvas-frame")
    }
    for path in frames:
        info = image_info(path)
        if not info:
            errors.append(f"无法读取截图宽高：{path}")
            continue
        ratio = info["width"] / info["height"] if info["height"] else 0
        expected = 9 / 16
        if abs(ratio - expected) > args.ratio_tolerance:
            errors.append(f"截图不是稳定 9:16 竖屏主体：{path} ({info['width']}x{info['height']})")
        try:
            gray = read_gray_pixels(path)
            gray_frames.append({"path": str(path), "pixels": gray})
            risks = [] if str(path) in canvas_frame_paths else frame_ui_risks(path)
            for risk in risks:
                ui_risk_counts[risk] = ui_risk_counts.get(risk, 0) + 1
        except Exception as exc:
            warnings.append(f"截图内容启发式检查失败：{path}：{exc}")
            risks = []
        frame_details.append({
            "path": str(path),
            "width": info["width"],
            "height": info["height"],
            "ratio": round(ratio, 4),
            "ui_risks": risks,
        })

    duplicate_pairs = []
    for index in range(1, len(gray_frames)):
        delta = mean_abs_delta(gray_frames[index - 1]["pixels"], gray_frames[index]["pixels"])
        if delta <= args.duplicate_delta:
            duplicate_pairs.append({
                "left": gray_frames[index - 1]["path"],
                "right": gray_frames[index]["path"],
                "mean_abs_delta": round(delta, 3),
            })
    if duplicate_pairs:
        errors.append(f"相邻截图疑似重复或画面未推进：{len(duplicate_pairs)} 组")

    repeated_ui_risks = [
        f"{risk}({count}帧)"
        for risk, count in sorted(ui_risk_counts.items())
        if count >= args.ui_risk_min_frames
    ]
    if repeated_ui_risks:
        errors.append("宫格疑似包含非视频主体 UI：" + "、".join(repeated_ui_risks))

    if report.get("chrome_js_unavailable"):
        errors.append("Chrome AppleScript JS 权限不可用，无法读取/控制真实 video 元素")
    if report.get("duration_sec", 0) <= 0:
        errors.append("视频时长为 0 或不可读，不能确认关键帧来自可控播放")
    if report.get("capture_mode") == "custom-rect":
        errors.append("使用了手动固定裁剪区域；正式宫格必须由可验证的 video 元素区域自动确定")
    if report.get("capture_mode") == "chrome-window":
        errors.append("使用了整窗截图；整窗截图不得作为正式参考宫格")
    if any(frame.get("mode") == "natural-playback" for frame in report.get("frames", [])):
        errors.append("使用自然播放间隔截图；正式宫格必须能按时长跳转或确认可控采样")

    return {
        "decision": "fail" if errors else ("needs_review" if warnings else "pass"),
        "errors": errors,
        "warnings": warnings,
        "grid_info": grid_info,
        "frame_details": frame_details,
        "duplicate_pairs": duplicate_pairs,
        "ui_risk_counts": ui_risk_counts,
    }


def compress_grid(frames, out_path, args):
    attempts = [
        (args.frame_width, args.quality),
        (280, max(args.quality, 7)),
        (240, max(args.quality, 8)),
        (200, max(args.quality, 9)),
    ]
    last = None
    for width, quality in attempts:
        last = make_grid(frames, out_path, args.tile, width, quality)
        if last["returncode"] != 0 or not out_path.exists():
            continue
        if out_path.stat().st_size <= args.target_bytes:
            return last
    return last


def write_report(out_dir, report):
    report_json = out_dir / "reference-grid-report.json"
    report_md = out_dir / "reference-grid-report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 参考视频宫格截图报告",
        "",
        f"- 结论：{report['decision']}",
        f"- 来源 URL：{report.get('url') or report['input_url']}",
        f"- 页面标题：{report.get('title') or '未读取'}",
        f"- 截图方式：{report.get('capture_mode') or '未执行'}",
        f"- 截图数量：{len(report.get('frames', []))}",
        f"- 视频时长：{report.get('duration_sec') or 0:.2f}s",
        f"- 是否下载原视频：否",
        f"- 宫格图：{report.get('grid_path') or '未生成'}",
        "",
        "## 问题",
    ]
    issues = report.get("errors", []) + report.get("warnings", [])
    lines.extend([f"- {item}" for item in issues] or ["- 无"])
    head_face = report.get("head_face_detection") or {}
    if head_face:
        if head_face.get("available"):
            lines.extend([
                "",
                "## 头脸信息检测",
                f"- 作用范围：仅供确认图 prompt lint 参考",
                f"- 结论：{head_face.get('decision')}",
                f"- 是否检测到头脸信息：{head_face.get('has_head_face_info')}",
                f"- 检测帧数：{head_face.get('frame_count', 0)}",
                f"- 人脸总数：{head_face.get('total_faces', 0)}",
                f"- 头部关键点总数：{head_face.get('total_head_points', 0)}",
            ])
        else:
            lines.extend([
                "",
                "## 头脸信息检测",
                f"- 作用范围：仅供确认图 prompt lint 参考",
                f"- 结论：{head_face.get('decision') or 'unavailable'}",
                f"- 原因：{head_face.get('reason') or head_face.get('error') or 'unknown'}",
            ])
    validation = report.get("validation") or {}
    if validation:
        grid_info = validation.get("grid_info") or {}
        lines.extend([
            "",
            "## 内容验证",
            f"- 结论：{validation.get('decision')}",
            f"- 宫格宽高：{grid_info.get('width', 0)}x{grid_info.get('height', 0)}",
        ])
        validation_issues = validation.get("errors", []) + validation.get("warnings", [])
        lines.extend([f"- {item}" for item in validation_issues] or ["- 无"])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_json, report_md


def target_times(duration, count):
    if duration > 0:
        points = [0.02, 0.20, 0.40, 0.60, 0.80, 0.95]
        return [max(0.0, min(duration - 0.15, duration * p)) for p in points[:count]]
    return []


def main():
    parser = argparse.ArgumentParser(description="通过当前账户本地 CDP Chrome 播放截图生成参考视频宫格图，不默认下载原视频。")
    parser.add_argument("url", help="抖音视频详情页 URL")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 TEMP/reference-grids/YYYYMMDD-HHMMSS")
    parser.add_argument("--frames", type=int, default=6, help="截图数量，默认 6")
    parser.add_argument("--tile", default="3x2", help="宫格 tile，默认 3x2")
    parser.add_argument("--frame-width", type=int, default=320, help="宫格中单帧宽度")
    parser.add_argument("--quality", type=int, default=6, help="JPEG 质量，数值越小质量越高")
    parser.add_argument("--target-bytes", type=int, default=200_000, help="宫格目标文件大小")
    parser.add_argument("--min-valid-frames", type=int, default=4, help="正式宫格最低有效截图数")
    parser.add_argument("--ratio-tolerance", type=float, default=0.035, help="截图 9:16 比例容忍值")
    parser.add_argument("--duplicate-delta", type=float, default=2.5, help="相邻低清灰度帧平均差低于该值视为疑似重复")
    parser.add_argument("--ui-risk-min-frames", type=int, default=2, help="同类 UI 风险命中至少多少帧后阻断")
    parser.add_argument("--initial-wait-sec", type=float, default=3.0, help="打开参考页后等待 video 元素加载的秒数")
    parser.add_argument("--settle-sec", type=float, default=0.8, help="跳转后等待画面稳定秒数")
    parser.add_argument("--natural-interval-sec", type=float, default=1.2, help="无法读取时长时自然播放截图间隔")
    parser.add_argument("--capture-method", choices=["auto", "canvas", "screen"], default="auto", help="auto 优先从 video 像素抽帧，失败后回退屏幕截图")
    parser.add_argument("--crop-mode", choices=["auto", "window"], default="auto", help="auto 优先估算 9:16 视频主体区域；window 仅用于调试，不得作为正式宫格")
    parser.add_argument("--rect", default=None, help="手动截图区域 x,y,w,h；设置后覆盖自动区域")
    parser.add_argument("--viewport-offset-x", type=int, default=0, help="video DOM 到屏幕坐标的 X 偏移校正")
    parser.add_argument("--viewport-offset-y", type=int, default=88, help="video DOM 到屏幕坐标的 Y 偏移校正，默认估算 Chrome 工具栏高度")
    parser.add_argument("--keep-tab", action="store_true", help="调试时保留临时参考页；默认生成报告后自动关闭")
    parser.add_argument("--record-jsonl", default=None, help="可选：追加写入 TEMP/RUN_ID/RUN_ID-run-record.jsonl")
    args = parser.parse_args()

    root = Path.cwd()
    out_dir = Path(args.out_dir) if args.out_dir else root / "TEMP/reference-grids" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "input_url": args.url,
        "record_jsonl": args.record_jsonl,
        "decision": "fail",
        "errors": [],
        "warnings": [],
        "frames": [],
        "downloaded_original_video": False,
    }
    no_js_fallback = False
    tab_session = None

    try:
        cdp_preflight = check_cdp(DEFAULT_CDP_URL, timeout=3, expected_user_data_dir=DEFAULT_USER_DATA_DIR)
        report["cdp_preflight"] = cdp_preflight
        if not cdp_preflight.get("ok"):
            report["errors"].append("当前账户本地 CDP Chrome 预检失败；请运行 TOOLS/open_cdp_chrome.sh 启动")
            write_report(out_dir, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 3

        if args.capture_method in {"auto", "canvas"} and not args.rect and args.crop_mode == "auto":
            try:
                frames = capture_video_frames_cdp(args.url, out_dir, args, report)
                if len(frames) < 2:
                    raise RuntimeError("有效 CDP 抽帧少于 2 张，未生成宫格")

                grid_path = out_dir / "reference-grid.jpg"
                grid_result = compress_grid(frames, grid_path, args)
                if grid_result["returncode"] != 0 or not grid_path.exists():
                    report["errors"].append(f"ffmpeg 拼接宫格失败：{stream_text(grid_result['stderr']).strip()}")
                    return finish(report, out_dir, None, 1)

                size = grid_path.stat().st_size
                if size > args.target_bytes:
                    report["warnings"].append(f"宫格图 {size / 1024:.1f}KB，超过目标 {args.target_bytes / 1024:.1f}KB")

                report.update({
                    "grid_path": str(grid_path),
                    "grid_size_bytes": size,
                    "output_dir": str(out_dir),
                })
                head_face_detection = detect_head_face_info(frames)
                report["head_face_detection"] = head_face_detection
                if not head_face_detection.get("available"):
                    report["warnings"].append("头脸信息检测不可用；仅影响确认图 prompt lint 的参考信息")
                validation = validate_capture(frames, grid_path, report, args)
                report["validation"] = validation
                if validation["errors"]:
                    report["errors"].extend(validation["errors"])
                    report["decision"] = "fail"
                    return finish(report, out_dir, None, 1)
                if validation["warnings"]:
                    report["warnings"].extend(validation["warnings"])
                    report["decision"] = "needs_review"
                    return finish(report, out_dir, None, 1)
                report["decision"] = "pass"
                return finish(report, out_dir, None, 0)
            except Exception as exc:
                cdp_errors = list(report.get("errors", []))
                cdp_warning = f"CDP/Playwright video canvas 抽帧失败：{exc}"
                if cdp_errors:
                    cdp_warning += "；" + "；".join(cdp_errors)
                if args.capture_method == "canvas":
                    report["errors"] = [cdp_warning]
                    return finish(report, out_dir, None, 1)
                report["warnings"].append(cdp_warning)
                report["warnings"].append("已回退旧 AppleScript/屏幕截图链路")
                report["errors"] = []
                report["frames"] = []
                report.pop("grid_path", None)
                report.pop("grid_size_bytes", None)
                report.pop("validation", None)
                report.pop("head_face_detection", None)
                report["capture_mode"] = None
                report["capture_rect"] = None

        tab_session = open_in_chrome(args.url, keep_tab=args.keep_tab)
        report["chrome_tab"] = dict(tab_session)
        time.sleep(max(0.0, args.initial_wait_sec))
        try:
            state = read_video_state()
        except RuntimeError as exc:
            if "Chrome 禁止 Apple 事件执行 JavaScript" not in str(exc):
                raise
            no_js_fallback = True
            report["chrome_js_unavailable"] = True
            state = {
                "ok": True,
                "url": args.url,
                "title": "",
                "duration": 0,
                "readyState": None,
                "hasCurrentSrc": False,
            }
            report["warnings"].append(str(exc))
            report["warnings"].append("已改用无 JS 权限兜底：不跳转进度，只按间隔截取 Chrome 前台窗口")
        report.update({
            "url": state.get("url"),
            "title": state.get("title"),
            "duration_sec": float(state.get("duration") or 0),
            "ready_state": state.get("readyState"),
            "has_current_src": state.get("hasCurrentSrc"),
        })
        if not state.get("ok"):
            report["errors"].append(state.get("reason") or "页面未找到可播放视频")
            return finish(report, out_dir, tab_session, 1)

        rect = choose_capture_rect(args, state)
        report["capture_rect"] = rect
        report["capture_mode"] = rect["source"]
        if rect["source"] == "chrome-window" and not args.rect:
            report["errors"].append("无法确认 9:16 视频主体裁剪区域，整窗截图不得作为正式参考宫格；请启用 Chrome AppleScript JS、传入 --rect，或先做视觉定位裁剪")
            return finish(report, out_dir, tab_session, 1)
        if rect["source"] == "video-subject-9x16-estimate":
            report["warnings"].append("已从横向播放器区域估算中央 9:16 视频主体；正式使用前应抽查宫格不含浏览器 UI、推荐栏、播放器控制条或模糊背景")
        if rect["source"] == "video-rect-estimate":
            report["warnings"].append("视频区域为 Chrome 窗口坐标估算；若裁剪偏移，可用 --rect 或 --viewport-offset-y 校正")

        frames = []
        duration = report["duration_sec"]
        if duration > 0 and not no_js_fallback:
            use_canvas = args.capture_method in {"auto", "canvas"}
            canvas_failed = False
            for index, seconds in enumerate(target_times(duration, args.frames), start=1):
                seek_result = seek_video(seconds)
                time.sleep(args.settle_sec)
                path = out_dir / f"frame-{index:02d}.png"
                cap = capture_video_frame(path) if use_canvas and not canvas_failed else capture(rect, path)
                if cap["returncode"] != 0 and args.capture_method == "auto" and not canvas_failed:
                    canvas_failed = True
                    report["warnings"].append(f"video canvas 抽帧失败，已回退屏幕截图：{stream_text(cap['stderr']).strip()}")
                    cap = capture(rect, path)
                if cap["returncode"] != 0:
                    report["errors"].append(f"第 {index} 帧截图失败：{stream_text(cap['stderr']).strip()}")
                    continue
                frames.append(path)
                frame_record = {"path": str(path), "target_time_sec": round(seconds, 3), "seek_result": seek_result}
                if not canvas_failed and use_canvas:
                    frame_record["capture"] = "video-canvas-frame"
                    try:
                        frame_record["canvas"] = json.loads(cap.get("stdout") or "{}")
                    except json.JSONDecodeError:
                        pass
                report["frames"].append(frame_record)
            if use_canvas and not canvas_failed and frames:
                report["capture_mode"] = "video-canvas-frame"
                report["capture_rect"] = {
                    "source": "video-canvas-frame",
                    "note": "从当前账户本地 CDP Chrome video 元素直接抽取当前帧像素，未下载原视频",
                }
        else:
            if duration <= 0:
                report["warnings"].append("无法读取视频时长，改用自然播放间隔截图")
            if no_js_fallback:
                report["play_result"] = "skipped-no-js-permission"
            else:
                play_result = play_video()
                report["play_result"] = play_result
            for index in range(1, args.frames + 1):
                time.sleep(args.natural_interval_sec)
                path = out_dir / f"frame-{index:02d}.png"
                cap = capture(rect, path)
                if cap["returncode"] != 0:
                    report["errors"].append(f"第 {index} 帧截图失败：{cap['stderr'].strip()}")
                    continue
                frames.append(path)
                report["frames"].append({"path": str(path), "mode": "natural-playback"})

        if len(frames) < 2:
            report["errors"].append("有效截图少于 2 张，未生成宫格")
            return finish(report, out_dir, tab_session, 1)

        grid_path = out_dir / "reference-grid.jpg"
        grid_result = compress_grid(frames, grid_path, args)
        if grid_result["returncode"] != 0 or not grid_path.exists():
            report["errors"].append(f"ffmpeg 拼接宫格失败：{grid_result['stderr'].strip()}")
            return finish(report, out_dir, tab_session, 1)

        size = grid_path.stat().st_size
        if size > args.target_bytes:
            report["warnings"].append(f"宫格图 {size / 1024:.1f}KB，超过目标 {args.target_bytes / 1024:.1f}KB")

        report.update({
            "grid_path": str(grid_path),
            "grid_size_bytes": size,
            "output_dir": str(out_dir),
        })
        head_face_detection = detect_head_face_info(frames)
        report["head_face_detection"] = head_face_detection
        if not head_face_detection.get("available"):
            report["warnings"].append("头脸信息检测不可用；仅影响确认图 prompt lint 的参考信息")
        validation = validate_capture(frames, grid_path, report, args)
        report["validation"] = validation
        if validation["errors"]:
            report["errors"].extend(validation["errors"])
            report["decision"] = "fail"
            return finish(report, out_dir, tab_session, 1)
        if validation["warnings"]:
            report["warnings"].extend(validation["warnings"])
            report["decision"] = "needs_review"
            return finish(report, out_dir, tab_session, 1)
        report["decision"] = "pass"
        return finish(report, out_dir, tab_session, 0)
    except Exception as exc:
        report["errors"].append(str(exc))
        report["output_dir"] = str(out_dir)
        return finish(report, out_dir, tab_session, 1, stderr=True)


if __name__ == "__main__":
    raise SystemExit(main())
