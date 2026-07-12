#!/usr/bin/env python3
"""Randomly select one numbered fixed environment for a single run."""

from __future__ import annotations

import argparse
import random
import re
from pathlib import Path


FILE_PATTERN = re.compile(r"anna-room-\d{2,}\.png")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = PROJECT_ROOT / "MATERIAL" / "fixed-environment"


def discover(directory: Path) -> list[Path]:
    return sorted(
        path.resolve()
        for path in directory.iterdir()
        if path.is_file() and FILE_PATTERN.fullmatch(path.name)
    )


def select_environment(directory: Path, seed: int | None = None) -> Path:
    candidates = discover(directory)
    if not candidates:
        raise SystemExit(f"no numbered fixed environments found in {directory}")
    chooser = random.Random(seed) if seed is not None else random.SystemRandom()
    return chooser.choice(candidates)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--seed", type=int)
    args = parser.parse_args()

    selected = select_environment(args.directory, args.seed)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(str(selected) + "\n", encoding="utf-8")
    print(selected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
