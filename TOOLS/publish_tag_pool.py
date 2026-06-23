#!/usr/bin/env python3
"""Sample publish tags from the dy hot tag pool."""

import argparse
import json
import random
from pathlib import Path


def load_pool(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def clean_tags(tags: list[str], blocked: set[str]) -> list[str]:
    result = []
    seen = set()
    for tag in tags:
        value = str(tag).strip().lstrip("#")
        if not value or value in blocked or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def sample_tags(pool: dict, count: int, scene: str | None = None) -> list[str]:
    blocked = set(pool.get("blocked_tags") or [])
    tags = clean_tags(pool.get("tags") or [], blocked)
    scene_tags = []
    if scene:
        scene_tags = clean_tags((pool.get("scene_tags") or {}).get(scene) or [], blocked)

    selected = []
    for tag in scene_tags:
        if tag not in selected:
            selected.append(tag)

    available = [tag for tag in tags if tag not in selected]
    random.SystemRandom().shuffle(available)
    selected.extend(available[: max(0, count - len(selected))])
    return selected[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description="从发布热门 tag 池随机抽取话题。")
    parser.add_argument("--pool", default="MATERIAL/publish-tag-pool.json")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--scene", default=None, help="可选：优先包含 scene_tags 中的场景标签")
    parser.add_argument("--shell-args", action="store_true", help="输出为 douyin_publish_helper.py 可直接拼接的 --tag 参数")
    args = parser.parse_args()

    pool = load_pool(Path(args.pool))
    count = args.count or int(pool.get("default_count") or 4)
    tags = sample_tags(pool, count, args.scene)

    if args.shell_args:
        print(" ".join(f"--tag {json.dumps(tag, ensure_ascii=False)}" for tag in tags))
    else:
        print("\n".join(tags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
