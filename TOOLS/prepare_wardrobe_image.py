#!/usr/bin/env python3
"""Prepare a generated wardrobe PNG with a minimal, no-upscale 9:16 crop."""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


DEFAULT_MAX_CROP_FRACTION = 0.02
MIN_OUTPUT_WIDTH = 720
MIN_OUTPUT_HEIGHT = 1280


class PrepareWardrobeImageError(RuntimeError):
    pass


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise PrepareWardrobeImageError(f"不是有效 PNG：{path}")
    return struct.unpack(">II", header[16:24])


def compute_crop(
    width: int,
    height: int,
    *,
    max_crop_fraction: float = DEFAULT_MAX_CROP_FRACTION,
) -> tuple[int, int, int, int]:
    if width <= 0 or height <= 0:
        raise PrepareWardrobeImageError(f"图片尺寸不合法：{width}x{height}")
    if not 0 <= max_crop_fraction <= DEFAULT_MAX_CROP_FRACTION:
        raise PrepareWardrobeImageError(
            "最大裁剪比例必须在 "
            f"0 到 {DEFAULT_MAX_CROP_FRACTION} 之间：{max_crop_fraction}"
        )
    unit = min(width // 9, height // 16)
    target_width = unit * 9
    target_height = unit * 16
    if target_width < MIN_OUTPUT_WIDTH or target_height < MIN_OUTPUT_HEIGHT:
        raise PrepareWardrobeImageError(
            f"原图不足以保留至少 {MIN_OUTPUT_WIDTH}x{MIN_OUTPUT_HEIGHT}：{width}x{height}"
        )
    width_fraction = (width - target_width) / width
    height_fraction = (height - target_height) / height
    if max(width_fraction, height_fraction) > max_crop_fraction:
        raise PrepareWardrobeImageError(
            "原图比例偏离 9:16，最小裁剪仍会丢失过多画面："
            f"{width}x{height} -> {target_width}x{target_height}"
        )
    x = (width - target_width) // 2
    y = (height - target_height) // 2
    return target_width, target_height, x, y


def prepare_image(
    source: Path,
    output: Path,
    *,
    max_crop_fraction: float = DEFAULT_MAX_CROP_FRACTION,
    overwrite: bool = False,
) -> tuple[int, int]:
    if not source.is_file():
        raise PrepareWardrobeImageError(f"输入图片不存在：{source}")
    if output.exists() and not overwrite:
        raise PrepareWardrobeImageError(f"输出已存在：{output}")
    width, height = png_dimensions(source)
    target_width, target_height, x, y = compute_crop(
        width,
        height,
        max_crop_fraction=max_crop_fraction,
    )
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise PrepareWardrobeImageError("找不到 ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output.stem}-",
        suffix=".png",
        dir=output.parent,
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
    try:
        command = [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            f"crop={target_width}:{target_height}:{x}:{y}",
            "-frames:v",
            "1",
            "-c:v",
            "png",
            str(temporary),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise PrepareWardrobeImageError(
                f"ffmpeg 裁剪失败：{completed.stderr.strip() or completed.stdout.strip()}"
            )
        if png_dimensions(temporary) != (target_width, target_height):
            raise PrepareWardrobeImageError(f"裁剪结果尺寸不一致：{temporary}")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return target_width, target_height


def main() -> int:
    parser = argparse.ArgumentParser(description="将衣柜候选 PNG 无放大微裁剪为严格 9:16。")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--max-crop-fraction",
        type=float,
        default=DEFAULT_MAX_CROP_FRACTION,
        help="任一边允许裁掉的最大比例，默认 0.02",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        width, height = prepare_image(
            args.input,
            args.output,
            max_crop_fraction=args.max_crop_fraction,
            overwrite=args.overwrite,
        )
    except (OSError, PrepareWardrobeImageError) as exc:
        parser.error(str(exc))
    print(f"{args.output.resolve()} {width}x{height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
