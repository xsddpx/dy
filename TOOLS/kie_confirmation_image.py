#!/usr/bin/env python3
"""Generate one confirmation image slot with Kie GPT Image 2."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


CREATE_TASK_URL = "https://api.kie.ai/api/v1/jobs/createTask"
QUERY_TASK_URL = "https://api.kie.ai/api/v1/jobs/recordInfo"
FILE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
MODEL = "gpt-image-2-image-to-image"
MODEL_VERSION = "gpt-image-2-image-to-image"
DONE_STATES = {"success", "fail"}
PENDING_STATES = {"waiting", "queuing", "generating"}


class KieError(RuntimeError):
    pass


def load_dotenv(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv as load_python_dotenv
    except ImportError:
        load_python_dotenv = None
    if load_python_dotenv:
        load_python_dotenv(env_path, override=False)
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_api_key(cli_value: str | None = None) -> str:
    token = (cli_value or os.environ.get("KIE_API_KEY") or "").strip()
    if not token:
        raise KieError("缺少 KIE_API_KEY；请在 .env 中配置或通过环境变量提供")
    return token


def headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def read_prompt(args: argparse.Namespace) -> str:
    if args.prompt_path:
        return Path(args.prompt_path).read_text(encoding="utf-8").strip()
    return (args.prompt or "").strip()


def ensure_file(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise KieError(f"{label} 不存在：{resolved}")
    if not resolved.is_file():
        raise KieError(f"{label} 不是文件：{resolved}")
    return resolved


def safe_part(value: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in value)


def response_json(response: requests.Response, context: str) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as exc:
        raise KieError(f"{context} 返回非 JSON：HTTP {response.status_code}") from exc
    if response.status_code >= 400:
        msg = data.get("msg") if isinstance(data, dict) else None
        raise KieError(f"{context} 失败：HTTP {response.status_code} {msg or response.text[:200]}")
    return data


def upload_file(path: Path, token: str, upload_path: str, timeout: int) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        files = {"file": (path.name, handle, mime_type)}
        data = {"uploadPath": upload_path, "fileName": path.name}
        response = requests.post(
            FILE_UPLOAD_URL,
            headers=headers(token),
            files=files,
            data=data,
            timeout=timeout,
        )
    payload = response_json(response, f"上传 {path.name}")
    if not payload.get("success") and payload.get("code") != 200:
        raise KieError(f"上传 {path.name} 失败：{payload.get('msg') or payload}")
    file_data = payload.get("data") or {}
    download_url = file_data.get("downloadUrl") or file_data.get("fileUrl")
    if not download_url:
        raise KieError(f"上传 {path.name} 未返回 downloadUrl")
    return {
        "source_path": str(path),
        "download_url": download_url,
        "file_name": file_data.get("fileName") or path.name,
        "file_size": file_data.get("fileSize"),
        "mime_type": file_data.get("mimeType"),
    }


def create_task(
    *,
    token: str,
    prompt: str,
    image_urls: list[str],
    aspect_ratio: str,
    resolution: str,
    output_format: str,
    callback_url: str | None,
    timeout: int,
) -> str:
    model_input = {
        "prompt": prompt,
        "input_urls": image_urls,
        "aspect_ratio": aspect_ratio,
    }
    body: dict[str, Any] = {
        "model": MODEL,
        "input": json.dumps(model_input, ensure_ascii=False),
    }
    if callback_url:
        body["callBackUrl"] = callback_url
    response = requests.post(
        CREATE_TASK_URL,
        headers={**headers(token), "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    payload = response_json(response, "创建 Kie 生图任务")
    if payload.get("code") != 200:
        raise KieError(f"创建 Kie 生图任务失败：{payload.get('msg') or payload}")
    task_id = ((payload.get("data") or {}).get("taskId") or "").strip()
    if not task_id:
        raise KieError("创建 Kie 生图任务未返回 taskId")
    return task_id


def query_task(task_id: str, token: str, timeout: int) -> dict[str, Any]:
    response = requests.get(
        QUERY_TASK_URL,
        headers=headers(token),
        params={"taskId": task_id},
        timeout=timeout,
    )
    payload = response_json(response, "查询 Kie 生图任务")
    data = payload.get("data") or {}
    if not data:
        raise KieError(f"查询 Kie 生图任务未返回 data：{payload}")
    return data


def parse_result_urls(task: dict[str, Any]) -> list[str]:
    raw = task.get("resultJson")
    if isinstance(raw, str):
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise KieError(f"Kie resultJson 不是合法 JSON：{raw[:200]}") from exc
    elif isinstance(raw, dict):
        result = raw
    else:
        result = {}
    urls = result.get("resultUrls") or result.get("urls") or result.get("images") or []
    if isinstance(urls, str):
        urls = [urls]
    return [str(url) for url in urls if str(url).strip()]


def wait_for_task(task_id: str, token: str, poll_seconds: float, max_wait_seconds: int, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait_seconds
    last_task: dict[str, Any] | None = None
    while time.monotonic() <= deadline:
        task = query_task(task_id, token, timeout)
        last_task = task
        state = str(task.get("state") or "").lower()
        if state in DONE_STATES:
            return task
        if state and state not in PENDING_STATES:
            raise KieError(f"Kie 生图任务状态未知：{state}")
        time.sleep(poll_seconds)
    raise KieError(f"Kie 生图任务超时：{task_id}；最后状态：{(last_task or {}).get('state')}")


def download_result(url: str, out_path: Path, timeout: int) -> None:
    response = requests.get(url, timeout=timeout)
    if response.status_code >= 400:
        raise KieError(f"下载 Kie 结果失败：HTTP {response.status_code}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(response.content)
    if out_path.stat().st_size == 0:
        raise KieError(f"下载 Kie 结果为空：{out_path}")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_failure_entry(args: argparse.Namespace, task_id: str | None, reason: str, prompt_path: str | None) -> dict[str, Any]:
    return {
        "slot": args.slot,
        "submit_id": task_id or f"kie-fail-{args.stamp}-{args.slot}",
        "status": "fail",
        "fail_reason": reason,
        "model_version": MODEL_VERSION,
        "prompt_path": prompt_path,
    }


def run_generation(args: argparse.Namespace) -> dict[str, Any]:
    load_dotenv(args.env_file)
    token = require_api_key(args.api_key)
    prompt = read_prompt(args)
    if not prompt:
        raise KieError("缺少 prompt；请提供 --prompt 或 --prompt-path")

    role_image = ensure_file(args.role_image, "角色参考图")
    out_dir = Path(args.out_dir).expanduser().resolve()
    raw_dir = Path(args.raw_dir).expanduser().resolve() if args.raw_dir else out_dir / "raw"
    entry_out = Path(args.entry_out).expanduser().resolve() if args.entry_out else out_dir / f"{args.slot}-entry.json"
    upload_path = args.upload_path or f"images/dy/{args.run_id}/{args.slot}"

    role_upload = upload_file(role_image, token, upload_path, args.timeout)
    task_id = create_task(
        token=token,
        prompt=prompt,
        image_urls=[role_upload["download_url"]],
        aspect_ratio=args.aspect_ratio,
        resolution=args.resolution,
        output_format=args.output_format,
        callback_url=args.callback_url,
        timeout=args.timeout,
    )
    task = wait_for_task(task_id, token, args.poll_seconds, args.max_wait_seconds, args.timeout)
    state = str(task.get("state") or "").lower()
    if state == "fail":
        reason = task.get("failMsg") or task.get("failCode") or "Kie generation failed"
        entry = build_failure_entry(args, task_id, str(reason), args.prompt_path)
        write_json(entry_out, entry)
        return {"entry": entry, "task": task, "entry_json": str(entry_out)}

    result_urls = parse_result_urls(task)
    if not result_urls:
        raise KieError(f"Kie 生图成功但未返回结果 URL：{task}")
    image_path = raw_dir / f"{safe_part(args.stamp)}-{safe_part(args.slot)}-{safe_part(task_id[:8])}-{safe_part(args.topic)}-kie-confirmation.{args.output_format}"
    download_result(result_urls[0], image_path, args.timeout)

    entry = {
        "slot": args.slot,
        "submit_id": task_id,
        "status": "success",
        "image_path": str(image_path),
        "model_version": MODEL_VERSION,
        "prompt_path": args.prompt_path,
        "prompt_note": args.prompt_note,
        "kie": {
            "model": MODEL,
            "aspect_ratio": args.aspect_ratio,
            "local_extension": args.output_format,
            "result_url": result_urls[0],
            "role_upload": role_upload,
            "credits_consumed": task.get("creditsConsumed"),
            "cost_time": task.get("costTime"),
        },
    }
    write_json(entry_out, entry)
    task_out = entry_out.with_name(f"{args.slot}-kie-task.json")
    write_json(task_out, task)
    return {
        "entry": entry,
        "task": task,
        "entry_json": str(entry_out),
        "task_json": str(task_out),
        "image_path": str(image_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 Kie GPT Image 2 生成单个确认图槽位。")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--stamp", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--slot", required=True, help="槽位，如 A-01")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--role-image", default="MATERIAL/fixed-role/anna.png")
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--prompt-path", default=None)
    parser.add_argument("--prompt-note", default=None)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--raw-dir", default=None)
    parser.add_argument("--entry-out", default=None)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--upload-path", default=None)
    parser.add_argument("--callback-url", default=None)
    parser.add_argument("--aspect-ratio", default="auto")
    parser.add_argument("--resolution", default=None, help="兼容旧调用；gpt-image-2-image-to-image 默认不提交该参数")
    parser.add_argument("--output-format", default="png")
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--max-wait-seconds", type=int, default=900)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    try:
        result = run_generation(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
