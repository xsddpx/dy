#!/usr/bin/env python3
"""Append compact per-run records for the Douyin workflow."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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


def _format_value(value: Any) -> str:
    if value is None:
        return "未记录"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _face_similarity_lines(event: dict[str, Any]) -> list[str]:
    data = event.get("data") or {}
    slot = data.get("reference_slot") or data.get("selected_slot")
    image = data.get("reference_confirmation_image") or data.get("selected_confirmation_image")
    return [
        f"- 结论：{_format_value(data.get('decision') or event.get('status'))}",
        f"- 参考槽位：{_format_value(slot)}",
        f"- 参考确认图：{_format_value(image)}",
        f"- 动态阈值：{_format_value(data.get('adjusted_threshold_min_percent'))}%",
        f"- 候选最高分：{_format_value(data.get('best_similarity_percent'))}%",
        f"- 跳过人脸槽位：{_format_value(data.get('face_gate_skipped_slots'))}",
        f"- 原因：{_format_value(data.get('reason'))}",
    ]


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

    return {
        "run_id": run_id,
        "updated_at": now_iso(),
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
            latest_by_stage[event.get("stage") or "unknown"] = event
        for stage, event in latest_by_stage.items():
            status = event.get("status") or "unknown"
            summary = event.get("summary") or event.get("event") or ""
            lines.append(f"- {stage}：{status}；{summary}")

    face_events = [event for event in events if event.get("event") == "face_similarity"]
    if face_events:
        lines.extend(["", "## 人脸相似度"])
        lines.extend(_face_similarity_lines(face_events[-1]))

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


def face_similarity_summary(report: dict[str, Any]) -> dict[str, Any]:
    slots = report.get("slots") or []
    best = None
    for slot in slots:
        score = slot.get("face_similarity_min_percent")
        if score is None:
            continue
        if best is None or float(score) > float(best.get("face_similarity_min_percent") or -1):
            best = slot

    selected = None
    selected_slot = report.get("reference_slot") or report.get("selected_slot")
    for slot in slots:
        if slot.get("slot") == selected_slot:
            selected = slot
            break
    skipped_slots = []
    for slot in slots:
        if slot.get("face_gate_skipped"):
            skipped_slots.append(slot.get("slot"))

    reason = None
    if selected:
        reason = selected.get("auto_select_reason")
    elif report.get("errors"):
        reason = "; ".join(str(item) for item in report.get("errors") or [])

    return {
        "decision": report.get("decision"),
        "selected_slot": selected_slot,
        "selected_confirmation_image": report.get("reference_confirmation_image") or report.get("selected_confirmation_image"),
        "reference_slot": report.get("reference_slot"),
        "reference_confirmation_image": report.get("reference_confirmation_image"),
        "adjusted_threshold_min_percent": (selected or {}).get("adjusted_threshold_min_percent"),
        "best_similarity_percent": (best or {}).get("face_similarity_min_percent"),
        "face_gate_skipped_slots": ", ".join(str(item) for item in skipped_slots) if skipped_slots else None,
        "reason": reason,
        "report": report.get("report") or report.get("report_json"),
    }


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
