#!/usr/bin/env python3
"""Append compact per-run records for the Douyin workflow."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d{2})?$")
SCHEMA_VERSION = 2

EVENT_RULES: dict[tuple[str, str], set[str]] = {
    ("run", "started"): {"in_progress"},
    ("content", "locked"): {"ready"},
    ("content", "prompt_version"): {"ready"},
    ("dreamina", "submitted"): {"querying"},
    ("dreamina", "succeeded"): {"success"},
    ("dreamina", "tns"): {"blocked"},
    ("dreamina", "failed"): {"failed"},
    ("dreamina", "environment_error"): {"blocked"},
    ("quality", "prepared"): {"pending"},
    ("quality", "reviewed"): {"pass", "blocked", "not_performed"},
    ("output", "created"): {"ready"},
    ("google_drive", "uploaded"): {"uploaded"},
    ("google_drive", "failed"): {"failed"},
    ("google_drive", "not_attempted"): {"not_attempted"},
    ("publish", "awaiting_confirmation"): {"awaiting_confirmation"},
    ("publish", "authorized"): {"in_progress"},
    ("publish", "not_requested"): {"not_requested"},
    ("publish", "platform_result"): {"published", "blocked", "failed"},
    ("publish", "both_publish"): {"published", "blocked"},
    ("run", "completed"): {"success", "failed", "cancelled"},
}


def now_iso() -> str:
    return datetime.now(SHANGHAI).isoformat(timespec="seconds")


class RecordError(ValueError):
    """Raised when a schema-v2 event is invalid or out of order."""


def is_v2_event(event: dict[str, Any]) -> bool:
    return event.get("schema_version") == SCHEMA_VERSION


def is_artifact(event: dict[str, Any]) -> bool:
    return event.get("event") == "artifact"


def latest_non_artifact(events: list[dict[str, Any]], stage: str, event: str | None = None) -> dict[str, Any] | None:
    for item in reversed(events):
        if item.get("stage") != stage or is_artifact(item):
            continue
        if event is None or item.get("event") == event:
            return item
    return None


def _event_exists(events: list[dict[str, Any]], stage: str, event: str, status: str | None = None) -> bool:
    return any(
        item.get("stage") == stage
        and item.get("event") == event
        and (status is None or item.get("status") == status)
        for item in events
        if not is_artifact(item)
    )


def validate_v2_transition(
    events: list[dict[str, Any]],
    *,
    run_id: str,
    stage: str,
    event: str,
    status: str,
    data: dict[str, Any],
) -> None:
    if not RUN_ID_RE.fullmatch(run_id):
        raise RecordError(f"RUN_ID 格式不合法：{run_id}")
    allowed = EVENT_RULES.get((stage, event))
    if allowed is None or status not in allowed:
        raise RecordError(f"未知 schema-v2 事件或状态：{stage}/{event}={status}")
    if events and not any(is_v2_event(item) for item in events):
        raise RecordError("旧运行记录只读，不能追加 schema-v2 事件")
    if any(is_v2_event(item) and item.get("run_id") != run_id for item in events):
        raise RecordError("运行记录包含其他 RUN_ID 的 schema-v2 事件")
    if _event_exists(events, "run", "completed"):
        raise RecordError("运行已经完成，不能继续追加状态事件")
    if not events:
        if (stage, event) != ("run", "started"):
            raise RecordError("schema-v2 首条事件必须是 run/started")
        return
    if not _event_exists(events, "run", "started"):
        raise RecordError("运行记录缺少 run/started")
    if (stage, event) == ("run", "started"):
        raise RecordError("run/started 只能写入一次")
    if stage == "content" and not _event_exists(events, "run", "started"):
        raise RecordError("内容锁定前必须先建档")
    if stage == "dreamina" and event == "submitted" and not _event_exists(events, "content", "locked"):
        raise RecordError("Dreamina 提交前必须锁定内容")
    if stage == "dreamina" and event in {"succeeded", "tns", "failed", "environment_error"}:
        version = data.get("version")
        if event == "environment_error" and not any(
            item.get("stage") == "dreamina"
            and item.get("event") == "submitted"
            and (item.get("data") or {}).get("version") == version
            for item in events
        ):
            return
        submitted = any(
            item.get("stage") == "dreamina"
            and item.get("event") == "submitted"
            and (item.get("data") or {}).get("version") == version
            for item in events
        )
        if not submitted:
            raise RecordError(f"Dreamina {event} 前缺少同版本 submitted 事件")
    if stage == "quality" and not _event_exists(events, "dreamina", "succeeded", "success"):
        terminal_failure = latest_non_artifact(events, "dreamina", "failed")
        if event != "reviewed" or status != "not_performed" or terminal_failure is None:
            raise RecordError("质检前必须存在 Dreamina 成功产物；无产物失败只能记录 not_performed")
    if stage == "output":
        review = latest_non_artifact(events, "quality", "reviewed")
        if review is None or review.get("status") not in {"pass", "not_performed"}:
            raise RecordError("正式成片只能在质检通过或明确跳过后创建")
    if stage == "google_drive" and not _event_exists(events, "output", "created", "ready"):
        if event != "not_attempted":
            raise RecordError("Drive 上传结果前必须存在正式成片")
    if stage == "publish" and not any(
        item.get("stage") == "google_drive" and item.get("event") != "artifact"
        for item in events
    ):
        raise RecordError("发布状态前必须记录 Drive 终态")
    if (stage, event) == ("run", "completed"):
        publish = latest_non_artifact(events, "publish")
        quality = latest_non_artifact(events, "quality", "reviewed")
        generation = latest_non_artifact(events, "dreamina")
        terminal_publish = publish and publish.get("status") in {"published", "blocked", "not_requested"}
        terminal_failure = (
            quality and quality.get("status") == "blocked"
        ) or (
            generation and generation.get("status") == "failed"
        )
        if not terminal_publish and not terminal_failure:
            raise RecordError("运行尚未到达可收尾终态")
        if status == "success" and publish and publish.get("status") == "blocked":
            raise RecordError("双平台发布 blocked 时不能把运行标记为 success")
        if status == "success" and data.get("outcome") != "success":
            raise RecordError("run/completed=success 与 outcome 不一致")
        if status == "failed" and data.get("outcome") == "success":
            raise RecordError("run/completed=failed 与 outcome 不一致")


def append_event_v2(
    record_jsonl: str | Path,
    *,
    run_id: str,
    stage: str,
    event: str,
    status: str,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically append one validated schema-v2 event."""
    path = Path(record_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        events = read_events(path)
        payload = data or {}
        validate_v2_transition(
            events,
            run_id=run_id,
            stage=stage,
            event=event,
            status=status,
            data=payload,
        )
        seq = max((int(item.get("seq") or 0) for item in events if is_v2_event(item)), default=0) + 1
        item = {
            "schema_version": SCHEMA_VERSION,
            "seq": seq,
            "run_id": run_id,
            "created_at": now_iso(),
            "stage": stage,
            "event": event,
            "status": status,
            "summary": summary,
            "data": payload,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    return item


def read_json_value(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def append_event(
    record_jsonl: str | Path,
    *,
    stage: str,
    event: str,
    status: str | None = None,
    summary: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(record_jsonl)
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "created_at": now_iso(),
        "stage": stage,
        "event": event,
        "status": status,
        "summary": summary,
        "data": data or {},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return item


def append_artifact(
    record_jsonl: str | Path,
    *,
    stage: str,
    path: str,
    kind: str | None = None,
    status: str | None = None,
    keep: bool | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    return append_event(
        record_jsonl,
        stage=stage,
        event="artifact",
        status=status,
        summary=summary,
        data={
            "path": path,
            "kind": kind,
            "keep": keep,
        },
    )


def read_events(record_jsonl: str | Path) -> list[dict[str, Any]]:
    path = Path(record_jsonl)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def derive_v2_state(events: list[dict[str, Any]]) -> dict[str, Any]:
    v2_events = [item for item in events if is_v2_event(item)]
    if not v2_events:
        return {"schema_version": 1, "terminal": False, "next_action": "legacy_read_only"}
    run = latest_non_artifact(v2_events, "run")
    content = latest_non_artifact(v2_events, "content", "locked")
    generation = latest_non_artifact(v2_events, "dreamina")
    quality = latest_non_artifact(v2_events, "quality", "reviewed")
    output = latest_non_artifact(v2_events, "output", "created")
    drive = latest_non_artifact(v2_events, "google_drive")
    publish = latest_non_artifact(v2_events, "publish")
    route = str(((content or {}).get("data") or {}).get("route") or "")
    publish_mode = str(((content or {}).get("data") or {}).get("publish_mode") or "default")

    terminal = bool(run and run.get("event") == "completed")
    if terminal:
        next_action = "none"
    elif content is None:
        next_action = "prepare_content"
    elif generation is None:
        next_action = "generate"
    elif generation.get("event") == "submitted":
        next_action = "poll_generation"
    elif generation.get("event") == "environment_error":
        next_action = "repair_environment"
    elif generation.get("status") in {"failed"}:
        next_action = "complete"
    elif generation.get("event") == "tns":
        version = int(str((generation.get("data") or {}).get("version") or "v1").removeprefix("v"))
        next_action = "complete" if version >= 5 else "generate_next_version"
    elif quality is None:
        next_action = "finalize_output" if route == "xdysp" else "review_quality"
    elif quality.get("status") == "blocked":
        next_action = "complete" if drive is not None and publish and publish.get("status") == "not_requested" else "record_failure_terminals"
    elif output is None:
        next_action = "finalize_output"
    elif drive is None:
        next_action = "upload_drive"
    elif publish_mode == "awaiting_confirmation" and (
        publish is None or publish.get("status") == "awaiting_confirmation"
    ):
        next_action = "await_confirmation"
    elif publish_mode == "not_requested" and (
        publish is None or publish.get("status") != "not_requested"
    ):
        next_action = "record_not_requested"
    elif route == "xdysp":
        next_action = "record_not_requested" if publish is None else "complete"
    elif publish is None or publish.get("event") == "authorized":
        next_action = "publish"
    elif publish.get("event") == "platform_result":
        next_action = "publish"
    elif publish.get("status") in {"published", "blocked", "not_requested"}:
        next_action = "complete"
    else:
        next_action = "inspect"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": v2_events[0].get("run_id"),
        "route": route,
        "publish_mode": publish_mode,
        "terminal": terminal,
        "terminal_status": run.get("status") if terminal else None,
        "next_action": next_action,
        "event_count": len(v2_events),
    }


def record_md_path(record_jsonl: str | Path, md_path: str | Path | None = None) -> Path:
    if md_path:
        return Path(md_path)
    jsonl_path = Path(record_jsonl)
    return jsonl_path.with_suffix(".md")


def record_summary_path(record_jsonl: str | Path, summary_path: str | Path | None = None) -> Path:
    if summary_path:
        return Path(summary_path)
    jsonl_path = Path(record_jsonl)
    run_id = jsonl_path.stem.removesuffix("-run-record")
    return jsonl_path.parent / "logs" / "summary" / f"{run_id}-summary.json"


def _artifact_bucket(event: dict[str, Any]) -> str:
    data = event.get("data") or {}
    artifact_path = str(data.get("path") or "")
    status = str(event.get("status") or "").lower()
    keep = data.get("keep")
    kind = str(data.get("kind") or "").lower()
    if "/logs/" in artifact_path or artifact_path.startswith("logs/"):
        return "evidence"
    if keep is False:
        return "evidence"
    if status in {"fail", "failed", "error", "blocked"}:
        return "evidence"
    if any(token in kind for token in ("log", "raw", "stderr", "query", "submit")):
        return "evidence"
    return "key"


def _artifact_item(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") or {}
    return {
        "stage": event.get("stage"),
        "event": event.get("event"),
        "status": event.get("status"),
        "summary": event.get("summary"),
        "path": data.get("path"),
        "kind": data.get("kind"),
        "keep": data.get("keep"),
        "created_at": event.get("created_at"),
    }


def build_summary(events: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    latest_by_stage: dict[str, dict[str, Any]] = {}
    for event in events:
        if is_artifact(event):
            continue
        latest_by_stage[event.get("stage") or "unknown"] = event

    artifact_events = [event for event in events if event.get("event") == "artifact"]
    deduped: dict[str, dict[str, Any]] = {}
    for event in artifact_events:
        data = event.get("data") or {}
        artifact_path = data.get("path")
        if artifact_path:
            deduped[artifact_path] = event

    key_artifacts = []
    evidence_artifacts = []
    for event in deduped.values():
        item = _artifact_item(event)
        if _artifact_bucket(event) == "evidence":
            evidence_artifacts.append(item)
        else:
            key_artifacts.append(item)

    state = derive_v2_state(events)
    return {
        "run_id": run_id,
        "schema_version": state.get("schema_version"),
        "updated_at": now_iso(),
        "terminal": state.get("terminal"),
        "next_action": state.get("next_action"),
        "final_status_by_stage": {
            stage: {
                "status": event.get("status"),
                "event": event.get("event"),
                "summary": event.get("summary"),
                "created_at": event.get("created_at"),
            }
            for stage, event in latest_by_stage.items()
        },
        "key_artifacts": key_artifacts,
        "evidence_artifacts": evidence_artifacts,
        "logs_dir": f"TEMP/{run_id}/logs",
        "event_count": len(events),
    }


def write_summary_json(record_jsonl: str | Path, events: list[dict[str, Any]], run_id: str, summary_path: str | Path | None = None) -> Path:
    target = record_summary_path(record_jsonl, summary_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_summary(events, run_id), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def refresh_markdown(record_jsonl: str | Path, md_path: str | Path | None = None) -> Path:
    events = read_events(record_jsonl)
    target = record_md_path(record_jsonl, md_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    run_id = target.stem.removesuffix("-run-record")

    lines = [
        f"# {run_id} 运行记录",
        "",
        "## 当前摘要",
    ]
    if not events:
        lines.append("- 暂无记录")
    else:
        latest_by_stage: dict[str, dict[str, Any]] = {}
        for event in events:
            if is_artifact(event):
                continue
            latest_by_stage[event.get("stage") or "unknown"] = event
        for stage, event in latest_by_stage.items():
            status = event.get("status") or "unknown"
            summary = event.get("summary") or event.get("event") or ""
            lines.append(f"- {stage}：{status}；{summary}")

    summary_json = write_summary_json(record_jsonl, events, run_id)
    lines.extend(["", "## 摘要 JSON", f"- {summary_json}"])

    artifact_events = [event for event in events if event.get("event") == "artifact"]
    if artifact_events:
        deduped: dict[str, dict[str, Any]] = {}
        for event in artifact_events:
            data = event.get("data") or {}
            artifact_path = data.get("path")
            if artifact_path:
                deduped[artifact_path] = event
        key_artifacts = [event for event in deduped.values() if _artifact_bucket(event) == "key"]
        evidence_artifacts = [event for event in deduped.values() if _artifact_bucket(event) == "evidence"]
        if key_artifacts:
            lines.extend(["", "## 关键产物"])
        for event in key_artifacts:
            data = event.get("data") or {}
            artifact_path = data.get("path")
            status = event.get("status") or "recorded"
            keep = data.get("keep")
            keep_text = "保留" if keep is True else "可清理" if keep is False else "未标记"
            lines.append(f"- {event.get('stage')}：{status}；{artifact_path}；{keep_text}")
        if evidence_artifacts:
            lines.extend(["", "## 过程证据索引"])
        for event in evidence_artifacts:
            data = event.get("data") or {}
            artifact_path = data.get("path")
            status = event.get("status") or "recorded"
            summary = event.get("summary") or data.get("kind") or "过程证据"
            lines.append(f"- {event.get('stage')}：{status}；{summary}；{artifact_path}")

    lines.extend(["", "## 事件流"])
    for event in events:
        summary = event.get("summary") or event.get("event") or ""
        lines.append(f"- {event.get('created_at')} [{event.get('stage')}] {event.get('event')} {event.get('status') or ''} {summary}".rstrip())

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="追加或刷新抖音日更任务增量记录。")
    subparsers = parser.add_subparsers(dest="command", required=True)

    append_parser = subparsers.add_parser("append", help="追加一条结构化事件")
    append_parser.add_argument("record_jsonl")
    append_parser.add_argument("--stage", required=True)
    append_parser.add_argument("--event", required=True)
    append_parser.add_argument("--status", default=None)
    append_parser.add_argument("--summary", default=None)
    append_parser.add_argument("--data", default=None, help="JSON 字符串，或 @path.json")

    artifact_parser = subparsers.add_parser("artifact", help="记录一个关键产物")
    artifact_parser.add_argument("record_jsonl")
    artifact_parser.add_argument("--stage", required=True)
    artifact_parser.add_argument("--path", required=True)
    artifact_parser.add_argument("--kind", default=None)
    artifact_parser.add_argument("--status", default=None)
    artifact_parser.add_argument("--keep", action="store_true")
    artifact_parser.add_argument("--cleanable", action="store_true")
    artifact_parser.add_argument("--summary", default=None)

    summary_parser = subparsers.add_parser("summary", help="根据 JSONL 刷新 Markdown 摘要")
    summary_parser.add_argument("record_jsonl")
    summary_parser.add_argument("--md", default=None)

    args = parser.parse_args()
    if args.command == "append":
        if any(is_v2_event(item) for item in read_events(args.record_jsonl)):
            parser.error("schema v2 记录只能由 TOOLS/xdy_flow.py 写入")
        item = append_event(
            args.record_jsonl,
            stage=args.stage,
            event=args.event,
            status=args.status,
            summary=args.summary,
            data=read_json_value(args.data),
        )
        md = refresh_markdown(args.record_jsonl)
        print(json.dumps({"recorded": item, "markdown": str(md)}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "artifact":
        if any(is_v2_event(item) for item in read_events(args.record_jsonl)):
            parser.error("schema v2 记录的详细证据只写入 logs/，不追加自由格式 artifact")
        keep = True if args.keep else False if args.cleanable else None
        item = append_artifact(
            args.record_jsonl,
            stage=args.stage,
            path=args.path,
            kind=args.kind,
            status=args.status,
            keep=keep,
            summary=args.summary,
        )
        md = refresh_markdown(args.record_jsonl)
        print(json.dumps({"recorded": item, "markdown": str(md)}, ensure_ascii=False, indent=2))
        return 0

    md = refresh_markdown(args.record_jsonl, args.md)
    print(json.dumps({"markdown": str(md)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
