#!/usr/bin/env python3
"""Track Douyin reference videos and detect exact reuse."""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
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


def utc_now():
    return datetime.now(timezone.utc)


def parse_time(value, default=None):
    if not value:
        return default
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid datetime: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def safe_load_history(path):
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"history json is invalid: {path}") from exc

    if isinstance(data, list):
        return {"version": 1, "entries": data}
    if not isinstance(data, dict):
        raise ValueError(f"history root must be object or list: {path}")
    entries = data.get("entries")
    if entries is None:
        data["entries"] = []
    elif not isinstance(entries, list):
        raise ValueError(f"history entries must be a list: {path}")
    return data


def write_history(path, history):
    path.parent.mkdir(parents=True, exist_ok=True)
    history["version"] = 1
    history["updated_at"] = utc_now().isoformat()
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def entry_time(entry):
    for key in ("recorded_at", "date", "created_at"):
        value = entry.get(key)
        if value:
            try:
                return parse_time(value)
            except argparse.ArgumentTypeError:
                return None
    return None


def find_duplicate(history, canonical, now, window_days):
    cutoff = now - timedelta(days=window_days)
    matches = []
    for entry in history.get("entries", []):
        recorded_at = entry_time(entry)
        if not recorded_at or recorded_at < cutoff or recorded_at > now + timedelta(minutes=5):
            continue
        if entry_key(entry) == canonical["match_key"]:
            matches.append({
                "recorded_at": recorded_at.isoformat(),
                "route": entry.get("route"),
                "status": entry.get("status"),
                "title": entry.get("title"),
                "author": entry.get("author"),
                "canonical_url": entry.get("canonical_url"),
                "video_id": entry.get("video_id"),
            })
    matches.sort(key=lambda item: item["recorded_at"], reverse=True)
    return matches[0] if matches else None


def prune_entries(history, now, retention_days):
    cutoff = now - timedelta(days=retention_days)
    kept = []
    for entry in history.get("entries", []):
        recorded_at = entry_time(entry)
        if recorded_at is None or recorded_at >= cutoff:
            kept.append(entry)
    history["entries"] = kept


def handle_check(args):
    now = parse_time(args.now, utc_now())
    canonical = canonicalize(args.reference)
    history = safe_load_history(args.history)
    duplicate = find_duplicate(history, canonical, now, args.window_days)
    result = {
        "duplicate": bool(duplicate),
        "window_days": args.window_days,
        "history": str(args.history),
        "reference": canonical,
        "matched_entry": duplicate,
        "decision": "skip_autonomous" if duplicate else "use",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if duplicate else 0


def handle_record(args):
    now = parse_time(args.now, utc_now())
    canonical = canonicalize(args.reference)

    history = safe_load_history(args.history)
    prune_entries(history, now, args.retention_days)

    entry = {
        "recorded_at": now.isoformat(),
        "route": args.route,
        "status": args.status,
        "video_id": canonical["video_id"],
        "canonical_url": canonical["canonical_url"],
        "source": args.reference,
    }
    if args.title:
        entry["title"] = args.title
    if args.author:
        entry["author"] = args.author

    history.setdefault("entries", []).append(entry)
    write_history(args.history, history)
    print(json.dumps({
        "recorded": True,
        "history": str(args.history),
        "entry": entry,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser():
    root = Path.cwd()
    default_history = root / "MATERIAL/reference-history.json"

    parser = argparse.ArgumentParser(description="检查并记录 7 天内参考视频精确复用。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="检查参考视频是否在时间窗内用过")
    check.add_argument("reference", help="抖音视频 URL、视频 ID，或其他可规范化 URL")
    check.add_argument("--history", type=Path, default=default_history, help="历史账本路径")
    check.add_argument("--window-days", type=float, default=7.0, help="去重时间窗，默认 7 天")
    check.add_argument("--now", default=None, help=argparse.SUPPRESS)
    check.set_defaults(func=handle_check)

    record = subparsers.add_parser("record", help="记录本次进入流程的参考视频")
    record.add_argument("reference", help="抖音视频 URL、视频 ID，或其他可规范化 URL")
    record.add_argument("--route", required=True, choices=["anna"], help="路线；dy 项目只支持 anna")
    record.add_argument("--status", default="used", help="参考状态，例如 used、blocked、abandoned")
    record.add_argument("--title", default=None, help="可选标题")
    record.add_argument("--author", default=None, help="可选作者")
    record.add_argument("--history", type=Path, default=default_history, help="历史账本路径")
    record.add_argument("--retention-days", type=float, default=30.0, help="账本保留天数，默认 30 天")
    record.add_argument("--now", default=None, help=argparse.SUPPRESS)
    record.set_defaults(func=handle_record)

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
