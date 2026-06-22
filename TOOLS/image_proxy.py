#!/usr/bin/env python3
"""Create lightweight image proxies for visual checks without opening originals."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


QUALITY_STEPS = [5, 7, 9, 12, 15, 18, 22, 26, 31]


def run(cmd):
    started = time.time()
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "elapsed_sec": round(time.time() - started, 3),
    }


def ffprobe_image(path):
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
        return result, None
    try:
        parsed = json.loads(result["stdout"])
    except json.JSONDecodeError:
        return result, None
    streams = parsed.get("streams") or []
    if not streams:
        return result, None
    stream = streams[0]
    return result, {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
    }


def safe_name(path):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in path.stem)


def scaled_dimensions(width, height, short_edge, allow_upscale):
    if width <= 0 or height <= 0:
        return None
    current_short = min(width, height)
    if current_short <= short_edge and not allow_upscale:
        out_w, out_h = width, height
    elif width <= height:
        out_w = short_edge
        out_h = round(height * (short_edge / width))
    else:
        out_h = short_edge
        out_w = round(width * (short_edge / height))
    if out_w % 2:
        out_w += 1
    if out_h % 2:
        out_h += 1
    return out_w, out_h


def make_proxy(source, out_path, width, height, quality):
    vf = f"scale={width}:{height}"
    return run([
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vf",
        vf,
        "-frames:v",
        "1",
        "-q:v",
        str(quality),
        str(out_path),
    ])


def create_proxy(source, out_dir, args):
    probe_result, meta = ffprobe_image(source)
    item = {
        "source": str(source),
        "probe_returncode": probe_result["returncode"],
        "source_meta": meta,
        "proxy": None,
        "proxy_size": None,
        "quality": None,
        "warnings": [],
        "errors": [],
    }
    if not meta or not meta.get("width") or not meta.get("height"):
        item["errors"].append("无法读取图片宽高")
        return item

    dims = scaled_dimensions(meta["width"], meta["height"], args.short_edge, args.allow_upscale)
    if not dims:
        item["errors"].append("无法计算代理图尺寸")
        return item

    out_path = out_dir / f"{safe_name(source)}-{args.suffix}.jpg"
    last_result = None
    for quality in QUALITY_STEPS:
        last_result = make_proxy(source, out_path, dims[0], dims[1], quality)
        if last_result["returncode"] != 0 or not out_path.exists():
            continue
        size = out_path.stat().st_size
        item.update({
            "proxy": str(out_path),
            "proxy_size": size,
            "quality": quality,
            "proxy_meta": {"width": dims[0], "height": dims[1]},
        })
        if size <= args.target_bytes:
            break

    if last_result and last_result["returncode"] != 0:
        item["errors"].append((last_result["stderr"] or "ffmpeg 生成代理图失败").strip())
    if not out_path.exists():
        item["errors"].append("代理图未生成")
    elif out_path.stat().st_size > args.target_bytes:
        item["warnings"].append(
            f"代理图 {out_path.stat().st_size / 1024:.1f}KB，超过目标 {args.target_bytes / 1024:.1f}KB"
        )
    return item


def write_reports(results, out_dir):
    report_json = out_dir / "image-proxy-report.json"
    report_md = out_dir / "image-proxy-report.md"
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 图片代理图报告",
        "",
        "| 结果 | 原图 | 代理图 | 代理尺寸 | KB | 问题 |",
        "|---|---|---|---:|---:|---|",
    ]
    for item in results:
        status = "fail" if item["errors"] else "pass"
        proxy_meta = item.get("proxy_meta") or {}
        size = "" if item.get("proxy_size") is None else f"{item['proxy_size'] / 1024:.1f}"
        issues = "; ".join(item["errors"] + item["warnings"]) or "无"
        lines.append(
            f"| {status} | {Path(item['source']).name} | {Path(item['proxy']).name if item.get('proxy') else ''} | "
            f"{proxy_meta.get('width', '')}x{proxy_meta.get('height', '')} | {size} | {issues} |"
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_json, report_md


def main():
    parser = argparse.ArgumentParser(description="为图片生成轻量代理图，避免主会话打开高清原图。")
    parser.add_argument("images", nargs="+", help="待生成代理图的图片")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 TEMP/image-proxies/YYYYMMDD-HHMMSS")
    parser.add_argument("--short-edge", type=int, default=720, help="代理图短边尺寸，默认 720")
    parser.add_argument("--target-bytes", type=int, default=250_000, help="代理图目标体积，默认 250KB")
    parser.add_argument("--suffix", default="proxy", help="输出文件名后缀")
    parser.add_argument("--allow-upscale", action="store_true", help="允许放大小图到目标短边")
    parser.add_argument("--no-report", action="store_true", help="只生成代理图，不写报告文件")
    args = parser.parse_args()

    root = Path.cwd()
    out_dir = Path(args.out_dir) if args.out_dir else root / "TEMP/image-proxies" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    images = [Path(value).expanduser().resolve() for value in args.images]
    missing = [str(path) for path in images if not path.exists()]
    if missing:
        print(json.dumps({"error": "图片不存在", "missing": missing}, ensure_ascii=False), file=sys.stderr)
        return 2

    results = [create_proxy(image, out_dir, args) for image in images]
    report_json = report_md = None
    if not args.no_report:
        report_json, report_md = write_reports(results, out_dir)
    print(json.dumps({
        "output_dir": str(out_dir),
        "report_json": str(report_json) if report_json else None,
        "report_md": str(report_md) if report_md else None,
        "total": len(results),
        "pass": sum(1 for item in results if not item["errors"]),
        "fail": sum(1 for item in results if item["errors"]),
        "proxies": [item.get("proxy") for item in results if item.get("proxy")],
    }, ensure_ascii=False, indent=2))
    return 1 if any(item["errors"] for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
