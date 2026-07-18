#!/usr/bin/env python3
"""Unified, resumable Anna dual-reference video workflow."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import prompt_lint
import run_workspace
from run_record import (
    RecordError,
    append_event_v2,
    derive_v2_state,
    latest_non_artifact,
    read_events,
    refresh_markdown,
)
from workflow_config import config_sha256, load_workflow_config, project_path


SHANGHAI = ZoneInfo("Asia/Shanghai")
WORKFLOW = load_workflow_config()
GENERATION = WORKFLOW["generation"]
ASSETS = WORKFLOW["assets"]
PROMPT = WORKFLOW["prompt"]
QUALITY = WORKFLOW["quality"]
PUBLISH = WORKFLOW["publish"]
TERMINAL_GENERATION_EVENTS = {"succeeded", "tns", "failed"}
ENVIRONMENT_CATEGORIES = set(WORKFLOW["runtime"]["environment_error_categories"])


class FlowError(RuntimeError):
    """Raised for a workflow contract or recoverable execution error."""


def root_path(value: str | Path | None = None) -> Path:
    return run_workspace.repo_root(value)


def run_paths(root: Path, run_id: str) -> tuple[Path, Path]:
    directory = root / "TEMP" / run_id
    record = directory / f"{run_id}-run-record.jsonl"
    if not directory.is_dir() or not record.is_file():
        raise FlowError(f"运行不存在：{run_id}")
    return directory, record


def relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FlowError(f"无法读取 JSON：{path}：{exc}") from exc
    if not isinstance(payload, dict):
        raise FlowError(f"JSON 必须是对象：{path}")
    return payload


def parse_json_output(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise FlowError("命令没有返回 JSON")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        starts = [index for index in (stripped.find("{"), stripped.find("[")) if index >= 0]
        if not starts:
            raise FlowError("命令输出不包含 JSON")
        payload = json.loads(stripped[min(starts) :])
    if isinstance(payload, list):
        if len(payload) != 1 or not isinstance(payload[0], dict):
            raise FlowError("命令返回了非单对象 JSON")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise FlowError("命令返回的 JSON 不是对象")
    return payload


def parse_wardrobe(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"夏-(\d{2})\.", line.strip())
        if match:
            current = match.group(1)
            continue
        if current and line.startswith("- 款式提示词："):
            entries[current] = line.split("：", 1)[1].strip()
            current = None
    if not entries:
        raise FlowError(f"衣柜中没有可用条目：{path}")
    return entries


def discover_environments(root: Path) -> list[Path]:
    directory = project_path(root, ASSETS["environment_directory"])
    pattern = re.compile(ASSETS["environment_pattern"])
    candidates = sorted(path.resolve() for path in directory.iterdir() if path.is_file() and pattern.fullmatch(path.name))
    if not candidates:
        raise FlowError(f"没有正式环境图：{directory}")
    return candidates


def successful_history(root: Path, limit: int | None = None) -> list[dict[str, str]]:
    result: list[tuple[str, dict[str, str]]] = []
    for directory in (root / "TEMP").iterdir() if (root / "TEMP").is_dir() else []:
        record = directory / f"{directory.name}-run-record.jsonl"
        if not record.is_file():
            continue
        try:
            events = read_events(record)
        except (OSError, json.JSONDecodeError):
            continue
        completed = latest_non_artifact(events, "run", "completed")
        content = latest_non_artifact(events, "content", "locked")
        prompt_version = latest_non_artifact(events, "content", "prompt_version")
        if not completed or completed.get("schema_version") != 2 or completed.get("status") != "success" or not content:
            continue
        data = content.get("data") or {}
        prompt_data = (prompt_version or {}).get("data") or {}
        item = {
            "wardrobe": str(prompt_data.get("wardrobe") or data.get("wardrobe") or ""),
            "environment": str(data.get("environment") or ""),
            "action": str(data.get("action") or ""),
        }
        if all(item.values()):
            result.append((str(completed.get("created_at") or ""), item))
    result.sort(key=lambda item: item[0], reverse=True)
    window = int(limit or WORKFLOW["selection"]["history_window"])
    return [item for _, item in result[:window]]


def _recency(value: str, key: str, history: list[dict[str, str]]) -> int:
    for index, item in enumerate(history):
        if item.get(key) == value:
            return index
    return len(history) + 1


def choose_content(
    root: Path,
    *,
    seed: int,
    wardrobe: str | None,
    environment: str | None,
    action: str | None,
) -> dict[str, Any]:
    wardrobe_entries = parse_wardrobe(project_path(root, ASSETS["wardrobe"]))
    environments = discover_environments(root)
    actions = sorted(PROMPT["actions"])
    if wardrobe and wardrobe not in wardrobe_entries:
        raise FlowError(f"衣柜编号不存在：{wardrobe}")
    if action and action not in actions:
        raise FlowError(f"动作模板不存在：{action}")
    if environment:
        requested = Path(environment).expanduser()
        if not requested.is_absolute():
            requested = root / requested
        requested = requested.resolve()
        if requested not in environments:
            raise FlowError(f"不是正式环境图：{requested}")
        environment_values = [str(requested)]
    else:
        environment_values = [str(path) for path in environments]

    history = successful_history(root)
    rng = random.Random(seed)
    wardrobe_values = [wardrobe] if wardrobe else sorted(wardrobe_entries)
    action_values = [action] if action else actions
    combinations = list(itertools.product(wardrobe_values, environment_values, action_values))
    rng.shuffle(combinations)
    recent_combinations = {
        (item["wardrobe"], item["environment"], item["action"])
        for item in history
    }
    combinations.sort(
        key=lambda combo: (
            _recency(combo[0], "wardrobe", history)
            + _recency(combo[1], "environment", history)
            + _recency(combo[2], "action", history),
            _recency(combo[0], "wardrobe", history),
            _recency(combo[1], "environment", history),
            _recency(combo[2], "action", history),
        ),
        reverse=True,
    )
    selected = next((combo for combo in combinations if combo not in recent_combinations), None)
    if selected is None:
        raise FlowError("候选空间无法避开最近 12 次的完全相同组合")
    return {
        "wardrobe": selected[0],
        "wardrobe_text": wardrobe_entries[selected[0]],
        "environment": selected[1],
        "action": selected[2],
        "seed": seed,
        "history_count": len(history),
    }


def build_prompt(wardrobe_text: str, action: str) -> str:
    values = {
        "人物": PROMPT["person"],
        "视频约束": PROMPT["video_constraint"],
        "穿搭": wardrobe_text,
        "环境": PROMPT["environment"],
        "人物动作": PROMPT["actions"][action]["text"],
        "背景音乐": PROMPT["music"],
        "其他": f"{PROMPT['other_base']}{PROMPT['other_suffix']}",
    }
    return "\n".join(f"{label}：{values[label]}" for label in PROMPT["sections"]) + "\n"


def write_prompt(directory: Path, version: int, wardrobe_text: str, action: str) -> Path:
    path = directory / f"vid-prompt-v{version}.txt"
    text = build_prompt(wardrobe_text, action)
    lint = prompt_lint.lint_text(text, path)
    if lint["decision"] != "pass":
        codes = sorted({item["code"] for item in lint["findings"] if item["severity"] == "error"})
        raise FlowError("生成的 vid prompt 未通过 lint：" + ", ".join(codes))
    if path.exists() and path.read_text(encoding="utf-8") != text:
        raise FlowError(f"拒绝覆盖已有 prompt：{path.name}")
    if not path.exists():
        atomic_write_text(path, text)
    return path


def content_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    event = latest_non_artifact(events, "content", "locked")
    if event is None:
        raise FlowError("运行尚未锁定内容")
    return event


def event_for_version(events: list[dict[str, Any]], event_name: str, version: str) -> dict[str, Any] | None:
    for item in reversed(events):
        if (
            item.get("stage") == "dreamina"
            and item.get("event") == event_name
            and (item.get("data") or {}).get("version") == version
        ):
            return item
    return None


def current_version(events: list[dict[str, Any]]) -> int:
    versions = []
    for item in events:
        if item.get("stage") not in {"content", "dreamina"}:
            continue
        match = re.fullmatch(r"v([1-5])", str((item.get("data") or {}).get("version") or ""))
        if match:
            versions.append(int(match.group(1)))
    return max(versions, default=1)


def append(record: Path, run_id: str, stage: str, event: str, status: str, data: dict[str, Any] | None = None, summary: str | None = None) -> dict[str, Any]:
    return append_event_v2(
        record,
        run_id=run_id,
        stage=stage,
        event=event,
        status=status,
        data=data or {},
        summary=summary,
    )


def initialize_run(
    root: Path,
    *,
    route: str,
    publish_mode: str,
    source: str,
    theme: str | None,
    wardrobe: str | None,
    environment: str | None,
    action: str | None,
    duration: int | None,
    seed: int | None,
    title: str | None,
    description: str | None,
    tags: list[str] | None,
) -> str:
    if route == "xdysp":
        publish_mode = "not_requested"
    if route not in {"xdy", "xdysp"}:
        raise FlowError(f"未知路线：{route}")
    if publish_mode not in {"default", "not_requested", "awaiting_confirmation"}:
        raise FlowError(f"未知发布模式：{publish_mode}")
    chosen_seed = seed if seed is not None else random.SystemRandom().randrange(1, 2**63)
    selected = choose_content(
        root,
        seed=chosen_seed,
        wardrobe=wardrobe,
        environment=environment,
        action=action,
    )
    chosen_duration = duration or int(PROMPT["actions"][selected["action"]]["preferred_duration"])
    if chosen_duration not in GENERATION["valid_durations"]:
        raise FlowError(f"时长必须是 {GENERATION['valid_durations']}，实际为 {chosen_duration}")

    run_id, directory = run_workspace.allocate_run_dir(root, datetime.now(SHANGHAI))
    record = directory / f"{run_id}-run-record.jsonl"
    try:
        (directory / "logs").mkdir()
        (root / "OUTPUT").mkdir(parents=True, exist_ok=True)
        append(record, run_id, "run", "started", "in_progress", {"source": source})
        environment_path = Path(selected["environment"])
        atomic_write_text(directory / "environment-path.txt", str(environment_path) + "\n")
        prompt_path = write_prompt(directory, 1, selected["wardrobe_text"], selected["action"])
        publish_tags = tags or load_publish_tags(root)
        append(
            record,
            run_id,
            "content",
            "locked",
            "ready",
            {
                "route": route,
                "publish_mode": publish_mode,
                "theme": theme,
                "seed": chosen_seed,
                "wardrobe": selected["wardrobe"],
                "environment": str(environment_path),
                "action": selected["action"],
                "duration": chosen_duration,
                "title": title or "今天的轻熟穿搭",
                "description": description or "简单记录今天自然自信的穿搭状态。",
                "candidate_tags": publish_tags[: int(PUBLISH["candidate_tag_count"])],
                "workflow_config_sha256": config_sha256(),
            },
            "内容、双图顺序、动作和时长已锁定",
        )
        append(
            record,
            run_id,
            "content",
            "prompt_version",
            "ready",
            {
                "version": "v1",
                "wardrobe": selected["wardrobe"],
                "prompt": relative(root, prompt_path),
                "prompt_sha256": sha256_file(prompt_path),
            },
        )
        refresh_markdown(record)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return run_id


def load_publish_tags(root: Path) -> list[str]:
    payload = load_json_object(root / "MATERIAL" / "publish-tag-pool.json")
    blocked = {str(item).strip().lstrip("#") for item in payload.get("blocked_tags") or []}
    tags: list[str] = []
    for item in payload.get("tags") or []:
        value = str(item).strip().lstrip("#")
        if value and value not in blocked and value not in tags:
            tags.append(value)
    return tags


def manifest_for_version(root: Path, run_id: str, route: str, duration: int, version: int) -> Path:
    result = run_workspace.validate_pre_generation_contract(
        root,
        run_id,
        route=route,
        duration=duration,
        prompt_version=version,
        write_manifest=True,
    )
    if result["decision"] != "pass":
        raise FlowError("生成合同未通过：" + "；".join(result["errors"]))
    return root / str(result["manifest"])


def classify_error(text: str) -> str:
    lowered = text.lower()
    if "tns" in lowered or "safety" in lowered or "安全" in text:
        return "tns"
    if any(token in lowered for token in ("login", "oauth", "unauthorized", "token expired")) or "登录" in text:
        return "login"
    if any(token in lowered for token in ("credit", "insufficient", "quota")) or "积分" in text:
        return "credits"
    if any(token in lowered for token in ("timeout", "timed out", "deadline")) or "超时" in text:
        return "timeout"
    if any(token in lowered for token in ("network", "connection", "dns", "tls", "proxy")) or "网络" in text:
        return "network"
    if "upload" in lowered or "上传" in text:
        return "upload"
    if "download" in lowered or "下载" in text:
        return "download"
    if any(token in lowered for token in ("invalid argument", "unknown flag", "parameter")) or "参数" in text:
        return "parameter"
    return "unknown"


def dreamina_binary(value: str | None = None) -> str:
    return value or os.environ.get("XDY_DREAMINA_BIN") or "dreamina"


def _run_logged_json(command: list[str], stdout_path: Path, stderr_path: Path, timeout: int | None = None) -> tuple[int, dict[str, Any] | None, str]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
            completed = subprocess.run(
                command,
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                timeout=timeout,
                check=False,
            )
    except subprocess.TimeoutExpired:
        return 124, None, "命令执行超时"
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    try:
        payload = parse_json_output(stdout_text)
    except (FlowError, json.JSONDecodeError):
        payload = None
    return completed.returncode, payload, (stderr_text or stdout_text).strip()


def recover_submission(binary: str, prompt: str, logs: Path) -> dict[str, Any] | None:
    stdout = logs / "recover-list-task.json"
    stderr = logs / "recover-list-task.stderr.log"
    code, payload, _ = _run_logged_json([binary, "list_task", "--limit=20"], stdout, stderr, timeout=60)
    if code != 0:
        return None
    raw = json.loads(stdout.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        return None
    matches = [item for item in raw if isinstance(item, dict) and item.get("prompt") == prompt and item.get("submit_id")]
    return matches[0] if matches else None


def submit_generation(root: Path, directory: Path, record: Path, run_id: str, events: list[dict[str, Any]], version: int, binary: str) -> dict[str, Any]:
    content = content_event(events).get("data") or {}
    route = str(content["route"])
    duration = int(content["duration"])
    version_text = f"v{version}"
    existing = event_for_version(events, "submitted", version_text)
    if existing:
        return existing
    manifest_path = manifest_for_version(root, run_id, route, duration, version)
    manifest = load_json_object(manifest_path)
    prompt_path = root / str(manifest["prompt"])
    prompt_text = prompt_path.read_text(encoding="utf-8")
    logs = directory / "logs" / "dreamina" / version_text
    submit_stdout = logs / "submit.json"
    submit_stderr = logs / "submit.stderr.log"
    payload: dict[str, Any] | None = None
    code = 1
    detail = ""
    if submit_stdout.is_file() and submit_stdout.stat().st_size:
        try:
            payload = parse_json_output(submit_stdout.read_text(encoding="utf-8"))
            code = 0
        except (FlowError, json.JSONDecodeError):
            payload = None
    if payload is None:
        recovered = recover_submission(binary, prompt_text, logs)
        if recovered:
            payload = recovered
            code = 0
            atomic_write_json(submit_stdout, payload)
    if payload is None:
        command = [binary, "multimodal2video"]
        for image in manifest["reference_images"]:
            command.extend(["--image", str(image)])
        command.extend(
            [
                "--prompt",
                prompt_text,
                "--model_version",
                str(GENERATION["model_version"]),
                "--ratio",
                str(manifest["ratio"]),
                "--video_resolution",
                str(manifest["video_resolution"]),
                "--duration",
                str(manifest["duration"]),
            ]
        )
        code, payload, detail = _run_logged_json(command, submit_stdout, submit_stderr, timeout=900)
    if code != 0 or payload is None or not payload.get("submit_id"):
        category = classify_error(detail)
        if category == "tns":
            raise FlowError("Dreamina 在提交阶段返回 TNS，但没有 submit_id，无法形成可追踪提交")
        record_environment_error(root, directory, record, run_id, version_text, category, detail or "Dreamina 提交失败")
        raise FlowError(f"Dreamina 提交失败（{category}）")
    event = append(
        record,
        run_id,
        "dreamina",
        "submitted",
        "querying",
        {
            "version": version_text,
            "submit_id": str(payload["submit_id"]),
            "manifest": relative(root, manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
        },
        f"Dreamina {version_text} 已提交",
    )
    return event


def record_environment_error(root: Path, directory: Path, record: Path, run_id: str, version: str, category: str, reason: str) -> None:
    category = category if category in ENVIRONMENT_CATEGORIES else "unknown"
    append(
        record,
        run_id,
        "dreamina",
        "environment_error",
        "blocked",
        {"version": version, "reason_category": category, "reason": reason[:500]},
        f"环境错误：{category}",
    )
    report = doctor(root)
    report_path = directory / "logs" / "doctor.json"
    atomic_write_json(report_path, report)


def poll_generation(root: Path, directory: Path, record: Path, run_id: str, submitted: dict[str, Any], binary: str, timeout_seconds: int) -> dict[str, Any]:
    data = submitted.get("data") or {}
    version = str(data["version"])
    submit_id = str(data["submit_id"])
    logs = directory / "logs" / "dreamina" / version
    download_dir = logs / "download"
    download_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    intervals = [int(value) for value in WORKFLOW["runtime"]["poll_intervals_seconds"]]
    attempts = 0
    while time.monotonic() - started <= timeout_seconds:
        attempts += 1
        stdout = logs / "query-latest.json"
        stderr = logs / "query-latest.stderr.log"
        command = [
            binary,
            "query_result",
            f"--submit_id={submit_id}",
            f"--download_dir={download_dir}",
        ]
        code, payload, detail = _run_logged_json(command, stdout, stderr, timeout=180)
        if code != 0 or payload is None:
            category = classify_error(detail)
            record_environment_error(root, directory, record, run_id, version, category, detail or "Dreamina 查询失败")
            raise FlowError(f"Dreamina 查询失败（{category}）")
        status = str(payload.get("gen_status") or payload.get("status") or "").lower()
        reason = str(payload.get("fail_reason") or payload.get("reason") or "")
        if status in {"success", "succeeded", "done"}:
            videos = sorted(download_dir.rglob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
            if not videos:
                category = "download"
                record_environment_error(root, directory, record, run_id, version, category, "Dreamina 成功但未下载到 MP4")
                raise FlowError("Dreamina 成功但未下载到 MP4")
            video = videos[0].resolve()
            return append(
                record,
                run_id,
                "dreamina",
                "succeeded",
                "success",
                {
                    "version": version,
                    "submit_id": submit_id,
                    "downloaded_video": str(video),
                    "downloaded_sha256": sha256_file(video),
                    "poll_attempts": attempts,
                },
                f"Dreamina {version} 生成并下载成功",
            )
        if status in {"fail", "failed", "blocked", "error"}:
            category = classify_error(reason)
            if category == "tns":
                return append(
                    record,
                    run_id,
                    "dreamina",
                    "tns",
                    "blocked",
                    {"version": version, "submit_id": submit_id, "reason_category": "tns", "reason": reason[:500]},
                    f"Dreamina {version} TNS",
                )
            if category in ENVIRONMENT_CATEGORIES:
                record_environment_error(root, directory, record, run_id, version, category, reason)
                raise FlowError(f"Dreamina 失败（{category}）")
            return append(
                record,
                run_id,
                "dreamina",
                "failed",
                "failed",
                {"version": version, "submit_id": submit_id, "reason_category": "unknown", "reason": reason[:500]},
                f"Dreamina {version} 未知失败",
            )
        delay = intervals[min(attempts - 1, len(intervals) - 1)]
        if time.monotonic() - started + delay > timeout_seconds:
            break
        time.sleep(delay)
    record_environment_error(root, directory, record, run_id, version, "timeout", f"轮询超过 {timeout_seconds} 秒")
    raise FlowError("Dreamina 轮询超时")


def create_next_prompt(root: Path, directory: Path, record: Path, run_id: str, events: list[dict[str, Any]], version: int) -> Path:
    if version < 2 or version > int(GENERATION["max_prompt_version"]):
        raise FlowError(f"TNS 版本超出范围：v{version}")
    content = content_event(events).get("data") or {}
    action = str(content["action"])
    wardrobe_entries = parse_wardrobe(project_path(root, ASSETS["wardrobe"]))
    used = {
        str((item.get("data") or {}).get("wardrobe") or "")
        for item in events
        if item.get("stage") == "content" and item.get("event") in {"locked", "prompt_version"}
    }
    history = successful_history(root)
    candidates = [item for item in sorted(wardrobe_entries) if item not in used]
    if not candidates:
        raise FlowError("TNS 重试没有未使用的衣柜条目")
    seed = int(content["seed"]) + version
    random.Random(seed).shuffle(candidates)
    candidates.sort(key=lambda item: _recency(item, "wardrobe", history), reverse=True)
    wardrobe = candidates[0]
    prompt_path = write_prompt(directory, version, wardrobe_entries[wardrobe], action)
    append(
        record,
        run_id,
        "content",
        "prompt_version",
        "ready",
        {
            "version": f"v{version}",
            "wardrobe": wardrobe,
            "prompt": relative(root, prompt_path),
            "prompt_sha256": sha256_file(prompt_path),
            "inherited_action": action,
            "inherited_environment": str(content["environment"]),
            "inherited_duration": int(content["duration"]),
        },
        f"TNS 重试 v{version} 仅更换衣柜",
    )
    return prompt_path


def executable(name: str, root: Path) -> str:
    local = root / ".venv" / "bin" / name
    if local.is_file() and os.access(local, os.X_OK):
        return str(local)
    found = shutil.which(name)
    if not found:
        raise FlowError(f"缺少命令：{name}；请运行 xdy_flow.py doctor")
    return found


def video_probe(root: Path, path: Path) -> dict[str, Any]:
    command = [
        executable("ffprobe", root),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise FlowError(f"ffprobe 无法读取视频：{completed.stderr.strip() or path}")
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise FlowError(f"视频没有可读取的视频流：{path}")
    return {
        "width": int(streams[0].get("width") or 0),
        "height": int(streams[0].get("height") or 0),
        "duration": float((payload.get("format") or {}).get("duration") or 0),
    }


def _render_proxy(root: Path, source: Path, target: Path, seek: float | None = None) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = int(QUALITY["proxy_max_bytes"])
    ffmpeg = executable("ffmpeg", root)
    for short_edge in (480, 400, 320, 260):
        for quality in (5, 8, 12, 18, 24, 31):
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if seek is not None:
                command.extend(["-ss", f"{seek:.3f}"])
            command.extend(
                [
                    "-i",
                    str(source),
                    "-vf",
                    f"scale={short_edge}:-2",
                    "-frames:v",
                    "1",
                    "-q:v",
                    str(quality),
                    str(target),
                ]
            )
            completed = subprocess.run(command, capture_output=True, text=True, timeout=90, check=False)
            if completed.returncode == 0 and target.is_file() and target.stat().st_size < max_bytes:
                return
    raise FlowError(f"无法生成小于 {max_bytes} 字节的质检代理图：{target.name}")


def successful_video(events: list[dict[str, Any]]) -> Path:
    success = latest_non_artifact(events, "dreamina", "succeeded")
    if success is None:
        raise FlowError("缺少 Dreamina 成功产物")
    path = Path(str((success.get("data") or {}).get("downloaded_video") or ""))
    if not path.is_file():
        raise FlowError(f"Dreamina 下载产物不存在：{path}")
    return path.resolve()


def prepare_quality(root: Path, directory: Path, record: Path, run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    existing = latest_non_artifact(events, "quality", "prepared")
    if existing:
        return existing
    video = successful_video(events)
    meta = video_probe(root, video)
    duration = float(meta["duration"])
    times = [max(0.0, min(duration, 0.5)), duration / 2.0, max(0.0, duration - 0.5)]
    quality_dir = directory / "quality"
    role_proxy = quality_dir / "role-proxy.jpg"
    frame_paths = [
        quality_dir / "frame-0.5.jpg",
        quality_dir / "frame-middle.jpg",
        quality_dir / "frame-end-minus-0.5.jpg",
    ]
    _render_proxy(root, project_path(root, ASSETS["role_image"]), role_proxy)
    for target, seek in zip(frame_paths, times):
        _render_proxy(root, video, target, seek)
    report = {
        "decision": "pending_visual_comparison",
        "criterion": "仅判断成片胸部体量是否相对固定角色图明显偏小",
        "role_proxy": relative(root, role_proxy),
        "frames": [
            {"path": relative(root, path), "time": round(seek, 3), "size": path.stat().st_size}
            for path, seek in zip(frame_paths, times)
        ],
        "proxy_max_bytes": int(QUALITY["proxy_max_bytes"]),
    }
    report_path = quality_dir / "quality-checklist.json"
    atomic_write_json(report_path, report)
    return append(
        record,
        run_id,
        "quality",
        "prepared",
        "pending",
        {"checklist": relative(root, report_path)},
        "角色代理图与首中尾三帧已准备，等待逐张视觉比对",
    )


def validate_video_contract(root: Path, video: Path, duration: int) -> dict[str, Any]:
    meta = video_probe(root, video)
    expected = (int(GENERATION["width"]), int(GENERATION["height"]))
    if (meta["width"], meta["height"]) != expected:
        raise FlowError(f"成片分辨率必须是 {expected[0]}x{expected[1]}，实际为 {meta['width']}x{meta['height']}")
    if abs(float(meta["duration"]) - duration) > run_workspace.VIDEO_DURATION_TOLERANCE:
        raise FlowError(f"成片时长与请求值不一致：请求 {duration}，实际 {meta['duration']:.3f}")
    return meta


def finalize_output(root: Path, directory: Path, record: Path, run_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    existing = latest_non_artifact(events, "output", "created")
    if existing:
        return existing
    content = content_event(events).get("data") or {}
    duration = int(content["duration"])
    source = successful_video(events)
    source_sha = sha256_file(source)
    if source_sha != str((latest_non_artifact(events, "dreamina", "succeeded").get("data") or {}).get("downloaded_sha256")):
        raise FlowError("Dreamina 下载产物在生成后发生变化")
    validate_video_contract(root, source, duration)
    output = root / "OUTPUT" / f"{run_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if sha256_file(output) != source_sha:
            raise FlowError("正式 OUTPUT 已存在且与本次下载产物不同")
    else:
        temporary = output.with_name(f".{output.name}.{os.getpid()}.part")
        with source.open("rb") as source_handle, temporary.open("wb") as output_handle:
            shutil.copyfileobj(source_handle, output_handle, 1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if sha256_file(temporary) != source_sha:
            temporary.unlink(missing_ok=True)
            raise FlowError("正式成片复制后的 SHA-256 不一致")
        validate_video_contract(root, temporary, duration)
        os.replace(temporary, output)
    meta = validate_video_contract(root, output, duration)
    return append(
        record,
        run_id,
        "output",
        "created",
        "ready",
        {
            "output_video": f"OUTPUT/{run_id}.mp4",
            "sha256": sha256_file(output),
            "size": output.stat().st_size,
            "width": meta["width"],
            "height": meta["height"],
            "duration": meta["duration"],
        },
        "正式成片已原子整理并通过 SHA-256、ffprobe 校验",
    )


def record_quality(root: Path, run_id: str, decision: str) -> dict[str, Any]:
    directory, record = run_paths(root, run_id)
    events = read_events(record)
    state = derive_v2_state(events)
    if state.get("schema_version") != 2:
        raise FlowError("旧运行记录只读")
    existing = latest_non_artifact(events, "quality", "reviewed")
    if existing:
        if existing.get("status") != decision:
            raise FlowError(f"质检已经记录为 {existing.get('status')}，不能改写")
        return {"quality": existing, "state": derive_v2_state(events)}
    content = content_event(events).get("data") or {}
    route = str(content["route"])
    if route == "xdysp" and decision != "not_performed":
        raise FlowError("xdysp 只能记录质检 not_performed")
    if route == "xdy" and decision not in {"pass", "blocked"}:
        raise FlowError("xdy 质检只能记录 pass 或 blocked")
    if route == "xdy" and latest_non_artifact(events, "quality", "prepared") is None:
        raise FlowError("xdy 记录质检前必须先生成代理图和质检清单")
    review = append(
        record,
        run_id,
        "quality",
        "reviewed",
        decision,
        {"criterion": "breast_volume_only", "reviewer": "executor" if route == "xdy" else "not_performed"},
        "胸部体量视觉比对已通过" if decision == "pass" else "胸部体量视觉比对阻断" if decision == "blocked" else "xdysp 不执行内容质检",
    )
    events = read_events(record)
    if decision in {"pass", "not_performed"}:
        finalize_output(root, directory, record, run_id, events)
    else:
        append(record, run_id, "google_drive", "not_attempted", "not_attempted", {"reason": "quality_blocked"})
        append(record, run_id, "publish", "not_requested", "not_requested", {"reason": "quality_blocked"})
    refresh_markdown(record)
    return {"quality": review, "state": derive_v2_state(read_events(record))}


def record_drive(root: Path, run_id: str, result: dict[str, Any]) -> dict[str, Any]:
    directory, record = run_paths(root, run_id)
    events = read_events(record)
    if derive_v2_state(events).get("schema_version") != 2:
        raise FlowError("旧运行记录只读")
    status = str(result.get("status") or "")
    normalized_result = {key: value for key, value in result.items() if key != "status"}
    existing = latest_non_artifact(events, "google_drive")
    if existing:
        expected_event = "uploaded" if status == "uploaded" else "failed" if status == "failed" else ""
        if existing.get("event") != expected_event or (existing.get("data") or {}) != normalized_result:
            raise FlowError("Drive 终态已记录，不能改写")
        return existing
    output = root / "OUTPUT" / f"{run_id}.mp4"
    if status == "uploaded":
        errors: list[str] = []
        if result.get("file_name") != f"{run_id}.mp4":
            errors.append("file_name 与 RUN_ID 不一致")
        if result.get("mime_type") != "video/mp4":
            errors.append("mime_type 必须是 video/mp4")
        try:
            recorded_size = int(result.get("size"))
        except (TypeError, ValueError):
            recorded_size = -1
        if not output.is_file() or recorded_size != output.stat().st_size:
            errors.append("size 与正式成片不一致")
        if not (result.get("file_id") or result.get("url")):
            errors.append("必须包含 file_id 或 url")
        if result.get("root_verified") is not True:
            errors.append("必须回读确认 root_verified=true")
        forbidden = {"folder_id", "folder_name", "parent_folder_id", "parent_id", "target_folder_id"}
        if any(result.get(key) for key in forbidden):
            errors.append("上传目标必须是 My Drive 根目录")
        if errors:
            raise FlowError("Drive 上传结果校验失败：" + "；".join(errors))
        event = append(record, run_id, "google_drive", "uploaded", "uploaded", normalized_result, "Drive 根目录上传已回读核验")
    elif status == "failed":
        if not result.get("reason") or result.get("needs_retry") is not True:
            raise FlowError("Drive 失败结果必须包含 reason 和 needs_retry=true")
        event = append(record, run_id, "google_drive", "failed", "failed", normalized_result, "Drive 上传失败，保留补传动作")
    else:
        raise FlowError("Drive 结果 status 必须是 uploaded 或 failed")
    refresh_markdown(record)
    return event


def publish_adapter_path(root: Path, value: str | None = None) -> Path:
    selected = value or os.environ.get("XDY_PUBLISH_ADAPTER")
    return Path(selected).resolve() if selected else root / "TOOLS" / "publish_adapter.py"


def publish_run(root: Path, directory: Path, record: Path, run_id: str, events: list[dict[str, Any]], adapter_value: str | None = None) -> dict[str, Any]:
    existing = latest_non_artifact(events, "publish", "both_publish")
    if existing:
        return existing
    content = content_event(events).get("data") or {}
    output = root / "OUTPUT" / f"{run_id}.mp4"
    if not output.is_file():
        raise FlowError("发布前缺少正式成片")
    out_dir = directory / "logs" / "publish"
    out_dir.mkdir(parents=True, exist_ok=True)
    adapter = publish_adapter_path(root, adapter_value)
    command = [
        sys.executable,
        str(adapter),
        "both",
        str(output),
        "--title",
        str(content.get("title") or "今天的轻熟穿搭"),
        "--description",
        str(content.get("description") or "简单记录今天自然自信的穿搭状态。"),
        "--cdp-url",
        "http://127.0.0.1:9222",
        "--out-dir",
        str(out_dir),
    ]
    for tag in content.get("candidate_tags") or []:
        command.extend(["--tag", str(tag)])
    stdout_path = out_dir / "adapter.stdout.json"
    stderr_path = out_dir / "adapter.stderr.log"
    code, payload, detail = _run_logged_json(command, stdout_path, stderr_path, timeout=1800)
    report_path = out_dir / "publish-both-report.json"
    if report_path.is_file():
        report = load_json_object(report_path)
    elif payload:
        report = payload
    else:
        raise FlowError(f"发布适配器没有生成聚合报告：{detail[:300]}")
    compact_platforms = []
    for item in report.get("platforms") or []:
        if not isinstance(item, dict):
            continue
        compact_platforms.append(
            {
                "platform": item.get("platform"),
                "decision": item.get("decision"),
                "report_json": item.get("report_json"),
                "requested_tags": item.get("requested_tags"),
                "applied_tags": item.get("applied_tags"),
            }
        )
    if {str(item.get("platform")) for item in compact_platforms} != {"douyin", "kuaishou"}:
        raise FlowError("发布聚合报告没有同时包含抖音和快手")
    decision = "published" if code == 0 and all(item.get("decision") == "published" for item in compact_platforms) else "blocked"
    for item in compact_platforms:
        append(
            record,
            run_id,
            "publish",
            "platform_result",
            "published" if item.get("decision") == "published" else "blocked",
            item,
            f"{item.get('platform')}={item.get('decision')}",
        )
    return append(
        record,
        run_id,
        "publish",
        "both_publish",
        decision,
        {"platforms": compact_platforms, "report_json": relative(root, report_path)},
        f"双平台发布 overall={decision}",
    )


def close_generation_failure(record: Path, run_id: str, events: list[dict[str, Any]]) -> None:
    latest = latest_non_artifact(events, "dreamina")
    data = latest.get("data") or {} if latest else {}
    if latest and latest.get("event") == "tns":
        append(
            record,
            run_id,
            "dreamina",
            "failed",
            "failed",
            {
                "version": str(data.get("version") or "v5"),
                "submit_id": data.get("submit_id"),
                "reason_category": "tns",
                "reason": data.get("reason"),
            },
            "TNS 已收敛至 v5，停止生成",
        )
    events = read_events(record)
    if latest_non_artifact(events, "quality", "reviewed") is None:
        append(record, run_id, "quality", "reviewed", "not_performed", {"reason": "no_generated_video"})
    if latest_non_artifact(read_events(record), "google_drive") is None:
        append(record, run_id, "google_drive", "not_attempted", "not_attempted", {"reason": "no_generated_video"})
    if latest_non_artifact(read_events(record), "publish") is None:
        append(record, run_id, "publish", "not_requested", "not_requested", {"reason": "no_generated_video"})


def completion_outcome(events: list[dict[str, Any]]) -> str:
    quality = latest_non_artifact(events, "quality", "reviewed")
    generation = latest_non_artifact(events, "dreamina")
    if quality and quality.get("status") == "blocked":
        return "quality_failed"
    if generation and generation.get("event") == "failed":
        return "generation_failed"
    publish = latest_non_artifact(events, "publish", "both_publish")
    if publish and publish.get("status") == "blocked":
        return "publish_failed"
    return "success"


def complete_run(root: Path, run_id: str) -> dict[str, Any]:
    directory, record = run_paths(root, run_id)
    events = read_events(record)
    state = derive_v2_state(events)
    if state.get("schema_version") != 2:
        raise FlowError("旧运行记录只读，不能用新工具收尾")
    completed = latest_non_artifact(events, "run", "completed")
    if completed:
        refresh_markdown(record)
        return {"completed": completed, "state": derive_v2_state(events)}
    if state.get("next_action") != "complete":
        raise FlowError(f"运行尚不能收尾，唯一 next_action={state.get('next_action')}")
    content = content_event(events).get("data") or {}
    outcome = completion_outcome(events)
    latest_publish = latest_non_artifact(events, "publish")
    if outcome in {"generation_failed", "quality_failed", "cancelled"} or (
        latest_publish and latest_publish.get("status") == "not_requested"
    ):
        publish_mode = "not_requested"
    elif latest_publish and latest_publish.get("event") == "both_publish":
        publish_mode = "default"
    else:
        publish_mode = str(content["publish_mode"])
    result = run_workspace.validate_finalize_contract(
        root,
        run_id,
        route=str(content["route"]),
        duration=int(content["duration"]),
        publish_mode=publish_mode,
        outcome=outcome,
    )
    if result["decision"] != "pass":
        raise FlowError("收尾合同未通过：" + "；".join(result["errors"]))
    status = "success" if outcome == "success" else "failed"
    completed = append(
        record,
        run_id,
        "run",
        "completed",
        status,
        {"outcome": outcome, "contract": "pass"},
        f"运行原子收尾：{outcome}",
    )
    refresh_markdown(record)
    audit = run_workspace.audit_workspace(root)
    if audit["decision"] != "pass":
        raise FlowError("运行已收尾，但命名审计失败：" + "；".join(audit["errors"]))
    if record.stat().st_size > 10_000:
        raise FlowError(f"运行 JSONL 超过 10KB：{record.stat().st_size} bytes")
    return {"completed": completed, "state": derive_v2_state(read_events(record)), "audit": audit}


def resume_run(
    root: Path,
    run_id: str,
    *,
    authorize_publish: bool = False,
    cancel_publish: bool = False,
    dreamina_bin: str | None = None,
    publish_adapter: str | None = None,
    poll_timeout: int = 3600,
) -> dict[str, Any]:
    directory, record = run_paths(root, run_id)
    events = read_events(record)
    state = derive_v2_state(events)
    if state.get("schema_version") != 2:
        raise FlowError("121 份旧记录只读，不允许用新工具续跑或改写")
    if state.get("terminal"):
        return state
    content = content_event(events).get("data") or {}
    if content.get("workflow_config_sha256") != config_sha256():
        raise FlowError("本次运行锁定后 workflow 配置发生变化，拒绝续跑")
    if authorize_publish and cancel_publish:
        raise FlowError("不能同时授权和取消发布")
    if authorize_publish:
        awaiting = latest_non_artifact(events, "publish")
        if not awaiting or awaiting.get("status") != "awaiting_confirmation":
            raise FlowError("当前不在等待发布确认状态")
        append(record, run_id, "publish", "authorized", "in_progress", {"authorized": True})
        events = read_events(record)
    if cancel_publish:
        awaiting = latest_non_artifact(events, "publish")
        if not awaiting or awaiting.get("status") != "awaiting_confirmation":
            raise FlowError("当前不在等待发布确认状态")
        append(record, run_id, "publish", "not_requested", "not_requested", {"reason": "cancelled_while_awaiting"})
        events = read_events(record)

    binary = dreamina_binary(dreamina_bin)
    while True:
        state = derive_v2_state(events)
        action = state.get("next_action")
        if action == "repair_environment":
            diagnostic = doctor(root)
            if diagnostic["decision"] != "pass":
                return {**state, "doctor": diagnostic}
            version = current_version(events)
            action = "poll_generation" if event_for_version(events, "submitted", f"v{version}") else "generate"
        if action in {"generate", "generate_next_version", "poll_generation"}:
            version = current_version(events)
            if action == "generate_next_version":
                prepared = latest_non_artifact(events, "content", "prompt_version")
                prepared_version = str((prepared or {}).get("data", {}).get("version") or "")
                if prepared_version == f"v{version}" and event_for_version(events, "submitted", f"v{version}") is None:
                    pass
                else:
                    version += 1
                    create_next_prompt(root, directory, record, run_id, events, version)
                    events = read_events(record)
            submitted = event_for_version(events, "submitted", f"v{version}")
            terminal = next(
                (
                    event_for_version(events, name, f"v{version}")
                    for name in TERMINAL_GENERATION_EVENTS
                    if event_for_version(events, name, f"v{version}") is not None
                ),
                None,
            )
            if submitted is None:
                submitted = submit_generation(root, directory, record, run_id, events, version, binary)
                events = read_events(record)
            if terminal is None:
                result = poll_generation(root, directory, record, run_id, submitted, binary, poll_timeout)
                events = read_events(record)
                if result.get("event") == "tns" and version >= int(GENERATION["max_prompt_version"]):
                    close_generation_failure(record, run_id, events)
                    events = read_events(record)
                elif result.get("event") == "failed":
                    close_generation_failure(record, run_id, events)
                    events = read_events(record)
            continue
        if action == "review_quality":
            prepare_quality(root, directory, record, run_id, events)
            refresh_markdown(record)
            return derive_v2_state(read_events(record))
        if action == "finalize_output":
            route = str(content["route"])
            if latest_non_artifact(events, "quality", "reviewed") is None:
                if route != "xdysp":
                    raise FlowError("xdy 正式成片前必须记录质检")
                append(record, run_id, "quality", "reviewed", "not_performed", {"reason": "xdysp"})
                events = read_events(record)
            finalize_output(root, directory, record, run_id, events)
            events = read_events(record)
            continue
        if action == "record_failure_terminals":
            if latest_non_artifact(events, "google_drive") is None:
                append(record, run_id, "google_drive", "not_attempted", "not_attempted", {"reason": "quality_blocked"})
            if latest_non_artifact(read_events(record), "publish") is None:
                append(record, run_id, "publish", "not_requested", "not_requested", {"reason": "quality_blocked"})
            events = read_events(record)
            continue
        if action == "upload_drive":
            output = root / "OUTPUT" / f"{run_id}.mp4"
            return {
                **derive_v2_state(events),
                "connector_request": {
                    "action": "upload_to_my_drive_root",
                    "source": str(output),
                    "file_name": output.name,
                    "mime_type": "video/mp4",
                    "parent_folder_id": None,
                    "expected_size": output.stat().st_size,
                    "then": f"xdy_flow.py record-drive {run_id} --result @result.json",
                },
            }
        if action == "record_not_requested":
            append(record, run_id, "publish", "not_requested", "not_requested", {"reason": "route_or_user_choice"})
            events = read_events(record)
            continue
        if action == "await_confirmation":
            current = latest_non_artifact(events, "publish")
            if current is None:
                append(record, run_id, "publish", "awaiting_confirmation", "awaiting_confirmation", {"requires_explicit_authorization": True})
                events = read_events(record)
            refresh_markdown(record)
            return derive_v2_state(events)
        if action == "publish":
            publish_run(root, directory, record, run_id, events, publish_adapter)
            events = read_events(record)
            continue
        if action == "complete":
            return complete_run(root, run_id)["state"]
        if action == "none":
            return state
        raise FlowError(f"无法自动处理 next_action={action}")


def doctor(root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str, next_action: str | None = None) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "next_action": None if ok else next_action})

    for label, path in (
        ("workflow_config", root / "MATERIAL" / "xdy-workflow.json"),
        ("role_image", project_path(root, ASSETS["role_image"])),
        ("wardrobe", project_path(root, ASSETS["wardrobe"])),
    ):
        add(label, path.is_file(), str(path), "恢复缺失文件")
    try:
        environments = discover_environments(root)
    except FlowError as exc:
        add("environments", False, str(exc), "恢复正式环境图")
    else:
        add("environments", True, f"{len(environments)} 张正式环境图")
    for name in ("ffmpeg", "ffprobe", "dreamina"):
        path = (root / ".venv" / "bin" / name) if (root / ".venv" / "bin" / name).is_file() else Path(shutil.which(name) or "")
        add(name, bool(path and path.is_file()), str(path) if path else "not found", "运行 zsh TOOLS/setup_env.sh" if name != "dreamina" else "安装 Dreamina CLI")
    dreamina = shutil.which("dreamina")
    if dreamina:
        credit = subprocess.run([dreamina, "user_credit"], capture_output=True, text=True, timeout=30, check=False)
        credit_detail = (credit.stderr or "Dreamina 登录检查失败").strip()[:300]
        if credit.returncode == 0:
            try:
                credit_payload = json.loads(credit.stdout)
            except json.JSONDecodeError:
                credit_detail = "登录有效"
            else:
                credit_detail = f"登录有效，可用积分 {credit_payload.get('total_credit', 'unknown')}"
        add(
            "dreamina_login",
            credit.returncode == 0,
            credit_detail,
            "运行 dreamina login 完成登录",
        )
    try:
        import playwright  # noqa: F401
    except ImportError as exc:
        add("playwright", False, str(exc), "运行 zsh TOOLS/setup_env.sh")
    else:
        add("playwright", True, "import ok")
    cdp_ok = False
    cdp_detail = "http://127.0.0.1:9222/json/version"
    try:
        from urllib.request import urlopen

        with urlopen(cdp_detail, timeout=2) as response:
            cdp_ok = response.status == 200
    except Exception as exc:  # environment diagnostic must preserve the actual error category
        cdp_detail = f"{cdp_detail}: {exc}"
    add("cdp", cdp_ok, cdp_detail, "启动带 CDP 的 Chrome 并确认平台登录")
    failed = [item for item in checks if not item["ok"]]
    return {
        "decision": "pass" if not failed else "failed",
        "checks": checks,
        "next_action": "resume_original_step" if not failed else next((item["next_action"] for item in failed if item.get("next_action")), "inspect_environment"),
    }


def status_run(root: Path, run_id: str) -> dict[str, Any]:
    _, record = run_paths(root, run_id)
    events = read_events(record)
    state = derive_v2_state(events)
    latest_by_stage: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("event") == "artifact":
            continue
        latest_by_stage[str(event.get("stage"))] = {
            "event": event.get("event"),
            "status": event.get("status"),
            "seq": event.get("seq"),
        }
    return {**state, "stages": latest_by_stage}


def read_result_argument(value: str) -> dict[str, Any]:
    path = Path(value[1:]) if value.startswith("@") else None
    if path:
        return load_json_object(path)
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise FlowError("--result 必须是 JSON 对象")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="xdy schema-v2 统一、可恢复执行入口")
    parser.add_argument("--root", default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="建档、锁定内容并执行到首个人工或连接器断点")
    run_parser.add_argument("--route", choices=("xdy", "xdysp"), default="xdy")
    run_parser.add_argument("--publish-mode", choices=("default", "not_requested", "awaiting_confirmation"), default="default")
    run_parser.add_argument("--source", default="manual")
    run_parser.add_argument("--theme")
    run_parser.add_argument("--wardrobe")
    run_parser.add_argument("--environment")
    run_parser.add_argument("--action", choices=tuple(sorted(PROMPT["actions"])))
    run_parser.add_argument("--duration", type=int, choices=tuple(GENERATION["valid_durations"]))
    run_parser.add_argument("--seed", type=int)
    run_parser.add_argument("--title")
    run_parser.add_argument("--description")
    run_parser.add_argument("--tag", action="append")
    run_parser.add_argument("--dreamina-bin", help=argparse.SUPPRESS)
    run_parser.add_argument("--poll-timeout", type=int, default=3600)

    status_parser = subparsers.add_parser("status", help="输出当前状态、终态和唯一 next_action")
    status_parser.add_argument("run_id")

    resume_parser = subparsers.add_parser("resume", help="从合法断点幂等续跑")
    resume_parser.add_argument("run_id")
    resume_parser.add_argument("--authorize-publish", action="store_true")
    resume_parser.add_argument("--cancel-publish", action="store_true")
    resume_parser.add_argument("--dreamina-bin", help=argparse.SUPPRESS)
    resume_parser.add_argument("--publish-adapter", help=argparse.SUPPRESS)
    resume_parser.add_argument("--poll-timeout", type=int, default=3600)

    quality_parser = subparsers.add_parser("record-quality", help="记录人工胸部体量结论并原子整理成片")
    quality_parser.add_argument("run_id")
    quality_parser.add_argument("decision", choices=("pass", "blocked", "not_performed"))

    drive_parser = subparsers.add_parser("record-drive", help="校验并记录 Drive 连接器返回")
    drive_parser.add_argument("run_id")
    drive_parser.add_argument("--result", required=True, help="JSON 对象或 @result.json")

    complete_parser = subparsers.add_parser("complete", help="原子执行收尾合同、completed、摘要和命名审计")
    complete_parser.add_argument("run_id")

    subparsers.add_parser("doctor", help="结构化检查依赖、Dreamina、CDP 与登录入口")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = root_path(args.root)
        if args.command == "run":
            run_id = initialize_run(
                root,
                route=args.route,
                publish_mode=args.publish_mode,
                source=args.source,
                theme=args.theme,
                wardrobe=args.wardrobe,
                environment=args.environment,
                action=args.action,
                duration=args.duration,
                seed=args.seed,
                title=args.title,
                description=args.description,
                tags=args.tag,
            )
            result = resume_run(root, run_id, dreamina_bin=args.dreamina_bin, poll_timeout=args.poll_timeout)
            print(json.dumps({"run_id": run_id, **result}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            result = status_run(root, args.run_id)
        elif args.command == "resume":
            result = resume_run(
                root,
                args.run_id,
                authorize_publish=args.authorize_publish,
                cancel_publish=args.cancel_publish,
                dreamina_bin=args.dreamina_bin,
                publish_adapter=args.publish_adapter,
                poll_timeout=args.poll_timeout,
            )
        elif args.command == "record-quality":
            result = record_quality(root, args.run_id, args.decision)
        elif args.command == "record-drive":
            result = record_drive(root, args.run_id, read_result_argument(args.result))
        elif args.command == "complete":
            result = complete_run(root, args.run_id)
        else:
            result = doctor(root)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (FlowError, RecordError, run_workspace.WorkspaceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
