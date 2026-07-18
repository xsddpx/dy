#!/usr/bin/env python3
"""Allocate and validate canonical dy workspaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
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
FORMAL_ENVIRONMENT_RE = re.compile(r"^anna-room-\d{2,}\.png$")
CONTRACTS_DIR = Path("logs/contracts")
VIDEO_RATIO = GENERATION_CONFIG["ratio"]
VIDEO_RESOLUTION = GENERATION_CONFIG["video_resolution"]
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

    contract_parser = subparsers.add_parser("contract", help="执行生成前合同门禁")
    contract_parser.add_argument("run_id")
    contract_parser.add_argument(
        "--phase",
        choices=("pre-generation",),
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
        if args.command == "contract":
            result = validate_pre_generation_contract(
                root,
                args.run_id,
                route=args.route,
                duration=args.duration,
                prompt_version=args.prompt_version,
                write_manifest=not args.no_write_manifest,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["decision"] == "pass" else 1
    except (WorkspaceError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
