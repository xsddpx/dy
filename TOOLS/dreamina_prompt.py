#!/usr/bin/env python3
"""Build Dreamina video prompts for the anna auto workflow."""

import argparse
import re
import sys
from pathlib import Path


FORBIDDEN_TERMS = (
    "附件",
    "节点",
    "模型参数",
    "分辨率",
    "结果数",
    "@图2",
    "@图3",
)


def rewrite_prompt(text, route="anna", channel="auto"):
    if route != "anna":
        raise ValueError("dy 项目只支持 route=anna")
    if channel != "auto":
        raise ValueError("dy 项目只支持 channel=auto")
    rewritten = text.replace("@anna", "@图1")
    rewritten = re.sub(r"本次确认图|选中确认图|确认图", "@图1", rewritten)
    return rewritten


def validate_prompt(text, route="anna", channel="auto"):
    errors = []
    if route != "anna":
        errors.append("dy 项目只支持 route=anna")
    if channel != "auto":
        errors.append("dy 项目只支持 channel=auto")
    if "@图1" not in text:
        errors.append("Dreamina prompt 缺少 @图1（@图1=自动门禁选中的确认图）")
    found = [term for term in FORBIDDEN_TERMS if term in text]
    if found:
        errors.append(f"Dreamina prompt 含不支持或内部流程词：{', '.join(found)}")
    return errors


def main():
    parser = argparse.ArgumentParser(description="将正式 prompt 转写为 dy 项目的 Dreamina @图1 视频 prompt。")
    parser.add_argument("prompt", help="源 prompt 文件")
    parser.add_argument("--route", choices=["anna"], default="anna")
    parser.add_argument("--channel", choices=["auto"], default="auto")
    parser.add_argument("--out", required=True, help="输出 Dreamina prompt 文件")
    args = parser.parse_args()

    source = Path(args.prompt)
    if not source.exists():
        print(f"源 prompt 不存在：{source}", file=sys.stderr)
        return 2

    try:
        rewritten = rewrite_prompt(source.read_text(encoding="utf-8", errors="replace"), args.route, args.channel)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    errors = validate_prompt(rewritten, args.route, args.channel)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rewritten, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
