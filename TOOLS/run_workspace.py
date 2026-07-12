#!/usr/bin/env python3
"""Allocate, audit, migrate, and roll back canonical dy run workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from run_record import append_event, refresh_markdown


SHANGHAI = ZoneInfo("Asia/Shanghai")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d{2})?$")
LEGACY_TIME_RE = re.compile(r"^(?:dy-)?(?P<date>\d{8})-(?P<time>\d{4}|\d{6})(?:-|$)")
TEXT_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".log"}
LOCK_NAME = ".run-id-migration.lock"
MIGRATIONS_DIR = "_run-id-migrations"


class WorkspaceError(RuntimeError):
    pass


def repo_root(value: str | Path | None = None) -> Path:
    root = Path(value or Path(__file__).resolve().parent.parent).resolve()
    if not (root / "TOOLS" / "run_record.py").is_file():
        raise WorkspaceError(f"不是 dy 项目根目录：{root}")
    return root


def temp_root(root: Path) -> Path:
    return root / "TEMP"


def output_root(root: Path) -> Path:
    return root / "OUTPUT"


def lock_path(root: Path) -> Path:
    return temp_root(root) / LOCK_NAME


@contextmanager
def migration_lock(root: Path) -> Iterator[None]:
    temp_root(root).mkdir(parents=True, exist_ok=True)
    path = lock_path(root)
    try:
        path.mkdir()
        (path / "owner.json").write_text(
            json.dumps(
                {"pid": os.getpid(), "created_at": datetime.now(SHANGHAI).isoformat()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except FileExistsError as exc:
        raise WorkspaceError(f"迁移锁已存在：{path}") from exc
    try:
        yield
    finally:
        shutil.rmtree(path, ignore_errors=True)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return events
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def timestamp_for_run(run_dir: Path, record: Path) -> tuple[datetime, str]:
    events = read_jsonl_events(record)
    for event in events:
        if event.get("stage") == "run" and event.get("event") == "started":
            for key in ("created_at", "ts"):
                parsed = parse_time(event.get(key))
                if parsed:
                    return parsed, f"run/started.{key}"
    for event in events:
        for key in ("created_at", "ts"):
            parsed = parse_time(event.get(key))
            if parsed:
                return parsed, f"first_event.{key}"
    match = LEGACY_TIME_RE.match(run_dir.name)
    if match:
        time_text = match.group("time")
        if len(time_text) == 4:
            time_text += "00"
        parsed = datetime.strptime(match.group("date") + time_text, "%Y%m%d%H%M%S")
        return parsed.replace(tzinfo=SHANGHAI), "legacy_name"
    mtimes = [path.stat().st_mtime for path in run_dir.rglob("*") if path.is_file()]
    if mtimes:
        return datetime.fromtimestamp(min(mtimes), SHANGHAI), "earliest_file_mtime"
    raise WorkspaceError(f"无法确定历史运行时间：{run_dir}")


def canonical_base(value: datetime) -> str:
    return value.astimezone(SHANGHAI).strftime("%Y%m%d-%H%M%S")


def formal_runs(root: Path) -> list[tuple[str, Path, Path]]:
    base = temp_root(root)
    if not base.exists():
        return []
    result: list[tuple[str, Path, Path]] = []
    for directory in sorted((path for path in base.iterdir() if path.is_dir()), key=lambda p: p.name):
        record = directory / f"{directory.name}-run-record.jsonl"
        if record.is_file():
            result.append((directory.name, directory, record))
    return result


def allocate_run_dir(root: Path, when: datetime) -> tuple[str, Path]:
    if lock_path(root).exists():
        raise WorkspaceError("历史迁移正在进行，暂不创建新运行")
    base = canonical_base(when)
    candidates = [base, *(f"{base}-{index:02d}" for index in range(1, 100))]
    temp_root(root).mkdir(parents=True, exist_ok=True)
    for run_id in candidates:
        path = temp_root(root) / run_id
        try:
            path.mkdir()
        except FileExistsError:
            continue
        return run_id, path
    raise WorkspaceError(f"同一秒的 RUN_ID 已耗尽：{base}")


def init_workspace(
    root: Path,
    *,
    when: datetime | None = None,
    source: str | None = None,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id, directory = allocate_run_dir(root, when or datetime.now(SHANGHAI))
    record = directory / f"{run_id}-run-record.jsonl"
    try:
        (directory / "logs").mkdir()
        output_root(root).mkdir(parents=True, exist_ok=True)
        event_data = dict(data or {})
        if source:
            event_data["source"] = source
        append_event(
            record,
            stage="run",
            event="started",
            status="in_progress",
            summary="本次运行已建档",
            data=event_data,
        )
        refresh_markdown(record)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return {
        "run_id": run_id,
        "temp_dir": str(directory.relative_to(root)),
        "record_jsonl": str(record.relative_to(root)),
        "output_mp4": f"OUTPUT/{run_id}.mp4",
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def output_for_old_id(root: Path, old_id: str) -> Path | None:
    candidates = [output_root(root) / f"{old_id}.mp4"]
    if old_id.startswith("dy-"):
        candidates.append(output_root(root) / f"{old_id.removeprefix('dy-')}.mp4")
    existing = [path for path in candidates if path.is_file()]
    if len(existing) > 1:
        raise WorkspaceError(f"历史成片匹配不唯一：{old_id} -> {existing}")
    return existing[0] if existing else None


def build_migration_plan(root: Path) -> dict[str, Any]:
    runs = formal_runs(root)
    source_names = {old_id for old_id, _, _ in runs}
    reserved_names = {
        path.name
        for path in temp_root(root).iterdir()
        if path.is_dir() and path.name not in source_names
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for old_id, directory, record in runs:
        stamp, source = timestamp_for_run(directory, record)
        grouped.setdefault(canonical_base(stamp), []).append(
            {
                "old_id": old_id,
                "timestamp": stamp.isoformat(),
                "timestamp_source": source,
            }
        )

    entries: list[dict[str, Any]] = []
    assigned: set[str] = set()
    for base in sorted(grouped):
        index = 0
        for item in sorted(grouped[base], key=lambda value: value["old_id"]):
            while True:
                if index > 99:
                    raise WorkspaceError(f"同一秒的历史 RUN_ID 超过 100 个：{base}")
                candidate = base if index == 0 else f"{base}-{index:02d}"
                index += 1
                if candidate not in reserved_names and candidate not in assigned:
                    break
            assigned.add(candidate)
            old_id = item["old_id"]
            output = output_for_old_id(root, old_id)
            entry = {**item, "new_id": candidate}
            if output:
                entry["output_old"] = str(output.relative_to(root))
                entry["output_new"] = f"OUTPUT/{candidate}.mp4"
                entry["output_size"] = output.stat().st_size
                entry["output_sha256"] = sha256_file(output)
            entries.append(entry)

    output_sources = [entry["output_old"] for entry in entries if entry.get("output_old")]
    if len(output_sources) != len(set(output_sources)):
        raise WorkspaceError("同一个历史成片被多个运行匹配")
    output_targets = [entry["output_new"] for entry in entries if entry.get("output_new")]
    if len(output_targets) != len(set(output_targets)):
        raise WorkspaceError("多个历史成片映射到了同一目标")
    source_set = set(output_sources)
    for target in output_targets:
        if (root / target).exists() and target not in source_set:
            raise WorkspaceError(f"迁移目标成片已被占用：{target}")
    return {
        "schema_version": 1,
        "created_at": datetime.now(SHANGHAI).isoformat(),
        "root": str(root),
        "status": "planned",
        "run_count": len(entries),
        "output_count": len(output_sources),
        "entries": sorted(entries, key=lambda value: value["old_id"]),
    }


def replacement_pairs(entry: dict[str, Any]) -> list[tuple[str, str]]:
    old_id = entry["old_id"]
    new_id = entry["new_id"]
    pairs = [
        (f"TEMP/{old_id}", f"TEMP/{new_id}"),
        (f"{old_id}-run-record.jsonl", f"{new_id}-run-record.jsonl"),
        (f"{old_id}-run-record.md", f"{new_id}-run-record.md"),
        (f"{old_id}-run-summary.md", f"{new_id}-run-summary.md"),
        (f"{old_id}-summary.json", f"{new_id}-summary.json"),
    ]
    output_old = entry.get("output_old")
    if output_old:
        pairs.append((output_old, entry["output_new"]))
    pairs.append((f"OUTPUT/{old_id}.mp4", f"OUTPUT/{new_id}.mp4"))
    return pairs


def rewrite_text(text: str, entry: dict[str, Any]) -> str:
    updated = text
    for old, new in replacement_pairs(entry):
        updated = updated.replace(old, new)
    old_id = re.escape(entry["old_id"])
    new_id = entry["new_id"]
    updated = re.sub(
        rf'("run_id"\s*:\s*"){old_id}(")',
        lambda match: match.group(1) + new_id + match.group(2),
        updated,
    )
    updated = updated.replace(f"# {entry['old_id']} 运行记录", f"# {new_id} 运行记录")
    return updated


def known_identity_filename(name: str, old_id: str, new_id: str) -> str:
    suffixes = (
        "-run-record.jsonl",
        "-run-record.md",
        "-run-summary.md",
        "-summary.json",
    )
    if name.startswith(old_id) and name[len(old_id) :] in suffixes:
        return new_id + name[len(old_id) :]
    return name


def collect_changes(root: Path, plan: dict[str, Any]) -> tuple[list[str], list[dict[str, str]]]:
    changed_text: list[str] = []
    file_renames: list[dict[str, str]] = []
    for entry in plan["entries"]:
        old_id = entry["old_id"]
        new_id = entry["new_id"]
        run_dir = temp_root(root) / old_id
        for path in run_dir.rglob("*"):
            if not path.is_file():
                continue
            relative_inside = path.relative_to(run_dir)
            new_name = known_identity_filename(path.name, old_id, new_id)
            if new_name != path.name:
                new_relative_inside = relative_inside.with_name(new_name)
                file_renames.append(
                    {
                        "old": str(path.relative_to(root)),
                        "new": str((temp_root(root) / new_id / new_relative_inside).relative_to(root)),
                    }
                )
                if path.suffix.lower() in TEXT_SUFFIXES:
                    changed_text.append(str(path.relative_to(root)))
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if rewrite_text(text, entry) != text:
                changed_text.append(str(path.relative_to(root)))
    return sorted(set(changed_text)), file_renames


def write_backup(root: Path, migration_dir: Path, changed_text: list[str]) -> Path:
    backup = migration_dir / "text-backup.tar.gz"
    with tarfile.open(backup, "w:gz") as archive:
        for relative in changed_text:
            archive.add(root / relative, arcname=relative, recursive=False)
    return backup


def safe_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def stage_and_move(root: Path, plan: dict[str, Any], *, reverse: bool = False) -> None:
    token = uuid.uuid4().hex[:10]
    temp_stage = temp_root(root) / f".run-id-stage-{token}"
    output_stage = output_root(root) / f".run-id-stage-{token}"
    temp_stage.mkdir()
    output_stage.mkdir()
    moved_temp: list[tuple[Path, Path, Path]] = []
    moved_output: list[tuple[Path, Path, Path]] = []
    try:
        for index, entry in enumerate(plan["entries"]):
            source_id = entry["new_id"] if reverse else entry["old_id"]
            target_id = entry["old_id"] if reverse else entry["new_id"]
            source = temp_root(root) / source_id
            target = temp_root(root) / target_id
            staged = temp_stage / f"{index:04d}"
            if not source.is_dir():
                raise WorkspaceError(f"待迁移运行目录不存在：{source}")
            source.rename(staged)
            moved_temp.append((source, staged, target))
        for index, entry in enumerate(item for item in plan["entries"] if item.get("output_old")):
            source_rel = entry["output_new"] if reverse else entry["output_old"]
            target_rel = entry["output_old"] if reverse else entry["output_new"]
            source = root / source_rel
            target = root / target_rel
            staged = output_stage / f"{index:04d}.mp4"
            if not source.is_file():
                raise WorkspaceError(f"待迁移成片不存在：{source}")
            source.rename(staged)
            moved_output.append((source, staged, target))
        for _, staged, target in moved_temp:
            if target.exists():
                raise WorkspaceError(f"目标运行目录已存在：{target}")
            staged.rename(target)
        for _, staged, target in moved_output:
            if target.exists():
                raise WorkspaceError(f"目标成片已存在：{target}")
            staged.rename(target)
    except Exception:
        # Put anything still staged or already finalized back at its source.
        for source, staged, target in reversed(moved_output):
            current = staged if staged.exists() else target
            if current.exists() and not source.exists():
                current.rename(source)
        for source, staged, target in reversed(moved_temp):
            current = staged if staged.exists() else target
            if current.exists() and not source.exists():
                current.rename(source)
        raise
    finally:
        shutil.rmtree(temp_stage, ignore_errors=True)
        shutil.rmtree(output_stage, ignore_errors=True)


def apply_internal_changes(root: Path, plan: dict[str, Any]) -> None:
    renames_by_old = {item["old"]: item["new"] for item in plan["file_renames"]}
    changed_set = set(plan["changed_text"])
    for entry in plan["entries"]:
        old_id = entry["old_id"]
        new_id = entry["new_id"]
        run_dir = temp_root(root) / new_id
        relevant_renames = [
            (old, new)
            for old, new in renames_by_old.items()
            if old.startswith(f"TEMP/{old_id}/")
        ]
        for old_rel, new_rel in sorted(relevant_renames, key=lambda item: item[0].count("/"), reverse=True):
            inside = Path(old_rel).relative_to("TEMP", old_id)
            source = run_dir / inside
            target = root / new_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
        for old_rel in sorted(path for path in changed_set if path.startswith(f"TEMP/{old_id}/")):
            new_rel = renames_by_old.get(old_rel)
            if new_rel:
                path = root / new_rel
            else:
                inside = Path(old_rel).relative_to("TEMP", old_id)
                path = run_dir / inside
            text = path.read_text(encoding="utf-8")
            updated = rewrite_text(text, entry)
            if updated != text:
                path.write_text(updated, encoding="utf-8")


def restore_internal_changes(root: Path, plan: dict[str, Any], migration_dir: Path) -> None:
    for item in sorted(plan.get("file_renames", []), key=lambda value: value["new"].count("/"), reverse=True):
        old_path = root / item["old"]
        new_path = root / item["new"]
        # Directories have already been restored, so translate the new run prefix to old.
        parts = Path(item["new"]).parts
        new_id = parts[1]
        entry = next(value for value in plan["entries"] if value["new_id"] == new_id)
        translated = temp_root(root) / entry["old_id"] / Path(*parts[2:])
        if translated.exists() and translated != old_path:
            translated.unlink()
    backup = migration_dir / "text-backup.tar.gz"
    if backup.is_file():
        with tarfile.open(backup, "r:gz") as archive:
            # Archive members are generated from repository-relative paths by this tool.
            archive.extractall(root)


def verify_plan(root: Path, plan: dict[str, Any], *, applied: bool) -> list[str]:
    errors: list[str] = []
    for entry in plan["entries"]:
        expected_id = entry["new_id"] if applied else entry["old_id"]
        unexpected_id = entry["old_id"] if applied else entry["new_id"]
        directory = temp_root(root) / expected_id
        if not directory.is_dir():
            errors.append(f"运行目录缺失：TEMP/{expected_id}")
            continue
        record = directory / f"{expected_id}-run-record.jsonl"
        if not record.is_file():
            errors.append(f"运行记录缺失：{record.relative_to(root)}")
        if applied and unexpected_id != expected_id and (temp_root(root) / unexpected_id).exists():
            errors.append(f"旧运行目录仍存在：TEMP/{unexpected_id}")
        if entry.get("output_old"):
            output_rel = entry["output_new"] if applied else entry["output_old"]
            output = root / output_rel
            if not output.is_file():
                errors.append(f"成片缺失：{output_rel}")
            else:
                if output.stat().st_size != entry["output_size"]:
                    errors.append(f"成片大小变化：{output_rel}")
                elif sha256_file(output) != entry["output_sha256"]:
                    errors.append(f"成片哈希变化：{output_rel}")
        if applied and entry["old_id"] != entry["new_id"]:
            old_temp_token = f"TEMP/{entry['old_id']}"
            old_output_tokens = {f"OUTPUT/{entry['old_id']}.mp4"}
            if entry.get("output_old"):
                old_output_tokens.add(entry["output_old"])
            for path in directory.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                if old_temp_token in text:
                    errors.append(f"旧 TEMP 路径残留：{path.relative_to(root)}")
                    break
                if any(token in text for token in old_output_tokens):
                    errors.append(f"旧 OUTPUT 路径残留：{path.relative_to(root)}")
                    break
    return errors


def apply_migration(root: Path, plan: dict[str, Any]) -> Path:
    migration_id = datetime.now(SHANGHAI).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    migration_dir = temp_root(root) / MIGRATIONS_DIR / migration_id
    migration_dir.mkdir(parents=True)
    changed_text, file_renames = collect_changes(root, plan)
    plan["migration_id"] = migration_id
    plan["changed_text"] = changed_text
    plan["file_renames"] = file_renames
    plan["status"] = "prepared"
    manifest = migration_dir / "manifest.json"
    safe_write_json(manifest, plan)
    write_backup(root, migration_dir, changed_text)
    moved = False
    try:
        stage_and_move(root, plan)
        moved = True
        apply_internal_changes(root, plan)
        errors = verify_plan(root, plan, applied=True)
        if errors:
            raise WorkspaceError("迁移后验证失败：\n- " + "\n- ".join(errors))
    except Exception:
        try:
            if moved:
                stage_and_move(root, plan, reverse=True)
                restore_internal_changes(root, plan, migration_dir)
            plan["status"] = "rolled_back_after_failure"
        finally:
            safe_write_json(manifest, plan)
        raise
    plan["status"] = "applied"
    plan["applied_at"] = datetime.now(SHANGHAI).isoformat()
    safe_write_json(manifest, plan)
    return manifest


def rollback_migration(root: Path, manifest: Path) -> dict[str, Any]:
    plan = json.loads(manifest.read_text(encoding="utf-8"))
    if plan.get("status") != "applied":
        raise WorkspaceError(f"迁移状态不可回滚：{plan.get('status')}")
    for entry in plan["entries"]:
        old_path = temp_root(root) / entry["old_id"]
        if old_path.exists() and old_path != temp_root(root) / entry["new_id"]:
            raise WorkspaceError(f"回滚目标已被占用：{old_path}")
        if entry.get("output_old"):
            old_output = root / entry["output_old"]
            if old_output.exists() and old_output != root / entry["output_new"]:
                raise WorkspaceError(f"回滚成片目标已被占用：{old_output}")
    stage_and_move(root, plan, reverse=True)
    restore_internal_changes(root, plan, manifest.parent)
    errors = verify_plan(root, plan, applied=False)
    if errors:
        raise WorkspaceError("回滚后验证失败：\n- " + "\n- ".join(errors))
    plan["status"] = "rolled_back"
    plan["rolled_back_at"] = datetime.now(SHANGHAI).isoformat()
    safe_write_json(manifest, plan)
    return plan


def audit_workspace(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    runs = formal_runs(root)
    run_ids = {old_id for old_id, _, _ in runs}
    formal_directories = {directory for _, directory, _ in runs}
    if temp_root(root).exists():
        for directory in (path for path in temp_root(root).iterdir() if path.is_dir()):
            if directory in formal_directories or directory.name.startswith("candidate-"):
                continue
            root_records = list(directory.glob("*-run-record.jsonl"))
            if root_records:
                errors.append(
                    f"运行目录与记录文件名不一致：{directory.relative_to(root)} -> "
                    + ", ".join(path.name for path in sorted(root_records))
                )
    for run_id, directory, _ in runs:
        if not RUN_ID_RE.fullmatch(run_id):
            errors.append(f"非法正式运行目录：{directory.relative_to(root)}")
        expected_record = directory / f"{run_id}-run-record.jsonl"
        expected_md = directory / f"{run_id}-run-record.md"
        if not expected_record.is_file():
            errors.append(f"运行记录缺失：{expected_record.relative_to(root)}")
        if not expected_md.is_file():
            warnings.append(f"Markdown 运行记录缺失：{expected_md.relative_to(root)}")
    outputs = sorted(output_root(root).glob("*.mp4")) if output_root(root).exists() else []
    for output in outputs:
        run_id = output.stem
        if not RUN_ID_RE.fullmatch(run_id):
            errors.append(f"非法正式成片名称：{output.relative_to(root)}")
        elif run_id not in run_ids:
            errors.append(f"正式成片没有对应运行目录：{output.relative_to(root)}")
    return {
        "decision": "pass" if not errors else "failed",
        "run_count": len(runs),
        "output_count": len(outputs),
        "errors": errors,
        "warnings": warnings,
    }


def read_data(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    if value.startswith("@"):
        parsed = json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    else:
        parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise WorkspaceError("--data 必须是 JSON 对象")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一管理 TEMP/OUTPUT 的 RUN_ID 命名")
    parser.add_argument("--root", default=None, help="项目根目录，默认从脚本位置解析")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="创建规范运行空间并写入 started 事件")
    init_parser.add_argument("--at", default=None, help="测试或补建用 ISO 时间，默认当前上海时间")
    init_parser.add_argument("--source", default=None)
    init_parser.add_argument("--data", default=None, help="JSON 对象或 @path.json")
    init_parser.add_argument("--format", choices=("id", "json"), default="id")

    subparsers.add_parser("audit", help="审计正式运行目录与成片命名")

    migrate_parser = subparsers.add_parser("migrate", help="预演或执行历史 RUN_ID 迁移")
    migrate_parser.add_argument("--apply", action="store_true", help="实际执行；默认只预演")

    rollback_parser = subparsers.add_parser("rollback", help="按 manifest 回滚已执行迁移")
    rollback_parser.add_argument("manifest")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        root = repo_root(args.root)
        if args.command == "init":
            when = parse_time(args.at) if args.at else None
            if args.at and when is None:
                raise WorkspaceError(f"无法解析 --at：{args.at}")
            result = init_workspace(root, when=when, source=args.source, data=read_data(args.data))
            print(result["run_id"] if args.format == "id" else json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.command == "audit":
            result = audit_workspace(root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["decision"] == "pass" else 1
        if args.command == "migrate":
            if not args.apply:
                plan = build_migration_plan(root)
                print(json.dumps(plan, ensure_ascii=False, indent=2))
                return 0
            with migration_lock(root):
                plan = build_migration_plan(root)
                manifest = apply_migration(root, plan)
            print(json.dumps({"status": "applied", "manifest": str(manifest)}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "rollback":
            manifest = Path(args.manifest).resolve()
            with migration_lock(root):
                result = rollback_migration(root, manifest)
            print(json.dumps({"status": result["status"], "manifest": str(manifest)}, ensure_ascii=False, indent=2))
            return 0
    except (WorkspaceError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
