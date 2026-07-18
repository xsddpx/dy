#!/usr/bin/env python3
"""Allocate, validate, and audit canonical dy workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import prompt_lint
from run_record import append_event, refresh_markdown
from workflow_config import config_sha256, load_workflow_config, project_path


SHANGHAI = ZoneInfo("Asia/Shanghai")
RUN_ID_RE = re.compile(r"^\d{8}-\d{6}(?:-\d{2})?$")
WORKFLOW_CONFIG = load_workflow_config()
GENERATION_CONFIG = WORKFLOW_CONFIG["generation"]
ASSET_CONFIG = WORKFLOW_CONFIG["assets"]
VALID_DURATIONS = set(GENERATION_CONFIG["valid_durations"])
VALID_ROUTES = {"xdy", "xdysp"}
VALID_PUBLISH_MODES = {"default", "not_requested", "awaiting_confirmation"}
VALID_OUTCOMES = {"success", "generation_failed", "quality_failed", "publish_failed", "cancelled"}
FORMAL_ENVIRONMENT_RE = re.compile(r"^anna-room-\d{2,}\.png$")
CONTRACTS_DIR = Path("logs/contracts")
VIDEO_RATIO = GENERATION_CONFIG["ratio"]
VIDEO_RESOLUTION = GENERATION_CONFIG["video_resolution"]
VIDEO_WIDTH = int(GENERATION_CONFIG["width"])
VIDEO_HEIGHT = int(GENERATION_CONFIG["height"])
VIDEO_DURATION_TOLERANCE = 0.75


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


def safe_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def read_contract_events(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"运行记录第 {line_number} 行不是合法 JSON：{exc.msg}")
            continue
        if not isinstance(item, dict):
            errors.append(f"运行记录第 {line_number} 行必须是 JSON 对象")
            continue
        if not isinstance(item.get("data", {}), dict):
            errors.append(f"运行记录第 {line_number} 行的 data 必须是 JSON 对象")
            continue
        events.append(item)
    return events, errors


def event_data(event: dict[str, Any] | None) -> dict[str, Any]:
    if event is None:
        return {}
    value = event.get("data")
    return value if isinstance(value, dict) else {}


def locked_environment_image(root: Path, directory: Path) -> tuple[Path | None, list[str]]:
    lock = directory / "environment-path.txt"
    errors: list[str] = []
    if not lock.is_file():
        return None, ["本次运行缺少 environment-path.txt"]
    lines = [line.strip() for line in lock.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1:
        return None, ["environment-path.txt 必须且只能包含一个环境图绝对路径"]
    candidate = Path(lines[0])
    if not candidate.is_absolute():
        return None, ["environment-path.txt 必须使用绝对路径"]
    image = candidate.resolve()
    formal_root = (root / "MATERIAL" / "fixed-environment").resolve()
    if not image.is_file():
        errors.append(f"锁定的环境图不存在：{image}")
    elif image.parent != formal_root or not FORMAL_ENVIRONMENT_RE.fullmatch(image.name):
        errors.append("锁定的环境图不属于正式 anna-room-NN.png 随机池")
    return image, errors


def contract_result(
    *,
    phase: str,
    run_id: str,
    route: str,
    errors: list[str],
    facts: dict[str, Any] | None = None,
    manifest: Path | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "decision": "pass" if not errors else "failed",
        "phase": phase,
        "run_id": run_id,
        "route": route,
        "errors": errors,
        "facts": facts or {},
    }
    if manifest is not None:
        result["manifest"] = str(manifest)
    return result


def run_contract_paths(root: Path, run_id: str) -> tuple[Path, Path]:
    if not RUN_ID_RE.fullmatch(run_id):
        raise WorkspaceError(f"非法 RUN_ID：{run_id}")
    directory = temp_root(root) / run_id
    record = directory / f"{run_id}-run-record.jsonl"
    if not directory.is_dir():
        raise WorkspaceError(f"运行目录不存在：TEMP/{run_id}")
    if not record.is_file():
        raise WorkspaceError(f"运行记录不存在：TEMP/{run_id}/{run_id}-run-record.jsonl")
    return directory, record


def latest_event(events: list[dict[str, Any]], stage: str, event: str | None = None) -> dict[str, Any] | None:
    matches = [
        item
        for item in events
        if item.get("stage") == stage and (event is None or item.get("event") == event)
    ]
    return matches[-1] if matches else None


def latest_state_event(events: list[dict[str, Any]], stage: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in events
        if item.get("stage") == stage and item.get("event") != "artifact"
    ]
    return matches[-1] if matches else None


def latest_success_event(events: list[dict[str, Any]], stage: str) -> dict[str, Any] | None:
    matches = [
        item
        for item in events
        if item.get("stage") == stage
        and item.get("event") != "artifact"
        and str(item.get("status") or "").lower() == "success"
    ]
    return matches[-1] if matches else None


def latest_versioned_event(
    events: list[dict[str, Any]],
    stage: str,
    event: str,
    version: str,
) -> dict[str, Any] | None:
    matches = [
        item
        for item in events
        if item.get("stage") == stage
        and item.get("event") == event
        and str(event_data(item).get("version") or "") == version
    ]
    return matches[-1] if matches else None


def generation_manifest_path(directory: Path, version: int) -> Path:
    return directory / CONTRACTS_DIR / f"generation-v{version}.json"


def validate_pre_generation_contract(
    root: Path,
    run_id: str,
    *,
    route: str,
    duration: int,
    prompt_version: int,
    write_manifest: bool = True,
) -> dict[str, Any]:
    directory, record = run_contract_paths(root, run_id)
    events, errors = read_contract_events(record)
    facts: dict[str, Any] = {
        "duration": duration,
        "prompt_version": f"v{prompt_version}",
        "ratio": VIDEO_RATIO,
        "resolution": VIDEO_RESOLUTION,
    }

    if route not in VALID_ROUTES:
        errors.append(f"未知运行路线：{route}")
    if latest_event(events, "run", "started") is None:
        errors.append("运行记录缺少 run/started 事件")
    if duration not in VALID_DURATIONS:
        errors.append(f"生成时长必须是 5、6 或 7 秒，实际为 {duration}")
    if prompt_version not in range(1, 6):
        errors.append(f"prompt 版本必须是 v1-v5，实际为 v{prompt_version}")

    video_prompt = directory / f"vid-prompt-v{prompt_version}.txt"
    environment_lock = directory / "environment-path.txt"
    role_image = project_path(root, ASSET_CONFIG["role_image"])
    environment_image, environment_errors = locked_environment_image(root, directory)
    errors.extend(environment_errors)

    if not video_prompt.is_file():
        errors.append(f"本次运行缺少 {video_prompt.name}")
    if not role_image.is_file():
        errors.append(f"固定角色图不存在：{ASSET_CONFIG['role_image']}")

    if video_prompt.is_file():
        video_text = video_prompt.read_text(encoding="utf-8")
        lint = prompt_lint.lint_text(video_text, video_prompt)
        facts["prompt_lint"] = lint["decision"]
        if lint["decision"] != "pass":
            codes = sorted({item["code"] for item in lint["findings"] if item["severity"] == "error"})
            errors.append("视频 prompt 校验失败：" + ", ".join(codes))
        references = sorted(set(re.findall(r"@图\d+", video_text)))
        facts["prompt_references"] = references
        if references != ["@图1", "@图2"]:
            errors.append(f"视频 prompt 必须且只能引用 @图1、@图2，实际为 {references}")

    reference_images = [str(role_image)]
    if environment_image is not None:
        reference_images.append(str(environment_image))
    facts["reference_images"] = reference_images
    facts["prompt"] = str(video_prompt.relative_to(root))

    manifest_path: Path | None = None
    if not errors and write_manifest:
        manifest_path = generation_manifest_path(directory, prompt_version)
        manifest = {
            "schema_version": 2,
            "decision": "pass",
            "phase": "pre-generation",
            "run_id": run_id,
            "route": route,
            "prompt_version": f"v{prompt_version}",
            "duration": duration,
            "ratio": VIDEO_RATIO,
            "video_resolution": VIDEO_RESOLUTION,
            "reference_images": reference_images,
            "prompt": str(video_prompt.relative_to(root)),
            "environment_lock": str(environment_lock.relative_to(root)),
            "workflow_config": "MATERIAL/xdy-workflow.json",
            "workflow_config_sha256": config_sha256(),
            "sha256": {
                "role_image": sha256_file(role_image),
                "environment_image": sha256_file(environment_image),
                "prompt": sha256_file(video_prompt),
                "environment_lock": sha256_file(environment_lock),
            },
        }
        if manifest_path.is_file():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                errors.append(f"已有合同清单不是合法 JSON，拒绝覆盖：{manifest_path.relative_to(root)}")
            else:
                if existing != manifest:
                    errors.append(f"已有合同清单与当前输入不同，拒绝覆盖：{manifest_path.relative_to(root)}")
        else:
            safe_write_json(manifest_path, manifest)
        if manifest_path.is_file():
            facts["manifest_sha256"] = sha256_file(manifest_path)
    return contract_result(
        phase="pre-generation",
        run_id=run_id,
        route=route,
        errors=errors,
        facts=facts,
        manifest=manifest_path.relative_to(root) if manifest_path else None,
    )


def probe_video(path: Path) -> dict[str, Any]:
    executable = shutil.which("ffprobe")
    if not executable:
        raise WorkspaceError("找不到 ffprobe，无法执行成片合同校验")
    completed = subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise WorkspaceError(f"ffprobe 无法读取成片：{completed.stderr.strip() or path}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise WorkspaceError(f"成片没有可读取的视频流：{path}")
    stream = streams[0]
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "duration": float((payload.get("format") or {}).get("duration") or 0),
    }


def normalized_reference_images(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(Path(item).resolve()) for item in value if isinstance(item, str)]


def reference_images_are_absolute(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, str) and Path(item).is_absolute() for item in value)
    )


def prompt_version_from_event(event: dict[str, Any] | None, label: str, errors: list[str]) -> int:
    if event is None:
        errors.append(f"运行记录缺少 {label} 事件")
        return 1
    version_text = str(event_data(event).get("version") or "")
    match = re.fullmatch(r"v([1-5])", version_text)
    if not match:
        errors.append(f"{label} 事件必须明确记录 v1-v5 版本，实际为 {version_text or '空'}")
        return 1
    return int(match.group(1))


def validate_generation_evidence(
    root: Path,
    directory: Path,
    run_id: str,
    *,
    route: str,
    duration: int,
    prompt_version: int,
    events: list[dict[str, Any]],
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    version_text = f"v{prompt_version}"
    prompt_relative = f"TEMP/{run_id}/vid-prompt-{version_text}.txt"
    lock_relative = f"TEMP/{run_id}/environment-path.txt"

    precheck = validate_pre_generation_contract(
        root,
        run_id,
        route=route,
        duration=duration,
        prompt_version=prompt_version,
        write_manifest=False,
    )
    if precheck["decision"] != "pass":
        errors.extend(f"生成输入复核失败：{item}" for item in precheck["errors"])
    current_references = normalized_reference_images(precheck["facts"].get("reference_images"))

    manifest_path = generation_manifest_path(directory, prompt_version)
    facts["generation_manifest"] = str(manifest_path.relative_to(root))
    if not manifest_path.is_file():
        errors.append(f"缺少生成前合同清单：{manifest_path.relative_to(root)}")
        return errors, facts
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"生成前合同清单不是合法 JSON：{exc.msg}")
        return errors, facts
    if not isinstance(manifest, dict):
        errors.append("生成前合同清单必须是 JSON 对象")
        return errors, facts

    manifest_schema = manifest.get("schema_version")
    if manifest_schema not in {1, 2}:
        errors.append(f"生成前合同清单 schema_version 不受支持：{manifest_schema!r}")
    expected_fields = {
        "decision": "pass",
        "phase": "pre-generation",
        "run_id": run_id,
        "route": route,
        "prompt_version": version_text,
        "duration": duration,
        "ratio": VIDEO_RATIO,
        "video_resolution": VIDEO_RESOLUTION,
        "prompt": prompt_relative,
        "environment_lock": lock_relative,
    }
    for key, expected in expected_fields.items():
        if manifest.get(key) != expected:
            errors.append(f"生成前合同清单字段 {key} 不匹配：应为 {expected!r}")
    if manifest_schema == 2:
        if manifest.get("workflow_config") != "MATERIAL/xdy-workflow.json":
            errors.append("生成前合同清单未引用统一 workflow 配置")
        if manifest.get("workflow_config_sha256") != config_sha256():
            errors.append("统一 workflow 配置在提交后发生变化")

    raw_references = manifest.get("reference_images")
    if not reference_images_are_absolute(raw_references):
        errors.append("生成前合同清单必须包含严格有序的两张绝对路径参考图")
    manifest_references = normalized_reference_images(raw_references)
    if manifest_references != current_references:
        errors.append("生成前合同清单的双图与当前角色图、环境锁不一致")

    hashes = manifest.get("sha256")
    if not isinstance(hashes, dict):
        hashes = {}
        errors.append("生成前合同清单缺少 sha256 对象")
    hash_targets: dict[str, Path | None] = {
        "role_image": Path(manifest_references[0]) if len(manifest_references) > 0 else None,
        "environment_image": Path(manifest_references[1]) if len(manifest_references) > 1 else None,
        "prompt": root / prompt_relative,
        "environment_lock": root / lock_relative,
    }
    for key, target in hash_targets.items():
        if target is None or not target.is_file():
            errors.append(f"生成后合同输入缺失：{key}")
        elif sha256_file(target) != hashes.get(key):
            errors.append(f"生成后合同输入发生变化：{key}")

    submit_event = latest_versioned_event(events, "dreamina", "submitted", version_text)
    if submit_event is not None:
        submit_data = event_data(submit_event)
        manifest_relative = str(manifest_path.relative_to(root))
        if submit_data.get("manifest") != manifest_relative:
            errors.append("Dreamina submitted 记录的 manifest 路径不一致")
        if submit_data.get("manifest_sha256") != sha256_file(manifest_path):
            errors.append("Dreamina submitted 记录的 manifest_sha256 不一致")
        return errors, facts

    submit_event = latest_versioned_event(events, "dreamina", "submit", version_text)
    if submit_event is None:
        errors.append(f"运行记录缺少 dreamina/submit {version_text} 事件")
        return errors, facts
    submit_data = event_data(submit_event)
    raw_submitted_references = submit_data.get("reference_images")
    if not reference_images_are_absolute(raw_submitted_references):
        errors.append("Dreamina submit 必须记录严格有序的两张绝对路径参考图")
    if normalized_reference_images(raw_submitted_references) != manifest_references:
        errors.append("Dreamina submit 记录的 reference_images 与合同清单不一致")
    submit_fields = {
        "duration": duration,
        "ratio": VIDEO_RATIO,
        "video_resolution": VIDEO_RESOLUTION,
        "prompt": prompt_relative,
        "prompt_sha256": hashes.get("prompt"),
    }
    for key, expected in submit_fields.items():
        if submit_data.get(key) != expected:
            errors.append(f"Dreamina submit 字段 {key} 与合同清单不一致")
    return errors, facts


def validate_no_output_closeout(
    root: Path,
    run_id: str,
    events: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if (output_root(root) / f"{run_id}.mp4").exists():
        errors.append("失败或取消路线不应存在正式 OUTPUT 成片")
    drive = latest_state_event(events, "google_drive")
    if drive is None or str(drive.get("status") or "").lower() != "not_attempted":
        errors.append("无正式成片时必须记录 Google Drive 状态 not_attempted")
    publish = latest_state_event(events, "publish")
    if publish is None or str(publish.get("status") or "") != "not_requested":
        errors.append("失败或取消路线必须记录发布状态 not_requested")
    return errors


def validate_finalize_contract(
    root: Path,
    run_id: str,
    *,
    route: str,
    duration: int,
    publish_mode: str,
    outcome: str = "success",
) -> dict[str, Any]:
    directory, record = run_contract_paths(root, run_id)
    events, errors = read_contract_events(record)
    facts: dict[str, Any] = {
        "duration": duration,
        "publish_mode": publish_mode,
        "outcome": outcome,
    }

    if latest_event(events, "run", "started") is None:
        errors.append("运行记录缺少 run/started 事件")
    if route not in VALID_ROUTES:
        errors.append(f"未知运行路线：{route}")
    if duration not in VALID_DURATIONS:
        errors.append(f"生成时长必须是 5、6 或 7 秒，实际为 {duration}")
    if publish_mode not in VALID_PUBLISH_MODES:
        errors.append(f"未知发布模式：{publish_mode}")
    if outcome not in VALID_OUTCOMES:
        errors.append(f"未知运行结果：{outcome}")
    if route == "xdysp" and publish_mode != "not_requested":
        errors.append("xdysp 的发布模式必须是 not_requested")
    if outcome not in {"success", "publish_failed"} and publish_mode != "not_requested":
        errors.append("失败或取消路线的发布模式必须是 not_requested")
    if publish_mode == "awaiting_confirmation":
        errors.append("awaiting_confirmation 是等待态，不能通过收尾合同门禁")

    if outcome == "cancelled":
        cancelled = latest_event(events, "run", "cancelled")
        if cancelled is None or str(cancelled.get("status") or "") != "cancelled":
            errors.append("取消路线必须记录 run/cancelled 状态 cancelled")
        errors.extend(validate_no_output_closeout(root, run_id, events))
        errors = list(dict.fromkeys(errors))
        return contract_result(
            phase="finalize",
            run_id=run_id,
            route=route,
            errors=errors,
            facts=facts,
        )

    if outcome == "generation_failed":
        terminal = latest_state_event(events, "dreamina")
        terminal_data = event_data(terminal)
        if terminal is None or str(terminal.get("status") or "").lower() not in {"failed", "blocked"}:
            errors.append("生成失败路线缺少 Dreamina failed/blocked 终态")
        terminal_version = str(terminal_data.get("version") or "")
        terminal_match = re.fullmatch(r"v([1-5])", terminal_version)
        if terminal_match is None:
            errors.append("生成失败路线必须明确记录 v1-v5")
        if terminal_data.get("reason_category") == "tns" and terminal_version != "v5":
            errors.append("TNS 生成失败路线必须收敛并记录至 v5")
        if not terminal_data.get("reason_category"):
            errors.append("生成失败路线必须明确记录 reason_category")
        evidence_errors, evidence_facts = validate_generation_evidence(
            root,
            directory,
            run_id,
            route=route,
            duration=duration,
            prompt_version=int(terminal_match.group(1)) if terminal_match else 1,
            events=events,
        )
        errors.extend(evidence_errors)
        facts.update(evidence_facts)
        review = latest_state_event(events, "review") or latest_state_event(events, "quality")
        if review is None or str(review.get("status") or "") != "not_performed":
            errors.append("无生成产物时必须记录质检状态 not_performed")
        errors.extend(validate_no_output_closeout(root, run_id, events))
        errors = list(dict.fromkeys(errors))
        return contract_result(
            phase="finalize",
            run_id=run_id,
            route=route,
            errors=errors,
            facts=facts,
        )

    dreamina_success = latest_success_event(events, "dreamina")
    if dreamina_success is not None and latest_state_event(events, "dreamina") is not dreamina_success:
        errors.append("Dreamina 最新终态不是本次成功事件")
    prompt_version = prompt_version_from_event(dreamina_success, "Dreamina success", errors)
    evidence_errors, evidence_facts = validate_generation_evidence(
        root,
        directory,
        run_id,
        route=route,
        duration=duration,
        prompt_version=prompt_version,
        events=events,
    )
    errors.extend(evidence_errors)
    facts.update(evidence_facts)

    if outcome == "quality_failed":
        if route != "xdy":
            errors.append("quality_failed 只适用于 xdy 路线")
        quality = latest_state_event(events, "quality")
        if quality is None or str(quality.get("status") or "").lower() not in {"failed", "blocked"}:
            errors.append("质检失败路线必须记录 quality failed/blocked 终态")
        errors.extend(validate_no_output_closeout(root, run_id, events))
        errors = list(dict.fromkeys(errors))
        return contract_result(
            phase="finalize",
            run_id=run_id,
            route=route,
            errors=errors,
            facts=facts,
        )

    output = output_root(root) / f"{run_id}.mp4"
    if not output.is_file():
        errors.append(f"正式成片不存在：OUTPUT/{run_id}.mp4")
    else:
        try:
            video = probe_video(output)
        except (WorkspaceError, ValueError, json.JSONDecodeError) as exc:
            errors.append(str(exc))
        else:
            facts["video"] = video
            if (video["width"], video["height"]) != (VIDEO_WIDTH, VIDEO_HEIGHT):
                errors.append(
                    f"正式成片必须为 {VIDEO_WIDTH}x{VIDEO_HEIGHT}，"
                    f"实际为 {video['width']}x{video['height']}"
                )
            if abs(video["duration"] - duration) > VIDEO_DURATION_TOLERANCE:
                errors.append(
                    f"正式成片时长与请求值偏差超过 {VIDEO_DURATION_TOLERANCE} 秒："
                    f"请求 {duration}，实际 {video['duration']:.3f}"
                )
    output_events = [
        item
        for item in events
        if item.get("stage") == "output"
        and item.get("event") != "artifact"
        and event_data(item).get("output_video") == f"OUTPUT/{run_id}.mp4"
    ]
    if not output_events:
        errors.append("output 事件未记录本次正式成片规范路径")

    drive_event = latest_state_event(events, "google_drive")
    if drive_event is None:
        errors.append("缺少 Google Drive 上传结果事件")
    else:
        drive_data = event_data(drive_event)
        drive_status = str(drive_event.get("status") or "").lower()
        drive_event_name = str(drive_event.get("event") or "").lower()
        uploaded = (
            drive_status in {"success", "uploaded"}
            and drive_event_name in {"upload", "uploaded"}
        )
        failed = (
            drive_status in {"fail", "failed", "error"}
            and drive_event_name in {"upload", "failed", "upload_verification"}
        )
        if uploaded:
            if drive_data.get("file_name") != f"{run_id}.mp4":
                errors.append("Google Drive 记录的文件名与 RUN_ID 不一致")
            if drive_data.get("mime_type") != "video/mp4":
                errors.append("Google Drive 记录的 MIME 类型必须是 video/mp4")
            if not (drive_data.get("file_id") or drive_data.get("url")):
                errors.append("Google Drive 上传成功事件必须记录 file_id 或 url")
            if drive_data.get("root_verified") is not True:
                errors.append("Google Drive 上传成功事件必须记录 root_verified: true")
            forbidden_parent_fields = (
                "folder_id",
                "folder_name",
                "parent_folder_id",
                "parent_id",
                "parent_folder",
                "target_folder_id",
                "target_folder_name",
            )
            if any(drive_data.get(key) for key in forbidden_parent_fields):
                errors.append("Google Drive 上传目标不是 My Drive 根目录")
            if output.is_file():
                try:
                    recorded_size = int(drive_data.get("size"))
                except (TypeError, ValueError):
                    errors.append("Google Drive 上传成功事件必须记录有效 size")
                else:
                    if recorded_size != output.stat().st_size:
                        errors.append("Google Drive 记录的 size 与正式成片不一致")
        elif failed:
            if drive_data.get("needs_retry") is not True:
                errors.append("Google Drive 上传失败时必须记录 needs_retry: true")
            if not (drive_data.get("reason") or drive_event.get("summary")):
                errors.append("Google Drive 上传失败时必须记录原因")
        else:
            errors.append("Google Drive 事件状态必须明确为 uploaded 或 failed")

    if route == "xdysp":
        review = latest_state_event(events, "review") or latest_state_event(events, "quality")
        if review is None or str(review.get("status")) != "not_performed":
            errors.append("xdysp 必须记录质检状态 not_performed")
    else:
        quality = latest_state_event(events, "quality")
        if quality is None or str(quality.get("status")) != "pass":
            errors.append("xdy 必须记录质检状态 pass")

    publish_event = latest_state_event(events, "publish")
    if publish_mode == "not_requested":
        if publish_event is None or str(publish_event.get("status")) != publish_mode:
            errors.append(f"发布状态必须记录为 {publish_mode}")
    elif publish_mode == "default":
        both_event = latest_event(events, "publish", "both_publish")
        both_status = str((both_event or {}).get("status") or "").lower()
        if both_event is None or both_status not in {"published", "blocked"}:
            errors.append("默认发布路线必须记录 publish/both_publish 的 published 或 blocked 终态")
        else:
            platforms = event_data(both_event).get("platforms")
            platform_items = (
                [item for item in platforms if isinstance(item, dict)]
                if isinstance(platforms, list)
                else []
            )
            platform_names = {str(item.get("platform")) for item in platform_items if item.get("platform")}
            if len(platform_items) != 2 or platform_names != {"douyin", "kuaishou"}:
                errors.append("publish/both_publish 必须包含抖音和快手两端实际结果")
            platform_decisions = [str(item.get("decision") or "") for item in platform_items]
            if both_status == "published" and any(value != "published" for value in platform_decisions):
                errors.append("publish/both_publish=published 与单平台结果不一致")
            if both_status == "blocked" and platform_decisions and all(
                value == "published" for value in platform_decisions
            ):
                errors.append("publish/both_publish=blocked 与单平台结果不一致")
            if outcome == "success" and both_status != "published":
                errors.append("运行结果 success 要求双平台发布均为 published")
            if outcome == "publish_failed" and both_status != "blocked":
                errors.append("运行结果 publish_failed 要求双平台聚合状态为 blocked")
            if publish_event is not both_event:
                errors.append("publish/both_publish 必须是最新发布终态")

    errors = list(dict.fromkeys(errors))
    return contract_result(
        phase="finalize",
        run_id=run_id,
        route=route,
        errors=errors,
        facts=facts,
    )


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
    parser = argparse.ArgumentParser(description="统一管理并校验 TEMP/OUTPUT 运行空间")
    parser.add_argument("--root", default=None, help="项目根目录，默认从脚本位置解析")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="创建规范运行空间并写入 started 事件")
    init_parser.add_argument("--at", default=None, help="测试或补建用 ISO 时间，默认当前上海时间")
    init_parser.add_argument("--source", default=None)
    init_parser.add_argument("--data", default=None, help="JSON 对象或 @path.json")
    init_parser.add_argument("--format", choices=("id", "json"), default="id")

    subparsers.add_parser("audit", help="审计正式运行目录与成片命名")

    contract_parser = subparsers.add_parser("contract", help="执行生成前或收尾合同门禁")
    contract_parser.add_argument("run_id")
    contract_parser.add_argument(
        "--phase",
        choices=("pre-generation", "finalize"),
        required=True,
    )
    contract_parser.add_argument("--route", choices=tuple(sorted(VALID_ROUTES)), required=True)
    contract_parser.add_argument(
        "--duration",
        type=int,
        required=True,
        choices=tuple(sorted(VALID_DURATIONS)),
    )
    contract_parser.add_argument("--prompt-version", type=int, choices=range(1, 6), default=1)
    contract_parser.add_argument("--publish-mode", choices=tuple(sorted(VALID_PUBLISH_MODES)))
    contract_parser.add_argument("--outcome", choices=tuple(sorted(VALID_OUTCOMES)), default="success")
    contract_parser.add_argument(
        "--no-write-manifest",
        action="store_true",
        help="只读验证生成前合同，不创建清单",
    )
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
        if args.command == "contract":
            if args.phase == "pre-generation":
                if args.publish_mode is not None:
                    raise WorkspaceError("pre-generation 阶段不接受 --publish-mode")
                if args.outcome != "success":
                    raise WorkspaceError("pre-generation 阶段不接受非 success 的 --outcome")
                result = validate_pre_generation_contract(
                    root,
                    args.run_id,
                    route=args.route,
                    duration=args.duration,
                    prompt_version=args.prompt_version,
                    write_manifest=not args.no_write_manifest,
                )
            else:
                if args.publish_mode is None:
                    raise WorkspaceError("finalize 阶段必须显式提供 --publish-mode")
                if args.no_write_manifest:
                    raise WorkspaceError("finalize 阶段不接受 --no-write-manifest")
                result = validate_finalize_contract(
                    root,
                    args.run_id,
                    route=args.route,
                    duration=args.duration,
                    publish_mode=args.publish_mode,
                    outcome=args.outcome,
                )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["decision"] == "pass" else 1
    except (WorkspaceError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
