#!/usr/bin/env python3
"""Build an auditable confirmation image batch manifest."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


QUALITY_STEPS = [5, 7, 9, 12, 15, 18, 22, 26, 31]


def load_entry(value):
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_part(value):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value)


def run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ffprobe_image(path):
    proc = run([
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
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or "ffprobe failed").strip())
    data = json.loads(proc.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise RuntimeError("ffprobe returned no image stream")
    return int(streams[0].get("width") or 0), int(streams[0].get("height") or 0)


def scaled_dimensions(width, height, short_edge):
    if width <= 0 or height <= 0:
        raise RuntimeError("invalid image dimensions")
    if width <= height:
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


def make_proxy(source, out_path, short_edge, target_bytes):
    width, height = ffprobe_image(source)
    out_w, out_h = scaled_dimensions(width, height, short_edge)
    last_error = ""
    for quality in QUALITY_STEPS:
        proc = run([
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            f"scale={out_w}:{out_h}",
            "-frames:v",
            "1",
            "-q:v",
            str(quality),
            str(out_path),
        ])
        if proc.returncode != 0:
            last_error = proc.stderr
            continue
        if out_path.exists() and out_path.stat().st_size <= target_bytes:
            break
    if not out_path.exists():
        raise RuntimeError((last_error or "proxy was not generated").strip())
    return {
        "path": str(out_path),
        "sha256": sha256_file(out_path),
        "bytes": out_path.stat().st_size,
        "width": out_w,
        "height": out_h,
    }


def validate_entries(entries, batch):
    expected = [f"{batch}-{idx:02d}" for idx in range(1, 3)]
    actual = [entry.get("slot") for entry in entries]
    if len(entries) != len(expected):
        raise ValueError(f"每批必须正好 {len(expected)} 个提交位，当前为 {len(entries)}")
    if sorted(actual) != expected:
        raise ValueError(f"提交位必须且只能是 {', '.join(expected)}，当前为 {', '.join(str(x) for x in actual)}")
    seen_submit_ids = set()
    for entry in entries:
        submit_id = entry.get("submit_id")
        if not submit_id:
            raise ValueError(f"{entry.get('slot')} 缺少 submit_id")
        if submit_id in seen_submit_ids:
            raise ValueError(f"重复 submit_id：{submit_id}")
        seen_submit_ids.add(submit_id)
        status = entry.get("status")
        if status not in {"success", "fail"}:
            raise ValueError(f"{entry.get('slot')} status 必须是 success 或 fail")
        if status == "success" and not entry.get("image_path"):
            raise ValueError(f"{entry.get('slot')} 成功提交位缺少 image_path")
        if status == "fail" and entry.get("image_path"):
            raise ValueError(f"{entry.get('slot')} 失败提交位不得提供 image_path")


def write_markdown(manifest, path):
    lines = [
        "# 确认图批次清单",
        "",
        f"- RUN_ID：{manifest['run_id']}",
        f"- 批次：{manifest['batch']}",
        f"- 生成时间：{manifest['generated_at']}",
        "",
        "| 编号 | 状态 | submit_id | 模型 | 原图 | 代理图 | 失败/备注 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in manifest["slots"]:
        lines.append(
            "| {slot} | {status} | {submit_id} | {model} | {image} | {proxy} | {note} |".format(
                slot=item["slot"],
                status=item["status"],
                submit_id=item["submit_id"],
                model=item.get("model_version") or "",
                image=Path(item["image_path"]).name if item.get("image_path") else "",
                proxy=Path(item["proxy_path"]).name if item.get("proxy_path") else "",
                note=item.get("fail_reason") or item.get("screening_note") or "",
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_manifest(args):
    entries = [load_entry(value) for value in args.entry]
    validate_entries(entries, args.batch)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "run_id": args.run_id,
        "stamp": args.stamp,
        "batch": args.batch,
        "topic": args.topic,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "slots": [],
    }

    for entry in sorted(entries, key=lambda item: item["slot"]):
        submit_id = entry["submit_id"]
        submit8 = safe_part(submit_id[:8])
        slot_dir = out_dir / entry["slot"]
        slot_dir.mkdir(parents=True, exist_ok=True)
        item = {
            "slot": entry["slot"],
            "slot_dir": str(slot_dir),
            "submit_id": submit_id,
            "submit_id_short": submit8,
            "status": entry["status"],
            "model_version": entry.get("model_version"),
            "prompt_note": entry.get("prompt_note"),
            "display": False,
        }
        if entry.get("prompt_path"):
            prompt_source = Path(entry["prompt_path"]).expanduser().resolve()
            if not prompt_source.exists():
                raise FileNotFoundError(f"{entry['slot']} prompt_path 不存在：{prompt_source}")
            prompt_dest = slot_dir / f"{entry['slot']}-img-prompt{prompt_source.suffix or '.txt'}"
            if prompt_source != prompt_dest.resolve():
                shutil.copy2(prompt_source, prompt_dest)
            item["prompt_path"] = str(prompt_dest)

        if entry["status"] == "fail":
            item["fail_reason"] = entry.get("fail_reason") or "unknown failure"
            slot_json = slot_dir / "slot.json"
            item["slot_json_path"] = str(slot_json)
            slot_json.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest["slots"].append(item)
            continue

        source = Path(entry["image_path"]).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"{entry['slot']} image_path 不存在：{source}")
        base = f"{args.stamp}-{entry['slot']}-{submit8}-{safe_part(args.topic)}-confirmation"
        image_dest = slot_dir / f"{base}{source.suffix.lower() or '.png'}"
        if source != image_dest.resolve():
            shutil.copy2(source, image_dest)
        proxy_dest = slot_dir / f"{base}-proxy.jpg"
        proxy = make_proxy(image_dest, proxy_dest, args.proxy_short_edge, args.proxy_target_bytes)

        item.update({
            "image_path": str(image_dest),
            "image_sha256": sha256_file(image_dest),
            "image_bytes": image_dest.stat().st_size,
            "proxy_path": proxy["path"],
            "proxy_sha256": proxy["sha256"],
            "proxy_bytes": proxy["bytes"],
            "proxy_width": proxy["width"],
            "proxy_height": proxy["height"],
            "display": not entry.get("screening_failed", False),
            "screening_note": entry.get("screening_note"),
        })
        slot_json = slot_dir / "slot.json"
        item["slot_json_path"] = str(slot_json)
        slot_json.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["slots"].append(item)

    json_path = out_dir / "confirmation-manifest.json"
    md_path = out_dir / "confirmation-manifest.md"
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown(manifest, md_path)
    return manifest, json_path, md_path


def main():
    parser = argparse.ArgumentParser(description="生成确认图批次清单，固定 01/02 两个提交位且失败占位。")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stamp", required=True, help="文件名前缀，如 YYYYMMDD-HHmm")
    parser.add_argument("--batch", required=True, help="批次字母，如 A、B、C")
    parser.add_argument("--topic", required=True, help="参考代号主题，如 ck06170959相思情感")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--entry", action="append", required=True, help="提交位 JSON，必须正好提供 01/02 两个")
    parser.add_argument("--proxy-short-edge", type=int, default=720)
    parser.add_argument("--proxy-target-bytes", type=int, default=200_000)
    args = parser.parse_args()

    try:
        manifest, json_path, md_path = build_manifest(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({
        "manifest_json": str(json_path),
        "manifest_md": str(md_path),
        "total": len(manifest["slots"]),
        "success": sum(1 for item in manifest["slots"] if item["status"] == "success"),
        "fail": sum(1 for item in manifest["slots"] if item["status"] == "fail"),
        "display": [item["slot"] for item in manifest["slots"] if item.get("display")],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
