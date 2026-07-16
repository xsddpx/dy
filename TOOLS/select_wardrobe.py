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
DEFAULT_MIGRATION_FILE = PROJECT_ROOT / "MATERIAL" / "wardrobe-id-migration.json"
SEASONS = ("春季", "夏季", "秋季", "冬季")
SEASON_ORDER = {season: index for index, season in enumerate(SEASONS)}
SEASON_PATTERN = "|".join(SEASONS)
ENTRY_RE = re.compile(rf"衣柜图-({SEASON_PATTERN})-(\d{{3}})")
WARDROBE_ID_RE = re.compile(rf"衣柜图-({SEASON_PATTERN})-(\d{{3}})")
SHORT_ID_RE = re.compile(rf"({SEASON_PATTERN})-(\d{{3}})")
SOURCE_IMAGE_RE = re.compile(r"原始参考图\.(?:png|jpe?g|webp|heic|heif|avif)", re.IGNORECASE)
MIN_IMAGE_WIDTH = 720
MIN_IMAGE_HEIGHT = 1280
DESCRIPTION_RE = re.compile(
    rf"# 衣柜图-({SEASON_PATTERN})-(\d{{3}})\n\n"
    rf"- 图片：衣柜图-({SEASON_PATTERN})-(\d{{3}})\.png\n"
    r"- 款式提示词：([^\n]+)\n?\Z"
)


class WardrobeError(RuntimeError):
    pass


class WardrobeEntry(NamedTuple):
    season: str
    number: str
    directory: Path
    image: Path
    description_file: Path
    prompt: str

    @property
    def identifier(self) -> str:
        return f"{self.season}-{self.number}"

    @property
    def wardrobe_id(self) -> str:
        return f"衣柜图-{self.identifier}"


def png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise WardrobeError(f"不是有效 PNG：{path}")
    return struct.unpack(">II", header[16:24])


def read_entry(directory: Path) -> WardrobeEntry:
    match = ENTRY_RE.fullmatch(directory.name)
    if not directory.is_dir() or not match:
        raise WardrobeError(f"衣柜条目目录名不合法：{directory}")
    season, number = match.groups()
    wardrobe_id = f"衣柜图-{season}-{number}"
    image = directory / f"{wardrobe_id}.png"
    description_file = directory / "服装描述.md"
    required = {image.name, description_file.name}
    actual = {path.name for path in directory.iterdir()}
    if not required.issubset(actual):
        raise WardrobeError(f"衣柜条目文件不完整：{directory}")
    source_names = {name for name in actual if SOURCE_IMAGE_RE.fullmatch(name)}
    if len(source_names) > 1:
        raise WardrobeError(f"衣柜条目最多保留一张原始参考图：{directory}")
    unexpected = actual - required - source_names
    if unexpected:
        raise WardrobeError(f"衣柜条目包含不允许的根目录内容：{directory}")
    if source_names:
        source = directory / next(iter(source_names))
        if not source.is_file() or source.is_symlink():
            raise WardrobeError(f"原始参考图必须是普通文件：{source}")
    if not image.is_file() or not description_file.is_file():
        raise WardrobeError(f"衣柜条目文件不完整：{directory}")
    width, height = png_dimensions(image)
    if width * 16 != height * 9:
        raise WardrobeError(f"衣柜商品图必须为 9:16：{image} ({width}x{height})")
    if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
        raise WardrobeError(
            "衣柜商品图分辨率不得低于 "
            f"{MIN_IMAGE_WIDTH}x{MIN_IMAGE_HEIGHT}：{image} ({width}x{height})"
        )
    text = description_file.read_text(encoding="utf-8")
    description_match = DESCRIPTION_RE.fullmatch(text)
    if not description_match:
        raise WardrobeError(f"服装描述格式不合法：{description_file}")
    title_season, title_number, image_season, image_number, prompt = description_match.groups()
    if (title_season, title_number) != (season, number) or (image_season, image_number) != (
        season,
        number,
    ):
        raise WardrobeError(f"衣柜条目编号不一致：{directory}")
    if not prompt.strip():
        raise WardrobeError(f"款式提示词不能为空：{description_file}")
    return WardrobeEntry(
        season=season,
        number=number,
        directory=directory.resolve(),
        image=image.resolve(),
        description_file=description_file.resolve(),
        prompt=prompt.strip(),
    )


def discover(directory: Path) -> list[WardrobeEntry]:
    if not directory.is_dir():
        raise WardrobeError(f"衣柜目录不存在：{directory}")
    children = list(directory.iterdir())
    if not children:
        raise WardrobeError(f"衣柜为空，请先通过衣柜入库工作流创建条目：{directory}")
    entries = sorted(
        (read_entry(path) for path in children),
        key=lambda entry: (SEASON_ORDER[entry.season], int(entry.number)),
    )
    identifiers = [entry.wardrobe_id for entry in entries]
    if len(identifiers) != len(set(identifiers)):
        raise WardrobeError("衣柜条目编号重复")
    return entries


def load_legacy_id_aliases(path: Path = DEFAULT_MIGRATION_FILE) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WardrobeError(f"衣柜迁移账本无法读取：{path}") from exc
    aliases = payload.get("aliases")
    if not isinstance(aliases, dict):
        raise WardrobeError(f"衣柜迁移账本缺少 aliases：{path}")
    result: dict[str, str] = {}
    for legacy_id, wardrobe_id in aliases.items():
        if not isinstance(legacy_id, str) or not isinstance(wardrobe_id, str):
            raise WardrobeError(f"衣柜迁移账本 aliases 格式不合法：{path}")
        if not WARDROBE_ID_RE.fullmatch(wardrobe_id):
            raise WardrobeError(f"衣柜迁移账本目标编号不合法：{wardrobe_id}")
        result[legacy_id] = wardrobe_id
    return result


def canonical_record_id(value: str, aliases: dict[str, str]) -> str | None:
    if WARDROBE_ID_RE.fullmatch(value):
        return value
    short_match = SHORT_ID_RE.fullmatch(value)
    if short_match:
        return f"衣柜图-{value}"
    return aliases.get(value) or aliases.get(value.removeprefix("衣柜图-"))


def previous_wardrobe_id(
    temp_root: Path,
    current_run_id: str | None = None,
    migration_file: Path = DEFAULT_MIGRATION_FILE,
) -> str | None:
    if not temp_root.is_dir():
        return None
    aliases = load_legacy_id_aliases(migration_file)
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
                if isinstance(value, str):
                    canonical = canonical_record_id(value, aliases)
                    if canonical:
                        selected = canonical
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
        match = WARDROBE_ID_RE.fullmatch(wardrobe_id)
        if not match:
            short_match = SHORT_ID_RE.fullmatch(wardrobe_id)
            if short_match:
                wardrobe_id = f"衣柜图-{wardrobe_id}"
            else:
                raise WardrobeError(f"衣柜编号必须为衣柜图-季节-NNN：{wardrobe_id}")
        for entry in entries:
            if entry.wardrobe_id == wardrobe_id:
                return entry
        raise WardrobeError(f"指定衣柜条目不存在：{wardrobe_id}")
    candidates = entries
    if len(entries) > 1 and previous_id:
        candidates = [entry for entry in entries if entry.wardrobe_id != previous_id]
    chooser = random.Random(seed) if seed is not None else random.SystemRandom()
    return chooser.choice(candidates)


def lock_entry(run_dir: Path, entry: WardrobeEntry) -> Path:
    if not run_dir.is_dir():
        raise WardrobeError(f"运行目录不存在，请先执行阶段 01 建档：{run_dir}")
    record = run_dir / f"{run_dir.name}-run-record.jsonl"
    if not record.is_file():
        raise WardrobeError(f"运行记录不存在，请先执行阶段 01 建档：{record}")
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
        summary=f"已锁定{entry.wardrobe_id}",
        data={
            "wardrobe_id": entry.wardrobe_id,
            "wardrobe_season": entry.season,
            "wardrobe_number": entry.number,
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
    parser.add_argument(
        "--wardrobe-id",
        help="完整编号衣柜图-季节-NNN（可省略衣柜图-前缀）；省略时随机且避免最近一次",
    )
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
        "wardrobe_id": selected.wardrobe_id,
        "wardrobe_season": selected.season,
        "wardrobe_number": selected.number,
        "image_path": str(selected.image),
        "description_path": str(selected.description_file),
        "previous_wardrobe_id": previous_id,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
