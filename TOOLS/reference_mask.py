#!/usr/bin/env python3
"""Create a black-box masked reference image for confirmation generation."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import cv2

DEFAULT_EXPAND_X = 2.4
DEFAULT_EXPAND_Y = 3.0
DEFAULT_Y_ANCHOR = 0.45


def parse_rect(value):
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("--rect must use x,y,w,h")
    try:
        x, y, width, height = [int(item) for item in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--rect values must be integers") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("--rect width and height must be greater than 0")
    return {"x": x, "y": y, "width": width, "height": height}


def clamp_rect(rect, image_width, image_height):
    x1 = max(0, rect["x"])
    y1 = max(0, rect["y"])
    x2 = min(image_width, rect["x"] + rect["width"])
    y2 = min(image_height, rect["y"] + rect["height"])
    if x2 <= x1 or y2 <= y1:
        raise ValueError(f"rect outside image bounds: {rect['x']},{rect['y']},{rect['width']},{rect['height']}")
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def vision_box_to_rect(face_box, image_width, image_height):
    x = float(face_box["x"]) * image_width
    y = (1.0 - float(face_box["y"]) - float(face_box["height"])) * image_height
    width = float(face_box["width"]) * image_width
    height = float(face_box["height"]) * image_height
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid Vision face box size: {face_box}")
    return {"x": x, "y": y, "width": width, "height": height}


def expand_face_rect(rect, expand_x=DEFAULT_EXPAND_X, expand_y=DEFAULT_EXPAND_Y, y_anchor=DEFAULT_Y_ANCHOR):
    center_x = rect["x"] + rect["width"] / 2
    center_y = rect["y"] + rect["height"] / 2
    width = rect["width"] * expand_x
    height = rect["height"] * expand_y
    return {
        "x": round(center_x - width / 2),
        "y": round(center_y - height * y_anchor),
        "width": round(width),
        "height": round(height),
    }


def frame_matches_report_item(source, item):
    item_path = Path(str(item.get("path", "")))
    if not item_path:
        return False
    try:
        if item_path.expanduser().resolve() == source:
            return True
    except OSError:
        pass
    return item_path.name == source.name


def rects_from_grid_report(source, image_width, image_height, report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    head_face = report.get("head_face_detection") or {}
    frames = head_face.get("frames") or []
    frame = next((item for item in frames if frame_matches_report_item(source, item)), None)
    if frame is None:
        raise ValueError(f"source frame not found in grid report: {source}")

    face_boxes = frame.get("face_boxes") or []
    if not face_boxes:
        raise ValueError(f"grid report has no face_boxes for source frame: {source}")

    rects = []
    for face_box in face_boxes:
        raw_rect = vision_box_to_rect(face_box, image_width, image_height)
        expanded_rect = expand_face_rect(raw_rect)
        rects.append(
            {
                "input": expanded_rect,
                "source": "grid_report_face_box",
                "face_box": face_box,
                "raw_top_left_rect": {
                    "x": round(raw_rect["x"], 3),
                    "y": round(raw_rect["y"], 3),
                    "width": round(raw_rect["width"], 3),
                    "height": round(raw_rect["height"], 3),
                },
                "expand": {
                    "x": DEFAULT_EXPAND_X,
                    "y": DEFAULT_EXPAND_Y,
                    "y_anchor": DEFAULT_Y_ANCHOR,
                },
            }
        )
    return rects


def mask_image(source, out, rects, mode):
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot read source image: {source}")
    height, width = image.shape[:2]
    applied = []
    for rect in rects:
        input_rect = rect.get("input", rect)
        clamped = clamp_rect(input_rect, width, height)
        x1 = clamped["x"]
        y1 = clamped["y"]
        x2 = x1 + clamped["width"]
        y2 = y1 + clamped["height"]
        image[y1:y2, x1:x2] = (0, 0, 0)
        item = {"input": input_rect, "applied": clamped}
        for key in ("source", "face_box", "raw_top_left_rect", "expand"):
            if key in rect:
                item[key] = rect[key]
        applied.append(item)

    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), image):
        raise ValueError(f"failed to write output image: {out}")
    return {
        "source": str(source),
        "output": str(out),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "width": width,
        "height": height,
        "rect_count": len(applied),
        "rects": applied,
    }


def build_parser():
    parser = argparse.ArgumentParser(description="用纯黑实心块制作强遮挡参考图。")
    parser.add_argument("source", help="参考帧图片路径")
    parser.add_argument("--rect", action="append", type=parse_rect, help="手工遮挡矩形 x,y,w,h；可重复")
    parser.add_argument("--grid-report", default=None, help="reference-grid-report.json；优先从 head_face_detection.face_boxes 自动生成遮挡框")
    parser.add_argument("--out", required=True, help="输出强遮挡参考图，如 TEMP/RUN_ID/reference-masked.png")
    parser.add_argument("--report", default=None, help="输出 JSON 报告；默认与 --out 同名加 -report.json")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    source = Path(args.source).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    report = Path(args.report).expanduser().resolve() if args.report else out.with_name(f"{out.stem}-report.json")
    grid_report = Path(args.grid_report).expanduser().resolve() if args.grid_report else None

    if not source.exists():
        print(json.dumps({"error": f"source image does not exist: {source}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if grid_report and not grid_report.exists():
        print(json.dumps({"error": f"grid report does not exist: {grid_report}"}, ensure_ascii=False), file=sys.stderr)
        return 2
    if not grid_report and not args.rect:
        print(json.dumps({"error": "provide --grid-report for auto masking or at least one --rect"}, ensure_ascii=False), file=sys.stderr)
        return 2

    try:
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"cannot read source image: {source}")
        height, width = image.shape[:2]
        if grid_report:
            rects = rects_from_grid_report(source, width, height, grid_report)
            mode = "auto_from_grid_report"
        else:
            rects = args.rect
            mode = "manual_rect"
        data = mask_image(source, out, rects, mode)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps({"output": str(out), "report": str(report), "rect_count": data["rect_count"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
