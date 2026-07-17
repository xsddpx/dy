#!/usr/bin/env python3
"""Check whether a Douyin reference is permanently blocked."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


VIDEO_ID_PARAMS = {
    "aweme_id",
    "item_id",
    "item_ids",
    "modal_id",
    "video_id",
    "vid",
}
TRACKING_PARAMS = {
    "enter_from",
    "from",
    "previous_page",
    "recommend",
    "share_app_id",
    "share_iid",
    "share_link_id",
    "timestamp",
    "u_code",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def safe_load_blocklist(path):
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"blocklist json is invalid: {path}") from exc

    if isinstance(data, list):
        return {"version": 1, "entries": data}
    if not isinstance(data, dict):
        raise ValueError(f"blocklist root must be object or list: {path}")
    entries = data.get("entries")
    if entries is None:
        data["entries"] = []
    elif not isinstance(entries, list):
        raise ValueError(f"blocklist entries must be a list: {path}")
    return data


def first_digits(value):
    match = re.search(r"\d{6,}", value or "")
    return match.group(0) if match else None


def canonicalize(reference):
    raw = reference.strip()
    path_id = None

    if re.fullmatch(r"\d{6,}", raw):
        return {
            "input": raw,
            "video_id": raw,
            "canonical_url": f"douyin:video:{raw}",
            "match_key": f"id:{raw}",
        }

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path_match = re.search(r"/(?:video|note)/(\d{6,})(?:/|$)", parsed.path)
        if path_match:
            path_id = path_match.group(1)

        query = parse_qsl(parsed.query, keep_blank_values=True)
        query_id = None
        for key, value in query:
            if key in VIDEO_ID_PARAMS:
                query_id = first_digits(value)
                if query_id:
                    break

        video_id = path_id or query_id
        if video_id:
            return {
                "input": raw,
                "video_id": video_id,
                "canonical_url": f"https://www.douyin.com/video/{video_id}",
                "match_key": f"id:{video_id}",
            }

        filtered_query = [
            (key, value)
            for key, value in query
            if key not in TRACKING_PARAMS
        ]
        canonical_query = urlencode(sorted(filtered_query))
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/") or "/"
        canonical_url = urlunparse((
            parsed.scheme.lower(),
            netloc,
            path,
            "",
            canonical_query,
            "",
        ))
        return {
            "input": raw,
            "video_id": None,
            "canonical_url": canonical_url,
            "match_key": f"url:{canonical_url}",
        }

    return {
        "input": raw,
        "video_id": None,
        "canonical_url": raw,
        "match_key": f"url:{raw}",
    }


def entry_key(entry):
    video_id = entry.get("video_id")
    if video_id:
        return f"id:{video_id}"
    canonical_url = entry.get("canonical_url") or entry.get("url") or entry.get("reference")
    return f"url:{canonical_url}" if canonical_url else None


def find_blocked(blocklist, canonical):
    for entry in blocklist.get("entries", []):
        if entry.get("enabled") is False:
            continue
        if entry_key(entry) == canonical["match_key"]:
            return {
                "route": entry.get("route"),
                "status": entry.get("status") or "blocked",
                "reason": entry.get("reason"),
                "title": entry.get("title"),
                "author": entry.get("author"),
                "canonical_url": entry.get("canonical_url"),
                "video_id": entry.get("video_id"),
                "recorded_at": entry.get("recorded_at"),
            }
    return None


def handle_check(args):
    canonical = canonicalize(args.reference)
    blocklist = safe_load_blocklist(args.blocklist)
    blocked = find_blocked(blocklist, canonical)
    result = {
        "blocked": bool(blocked),
        "blocklist": str(args.blocklist),
        "reference": canonical,
        "blocked_entry": blocked,
        "decision": "skip_autonomous" if blocked else "use",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if blocked else 0


def build_parser():
    root = Path.cwd()
    default_blocklist = root / "MATERIAL/reference-blocklist.json"

    parser = argparse.ArgumentParser(description="检查参考视频是否命中永久禁用账本。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="检查参考视频是否永久禁用")
    check.add_argument("reference", help="抖音视频 URL、视频 ID，或其他可规范化 URL")
    check.add_argument("--blocklist", type=Path, default=default_blocklist, help="永久禁用参考账本路径")
    check.set_defaults(func=handle_check)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, argparse.ArgumentTypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
