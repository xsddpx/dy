#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
SKILLS_HOME="$CODEX_HOME_DIR/skills"

mkdir -p "$SKILLS_HOME"

for skill in xdy xdysp; do
  source_path="$ROOT_DIR/SKILLS/$skill"
  target_path="$SKILLS_HOME/$skill"

  if [[ ! -f "$source_path/SKILL.md" ]]; then
    print -u2 "项目技能不存在：$source_path"
    exit 2
  fi

  if [[ -L "$target_path" ]]; then
    current_target="$(cd "$(dirname "$target_path")" && cd "$(dirname "$(readlink "$target_path")")" 2>/dev/null && pwd)/$(basename "$(readlink "$target_path")")"
    if [[ "$current_target" == "$source_path" ]]; then
      print "已链接：$target_path -> $source_path"
      continue
    fi
    print -u2 "技能链接指向其他位置，停止覆盖：$target_path -> $(readlink "$target_path")"
    exit 3
  fi

  if [[ -e "$target_path" ]]; then
    print -u2 "目标已存在且不是软链接，停止覆盖：$target_path"
    print -u2 "确认仓库技能已提交后，请先手动移走旧目录再重新运行。"
    exit 4
  fi

  ln -s "$source_path" "$target_path"
  print "已链接：$target_path -> $source_path"
done
