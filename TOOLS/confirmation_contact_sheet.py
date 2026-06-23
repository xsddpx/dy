#!/usr/bin/env python3
"""Build a labeled contact sheet for confirmation images."""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_path(value, base_dir):
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    base_path = base_dir / path
    if base_path.exists():
        return base_path
    return cwd_path


def score_map(report):
    scores = {}
    for item in report.get("slots", []):
        slot = item.get("slot")
        if not slot:
            continue
        scores[slot] = {
            "similarity": item.get("face_similarity_min_percent"),
            "face_skipped": item.get("face_gate_skipped"),
            "eligible": item.get("auto_select_eligible"),
            "reason": item.get("auto_select_reason"),
        }
    return scores


def fit_image(image, width, height):
    h, w = image.shape[:2]
    scale = min(width / w, height / h)
    resized = cv2.resize(image, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((height, width, 3), 245, dtype=np.uint8)
    y = (height - resized.shape[0]) // 2
    x = (width - resized.shape[1]) // 2
    canvas[y:y + resized.shape[0], x:x + resized.shape[1]] = resized
    return canvas


def draw_multiline(image, lines, origin, scale=0.55, color=(25, 25, 25), line_height=24, thickness=1):
    x, y = origin
    for idx, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (x, y + idx * line_height),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )


def compress_jpeg(image, out_path, target_bytes):
    last_quality = 34
    for quality in [88, 82, 76, 70, 64, 58, 52, 46, 40, 34]:
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            raise RuntimeError("JPEG encode failed")
        out_path.write_bytes(encoded.tobytes())
        last_quality = quality
        if out_path.stat().st_size <= target_bytes:
            break
    return last_quality


def build_sheet(args):
    manifest_path = Path(args.manifest).resolve()
    manifest = load_json(manifest_path)
    report = load_json(args.face_report) if args.face_report else {}
    scores = score_map(report)
    selected_slot = report.get("selected_slot")

    slots = manifest.get("slots", [])
    if not slots:
        raise ValueError("contact sheet expects at least one slot")

    thumb_w, thumb_h = args.thumb_width, args.thumb_height
    label_h = args.label_height
    margin = args.margin
    header_h = 58
    cols = 3
    rows = math.ceil(len(slots) / cols)
    sheet_w = cols * thumb_w + (cols + 1) * margin
    sheet_h = header_h + rows * (thumb_h + label_h) + (rows + 1) * margin
    sheet = np.full((sheet_h, sheet_w, 3), 238, dtype=np.uint8)

    title = f"{manifest.get('batch', '')} confirmation contact sheet"
    subtitle = f"selected: {selected_slot or '-'} | confirmation similarity gate: {report.get('decision', '-')}"
    draw_multiline(sheet, [title, subtitle], (margin, 24), scale=0.62, line_height=25, thickness=2)

    entries = []
    for index, item in enumerate(sorted(slots, key=lambda x: x.get("slot", ""))):
        row = index // cols
        col = index % cols
        x = margin + col * (thumb_w + margin)
        y = header_h + margin + row * (thumb_h + label_h + margin)
        slot = item.get("slot", f"slot-{index + 1}")
        status = item.get("status", "")
        selected = slot == selected_slot
        score = scores.get(slot, {})
        similarity = score.get("similarity")
        if score.get("face_skipped"):
            similarity_text = "face skip"
        else:
            similarity_text = "face --" if similarity is None else f"face {similarity:.2f}%"
        if item.get("display") and item.get("proxy_path"):
            image_path = resolve_path(item["proxy_path"], manifest_path.parent)
            image = cv2.imread(str(image_path))
            if image is None:
                tile = np.full((thumb_h, thumb_w, 3), 225, dtype=np.uint8)
                draw_multiline(tile, ["IMAGE LOAD FAIL", slot], (22, thumb_h // 2), scale=0.65, color=(0, 0, 180), thickness=2)
            else:
                tile = fit_image(image, thumb_w, thumb_h)
        else:
            tile = np.full((thumb_h, thumb_w, 3), 224, dtype=np.uint8)
            reason = item.get("fail_reason") or item.get("screening_note") or "not displayed"
            draw_multiline(tile, ["FAILED", reason[:26]], (22, thumb_h // 2), scale=0.55, color=(45, 45, 45), thickness=1)

        border_color = (60, 170, 60) if selected else (185, 185, 185)
        sheet[y:y + thumb_h, x:x + thumb_w] = tile
        cv2.rectangle(sheet, (x, y), (x + thumb_w - 1, y + thumb_h - 1), border_color, 4 if selected else 2)
        label_y = y + thumb_h + 23
        label_lines = [
            f"{slot} | {status} | {similarity_text}",
            f"{'AUTO SELECTED' if selected else item.get('prompt_note') or ''}"[:42],
        ]
        draw_multiline(sheet, label_lines, (x + 8, label_y), scale=0.52, line_height=23, thickness=1)
        entries.append({
            "slot": slot,
            "status": status,
            "similarity_percent": similarity,
            "face_gate_skipped": score.get("face_skipped"),
            "selected": selected,
            "proxy_path": item.get("proxy_path"),
            "fail_reason": item.get("fail_reason"),
        })

    out_path = Path(args.out or (manifest_path.parent / "confirmation-contact-sheet.jpg"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    quality = compress_jpeg(sheet, out_path, args.target_bytes)

    summary_path = out_path.with_suffix(".json")
    summary = {
        "contact_sheet": str(out_path),
        "bytes": out_path.stat().st_size,
        "jpeg_quality": quality,
        "selected_slot": selected_slot,
        "entries": entries,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="生成带编号和相似度的确认图接触表。")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--face-report", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--thumb-width", type=int, default=300)
    parser.add_argument("--thumb-height", type=int, default=534)
    parser.add_argument("--label-height", type=int, default=82)
    parser.add_argument("--margin", type=int, default=16)
    parser.add_argument("--target-bytes", type=int, default=250_000)
    args = parser.parse_args()
    print(json.dumps(build_sheet(args), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
