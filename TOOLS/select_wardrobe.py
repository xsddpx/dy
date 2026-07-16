#!/usr/bin/env python3
"""Validate and lock one image-wardrobe entry for a dy run."""

from __future__ import annotations

import argparse
import json
import random
import re
import struct
from pathlib import Path
from typing import NamedTuple

from run_record import append_event


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = PROJECT_ROOT / "MATERIAL" / "wardrobe-images"
DEFAULT_TEMP_ROOT = PROJECT_ROOT / "TEMP"
ENTRY_RE = re.compile(r"衣柜图-(\d{3})")
DESCRIPTION_RE = re.compile(
    r"# 衣柜图-(\d{3})\n\n"
    r"- 图片：衣柜图-(\d{3})\.png\n"
    r"- 款式提示词：([^\n]+)\n?\Z"
)


class WardrobeError(RuntimeError):
    pass


class WardrobeEntry(NamedTuple):
    identifier: str
    directory: Path
    image: Path
    description_file: Path
    prompt: str


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise WardrobeError(f"不是有效 PNG：{path}")
    return struct.unpack(">II", header[16:24])


def read_entry(directory: Path) -> WardrobeEntry:
    match = ENTRY_RE.fullmatch(directory.name)
    if not directory.is_dir() or not match:
        raise WardrobeError(f"衣柜条目目录名不合法：{directory}")
    identifier = match.group(1)
    image = directory / f"衣柜图-{identifier}.png"
    description_file = directory / "服装描述.md"
    expected = {image.name, description_file.name}
    actual = {path.name for path in directory.iterdir()}
    if actual != expected:
        raise WardrobeError(f"衣柜条目必须且只能包含商品图和服装描述：{directory}")
    if not image.is_file() or not description_file.is_file():
        raise WardrobeError(f"衣柜条目文件不完整：{directory}")
    width, height = png_dimensions(image)
    if width * 16 != height * 9:
        raise WardrobeError(f"衣柜商品图必须为 9:16：{image} ({width}x{height})")
    text = description_file.read_text(encoding="utf-8")
    description_match = DESCRIPTION_RE.fullmatch(text)
    if not description_match:
        raise WardrobeError(f"服装描述格式不合法：{description_file}")
    title_id, image_id, prompt = description_match.groups()
    if title_id != identifier or image_id != identifier:
        raise WardrobeError(f"衣柜条目编号不一致：{directory}")
    if not prompt.strip():
        raise WardrobeError(f"款式提示词不能为空：{description_file}")
    return WardrobeEntry(
        identifier=identifier,
        directory=directory.resolve(),
        image=image.resolve(),
        description_file=description_file.resolve(),
        prompt=prompt.strip(),
    )


def discover(directory: Path) -> list[WardrobeEntry]:
    if not directory.is_dir():
        raise WardrobeError(f"衣柜目录不存在：{directory}")
    children = sorted(directory.iterdir(), key=lambda path: path.name)
    if not children:
        raise WardrobeError(f"衣柜为空，请先通过模块 05 入库：{directory}")
    entries = [read_entry(path) for path in children]
    identifiers = [entry.identifier for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise WardrobeError("衣柜条目编号重复")
    return entries


def previous_wardrobe_id(temp_root: Path, current_run_id: str | None = None) -> str | None:
    if not temp_root.is_dir():
        return None
    for run_dir in sorted(temp_root.iterdir(), key=lambda path: path.name, reverse=True):
        if not run_dir.is_dir() or run_dir.name == current_run_id:
            continue
        record = run_dir / f"{run_dir.name}-run-record.jsonl"
        if not record.is_file():
            continue
        selected = None
        for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("stage") == "wardrobe" and event.get("event") == "selected":
                value = (event.get("data") or {}).get("wardrobe_id")
                if isinstance(value, str) and re.fullmatch(r"\d{3}", value):
                    selected = value
        if selected:
            return selected
    return None


def select_entry(
    entries: list[WardrobeEntry],
    *,
    wardrobe_id: str | None = None,
    previous_id: str | None = None,
    seed: int | None = None,
) -> WardrobeEntry:
    if wardrobe_id:
        normalized = wardrobe_id.removeprefix("衣柜图-")
        if not re.fullmatch(r"\d{3}", normalized):
            raise WardrobeError(f"衣柜编号必须为三位数字：{wardrobe_id}")
        for entry in entries:
            if entry.identifier == normalized:
                return entry
        raise WardrobeError(f"指定衣柜条目不存在：衣柜图-{normalized}")
    candidates = entries
    if len(entries) > 1 and previous_id:
        candidates = [entry for entry in entries if entry.identifier != previous_id]
    chooser = random.Random(seed) if seed is not None else random.SystemRandom()
    return chooser.choice(candidates)


def lock_entry(run_dir: Path, entry: WardrobeEntry) -> Path:
    if not run_dir.is_dir():
        raise WardrobeError(f"运行目录不存在，请先由模块 04 建档：{run_dir}")
    record = run_dir / f"{run_dir.name}-run-record.jsonl"
    if not record.is_file():
        raise WardrobeError(f"运行记录不存在，请先由模块 04 建档：{record}")
    lock_files = (
        run_dir / "wardrobe-image-path.txt",
        run_dir / "wardrobe-description-path.txt",
        run_dir / "wardrobe-description.txt",
    )
    existing = [path for path in lock_files if path.exists()]
    if existing:
        raise WardrobeError(f"本次运行已经锁定衣柜，不得重新选择：{existing[0]}")
    (run_dir / "wardrobe-image-path.txt").write_text(str(entry.image) + "\n", encoding="utf-8")
    (run_dir / "wardrobe-description-path.txt").write_text(
        str(entry.description_file) + "\n",
        encoding="utf-8",
    )
    (run_dir / "wardrobe-description.txt").write_text(entry.prompt + "\n", encoding="utf-8")
    append_event(
        record,
        stage="wardrobe",
        event="selected",
        status="locked",
        summary=f"已锁定衣柜图-{entry.identifier}",
        data={
            "wardrobe_id": entry.identifier,
            "image_path": str(entry.image),
            "description_path": str(entry.description_file),
        },
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="校验并锁定本次三图视频使用的衣柜条目。")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--temp-root", type=Path, default=DEFAULT_TEMP_ROOT)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--wardrobe-id", help="三位编号或衣柜图-NNN；省略时随机且避免最近一次")
    parser.add_argument("--seed", type=int, help="仅用于离线测试复现")
    args = parser.parse_args()

    try:
        entries = discover(args.directory)
        previous_id = previous_wardrobe_id(args.temp_root, args.run_dir.name)
        selected = select_entry(
            entries,
            wardrobe_id=args.wardrobe_id,
            previous_id=previous_id,
            seed=args.seed,
        )
        lock_entry(args.run_dir, selected)
    except (OSError, UnicodeError, WardrobeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "wardrobe_id": selected.identifier,
        "image_path": str(selected.image),
        "description_path": str(selected.description_file),
        "previous_wardrobe_id": previous_id,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
